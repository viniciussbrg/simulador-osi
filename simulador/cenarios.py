# -*- coding: utf-8 -*-
"""Os sete cenarios de validacao.

O enunciado os chama de C1 a C7 e os criterios, de E1 a E7. O programa aceita
os dois nomes. Cada cenario e so um conjunto de parametros; quem executa e o
motor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import config
from .motor import Fluxo, Motor, ResultadoSimulacao
from .rede import Topologia

# Mensagem curta de referencia: exatamente 42 octetos.
# 42 + 4 (L5) + 8 (L4) + 20 (L3) + 14 + 4 (L2) = 92 octetos por quadro.
MENSAGEM_CURTA = "Requisicao HTTP/1.1 para o servidorWeb OSI"

# Mensagem longa de referencia: exatamente 100 octetos.
# 100 + 4 (L5) = 104 octetos, que a camada 4 divide em 40, 40 e 24 octetos.
MENSAGEM_LONGA = (
    "Mensagem longa de teste com exatamente cem octetos usada para validar "
    "a segmentacao da camada quatro"
)

IP_INALCANCAVEL = "10.0.9.10"


@dataclass
class Cenario:
    """Um caso de validacao selecionavel pela interface."""

    identificador: str            # "E1" ... "E7"
    alias: str                    # "C1" ... "C7"
    nome: str
    descricao: str
    montar: Callable[[Topologia], dict]
    conferencia: list[str] = field(default_factory=list)

    @property
    def rotulo(self) -> str:
        return f"{self.identificador}/{self.alias} - {self.nome}"


# Montagem dos cenarios


def _ip(topologia: Topologia, host: str) -> str:
    dispositivo = topologia.dispositivos.get(host)
    return dispositivo.ip_principal if dispositivo else ""


def _e1(topologia: Topologia) -> dict:
    return {
        "fluxos": [Fluxo(
            origem="H1", destino_ip=_ip(topologia, "H2"), texto=MENSAGEM_CURTA,
            processo_origem="navegador", processo_destino="servidorWeb",
        )],
        "observacao": ("H1 e H2 estao na Rede A. A camada 3 reconhece que o "
                       "destino compartilha o prefixo e entrega sem roteador."),
    }


def _e2(topologia: Topologia) -> dict:
    return {
        "fluxos": [Fluxo(
            origem="H1", destino_ip=_ip(topologia, "H4"), texto=MENSAGEM_CURTA,
            processo_origem="navegador", processo_destino="servidorWeb",
        )],
        "observacao": ("Caso central: tres roteadores, quatro quadros "
                       "independentes e um unico pacote."),
    }


def _e3(topologia: Topologia) -> dict:
    destino = _ip(topologia, "H4")
    return {
        "fluxos": [
            Fluxo(origem="H1", destino_ip=destino, texto=MENSAGEM_CURTA,
                  processo_origem="navegador", processo_destino="servidorWeb",
                  porta_origem=5210, porta_destino=443, rotulo="A"),
            Fluxo(origem="H2", destino_ip=destino, texto=MENSAGEM_CURTA,
                  processo_origem="navegador", processo_destino="servidorWeb",
                  porta_origem=5310, porta_destino=443, rotulo="B"),
        ],
        "observacao": ("Dois fluxos chegam a porta 443 de H4. A camada 4 os "
                       "separa pelas portas de origem 5210 e 5310."),
    }


def _e4(topologia: Topologia) -> dict:
    return {
        "fluxos": [Fluxo(
            origem="H1", destino_ip=_ip(topologia, "H4"), texto=MENSAGEM_CURTA,
            processo_origem="navegador", processo_destino="servidorWeb",
        )],
        "enlaces_derrubados": ["R1-R4"],
        "observacao": ("Com o enlace R1-R4 derrubado, a rota de menor custo "
                       "para a Rede C passa a ser R1-R2-R3, de custo 3."),
    }


def _e5(topologia: Topologia) -> dict:
    return {
        "fluxos": [Fluxo(
            origem="H1", destino_ip=IP_INALCANCAVEL, texto=MENSAGEM_CURTA,
            processo_origem="navegador", processo_destino="servidorWeb",
        )],
        "observacao": ("H1 entrega o pacote ao roteador padrao. R1 e o "
                       "primeiro a nao encontrar rota e descarta o pacote."),
    }


def _e6(topologia: Topologia) -> dict:
    return {
        "fluxos": [Fluxo(
            origem="H1", destino_ip=_ip(topologia, "H4"), texto=MENSAGEM_CURTA,
            processo_origem="navegador", processo_destino="servidorWeb",
        )],
        "enlace_com_erro": "R4-R3",
        "observacao": ("Um bit do quadro Q3 e alterado no enlace R4-R3. A "
                       "camada 2 de R3 descarta o quadro e nenhuma camada "
                       "superior de R3 e acionada."),
    }


def _e7(topologia: Topologia) -> dict:
    return {
        "fluxos": [Fluxo(
            origem="H1", destino_ip=_ip(topologia, "H4"), texto=MENSAGEM_LONGA,
            processo_origem="navegador", processo_destino="servidorWeb",
        )],
        "observacao": ("A mensagem de 100 octetos, somada aos 4 octetos de "
                       "sessao, rende tres segmentos de 40, 40 e 24 octetos."),
    }


CENARIOS: list[Cenario] = [
    Cenario("E1", "C1", "Entrega direta",
            "H1 envia para H2 na Rede A; um unico quadro, sem roteador.",
            _e1,
            ["1 quadro", "eficiencia 45,7%", "caminho H1 - H2"]),
    Cenario("E2", "C2", "Entrega indireta (caso central)",
            "H1:5210 envia 42 B para H4:443 por R1, R4 e R3.",
            _e2,
            ["4 quadros", "1 pacote", "eficiencia 11,4%",
             "caminho H1 - R1 - R4 - R3 - H4"]),
    Cenario("E3", "C3", "Demultiplexacao",
            "H1 e H2 enviam ao mesmo servidorWeb de H4, com portas de origem distintas.",
            _e3,
            ["8 quadros", "2 sessoes", "portas de origem 5210 e 5310"]),
    Cenario("E4", "C4", "Falha de enlace",
            "O enlace R1-R4 e derrubado; o caminho passa a ser por R2, custo 3.",
            _e4,
            ["4 quadros", "caminho H1 - R1 - R2 - R3 - H4", "custo 3"]),
    Cenario("E5", "C5", "Destino inalcancavel",
            f"H1 envia para {IP_INALCANCAVEL}; R1 descarta por ausencia de rota.",
            _e5,
            ["1 quadro", "descarte na camada 3 de R1", "mensagem nao entregue"]),
    Cenario("E6", "C6", "Erro de transmissao",
            "Um bit e alterado no enlace R4-R3; a camada 2 de R3 descarta o quadro.",
            _e6,
            ["3 quadros", "nenhuma linha de camada 3 em R3",
             "mensagem nao entregue"]),
    Cenario("E7", "C7", "Mensagem longa",
            "Mensagem de 100 B dividida em tres segmentos, remontados em ordem.",
            _e7,
            ["segmentos de 40, 40 e 24 B", "12 quadros", "eficiencia 10,3%"]),
]

POR_IDENTIFICADOR: dict[str, Cenario] = {}
for _cenario in CENARIOS:
    POR_IDENTIFICADOR[_cenario.identificador] = _cenario
    POR_IDENTIFICADOR[_cenario.alias] = _cenario


def obter(identificador: str) -> Cenario:
    """Devolve o cenario pelo identificador E1..E7 ou pelo alias C1..C7."""
    chave = identificador.strip().upper()
    if chave not in POR_IDENTIFICADOR:
        raise KeyError(f"cenario desconhecido: {identificador!r}")
    return POR_IDENTIFICADOR[chave]


def executar(topologia: Topologia, identificador: str,
             motor: Motor | None = None) -> ResultadoSimulacao:
    """Monta e executa um cenario de validacao sobre a topologia informada."""
    cenario = obter(identificador)
    parametros = cenario.montar(topologia)
    motor = motor or Motor(topologia)
    return motor.executar(
        parametros["fluxos"],
        enlaces_derrubados=parametros.get("enlaces_derrubados"),
        enlace_com_erro=parametros.get("enlace_com_erro", ""),
        observacao=parametros.get("observacao", ""),
    )


def comparativo_eficiencia(topologia: Topologia) -> dict[str, float]:
    """Eficiencia de E1 (um enlace) e de E2 (quatro enlaces), lado a lado.

    O enunciado pede que os dois valores sejam apresentados juntos, porque a
    comparacao e o que torna visivel o custo do empilhamento.
    """
    quadro = (len(MENSAGEM_CURTA.encode(config.CODIFICACAO))
              + config.TAMANHO_CABECALHO_SESSAO
              + config.TAMANHO_CABECALHO_TRANSPORTE
              + config.TAMANHO_CABECALHO_REDE
              + config.TAMANHO_CABECALHO_ENLACE
              + config.TAMANHO_FINALIZADOR_ENLACE)
    uteis = len(MENSAGEM_CURTA.encode(config.CODIFICACAO))
    return {
        "mensagem": uteis,
        "quadro": quadro,
        "E1_transmitido": quadro,
        "E1_eficiencia": uteis / quadro,
        "E2_transmitido": quadro * 4,
        "E2_eficiencia": uteis / (quadro * 4),
    }
