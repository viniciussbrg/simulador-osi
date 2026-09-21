"""As sete camadas do modelo OSI.

Cada classe implementa uma camada e expoe apenas descer() e subir(). Nenhuma
camada conhece a vizinha: quem as encadeia e a pilha do dispositivo
(dispositivos.py). Tudo o que uma camada decide e outra precisa saber passa
pelo Contexto, que a pilha entrega a todas as camadas do dispositivo.

Convencao de retorno: descer() e subir() devolvem (pdus, eventos), em que
pdus e uma tupla de PDUs novas. Quase sempre ha exatamente uma; a camada 4
devolve varias ao segmentar, e a tupla vazia significa que nada segue
adiante (pacote sem rota, quadro com soma divergente, segmento aguardando os
demais). A pilha nao precisa de casos especiais: percorre o que voltou.

Nenhuma camada imprime nada. O que aconteceu vai na lista de eventos, que
registro.py formata.

Leitura de cabecalhos (R5): toda leitura passa por Camada._meu_cabecalho(),
que consulta sempre o numero da propria camada. Nao ha no modulo nenhuma
chamada a cabecalho_da_camada() com outro numero.

Topologia: apenas as camadas 3 e 2 consultam rede.Topologia. A camada 3
decide o proximo salto (nome do dispositivo) e a interface de saida; a
camada 2 so traduz essa decisao em enderecos fisicos (R4).
"""

import itertools
from dataclasses import dataclass, field, replace

from .pdu import Cabecalho
from .registro import ACOES, Evento

# Chave fixa da cifra da camada 6. XOR octeto a octeto nao altera o tamanho.
CHAVE_XOR = 0x5A

# Processos do caso central: o navegador fala com o servidor web do destino.
PROCESSO_PADRAO = "navegador"
PORTAS_PADRAO = (5210, 443)
PROCESSOS_PADRAO = {5210: "navegador", 443: "servidorWeb"}


def octetos_do_quadro(quadro):
    """Octetos cobertos pela soma de verificacao: cabecalhos e dados.

    Os cabecalhos das outras camadas entram como octetos opacos, na ordem em
    que viajam no quadro: a camada 2 nao interpreta nenhum campo deles,
    apenas os soma, como faria com o conteudo de um quadro real. O
    finalizador fica de fora porque e ele que guarda a soma.
    """
    cabecalhos = b"".join(
        f"H{c.camada}[{c.resumo()}]".encode("utf-8")
        for c in quadro.cabecalhos
        if not c.finalizador
    )
    return cabecalhos + quadro.dados


def soma_de_verificacao(octetos):
    """Soma simples dos octetos, truncada em 32 bits para caber no finalizador.

    Qualquer inversao de um unico bit altera a soma em uma potencia de dois,
    o que basta para a camada 2 detectar o erro de bit do cenario E6, caia
    ele nos dados ou em um cabecalho.
    """
    return sum(octetos) & 0xFFFFFFFF


def _xor(octetos):
    return bytes(o ^ CHAVE_XOR for o in octetos)


def _interfaces_de(topologia, dispositivo):
    return [i for i in topologia.interfaces.values() if i.dispositivo == dispositivo]


def _octetos(pdu):
    """Tamanho em octetos, mesmo quando os dados ainda sao texto.

    Nas camadas 7 e 6 os dados sao str, e PDU.tamanho contaria caracteres;
    o registro precisa dos octetos UTF-8.
    """
    if isinstance(pdu.dados, str):
        return pdu.tamanho - len(pdu.dados) + len(pdu.dados.encode("utf-8"))
    return pdu.tamanho


class ContadorDeQuadros:
    """Numeracao dos quadros, reiniciada a cada mensagem (C5).

    C5 pede Q1, Q2, ... na ordem de transmissao, "reiniciando a cada
    mensagem". A contagem nao pode entao ser global nem por dispositivo: ela
    pertence a mensagem, que atravessa varios dispositivos. A chave e o par
    de enderecos logicos, que por C6 e inserido na origem e permanece o mesmo
    ate o destino -- e exatamente a identidade fim a fim que se procura.

    Por ser dado de camada 3, essa chave esta ao alcance de todo salto,
    inclusive de um roteador, sem violar C4. Usar a porta de origem daria o
    mesmo resultado em E3 e obrigaria o roteador a ler um campo de camada 4.

    Em E3 os dois fluxos tem origens logicas distintas (10.0.1.10 e
    10.0.1.11) e cada um recebe Q1 a Q4. Em E7 os tres segmentos sao a mesma
    mensagem, com o mesmo par logico, e a contagem segue de Q1 a Q12.
    """

    def __init__(self):
        self._por_mensagem = {}

    def proximo(self, logicos):
        numero = self._por_mensagem.get(logicos, 0) + 1
        self._por_mensagem[logicos] = numero
        return numero


@dataclass
class Contexto:
    """O que a pilha de um dispositivo entrega a cada camada.

    Os contadores de passo, de quadro e de sessao devem ser os mesmos objetos
    em todos os contextos de uma simulacao, para que a numeracao seja unica:
    em E3, H1 e H2 abrem S-0001 e S-0002, e nao duas vezes S-0001.
    """

    dispositivo: str
    topologia: object

    # Na origem: processo que envia, par de portas e endereco logico de destino.
    processo: str = PROCESSO_PADRAO
    portas: tuple = PORTAS_PADRAO
    destino: str = None
    # No destino: porta -> nome do processo que a escuta.
    processos: dict = field(default_factory=lambda: dict(PROCESSOS_PADRAO))

    # Decisao da camada 3 no salto corrente, consumida pela camada 2:
    # nome da interface deste dispositivo e nome do dispositivo vizinho.
    interface_de_saida: str = None
    proximo_salto: str = None

    passos: object = field(default_factory=lambda: itertools.count(1))
    quadros: object = field(default_factory=ContadorDeQuadros)
    sessoes: object = field(default_factory=lambda: itertools.count(1))

    def proximo_passo(self):
        return next(self.passos)


class Camada:
    """Base comum: numero, nome e os apoios de leitura e registro."""

    numero = None
    nome = ""

    def descer(self, pdu, contexto):
        raise NotImplementedError

    def subir(self, pdu, contexto):
        raise NotImplementedError

    def _meu_cabecalho(self, pdu):
        """Unica via de leitura de cabecalho: sempre o da propria camada."""
        return pdu.cabecalho_da_camada(self.numero)

    def _tamanho_do_cabecalho(self, contexto):
        return contexto.topologia.convencoes["cabecalhos"][str(self.numero)]

    def _evento(self, contexto, acao, descricao, pdu):
        if acao not in ACOES:
            raise ValueError(f"acao desconhecida: {acao}")
        return Evento(
            passo=contexto.proximo_passo(),
            dispositivo=contexto.dispositivo,
            camada=self.numero,
            acao=acao,
            descricao=descricao,
            tamanho=_octetos(pdu),
        )


class Aplicacao(Camada):
    """L7: gera a mensagem e identifica o processo pelo nome. Sem cabecalho."""

    numero = 7
    nome = "Aplicacao"

    def descer(self, pdu, contexto):
        mensagem = replace(pdu, camada=7)
        return (mensagem,), [self._evento(
            contexto, "GERA",
            f"processo '{contexto.processo}' gera a mensagem", mensagem,
        )]

    def subir(self, pdu, contexto):
        mensagem = replace(pdu, camada=7)
        return (mensagem,), [self._evento(
            contexto, "ENTREGA",
            f"mensagem entregue ao processo '{contexto.processo}': {mensagem.dados!r}",
            mensagem,
        )]


class Apresentacao(Camada):
    """L6: texto <-> octetos UTF-8, cifrados com XOR de chave fixa.

    Sem cabecalho e sem mudanca de tamanho. Roteadores nao tem esta camada,
    entao so a L6 do destino decifra.
    """

    numero = 6
    nome = "Apresentacao"

    def descer(self, pdu, contexto):
        octetos = pdu.dados.encode("utf-8")
        cifrada = replace(pdu, dados=_xor(octetos), cifrado=True, camada=6)
        return (cifrada,), [self._evento(
            contexto, "CODIFICA",
            f"texto em {len(octetos)} octetos UTF-8 cifrado com XOR {CHAVE_XOR:#04x}; "
            f"tamanho inalterado",
            cifrada,
        )]

    def subir(self, pdu, contexto):
        texto = _xor(pdu.dados).decode("utf-8")
        clara = replace(pdu, dados=texto, cifrado=False, camada=7)
        return (clara,), [self._evento(
            contexto, "DECIFRA",
            f"{len(pdu.dados)} octetos decifrados com XOR e convertidos em texto",
            clara,
        )]


class Sessao(Camada):
    """L5: cabecalho com o identificador de sessao, uma unica vez por mensagem."""

    numero = 5
    nome = "Sessao"

    def descer(self, pdu, contexto):
        sessao = f"S-{next(contexto.sessoes):04d}"
        cabecalho = Cabecalho(5, self._tamanho_do_cabecalho(contexto), {"sessao": sessao})
        mensagem = replace(pdu, sessao=sessao).encapsular(cabecalho, camada=5)
        return (mensagem,), [self._evento(
            contexto, "ABRE",
            f"sessao {sessao} aberta, uma unica vez, antes da segmentacao",
            mensagem,
        )]

    def subir(self, pdu, contexto):
        sessao = self._meu_cabecalho(pdu).campos["sessao"]
        mensagem = replace(pdu.desencapsular(5, camada=6), sessao=sessao)
        return (mensagem,), [self._evento(
            contexto, "ENTREGA",
            f"sessao {sessao} reconhecida; mensagem entregue a camada 6",
            mensagem,
        )]


class Transporte(Camada):
    """L4: portas, segmentacao acima do limiar e remontagem em ordem."""

    numero = 4
    nome = "Transporte"

    def __init__(self):
        # (porta de origem, porta de destino) -> {numero do segmento: pedaco}
        self._pendentes = {}

    def descer(self, pdu, contexto):
        # Por que existe um limiar separado do limite de 40 octetos
        # ---------------------------------------------------------
        # C2 diz que a camada 4 divide em segmentos de no maximo 40 octetos
        # os dados que recebe da camada 5. Ao pe da letra, a mensagem de
        # referencia de 42 octetos chegaria aqui com 46 (42 + 4 do cabecalho
        # de sessao) e viraria dois segmentos, de 40 e 6.
        #
        # Isso contradiz a propria tabela de validacao da especificacao: o
        # log oficial traz "004 | H1 | L4 | SEGMENTA | porta 5210 -> 443,
        # segmento 1 de 1  54 B", um unico segmento, e E1 a E6 so fecham em
        # 92 octetos por quadro com um segmento. Dois segmentos dariam dois
        # quadros por enlace e derrubariam os sete valores oficiais.
        #
        # A leitura que reproduz todos os numeros da especificacao e a de
        # que 40 e o tamanho de corte, aplicado quando a mensagem e longa o
        # bastante para exigir divisao. O limiar guarda esse "longa o
        # bastante" e vem do topologia.json, nao do codigo. E7 (100 octetos
        # -> 104 -> 40, 40 e 24) continua exato, e E1 a E6 tambem.
        #
        # Nao altere o limiar sem refazer a tabela de validacao inteira.
        convencoes = contexto.topologia.convencoes
        limiar = convencoes["limiar_segmentacao_octetos"]
        limite = convencoes["limite_segmento_octetos"]
        origem, destino = contexto.portas

        pedacos = self._fatiar(pdu, limite) if pdu.tamanho > limiar else [pdu]
        total = len(pedacos)
        segmentos, eventos = [], []
        for numero, pedaco in enumerate(pedacos, start=1):
            cabecalho = Cabecalho(4, self._tamanho_do_cabecalho(contexto), {
                "porta_origem": origem,
                "porta_destino": destino,
                "segmento": numero,
                "total": total,
            })
            segmento = replace(
                pedaco, portas=(origem, destino),
                numero_segmento=numero, total_segmentos=total,
            ).encapsular(cabecalho, camada=4)
            segmentos.append(segmento)

            descricao = f"segmento {numero} de {total}: porta {origem} -> {destino}"
            if total > 1 and numero == 1:
                descricao += f" ({pdu.tamanho} octetos acima do limiar de {limiar})"
            eventos.append(self._evento(contexto, "SEGMENTA", descricao, segmento))
        return tuple(segmentos), eventos

    @staticmethod
    def _fatiar(pdu, limite):
        """Divide a unidade da L5 em pedacos de ate `limite` octetos.

        Os cabecalhos superiores (o da sessao) seguem inteiros no primeiro
        pedaco e ocupam parte dele; a camada 4 so conta o tamanho deles, nao
        os le. Assim 100 octetos de dados mais 4 de sessao dao 40, 40 e 24.
        """
        superiores = pdu.tamanho - len(pdu.dados)
        if superiores >= limite:
            raise ValueError("cabecalhos superiores nao cabem no primeiro segmento")
        primeiro = limite - superiores
        pedacos = [replace(pdu, dados=pdu.dados[:primeiro])]
        for inicio in range(primeiro, len(pdu.dados), limite):
            pedacos.append(replace(
                pdu, dados=pdu.dados[inicio:inicio + limite], cabecalhos=(),
            ))
        return pedacos

    def subir(self, pdu, contexto):
        # O fluxo e identificado pelo par de portas. Em E3, H1 e H2 falam com
        # a mesma porta 443 a partir de 5210 e 6120: sao duas chaves, dois
        # conjuntos de pendentes, e os segmentos de um nunca completam o outro.
        campos = self._meu_cabecalho(pdu).campos
        chave = (campos["porta_origem"], campos["porta_destino"])
        fluxo = f"fluxo {chave[0]} -> {chave[1]}"
        numero, total = campos["segmento"], campos["total"]

        recebidos = self._pendentes.setdefault(chave, {})
        recebidos[numero] = pdu.desencapsular(4, camada=5)
        if len(recebidos) < total:
            return (), [self._evento(
                contexto, "RECEBE",
                f"segmento {numero} de {total} do {fluxo} guardado; aguardando "
                f"{total - len(recebidos)}",
                pdu,
            )]

        del self._pendentes[chave]
        pedacos = [recebidos[n] for n in range(1, total + 1)]
        unidade = replace(
            pedacos[0],
            dados=b"".join(p.dados for p in pedacos),
            numero_segmento=1, total_segmentos=1,
        )

        porta = campos["porta_destino"]
        processo = contexto.processos.get(porta)
        if processo is None:
            return (), [self._evento(
                contexto, "DESCARTA",
                f"nenhum processo escuta a porta {porta}; mensagem descartada",
                unidade,
            )]
        contexto.processo = processo
        return (unidade,), [self._evento(
            contexto, "REMONTA",
            f"{total} segmento(s) do {fluxo} remontado(s) em ordem; "
            f"porta {porta} -> '{processo}'",
            unidade,
        )]


class Rede(Camada):
    """L3: par de enderecos logicos e escolha do proximo salto.

    E a camada mais alta de um roteador. O cabecalho e posto uma unica vez,
    na origem; nos roteadores ele passa intacto (R3).
    """

    numero = 3
    nome = "Rede"

    def __init__(self):
        self._pacotes = itertools.count(1)

    def descer(self, pdu, contexto):
        eventos = []
        cabecalho = self._meu_cabecalho(pdu)
        if cabecalho is None:
            origem = contexto.topologia.interface_de(contexto.dispositivo).logico
            destino = contexto.destino
            cabecalho = Cabecalho(3, self._tamanho_do_cabecalho(contexto), {
                "origem": origem, "destino": destino,
            })
            pdu = replace(
                pdu, logicos=(origem, destino),
                id_pacote=f"{contexto.dispositivo}-P{next(self._pacotes)}",
            ).encapsular(cabecalho, camada=3)
            eventos.append(self._evento(
                contexto, "ENCAPSULA",
                f"pacote {pdu.id_pacote}: {origem} -> {destino}", pdu,
            ))

        saida, vizinho, descricao = self._escolher_salto(cabecalho.campos["destino"], contexto)
        contexto.interface_de_saida, contexto.proximo_salto = saida, vizinho
        if saida is None:
            eventos.append(self._evento(
                contexto, "DESCARTA", f"{descricao}; pacote {pdu.id_pacote} descartado", pdu,
            ))
            return (), eventos

        eventos.append(self._evento(contexto, "ROTEIA", descricao, pdu))
        return (pdu,), eventos

    @staticmethod
    def _escolher_salto(destino, contexto):
        """Devolve (interface de saida, vizinho, descricao).

        Mesma rede de uma interface local: entrega direta. Senao, o roteador
        consulta a tabela de encaminhamento e o computador entrega ao
        roteador da sua rede. Interface None significa descarte.
        """
        topologia = contexto.topologia
        for interface in _interfaces_de(topologia, contexto.dispositivo):
            if topologia.mesma_rede(interface.logico, destino):
                alvo = topologia.interface_por_logico(destino)
                if alvo is None:
                    return None, None, f"{destino} nao existe na rede de {interface.nome}"
                return (interface.nome, alvo.dispositivo,
                        f"entrega direta a {alvo.dispositivo} pela interface {interface.nome}")

        if contexto.dispositivo in topologia.roteadores:
            rota = topologia.rota_para(contexto.dispositivo, destino)
            if rota is None:
                return None, None, f"sem rota para {destino}"
            return (rota.interface_de_saida, rota.proximo_salto,
                    f"{rota.prefixo} via {rota.proximo_salto}, custo {rota.custo}, "
                    f"interface {rota.interface_de_saida}")

        interface = topologia.interface_de(contexto.dispositivo)
        roteador = topologia.roteador_da_rede(interface.rede)
        if roteador is None:
            return None, None, f"{interface.rede} nao tem roteador para alcancar {destino}"
        return (interface.nome, roteador,
                f"{destino} fora da rede local: entrega indireta via {roteador}, "
                f"interface {interface.nome}")

    def subir(self, pdu, contexto):
        topologia = contexto.topologia
        destino = self._meu_cabecalho(pdu).campos["destino"]
        alvo = topologia.interface_por_logico(destino)
        if alvo is not None and alvo.dispositivo == contexto.dispositivo:
            pacote = pdu.desencapsular(3, camada=4)
            return (pacote,), [self._evento(
                contexto, "ENTREGA",
                f"pacote {pdu.id_pacote} destinado a {destino}; entregue a camada 4",
                pacote,
            )]
        if contexto.dispositivo in topologia.roteadores:
            # Em transito: cabecalho intacto; a pilha devolve o pacote a
            # descer(), que registra o ROTEIA deste salto.
            return (pdu,), []
        return (), [self._evento(
            contexto, "DESCARTA",
            f"pacote {pdu.id_pacote} para {destino} nao e deste dispositivo", pdu,
        )]


class Enlace(Camada):
    """L2: quadro novo a cada salto, com soma de verificacao no finalizador.

    Nao escolhe rota (R4): recebe da camada 3 a interface de saida e o nome
    do vizinho, e apenas procura a interface desse vizinho que esta na mesma
    rede da interface de saida para obter o endereco fisico de destino.
    """

    numero = 2
    nome = "Enlace"

    def descer(self, pdu, contexto):
        topologia = contexto.topologia
        saida = topologia.interface_de(contexto.dispositivo, contexto.interface_de_saida)
        vizinho = self._interface_do_vizinho(topologia, contexto.proximo_salto, saida.rede)
        # A numeracao acompanha a mensagem, nao o dispositivo (C5): a chave e
        # o par de enderecos logicos, que a camada 2 le da propria PDU.
        numero = f"Q{contexto.quadros.proximo(pdu.logicos)}"

        cabecalho = Cabecalho(2, self._tamanho_do_cabecalho(contexto), {
            "origem": saida.fisico, "destino": vizinho.fisico,
        })
        quadro = pdu.com_fisicos(saida.fisico, vizinho.fisico, numero)
        quadro = quadro.encapsular(cabecalho, camada=2)
        soma = soma_de_verificacao(octetos_do_quadro(quadro))
        finalizador = Cabecalho(
            2, contexto.topologia.convencoes["finalizador_camada_2"], {"soma": soma},
            finalizador=True,
        )
        quadro = quadro.encapsular(finalizador)
        # O pacote identifica a mensagem na linha do registro. Em E3 os dois
        # fluxos tem quadros de mesmo numero em cada salto, e e o pacote
        # (H1-P1 e H2-P1) que diz de quem e cada quadro. A porta de origem
        # faria o mesmo papel, mas so a custo de o roteador ler camada 4 (C4).
        return (quadro,), [self._evento(
            contexto, "ENQUADRA",
            f"pacote {pdu.id_pacote}, quadro {numero} para {vizinho.dispositivo}: "
            f"{saida.fisico} -> {vizinho.fisico}; soma {soma:#010x}",
            quadro,
        )]

    @staticmethod
    def _interface_do_vizinho(topologia, vizinho, rede):
        for interface in _interfaces_de(topologia, vizinho):
            if interface.rede == rede:
                return interface
        raise LookupError(f"{vizinho} nao tem interface em {rede}")

    def _meu_finalizador(self, pdu):
        for c in pdu.cabecalhos:
            if c.camada == self.numero and c.finalizador:
                return c
        return None

    def subir(self, pdu, contexto):
        recebida = self._meu_finalizador(pdu).campos["soma"]
        calculada = soma_de_verificacao(octetos_do_quadro(pdu))
        if calculada != recebida:
            return (), [self._evento(
                contexto, "DESCARTA",
                f"pacote {pdu.id_pacote}, quadro {pdu.numero_quadro}: soma recebida "
                f"{recebida:#010x} difere da calculada {calculada:#010x}; quadro descartado",
                pdu,
            )]

        origem = self._meu_cabecalho(pdu).campos["origem"]
        pacote = pdu.desencapsular(2, camada=3).com_fisicos(None, None, "")
        return (pacote,), [self._evento(
            contexto, "DESENQUADRA",
            f"pacote {pdu.id_pacote}, quadro {pdu.numero_quadro} de {origem} "
            f"conferido e descartado",
            pacote,
        )]


class Fisica(Camada):
    """L1: converte o quadro em bits e o transporta. Sem cabecalho."""

    numero = 1
    nome = "Fisica"

    def descer(self, pdu, contexto):
        bits = replace(pdu, camada=1)
        return (bits,), [self._evento(
            contexto, "TRANSMITE",
            f"pacote {pdu.id_pacote}, quadro {pdu.numero_quadro} convertido em "
            f"{bits.tamanho_em_bits} bits e transmitido",
            bits,
        )]

    def subir(self, pdu, contexto):
        quadro = replace(pdu, camada=2)
        return (quadro,), [self._evento(
            contexto, "RECEBE",
            f"{pdu.tamanho_em_bits} bits recebidos e reagrupados no pacote "
            f"{pdu.id_pacote}, quadro {pdu.numero_quadro}",
            quadro,
        )]
