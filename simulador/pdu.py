"""Unidade de dados de protocolo (PDU) e cabecalhos.

Este modulo concentra a estrutura que circula entre as camadas. A unidade de
dados e imutavel: cada camada devolve um objeto novo em vez de alterar o que
recebeu. Essa escolha implementa estruturalmente a restricao R2 do enunciado,
segundo a qual o quadro recebido em um salto e descartado e um quadro novo e
construido na saida.

O acesso aos cabecalhos e controlado: uma camada so consegue ler o cabecalho
mais externo da unidade, que e exatamente aquele inserido pela sua camada par.
E o que implementa as restricoes R1 (o roteador nao le o que nao lhe pertence)
e R5 (cada camada conversa com a sua par).
"""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Tuple

# Convencoes de tamanho fixadas pelo enunciado (secao "Custo do empilhamento")


TAMANHO_CABECALHO: Dict[int, int] = {5: 4, 4: 8, 3: 20, 2: 14}
TAMANHO_FINALIZADOR = 4

#: Nome da unidade de dados de cada camada (Tabela 2 do enunciado).
NOME_UNIDADE: Dict[int, str] = {
    7: "Mensagem",
    6: "Mensagem",
    5: "Mensagem",
    4: "Segmento",
    3: "Pacote",
    2: "Quadro",
    1: "Bits",
}


class ViolacaoDeCamadaError(RuntimeError):
    """Tentativa de ler um cabecalho que nao pertence a camada solicitante."""


class ErroDeSegmentacaoError(ValueError):
    """Parametros de segmentacao incompativeis com os cabecalhos ja inseridos."""


def abreviar_fisico(endereco: str) -> str:
    """Reduz um endereco fisico ao formato usado no registro do enunciado.

    ``AA:00:00:00:01:0A`` vira ``AA:...:01:0A``.
    """
    partes = endereco.split(":")
    if len(partes) != 6:
        return endereco
    return f"{partes[0]}:...:{partes[4]}:{partes[5]}"


@dataclass(frozen=True)
class Cabecalho:
    """Cabecalho inserido por uma camada.

    :param camada: numero da camada que o inseriu (e a unica que pode le-lo).
    :param campos: conteudo logico do cabecalho, usado na exibicao.
    :param tamanho: tamanho em octetos, fixado pela convencao do enunciado.
    :param finalizador: verdadeiro para o finalizador da camada 2.
    """

    camada: int
    campos: Dict[str, Any]
    tamanho: int
    finalizador: bool = False

    @property
    def rotulo(self) -> str:
        return f"T{self.camada}" if self.finalizador else f"H{self.camada}"

    def para_octetos(self) -> bytes:
        """Serializa o cabecalho em exatamente ``tamanho`` octetos.

        A serializacao e deterministica para que a verificacao de erro da
        camada 2 seja reproduzivel entre execucoes.
        """
        bruto = json.dumps(self.campos, sort_keys=True, ensure_ascii=True).encode(
            "utf-8"
        )
        if len(bruto) >= self.tamanho:
            return bruto[: self.tamanho]
        return bruto + b"\x00" * (self.tamanho - len(bruto))

    def resumo(self) -> str:
        return ", ".join(f"{chave}={valor}" for chave, valor in self.campos.items())


@dataclass(frozen=True)
class UnidadeDados:
    """Unidade de dados que circula entre as camadas.

    :param dados: conteudo transportado, ja em octetos.
    :param cabecalhos: cabecalhos acrescentados, do mais interno (indice 0) ao
        mais externo (ultimo indice). Apenas o ultimo pode ser lido.
    :param finalizador: finalizador da camada 2, quando presente.
    :param unidade: nome da unidade corrente (Mensagem, Segmento, Pacote, ...).
    :param identificador: rotulo de exibicao, como ``Q3`` ou ``S2/3``.
    :param contexto: primitiva de servico trocada entre camadas adjacentes.
        Nao e transmitido pela rede e nao entra no calculo de tamanho.
    """

    dados: bytes = b""
    cabecalhos: Tuple[Cabecalho, ...] = ()
    finalizador: Optional[Cabecalho] = None
    unidade: str = "Mensagem"
    identificador: str = ""
    contexto: Dict[str, Any] = field(default_factory=dict, compare=False)

    # -- tamanho -----------------------------------------------------------

    @property
    def tamanho(self) -> int:
        """Tamanho corrente em octetos, incluindo cabecalhos e finalizador."""
        total = len(self.dados) + sum(c.tamanho for c in self.cabecalhos)
        if self.finalizador is not None:
            total += self.finalizador.tamanho
        return total

    @property
    def tamanho_bits(self) -> int:
        return self.tamanho * 8

    @property
    def sobrecarga_superior(self) -> int:
        """Octetos de cabecalho ja presentes, usados no calculo da segmentacao."""
        return sum(c.tamanho for c in self.cabecalhos)

    # -- manipulacao de cabecalhos ----------------------------------------

    def acrescentar_cabecalho(
        self, cabecalho: Cabecalho, unidade: str, identificador: Optional[str] = None
    ) -> "UnidadeDados":
        """Devolve uma unidade nova com o cabecalho acrescentado."""
        return replace(
            self,
            cabecalhos=self.cabecalhos + (cabecalho,),
            unidade=unidade,
            identificador=(
                self.identificador if identificador is None else identificador
            ),
        )

    def ler_cabecalho(self, camada_solicitante: int) -> Cabecalho:
        """Le o cabecalho mais externo, desde que pertenca a camada solicitante.

        :raises ViolacaoDeCamadaError: se a camada tentar ler um cabecalho que
            nao e o seu. E este guarda que impede o roteador de alcancar as
            camadas 4 a 7 (restricao R1).
        """
        if not self.cabecalhos:
            raise ViolacaoDeCamadaError(
                f"a camada {camada_solicitante} tentou ler um cabecalho de uma "
                f"unidade que nao possui cabecalhos"
            )
        externo = self.cabecalhos[-1]
        if externo.camada != camada_solicitante:
            raise ViolacaoDeCamadaError(
                f"a camada {camada_solicitante} tentou ler o cabecalho da camada "
                f"{externo.camada}; cada camada so interpreta o cabecalho inserido "
                f"pela sua camada par"
            )
        return externo

    def remover_cabecalho(
        self, camada_solicitante: int, unidade: str
    ) -> "UnidadeDados":
        """Remove o cabecalho da camada solicitante e devolve a unidade nova."""
        self.ler_cabecalho(camada_solicitante)
        return replace(self, cabecalhos=self.cabecalhos[:-1], unidade=unidade)

    def acrescentar_finalizador(self, finalizador: Cabecalho) -> "UnidadeDados":
        return replace(self, finalizador=finalizador)

    def remover_finalizador(self) -> "UnidadeDados":
        return replace(self, finalizador=None)

    # -- contexto entre camadas adjacentes ---------------------------------

    def com_contexto(self, **valores: Any) -> "UnidadeDados":
        """Anexa parametros da primitiva de servico para a camada adjacente."""
        novo = dict(self.contexto)
        novo.update(valores)
        return replace(self, contexto=novo)

    def com_dados(self, dados: bytes) -> "UnidadeDados":
        return replace(self, dados=dados)

    def com_identificador(self, identificador: str) -> "UnidadeDados":
        return replace(self, identificador=identificador)

    # -- serializacao e verificacao de erro --------------------------------

    def serializar(self) -> bytes:
        """Sequencia de octetos efetivamente colocada no meio fisico."""
        partes = [c.para_octetos() for c in reversed(self.cabecalhos)]
        partes.append(self.dados)
        if self.finalizador is not None:
            partes.append(self.finalizador.para_octetos())
        return b"".join(partes)

    def conteudo_protegido(self) -> bytes:
        """Octetos cobertos pela verificacao de erro (tudo menos o finalizador)."""
        partes = [c.para_octetos() for c in reversed(self.cabecalhos)]
        partes.append(self.dados)
        return b"".join(partes)

    def verificacao(self) -> int:
        """Verificacao de erro da camada 2, calculada sobre o quadro."""
        return zlib.crc32(self.conteudo_protegido()) & 0xFFFFFFFF

    def para_bits(self) -> str:
        """Representacao em bits usada pela camada fisica (apenas exibicao)."""
        return "".join(f"{octeto:08b}" for octeto in self.serializar())

    # -- exibicao ----------------------------------------------------------

    def blocos(self) -> list:
        """Descreve a unidade como blocos, para o desenho exigido em V3.

        Os cabecalhos aparecem a esquerda dos dados, do mais externo para o
        mais interno, e o finalizador da camada 2 a direita.
        """
        blocos = [
            {
                "rotulo": c.rotulo,
                "tamanho": c.tamanho,
                "tipo": "cabecalho",
                "camada": c.camada,
                "detalhe": c.resumo(),
            }
            for c in reversed(self.cabecalhos)
        ]
        blocos.append(
            {
                "rotulo": "Dados",
                "tamanho": len(self.dados),
                "tipo": "dados",
                "camada": 0,
                "detalhe": f"{len(self.dados)} octetos de carga util",
            }
        )
        if self.finalizador is not None:
            blocos.append(
                {
                    "rotulo": self.finalizador.rotulo,
                    "tamanho": self.finalizador.tamanho,
                    "tipo": "finalizador",
                    "camada": self.finalizador.camada,
                    "detalhe": self.finalizador.resumo(),
                }
            )
        return blocos


def dividir_carga(unidade: UnidadeDados, carga_por_segmento: int) -> list:
    """Divide os dados de uma unidade em fatias de segmento.

    A primeira fatia acomoda os cabecalhos ja presentes (o cabecalho de sessao,
    na pratica), porque a convencao adotada e que esse cabecalho entra uma
    unica vez na conta, e nao em cada segmento. As fatias seguintes levam
    apenas dados.

    :returns: lista de ``bytes`` na ordem original.
    """
    sobrecarga = unidade.sobrecarga_superior
    if sobrecarga >= carga_por_segmento:
        raise ErroDeSegmentacaoError(
            f"carga por segmento ({carga_por_segmento} octetos) nao acomoda os "
            f"{sobrecarga} octetos de cabecalho ja presentes na unidade"
        )
    dados = unidade.dados
    fatias = [dados[: carga_por_segmento - sobrecarga]]
    restante = dados[carga_por_segmento - sobrecarga :]
    for inicio in range(0, len(restante), carga_por_segmento):
        fatias.append(restante[inicio : inicio + carga_por_segmento])
    return [fatia for fatia in fatias if fatia] or [b""]
