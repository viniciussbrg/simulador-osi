# -*- coding: utf-8 -*-
"""Relogio e laco de simulacao.

Recebe um ou mais fluxos e produz a lista de eventos que a interface consome.

O motor nao escolhe rota: le o enlace que a camada 2 anotou no quadro, entrega
ao vizinho e deixa a camada 3 desse vizinho decidir o salto seguinte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any

from . import config
from .camadas import ContadorGlobal
from .dispositivos import Computador, Roteador
from .eventos import Evento, RegistroEventos
from .pdu import UnidadeDados, ip_valido
from .rede import Topologia

# Limite de saltos aceito antes de considerar que ha um laco de roteamento.
LIMITE_SALTOS = 32


@dataclass
class Fluxo:
    """Uma comunicacao ponta a ponta a ser simulada."""

    origem: str
    destino_ip: str
    texto: str
    processo_origem: str = "navegador"
    processo_destino: str = "servidorWeb"
    porta_origem: int | None = None
    porta_destino: int | None = None
    rotulo: str = "A"


@dataclass
class ResumoFluxo:
    """O que aconteceu com um fluxo: percurso, quadros e entrega."""

    rotulo: str
    origem: str
    destino_ip: str
    caminho: list[str] = field(default_factory=list)
    quadros: list[dict[str, Any]] = field(default_factory=list)
    segmentos: list[int] = field(default_factory=list)
    octetos_dados: int = 0
    octetos_transmitidos: int = 0
    entregue: bool = False
    texto_recebido: str = ""
    motivo: str = ""


class ResultadoSimulacao:
    """Tudo o que uma execucao produz, pronto para ser lido pela interface."""

    def __init__(self) -> None:
        self.registro = RegistroEventos()
        self.fluxos: list[ResumoFluxo] = []
        self.tabelas: dict[str, list] = {}
        self.enlaces_derrubados: list[str] = []
        self.enlace_com_erro: str = ""
        self.observacao: str = ""

    # leitura

    @property
    def eventos(self) -> list[Evento]:
        return list(self.registro)

    @property
    def caminho(self) -> list[str]:
        return self.fluxos[0].caminho if self.fluxos else []

    @property
    def octetos_dados(self) -> int:
        return sum(f.octetos_dados for f in self.fluxos)

    @property
    def octetos_transmitidos(self) -> int:
        return sum(f.octetos_transmitidos for f in self.fluxos)

    @property
    def eficiencia(self) -> float:
        if self.octetos_transmitidos == 0:
            return 0.0
        return self.octetos_dados / self.octetos_transmitidos

    @property
    def sobrecarga(self) -> float:
        return 1.0 - self.eficiencia

    @property
    def entregue(self) -> bool:
        return bool(self.fluxos) and all(f.entregue for f in self.fluxos)

    @property
    def total_quadros(self) -> int:
        return sum(len(f.quadros) for f in self.fluxos)

    def resumo_texto(self) -> list[str]:
        """Quadro numerico da comunicacao, em linhas prontas para exibicao."""
        linhas = [
            f"Octetos uteis da mensagem ....... {self.octetos_dados} B",
            f"Octetos transmitidos nos enlaces  {self.octetos_transmitidos} B",
            f"Quadros construidos ............. {self.total_quadros}",
            f"Eficiencia (n) .................. {self.eficiencia:.1%}",
            f"Sobrecarga (1 - n) .............. {self.sobrecarga:.1%}",
        ]
        if not self.entregue:
            motivos = "; ".join(f.motivo for f in self.fluxos if f.motivo)
            linhas.append(f"Mensagem nao entregue ........... {motivos}")
        return linhas


class Motor:
    """Executa fluxos de comunicacao sobre uma topologia."""

    def __init__(self, topologia: Topologia) -> None:
        self.topologia = topologia
        self.contador = ContadorGlobal()
        self.dispositivos: dict[str, Any] = {}

    # preparacao

    def _preparar(self) -> None:
        """Recria as pilhas de todos os dispositivos e zera os contadores."""
        self.contador.reiniciar()
        self.dispositivos = {
            nome: (Roteador(nome) if dispositivo.tipo == "roteador"
                   else Computador(nome))
            for nome, dispositivo in self.topologia.dispositivos.items()
        }

    # execucao

    def executar(self, fluxos: list[Fluxo], *,
                 enlaces_derrubados: list[str] | None = None,
                 enlace_com_erro: str = "",
                 observacao: str = "") -> ResultadoSimulacao:
        """Simula todos os fluxos e devolve o resultado consolidado.

        Quando ha mais de um fluxo, os eventos sao intercalados passo a passo
        para representar a concorrencia; os identificadores de sessao, pacote
        e quadro continuam unicos porque o contador e compartilhado.
        """
        self.topologia.restaurar_enlaces()
        for identificador in enlaces_derrubados or []:
            self.topologia.definir_estado_enlace(identificador, False)

        self._preparar()

        resultado = ResultadoSimulacao()
        resultado.enlaces_derrubados = list(enlaces_derrubados or [])
        resultado.enlace_com_erro = enlace_com_erro
        resultado.observacao = observacao

        listas: list[list[Evento]] = []
        for fluxo in fluxos:
            eventos, resumo = self._executar_fluxo(fluxo, enlace_com_erro)
            listas.append(eventos)
            resultado.fluxos.append(resumo)

        for evento in self._intercalar(listas):
            resultado.registro.adicionar(evento)
        resultado.registro.renumerar()

        resultado.tabelas = {
            nome: self.topologia.tabela_encaminhamento(nome)
            for nome in self.topologia.dispositivos
        }
        self.topologia.restaurar_enlaces()
        return resultado

    @staticmethod
    def _intercalar(listas: list[list[Evento]]) -> list[Evento]:
        """Intercala as listas de eventos de fluxos concorrentes.

        SIMPLIFICADO: usa itertools.zip_longest em vez de laco aninhado com
        indice manual. zip_longest agrupa a N-esima posicao de cada lista
        (preenchendo com None onde uma lista ja acabou); o filtro descarta
        esses None. Com uma unica lista, o resultado e ela mesma.
        """
        return [evento for grupo in zip_longest(*listas) for evento in grupo
                if evento is not None]

    # um fluxo

    def _executar_fluxo(self, fluxo: Fluxo,
                        enlace_com_erro: str) -> tuple[list[Evento], ResumoFluxo]:
        resumo = ResumoFluxo(rotulo=fluxo.rotulo, origem=fluxo.origem,
                             destino_ip=fluxo.destino_ip)
        eventos: list[Evento] = []

        origem = self.topologia.dispositivos.get(fluxo.origem)
        if origem is None or origem.tipo != "computador":
            resumo.motivo = f"{fluxo.origem} nao e um computador da topologia"
            return eventos, resumo
        if not ip_valido(fluxo.destino_ip):
            resumo.motivo = f"endereco de destino invalido: {fluxo.destino_ip}"
            return eventos, resumo

        porta_origem = (fluxo.porta_origem
                        or self.topologia.porta_do_processo(fluxo.processo_origem)
                        or 5210)
        porta_destino = (fluxo.porta_destino
                         or self.topologia.porta_do_processo(fluxo.processo_destino)
                         or 443)

        contexto: dict[str, Any] = {
            "contador": self.contador,
            "topologia": self.topologia,
            "dispositivo": fluxo.origem,
            "ip_local": origem.ip_principal,
            "ip_origem": origem.ip_principal,
            "ip_destino": fluxo.destino_ip,
            "processo_origem": fluxo.processo_origem,
            "processo_destino": fluxo.processo_destino,
            "porta_origem": porta_origem,
            "porta_destino": porta_destino,
            "fluxo": fluxo.rotulo,
            "caminho": [fluxo.origem],
            "saida": None,
        }

        emissor = self.dispositivos[fluxo.origem]
        texto_octetos = len(fluxo.texto.encode(config.CODIFICACAO))

        segmentos, eventos_comuns = emissor.preparar_envio(fluxo.texto, contexto)
        eventos.extend(eventos_comuns)
        resumo.segmentos = [
            segmento.metadados.get("carga_l4", len(segmento.dados))
            for segmento, _ in segmentos
        ]

        entregues = 0
        for segmento, eventos_segmento in segmentos:
            eventos.extend(eventos_segmento)

            # FIX: o mesmo `contexto` e reaproveitado entre segmentos, e
            # _percorrer() reescreve "ip_local" a cada salto do segmento
            # anterior (com o endereco do ultimo dispositivo visitado, nao
            # mais o da origem). Sem este reset, o 2o/3o segmento de uma
            # mensagem longa despacharia com "ip_local" incorreto.
            contexto["ip_local"] = origem.ip_principal

            unidade, eventos_descida = emissor.despachar(segmento, contexto)
            eventos.extend(eventos_descida)
            if unidade is None:
                resumo.motivo = resumo.motivo or self._motivo(eventos_descida)
                continue

            eventos_percurso, chegou = self._percorrer(
                unidade, fluxo.origem, contexto, resumo, enlace_com_erro
            )
            eventos.extend(eventos_percurso)
            if chegou:
                entregues += 1

        resumo.caminho = list(contexto["caminho"])
        # FIX: a entrega nao pode depender de `resumo.texto_recebido` ser
        # "truthy" -- uma mensagem vazia ("") entregue com sucesso e falsy
        # em Python e seria erroneamente contada como falha. O sinal de
        # sucesso e `entregues`, definido explicitamente em _percorrer().
        if entregues:
            resumo.entregue = True
            resumo.octetos_dados = texto_octetos
        elif not resumo.motivo:
            resumo.motivo = "mensagem nao chegou ao processo de destino"

        return eventos, resumo

    # percurso de um quadro

    def _percorrer(self, unidade: UnidadeDados, transmissor: str,
                   contexto: dict[str, Any], resumo: ResumoFluxo,
                   enlace_com_erro: str) -> tuple[list[Evento], bool]:
        """Leva um quadro de enlace em enlace ate o destino ou ate o descarte."""
        eventos: list[Evento] = []
        atual = transmissor
        saltos = 0

        # SIMPLIFICADO: era `while unidade is not None:`, mas toda saida do
        # laco sempre acontece por `return` explicito (descarte ou entrega);
        # `unidade` nunca vira None e "cai fora" naturalmente. `while True`
        # deixa isso claro para quem le o codigo.
        while True:
            saltos += 1
            if saltos > LIMITE_SALTOS:
                # FIX: antes saia sem motivo, caindo no fallback generico
                # "mensagem nao chegou ao processo de destino" em
                # _executar_fluxo. Agora identifica a causa real: um laco
                # de roteamento entre dispositivos mal configurados.
                resumo.motivo = resumo.motivo or (
                    "laco de roteamento detectado (limite de saltos excedido)"
                )
                return eventos, False

            proximo_nome = unidade.metadados.get("proximo_dispositivo", "")
            proximo = self.topologia.dispositivos.get(proximo_nome)
            if proximo is None:
                # FIX: mesma logica -- antes saia sem motivo. Agora informa
                # que o quadro apontava para um dispositivo desconhecido
                # ou ausente na topologia (proximo_dispositivo vazio ou
                # invalido), em vez do fallback generico de "nao chegou".
                resumo.motivo = resumo.motivo or (
                    f"proximo dispositivo desconhecido: '{proximo_nome}'"
                )
                return eventos, False

            # O quadro entra no enlace: e aqui que os octetos sao contados.
            resumo.octetos_transmitidos += unidade.tamanho()
            resumo.quadros.append({
                "rotulo": unidade.quadro or "?",
                "enlace": unidade.metadados.get("rotulo_enlace", ""),
                "de": atual,
                "para": proximo_nome,
                "fisicos": unidade.fisicos,
                "logicos": unidade.logicos,
                "octetos": unidade.tamanho(),
            })

            if enlace_com_erro and unidade.metadados.get("enlace") == enlace_com_erro:
                unidade = self._alterar_um_bit(unidade)

            contexto["enlace_origem"] = atual
            contexto["ip_local"] = self._ip_de_chegada(proximo_nome, unidade)
            if proximo_nome not in contexto["caminho"]:
                contexto["caminho"].append(proximo_nome)

            receptor = self.dispositivos[proximo_nome]

            if proximo.tipo == "roteador":
                unidade, novos = receptor.encaminhar(unidade, contexto)
                eventos.extend(novos)
                if unidade is None:
                    # FIX: preserva a causa-raiz do descarte, em vez de
                    # sobrescrever um motivo ja registrado por um segmento
                    # anterior (mesma politica usada em _executar_fluxo).
                    resumo.motivo = resumo.motivo or self._motivo(novos)
                    return eventos, False
                atual = proximo_nome
                continue

            mensagem, novos = receptor.receber(unidade, contexto)
            eventos.extend(novos)
            if mensagem is None:
                motivo = self._motivo(novos)
                if motivo:
                    # FIX: mesma politica de causa-raiz aplicada aqui.
                    resumo.motivo = resumo.motivo or motivo
                return eventos, False
            resumo.texto_recebido = mensagem.texto_original or ""
            return eventos, True

    # auxiliares

    def _ip_de_chegada(self, dispositivo: str, unidade: UnidadeDados) -> str:
        """Endereco logico da interface pela qual o quadro chega ao vizinho.

        SIMPLIFICADO: laco com `return` no meio trocado por `next()` com
        valor padrao -- mesmo comportamento, uma expressao em vez de laco.
        """
        alvo = self.topologia.dispositivos[dispositivo]
        fisico_destino = unidade.fisicos[1] if unidade.fisicos else ""
        return next(
            (interface.logico for interface in alvo.interfaces
             if interface.fisico == fisico_destino),
            alvo.ip_principal,
        )

    @staticmethod
    def _alterar_um_bit(unidade: UnidadeDados) -> UnidadeDados:
        """Inverte um bit da carga do quadro, sem tocar na verificacao de erro.

        E o que ocorre em um meio ruidoso: o quadro chega diferente do que foi
        transmitido, mas o finalizador continua sendo o que o transmissor
        calculou. A camada 2 do receptor descobre a divergencia ao refazer a
        conta.
        """
        alterada = unidade.copia()
        if alterada.dados:
            octetos = bytearray(alterada.dados)
            octetos[0] ^= 0x01
            alterada.dados = bytes(octetos)
        elif alterada.cabecalhos:
            cabecalho = alterada.cabecalhos[-1]
            octetos = bytearray(cabecalho.octetos)
            octetos[-1] ^= 0x01
            alterada.cabecalhos = list(alterada.cabecalhos)
            alterada.cabecalhos[-1] = type(cabecalho)(
                cabecalho.camada, cabecalho.nome, bytes(octetos),
                dict(cabecalho.campos), cabecalho.finalizador,
            )
        alterada.metadados["bit_alterado"] = True
        return alterada

    @staticmethod
    def _motivo(eventos: list[Evento]) -> str:
        """Extrai a descricao do evento de descarte, para o resumo.

        SIMPLIFICADO: laco com `return` no meio trocado por `next()` com
        valor padrao -- mesmo comportamento, uma expressao em vez de laco.
        """
        return next(
            (f"{evento.dispositivo}/{evento.camada}: {evento.descricao}"
             for evento in reversed(eventos) if evento.acao == "DESCARTA"),
            "",
        )