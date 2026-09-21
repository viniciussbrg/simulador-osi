# -*- coding: utf-8 -*-
"""As sete classes de camada do modelo OSI.

Cada camada tem dois metodos: `desce` encapsula, `sobe` desencapsula. Quem
encadeia as chamadas e o dispositivo, em dispositivos.py, entao uma camada
nunca acessa outra que nao seja adjacente.

O que nao cabe na unidade de dados passa pelo dicionario `contexto`: a camada
3 escreve la a decisao de rota e a camada 2 so le o vizinho ja escolhido.
"""

from __future__ import annotations

import struct
from typing import Any

from . import config
from .eventos import Evento
from .pdu import (
    UnidadeDados,
    cabecalho_enlace,
    cabecalho_rede,
    cabecalho_sessao,
    cabecalho_transporte,
    calcular_verificacao,
    finalizador_enlace,
    mac_curto,
    sessao_do_cabecalho,
)

SETA = "→"


# Contadores compartilhados


class ContadorGlobal:
    """Numeracao sequencial de passos, quadros, pacotes e sessoes.

    Os quadros sao numerados na ordem em que entram em um enlace (Q1, Q2, ...),
    o que torna visivel que o quadro de cada salto e um objeto novo.
    """

    def __init__(self) -> None:
        self.passo = 0
        self.quadro = 0
        self.pacote = 0
        self.sessao = 0

    def proximo_passo(self) -> int:
        self.passo += 1
        return self.passo

    def proximo_quadro(self) -> str:
        self.quadro += 1
        return f"{config.PREFIXO_QUADRO}{self.quadro}"

    def proximo_pacote(self) -> str:
        self.pacote += 1
        return f"{config.PREFIXO_PACOTE}{self.pacote}"

    def proxima_sessao(self) -> str:
        self.sessao += 1
        return f"{config.PREFIXO_SESSAO}{self.sessao:04d}"

    def reiniciar(self) -> None:
        self.passo = self.quadro = self.pacote = self.sessao = 0


def _evento(contexto: dict[str, Any], camada: str, acao: str, descricao: str,
            unidade: UnidadeDados, *, estado: str = "normal",
            enlace: tuple[str, str] | None = None) -> Evento:
    """Cria um evento ja preenchido com o passo, o dispositivo e o tamanho."""
    contador: ContadorGlobal = contexto["contador"]
    return Evento(
        passo=contador.proximo_passo(),
        dispositivo=contexto["dispositivo"],
        camada=camada,
        acao=acao,
        descricao=descricao,
        tamanho=unidade.tamanho(),
        unidade=unidade.copia(),
        enlace=enlace,
        caminho=list(contexto.get("caminho", [])),
        estado=estado,
    )


# Camada 7 - Aplicacao


class CamadaAplicacao:
    """Gera a mensagem e identifica o processo pelo nome (endereco especifico)."""

    def desce(self, texto: str,
              contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        """Cria a mensagem a partir do texto informado pelo usuario.

        O texto e guardado como esta; a conversao em octetos pertence a
        camada 6 e so acontece la.
        """
        origem = contexto["processo_origem"]
        destino = contexto["processo_destino"]

        unidade = UnidadeDados(
            dados=texto.encode(config.CODIFICACAO),
            unidade="Mensagem",
            processos=(origem, destino),
            texto_original=texto,
            fluxo=contexto.get("fluxo", "A"),
        )
        evento = _evento(contexto, "L7", "GERA",
                         f"processo {origem}, destino {destino}", unidade)
        return unidade, [evento]

    def sobe(self, unidade: UnidadeDados,
             contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        """Entrega a mensagem ao processo de destino."""
        destino = unidade.processos[1] if unidade.processos else "?"
        evento = _evento(contexto, "L7", "ENTREGA",
                         f"mensagem entregue ao processo {destino}",
                         unidade, estado="sucesso")
        return unidade, [evento]


# Camada 6 - Apresentacao


def _cifrar(dados: bytes) -> bytes:
    """Cifra de fluxo por ou-exclusivo com chave repetida.

    E involutiva: aplicar duas vezes devolve o original. Preserva o
    comprimento em octetos, o que mantem os tamanhos da convencao.
    """
    chave = config.CHAVE_CIFRA
    return bytes(b ^ chave[i % len(chave)] for i, b in enumerate(dados))


class CamadaApresentacao:
    """Converte texto em octetos, registra a codificacao e cifra o conteudo."""

    def desce(self, unidade: UnidadeDados,
              contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        nova = unidade.copia()
        nova.dados = _cifrar(unidade.dados)
        nova.metadados["codificacao"] = config.CODIFICACAO
        nova.metadados["cifrado"] = True
        # O texto legivel deixa de existir a partir daqui e so reaparece na
        # camada 6 do destino.
        nova.texto_original = None

        evento = _evento(contexto, "L6", "CODIFICA",
                         f"octetos {config.CODIFICACAO.upper()}, conteudo cifrado",
                         nova)
        return nova, [evento]

    def sobe(self, unidade: UnidadeDados,
             contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        nova = unidade.copia()
        nova.dados = _cifrar(unidade.dados)
        nova.metadados["cifrado"] = False
        nova.texto_original = nova.dados.decode(config.CODIFICACAO, errors="replace")

        evento = _evento(contexto, "L6", "DECODIFICA",
                         "conteudo decifrado e texto restaurado", nova)
        return nova, [evento]


# Camada 5 - Sessao


class CamadaSessao:
    """Abre, mantem e encerra o dialogo, atribuindo um identificador."""

    def desce(self, unidade: UnidadeDados,
              contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        contador: ContadorGlobal = contexto["contador"]
        identificador = contador.proxima_sessao()

        nova = unidade.com_cabecalho(cabecalho_sessao(identificador))
        nova.sessao = identificador
        nova.unidade = "Mensagem"

        evento = _evento(contexto, "L5", "ABRE",
                         f"sessao {identificador} estabelecida", nova)
        return nova, [evento]

    def sobe(self, unidade: UnidadeDados,
             contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        """Le o proprio cabecalho, recupera o identificador e encerra o dialogo."""
        cabecalho = unidade.cabecalho_da_camada(5)
        identificador = (sessao_do_cabecalho(cabecalho)
                         if cabecalho is not None else "desconhecida")

        _, nova = unidade.sem_cabecalho(5)
        nova.sessao = identificador
        nova.unidade = "Mensagem"

        evento = _evento(contexto, "L5", "ENCERRA",
                         f"sessao {identificador} encerrada", nova)
        return nova, [evento]


# Camada 4 - Transporte


class CamadaTransporte:
    """Numera portas, segmenta na origem e remonta em ordem no destino.

    O buffer de remontagem e indexado pelo par de portas, que e o unico
    identificador de fluxo que pertence a esta camada. E por isso que dois
    fluxos concorrentes vindos de portas de origem distintas nao se misturam,
    ainda que cheguem a mesma porta de destino (cenario E3).
    """

    def __init__(self) -> None:
        self._buffer: dict[tuple[int, int], dict[int, UnidadeDados]] = {}
        self._esperado: dict[tuple[int, int], int] = {}

    # descida

    def desce(self, unidade: UnidadeDados,
              contexto: dict[str, Any]) -> list[tuple[UnidadeDados, list[Evento]]]:
        """Devolve um par (segmento, eventos) por segmento produzido.

        A unidade recebida da camada 5 e formada pelo cabecalho de sessao mais
        o conteudo cifrado. Se o conjunto nao passa do limiar, viaja inteiro;
        se passa, e fatiado. O cabecalho de sessao entra uma unica vez, no
        primeiro segmento, e ocupa os seus primeiros octetos.
        """
        porta_origem = contexto["porta_origem"]
        porta_destino = contexto["porta_destino"]

        cabecalho_superior = unidade.cabecalho_da_camada(5)
        tamanho_superior = len(cabecalho_superior) if cabecalho_superior else 0
        total = tamanho_superior + len(unidade.dados)

        if total <= config.LIMIAR_SEGMENTACAO:
            fatias = [unidade.dados]
        else:
            primeira = max(1, config.CARGA_MAXIMA_SEGMENTO - tamanho_superior)
            fatias = [unidade.dados[:primeira]]
            fatias += [
                unidade.dados[i:i + config.CARGA_MAXIMA_SEGMENTO]
                for i in range(primeira, len(unidade.dados),
                               config.CARGA_MAXIMA_SEGMENTO)
            ]

        quantidade = len(fatias)
        resultados: list[tuple[UnidadeDados, list[Evento]]] = []

        for numero, fatia in enumerate(fatias, start=1):
            segmento = unidade.copia()
            segmento.dados = fatia
            # Apenas o primeiro segmento carrega o cabecalho de sessao.
            segmento.cabecalhos = list(unidade.cabecalhos) if numero == 1 else []
            segmento = segmento.com_cabecalho(
                cabecalho_transporte(porta_origem, porta_destino, numero, quantidade)
            )
            segmento.unidade = "Segmento"
            segmento.portas = (porta_origem, porta_destino)
            segmento.numero_segmento = numero
            segmento.total_segmentos = quantidade
            # Carga util deste segmento, isto e, tudo o que a camada 4 recebeu
            # da camada 5 e coube aqui. E este o numero citado no cenario E7.
            segmento.metadados["carga_l4"] = (
                len(fatia) + (tamanho_superior if numero == 1 else 0)
            )

            evento = _evento(
                contexto, "L4", "SEGMENTA",
                f"porta {porta_origem} {SETA} {porta_destino}, "
                f"segmento {numero} de {quantidade}",
                segmento,
            )
            resultados.append((segmento, [evento]))

        return resultados

    # subida

    def sobe(self, unidade: UnidadeDados,
             contexto: dict[str, Any]) -> tuple[UnidadeDados | None, list[Evento]]:
        """Remove o cabecalho de transporte e remonta os segmentos em ordem.

        Devolve `None` enquanto faltarem segmentos: a camada 5 so e acionada
        depois que a mensagem inteira foi reconstituida.
        """
        cabecalho = unidade.cabecalho_da_camada(4)
        if cabecalho is None:
            return None, []

        porta_origem, porta_destino, numero, total = struct.unpack(
            ">HHHH", cabecalho.octetos
        )
        chave = (porta_origem, porta_destino)

        _, nova = unidade.sem_cabecalho(4)
        nova.unidade = "Mensagem"
        nova.portas = (porta_origem, porta_destino)
        nova.numero_segmento = numero
        nova.total_segmentos = total

        processo = contexto["topologia"].processo_da_porta(porta_destino)
        rotulo_processo = f" ({processo})" if processo else ""

        if total == 1:
            evento = _evento(
                contexto, "L4", "DEMULTIPLEXA",
                f"porta {porta_destino}{rotulo_processo} recebe da porta "
                f"{porta_origem}, segmento 1 de 1",
                nova, estado="sucesso",
            )
            return nova, [evento]

        armazenados = self._buffer.setdefault(chave, {})
        armazenados[numero] = nova
        self._esperado[chave] = total

        if len(armazenados) < total:
            evento = _evento(
                contexto, "L4", "ARMAZENA",
                f"porta {porta_destino}{rotulo_processo}, segmento {numero} de "
                f"{total} retido; faltam {total - len(armazenados)}",
                nova,
            )
            return None, [evento]

        # Todos os segmentos chegaram: remonta em ordem de numero.
        ordenados = [armazenados[i] for i in sorted(armazenados)]
        remontada = ordenados[0].copia()
        remontada.dados = b"".join(parte.dados for parte in ordenados)
        remontada.numero_segmento = 1
        remontada.total_segmentos = 1

        evento_retencao = _evento(
            contexto, "L4", "ARMAZENA",
            f"porta {porta_destino}{rotulo_processo}, segmento {numero} de "
            f"{total} retido; faltam 0",
            nova,
        )
        evento_remontagem = _evento(
            contexto, "L4", "REMONTA",
            f"segmentos 1 a {total} remontados em ordem na porta {porta_destino}",
            remontada, estado="sucesso",
        )

        del self._buffer[chave]
        del self._esperado[chave]
        return remontada, [evento_retencao, evento_remontagem]

    def limpar(self) -> None:
        self._buffer.clear()
        self._esperado.clear()


# Camada 3 - Rede


class CamadaRede:
    """Insere o par de enderecos logicos e consulta a tabela de encaminhamento.

    Esta e a unica camada que decide para onde a unidade vai. O resultado da
    decisao e depositado em `contexto["saida"]`, de onde a camada 2 o retira
    para enderecar o quadro do salto.
    """

    def desce(self, unidade: UnidadeDados,
              contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        """Encapsula o segmento em um pacote e decide o primeiro salto."""
        contador: ContadorGlobal = contexto["contador"]
        ip_origem = contexto["ip_origem"]
        ip_destino = contexto["ip_destino"]

        rotulo = contador.proximo_pacote()
        comprimento = config.TAMANHO_CABECALHO_REDE + unidade.tamanho()

        nova = unidade.com_cabecalho(
            cabecalho_rede(ip_origem, ip_destino,
                           int(rotulo[1:]), comprimento)
        )
        nova.unidade = "Pacote"
        nova.logicos = (ip_origem, ip_destino)
        nova.pacote = rotulo

        eventos = [_evento(contexto, "L3", "ENCAPSULA",
                           f"{ip_origem} {SETA} {ip_destino}", nova)]
        eventos.extend(self._decidir(nova, contexto))
        return nova, eventos

    def encaminha(self, unidade: UnidadeDados,
                  contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        """Decide o proximo salto de um pacote em transito, dentro do roteador.

        O cabecalho de rede nao e removido nem reescrito: o roteador apenas le
        o endereco logico de destino. Tudo o que esta a direita desse
        cabecalho e, para este objeto, uma sequencia opaca de octetos.
        """
        return unidade, self._decidir(unidade, contexto)

    def sobe(self, unidade: UnidadeDados,
             contexto: dict[str, Any]) -> tuple[UnidadeDados | None, list[Evento]]:
        """Confere o destino logico e entrega o segmento a camada 4."""
        proprio = contexto["ip_local"]
        destino = unidade.logicos[1] if unidade.logicos else ""

        if destino != proprio:
            evento = _evento(
                contexto, "L3", "DESCARTA",
                f"endereco logico {destino} nao pertence a este dispositivo",
                unidade, estado="erro",
            )
            return None, [evento]

        rotulo = unidade.pacote or "?"
        _, nova = unidade.sem_cabecalho(3)
        nova.unidade = "Segmento"

        evento = _evento(contexto, "L3", "DESENCAPSULA",
                         f"pacote {rotulo} entregue ao destino {destino}", nova)
        return nova, [evento]

    # decisao de rota

    def _decidir(self, unidade: UnidadeDados,
                 contexto: dict[str, Any]) -> list[Evento]:
        """Consulta a tabela de encaminhamento e escreve a decisao no contexto."""
        topologia = contexto["topologia"]
        dispositivo = contexto["dispositivo"]
        ip_destino = unidade.logicos[1] if unidade.logicos else ""

        entrada = topologia.consultar_rota(dispositivo, ip_destino)
        if entrada is None:
            contexto["saida"] = None
            return [_evento(
                contexto, "L3", "DESCARTA",
                f"sem rota para {ip_destino}; pacote descartado",
                unidade, estado="erro",
            )]

        segmento = topologia.segmento_ativo_de(dispositivo, entrada.interface_saida)
        if segmento is None:
            contexto["saida"] = None
            return [_evento(
                contexto, "L3", "DESCARTA",
                f"interface {entrada.interface_saida} indisponivel; "
                f"pacote descartado",
                unidade, estado="erro",
            )]

        if entrada.tipo == "direto":
            ip_proximo = ip_destino
            descricao = (f"{entrada.destino_prefixo} e rede local, "
                         f"entrega direta pela interface {entrada.interface_saida}")
        else:
            ip_proximo = entrada.proximo_salto
            if entrada.via == "padrao":
                descricao = (f"proximo salto {ip_proximo} pela interface "
                             f"{entrada.interface_saida}")
            else:
                descricao = (f"{entrada.destino_prefixo} via {entrada.via}, "
                             f"custo {entrada.custo}, interface "
                             f"{entrada.interface_saida}")

        fisico_proximo = topologia.resolver_fisico(ip_proximo, segmento)
        if fisico_proximo is None:
            contexto["saida"] = None
            return [_evento(
                contexto, "L3", "DESCARTA",
                f"nenhum vizinho responde por {ip_proximo} em {segmento.rotulo}; "
                f"pacote descartado",
                unidade, estado="erro",
            )]

        interface_local = topologia.dispositivos[dispositivo].interface_por_nome(
            entrada.interface_saida
        )
        vizinho = topologia.dispositivo_por_ip(ip_proximo)

        contexto["saida"] = {
            "interface": entrada.interface_saida,
            "fisico_origem": interface_local.fisico if interface_local else "",
            "fisico_destino": fisico_proximo,
            "proximo_salto_ip": ip_proximo,
            "proximo_dispositivo": vizinho.nome if vizinho else "",
            "segmento": segmento.id,
            "rotulo_enlace": segmento.rotulo,
        }
        return [_evento(contexto, "L3", "ROTEIA", descricao, unidade)]


# Camada 2 - Enlace


class CamadaEnlace:
    """Insere o par de enderecos fisicos do salto, delimita e verifica o quadro.

    Esta camada nao escolhe rota: ela apenas entrega ao vizinho que a camada 3
    indicou em `contexto["saida"]`.
    """

    def desce(self, unidade: UnidadeDados,
              contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        contador: ContadorGlobal = contexto["contador"]
        saida = contexto["saida"]
        fisico_origem = saida["fisico_origem"]
        fisico_destino = saida["fisico_destino"]

        rotulo = contador.proximo_quadro()
        cabecalho = cabecalho_enlace(fisico_origem, fisico_destino)

        nova = unidade.com_cabecalho(cabecalho)
        nova.finalizador = finalizador_enlace(nova.conteudo_protegido())
        nova.unidade = "Quadro"
        nova.fisicos = (fisico_origem, fisico_destino)
        nova.quadro = rotulo
        # Um quadro so existe dentro de um enlace. Anotar aqui o enlace em que
        # ele viaja permite ao motor transporta-lo sem reconsultar a decisao de
        # rota, que ja pertence ao passado.
        nova.metadados["enlace"] = saida["segmento"]
        nova.metadados["rotulo_enlace"] = saida["rotulo_enlace"]
        nova.metadados["proximo_dispositivo"] = saida["proximo_dispositivo"]
        nova.metadados["bit_alterado"] = False

        evento = _evento(
            contexto, "L2", "ENQUADRA",
            f"{mac_curto(fisico_origem)} {SETA} {mac_curto(fisico_destino)}, "
            f"quadro {rotulo}",
            nova,
            enlace=(contexto["dispositivo"], saida["proximo_dispositivo"]),
        )
        return nova, [evento]

    def sobe(self, unidade: UnidadeDados,
             contexto: dict[str, Any]) -> tuple[UnidadeDados | None, list[Evento]]:
        """Confere a verificacao de erro e extrai o pacote.

        O quadro recebido e sempre descartado: quando a unidade segue adiante,
        e um quadro novo que sera construido na saida (restricao R2). Quando a
        verificacao falha, nenhuma camada superior chega a ser acionada.
        """
        rotulo = unidade.quadro or "?"
        finalizador = unidade.finalizador
        cabecalho = unidade.cabecalho_da_camada(2)

        if finalizador is None or cabecalho is None:
            evento = _evento(contexto, "L2", "DESCARTA",
                             f"quadro {rotulo} malformado; descartado",
                             unidade, estado="erro")
            return None, [evento]

        recebida = struct.unpack(">I", finalizador.octetos)[0]
        calculada = calcular_verificacao(unidade.conteudo_protegido())

        if recebida != calculada:
            evento = _evento(
                contexto, "L2", "DESCARTA",
                f"verificacao de erro inconsistente "
                f"(0x{recebida:08X} != 0x{calculada:08X}); "
                f"quadro {rotulo} descartado",
                unidade, estado="erro",
            )
            return None, [evento]

        _, nova = unidade.sem_cabecalho(2)
        nova.finalizador = None
        nova.unidade = "Pacote"

        evento = _evento(contexto, "L2", "DESENQUADRA",
                         f"verificacao de erro correta, quadro {rotulo} descartado",
                         nova)
        return nova, [evento]


# Camada 1 - Fisica


class CamadaFisica:
    """Converte o quadro em uma sequencia de bits e a transporta pelo enlace."""

    def desce(self, unidade: UnidadeDados,
              contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        vizinho = contexto["saida"]["proximo_dispositivo"]
        par = (contexto["dispositivo"], vizinho)

        evento = _evento(
            contexto, "L1", "TRANSMITE",
            f"{unidade.tamanho_bits()} bits no enlace "
            f"{par[0]}–{par[1]}",
            unidade, enlace=par,
        )
        return unidade, [evento]

    def sobe(self, unidade: UnidadeDados,
             contexto: dict[str, Any]) -> tuple[UnidadeDados, list[Evento]]:
        anterior = contexto.get("enlace_origem", "?")
        par = (anterior, contexto["dispositivo"])
        alterado = unidade.metadados.get("bit_alterado", False)

        complemento = "; um bit foi alterado no meio" if alterado else ""
        evento = _evento(
            contexto, "L1", "RECEBE",
            f"{unidade.tamanho_bits()} bits do enlace "
            f"{par[0]}–{par[1]}{complemento}",
            unidade, enlace=par, estado="erro" if alterado else "normal",
        )
        return unidade, [evento]
