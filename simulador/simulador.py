"""Execucao dos cenarios: dispositivos, meio fisico e registro.

A Simulacao recebe a topologia e um cenario, monta os dispositivos que
participam, faz o papel do meio fisico entre eles e produz a lista de
eventos do registro. Nao imprime nada e nao conhece interface grafica: a
interface pede um evento por vez com passo(), ou todos de uma vez com
executar(), e le o quadro resumo com resumo().

O meio fisico entrega cada quadro ao dispositivo dono do endereco fisico de
destino, sem consultar a decisao de rota: foi a camada 2 do emissor que
escreveu esse endereco, a partir do vizinho que a camada 3 indicou.

Quadros de origens distintas saem ao mesmo tempo, cada um pelo seu enlace.
A fila de transmissao intercala essas rajadas e, dali em diante, cada
quadro avanca um enlace por vez, na ordem em que foi posto no meio. E assim
que os dois fluxos de E3 chegam alternados a H4.

Os cenarios E1 a E7 sao dados: a tabela CENARIOS, no fim do modulo.
"""

import copy
import itertools
import os
from collections import deque
from dataclasses import dataclass, field, replace

from .camadas import ContadorDeQuadros
from .dispositivos import criar_dispositivo
from .recursos import caminho_de
from .registro import Evento, Registro

# Pasta dos registros dos sete cenarios, ao lado do programa (R10).
PASTA_DOS_REGISTROS = "registros"


# ----------------------------------------------------------------------
# Descricao de um cenario
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Falhas:
    """Falhas injetadas em uma execucao (R9). Sem argumentos, nenhuma."""

    # Par de dispositivos cujo enlace sai de servico, como ("R1", "R4").
    enlace_derrubado: tuple = None
    # Par de dispositivos em cujo enlace o primeiro quadro tem um bit invertido.
    bit_invertido: tuple = None
    # Qual bit dos dados do quadro e invertido, contado a partir de 0.
    posicao_do_bit: int = 0
    # Endereco fora da topologia que substitui o destino de todos os fluxos.
    destino_inalcancavel: str = None


@dataclass(frozen=True)
class Fluxo:
    """Uma mensagem de um processo de origem para um processo de destino."""

    origem: str          # dispositivo
    destino: str         # dispositivo
    processos: tuple     # (processo de origem, processo de destino)
    portas: tuple        # (porta de origem, porta de destino)
    mensagem: str


@dataclass(frozen=True)
class Cenario:
    codigo: str
    nome: str
    fluxos: tuple
    falhas: Falhas = field(default_factory=Falhas)


# ----------------------------------------------------------------------
# Resultados
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Transmissao:
    """Um quadro posto em um enlace, na forma em que o emissor o enviou."""

    de: str
    para: str
    quadro: object


@dataclass(frozen=True)
class Entrega:
    """Uma mensagem que chegou a camada 7 de um destino."""

    dispositivo: str
    processo: str
    sessao: str
    portas: tuple
    logicos: tuple
    mensagem: str


@dataclass(frozen=True)
class Resumo:
    """O quadro exibido ao fim de cada execucao (R8).

    A eficiencia usa os octetos efetivamente entregues: sem entrega, ela e
    zero, ainda que a mensagem tenha sido enviada (E5 e E6).
    """

    quadros: int
    octetos_da_mensagem: int
    octetos_uteis: int
    octetos_transmitidos: int
    eficiencia: float
    sobrecarga: float


# ----------------------------------------------------------------------
# Meio fisico
# ----------------------------------------------------------------------

def inverter_bit(quadro, posicao=0):
    """Devolve o quadro com um bit dos dados invertido, como faria um ruido.

    O finalizador continua com a soma calculada pelo emissor, e e essa
    divergencia que a camada 2 do receptor detecta (E6).
    """
    dados = bytearray(quadro.dados)
    posicao %= len(dados) * 8
    dados[posicao // 8] ^= 0x80 >> (posicao % 8)
    return replace(quadro, dados=bytes(dados))


def _dono_do_fisico(topologia, fisico):
    for interface in topologia.interfaces.values():
        if interface.fisico == fisico:
            return interface.dispositivo
    raise LookupError(f"nenhuma interface com o endereco fisico {fisico}")


def _intercalar(rajadas):
    """Um quadro de cada origem por vez, ate esgotar todas as rajadas."""
    return [
        item
        for grupo in itertools.zip_longest(*rajadas)
        for item in grupo
        if item is not None
    ]


# ----------------------------------------------------------------------
# Simulacao
# ----------------------------------------------------------------------

class Simulacao:
    """Uma execucao de um cenario sobre uma topologia.

    As falhas de enlace valem so para esta execucao: a simulacao trabalha
    sobre uma copia rasa da topologia recebida, com o proprio conjunto de
    enlaces derrubados.
    """

    def __init__(self, topologia, cenario):
        self.cenario = cenario
        self.topologia = copy.copy(topologia)
        self.topologia.enlaces_derrubados = set()
        derrubado = cenario.falhas.enlace_derrubado
        if derrubado and not self.topologia.derrubar(*derrubado):
            raise ValueError(f"enlace inexistente: {derrubado[0]}-{derrubado[1]}")

        self.registro = Registro()
        self.transmissoes = []
        self.entregas = []
        # A PDU descrita pelo ultimo evento devolvido por passo().
        self.unidade = None

        self._passos = itertools.count(1)
        self._contadores = {
            "passos": self._passos,
            # Um contador por mensagem, e nao um contador global: C5 reinicia
            # a numeracao dos quadros a cada mensagem (ver ContadorDeQuadros).
            "quadros": ContadorDeQuadros(),
            "sessoes": itertools.count(1),
        }
        self._dispositivos = {}
        self._bit_ja_invertido = False

        # O proximo passo fica sempre calculado, para que terminou seja exato
        # logo apos o ultimo evento, e nao so na chamada seguinte.
        self._andamento = self._percorrer()
        self._proximo = next(self._andamento, None)

    # ------------------------------------------------------------------
    # Controle de execucao
    # ------------------------------------------------------------------

    @property
    def terminou(self):
        return self._proximo is None

    def passo(self):
        """Avanca um evento e o devolve; None quando nao ha mais nenhum."""
        if self._proximo is None:
            return None
        evento, self.unidade = self._proximo
        self._proximo = next(self._andamento, None)
        self.registro.registrar([evento])
        return evento

    def executar(self):
        """Executa o que falta e devolve todos os eventos da execucao."""
        while self.passo() is not None:
            pass
        return self.eventos

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    @property
    def eventos(self):
        return self.registro.eventos

    @property
    def quadros(self):
        return [t.quadro for t in self.transmissoes]

    def dispositivo(self, nome):
        if nome not in self._dispositivos:
            self._dispositivos[nome] = criar_dispositivo(
                nome, self.topologia, **self._contadores,
            )
        return self._dispositivos[nome]

    def resumo(self):
        mensagem = sum(len(f.mensagem.encode("utf-8")) for f in self.cenario.fluxos)
        uteis = sum(len(e.mensagem.encode("utf-8")) for e in self.entregas)
        transmitidos = sum(q.tamanho for q in self.quadros)
        eficiencia = uteis / transmitidos if transmitidos else 0.0
        return Resumo(
            quadros=len(self.transmissoes),
            octetos_da_mensagem=mensagem,
            octetos_uteis=uteis,
            octetos_transmitidos=transmitidos,
            eficiencia=eficiencia,
            sobrecarga=1 - eficiencia,
        )

    # ------------------------------------------------------------------
    # Percurso
    # ------------------------------------------------------------------

    def _percorrer(self):
        """Gera os passos (evento, unidade) da execucao, na ordem em que ocorrem."""
        rajadas = []
        for fluxo in self.cenario.fluxos:
            origem = self.dispositivo(fluxo.origem)
            self.dispositivo(fluxo.destino).escutar(fluxo.portas[1], fluxo.processos[1])
            quadros, passos = origem.enviar(
                fluxo.mensagem, self._endereco_de_destino(fluxo),
                fluxo.portas, fluxo.processos[0],
            )
            yield from passos
            itens, passos = self._transmitir(origem.nome, quadros)
            yield from passos
            rajadas.append(itens)

        fila = deque(_intercalar(rajadas))
        while fila:
            quadro, para = fila.popleft()
            dispositivo = self.dispositivo(para)
            entregues, seguintes, passos = dispositivo.receber(quadro)
            yield from passos
            self.entregas.extend(
                Entrega(para, dispositivo.contexto.processo, u.sessao,
                        u.portas, u.logicos, u.dados)
                for u in entregues
            )
            itens, passos = self._transmitir(para, seguintes)
            yield from passos
            fila.extend(itens)

    def _endereco_de_destino(self, fluxo):
        inalcancavel = self.cenario.falhas.destino_inalcancavel
        if inalcancavel:
            return inalcancavel
        return self.topologia.interface_de(fluxo.destino).logico

    def _transmitir(self, de, quadros):
        """Poe no meio os quadros que sairam da camada 1 de um dispositivo.

        Devolve os itens (quadro, receptor) a enfileirar e os passos gerados
        pelo proprio meio, que so existem quando o enlace esta derrubado.
        """
        itens, passos = [], []
        for quadro in quadros:
            para = _dono_do_fisico(self.topologia, quadro.fisicos[1])
            self.transmissoes.append(Transmissao(de, para, quadro))

            if self._enlace_fora(de, para):
                evento = Evento(
                    passo=next(self._passos), dispositivo=de, camada=1,
                    acao="DESCARTA",
                    descricao=f"enlace {de}-{para} fora de servico; pacote "
                              f"{quadro.id_pacote}, quadro {quadro.numero_quadro} perdido",
                    tamanho=quadro.tamanho,
                )
                passos.append((evento, quadro))
                continue

            if self._inverte_bit_em(de, para):
                quadro = self.corromper(quadro)
            itens.append((quadro, para))
        return itens, passos

    def corromper(self, quadro):
        """O que o ruido faz com o quadro no enlace escolhido em Falhas."""
        return inverter_bit(quadro, self.cenario.falhas.posicao_do_bit)

    def _inverte_bit_em(self, de, para):
        """Informa se o quadro deste enlace e o que recebe o erro de bit.

        So o primeiro quadro que atravessa o enlace escolhido e corrompido:
        a falha e um erro de bit, e nao um enlace permanentemente ruidoso.
        """
        enlace = self.cenario.falhas.bit_invertido
        if self._bit_ja_invertido or not enlace or {de, para} != set(enlace):
            return False
        self._bit_ja_invertido = True
        return True

    def _enlace_fora(self, a, b):
        return any(
            {e.a.split(":")[0], e.b.split(":")[0]} == {a, b}
            and not self.topologia.ativo(e)
            for e in self.topologia.enlaces
        )


# ----------------------------------------------------------------------
# Cenarios de validacao (secao 4 da especificacao)
# ----------------------------------------------------------------------

# Todos usam a mensagem de referencia de 42 octetos, exceto E7 (100).
MENSAGEM_E1 = "Ola H2, aqui e o H1 testando a pilha OSI!!"
MENSAGEM_E2 = "Ola H4, aqui e o H1 testando a pilha OSI!!"
MENSAGEM_E3_H2 = "Ola H4, aqui e o H2 testando a pilha OSI!!"
MENSAGEM_E5 = "H1 envia a 10.0.9.10, fora da topologia!!!"
MENSAGEM_E7 = ("Ola H4, aqui e o H1 com uma mensagem longa: passa do limiar "
               "e a camada 4 a divide em tres segmentos.")

NAVEGADOR_E_SERVIDOR = ("navegador", "servidorWeb")

# O caso central: navegador, porta 5210, em H1, para servidorWeb, porta 443,
# em H4. E4, E5 e E6 sao este mesmo envio com uma falha injetada.
FLUXO_CENTRAL = Fluxo("H1", "H4", NAVEGADOR_E_SERVIDOR, (5210, 443), MENSAGEM_E2)

def gerar_registros_dos_cenarios(topologia, pasta=None):
    """Regera registros/registro_E1.txt a registro_E7.txt; devolve o que gravou.

    Existe para que os registros entregues nunca fiquem defasados do codigo:
    em vez de salvos um a um e a mao, os sete saem de uma execucao limpa de
    cada cenario, no formato oficial de R8. A pasta fica ao lado do programa,
    e nunca na pasta temporaria do empacotador (R10).

    Devolve uma lista de (codigo, caminho, numero de eventos).
    """
    destino = pasta or caminho_de(PASTA_DOS_REGISTROS)
    os.makedirs(destino, exist_ok=True)
    gravados = []
    for codigo, cenario in CENARIOS.items():
        sim = Simulacao(topologia, cenario)
        sim.executar()
        caminho = os.path.join(destino, f"registro_{codigo}.txt")
        sim.registro.salvar_em_arquivo(caminho)
        gravados.append((codigo, caminho, len(sim.eventos)))
    return gravados


CENARIOS = {c.codigo: c for c in (
    Cenario("E1", "Entrega direta", (
        Fluxo("H1", "H2", NAVEGADOR_E_SERVIDOR, (5210, 443), MENSAGEM_E1),
    )),
    Cenario("E2", "Entrega indireta", (FLUXO_CENTRAL,)),
    Cenario("E3", "Demultiplexacao", (
        FLUXO_CENTRAL,
        Fluxo("H2", "H4", NAVEGADOR_E_SERVIDOR, (6120, 443), MENSAGEM_E3_H2),
    )),
    Cenario("E4", "Falha de enlace", (FLUXO_CENTRAL,),
            Falhas(enlace_derrubado=("R1", "R4"))),
    Cenario("E5", "Destino inalcancavel", (replace(FLUXO_CENTRAL, mensagem=MENSAGEM_E5),),
            Falhas(destino_inalcancavel="10.0.9.10")),
    Cenario("E6", "Erro de transmissao", (FLUXO_CENTRAL,),
            Falhas(bit_invertido=("R4", "R3"))),
    Cenario("E7", "Mensagem longa", (replace(FLUXO_CENTRAL, mensagem=MENSAGEM_E7),)),
)}
