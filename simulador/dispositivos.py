# -*- coding: utf-8 -*-
"""Computador (sete camadas) e roteador (tres camadas).

O roteador nao instancia as camadas 4 a 7, entao nao existe nele nenhum
atributo ou metodo capaz de ler uma porta ou o nome de um processo.
"""

from __future__ import annotations

from typing import Any

from .camadas import (
    CamadaAplicacao,
    CamadaApresentacao,
    CamadaEnlace,
    CamadaFisica,
    CamadaRede,
    CamadaSessao,
    CamadaTransporte,
)
from .eventos import Evento
from .pdu import UnidadeDados


class Computador:
    """Dispositivo com as sete camadas do modelo OSI."""

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.aplicacao = CamadaAplicacao()
        self.apresentacao = CamadaApresentacao()
        self.sessao = CamadaSessao()
        self.transporte = CamadaTransporte()
        self.rede = CamadaRede()
        self.enlace = CamadaEnlace()
        self.fisica = CamadaFisica()

    # envio

    def preparar_envio(
        self, texto: str, contexto: dict[str, Any]
    ) -> tuple[list[tuple[UnidadeDados, list[Evento]]], list[Evento]]:
        """Percorre as camadas 7 a 4 e devolve os segmentos a transmitir.

        As camadas 7, 6 e 5 sao percorridas uma unica vez, porque a mensagem e
        uma so; os eventos delas voltam separados, na segunda posicao. A
        camada 4 pode produzir varios segmentos, e cada um leva consigo o
        proprio evento de segmentacao.
        """
        contexto["dispositivo"] = self.nome
        comuns: list[Evento] = []

        unidade, eventos = self.aplicacao.desce(texto, contexto)
        comuns.extend(eventos)

        unidade, eventos = self.apresentacao.desce(unidade, contexto)
        comuns.extend(eventos)

        unidade, eventos = self.sessao.desce(unidade, contexto)
        comuns.extend(eventos)

        return self.transporte.desce(unidade, contexto), comuns

    def despachar(self, segmento: UnidadeDados,
                  contexto: dict[str, Any]) -> tuple[UnidadeDados | None, list[Evento]]:
        """Desce um segmento pelas camadas 3, 2 e 1 e o poe no enlace.

        O metodo e chamado uma vez por segmento, imediatamente antes de o
        segmento entrar na rede: assim cada um vira um quadro independente,
        numerado na ordem em que ocupa um enlace.

        Devolve `None` quando a camada 3 nao encontra rota; nesse caso os
        eventos devolvidos ja contem a linha de descarte.
        """
        contexto["dispositivo"] = self.nome
        eventos_total: list[Evento] = []

        pacote, eventos = self.rede.desce(segmento, contexto)
        eventos_total.extend(eventos)
        if contexto.get("saida") is None:
            return None, eventos_total

        quadro, eventos = self.enlace.desce(pacote, contexto)
        eventos_total.extend(eventos)

        bits, eventos = self.fisica.desce(quadro, contexto)
        eventos_total.extend(eventos)

        return bits, eventos_total

    # recepcao

    def receber(self, unidade: UnidadeDados,
                contexto: dict[str, Any]) -> tuple[UnidadeDados | None, list[Evento]]:
        """Sobe a pilha de 1 a 7.

        Devolve `None` quando a unidade nao chega ao topo: quadro descartado
        pela verificacao de erro, pacote endereçado a outro dispositivo ou
        segmento retido pela camada 4 a espera dos demais.
        """
        contexto["dispositivo"] = self.nome
        eventos_total: list[Evento] = []

        unidade, eventos = self.fisica.sobe(unidade, contexto)
        eventos_total.extend(eventos)

        pacote, eventos = self.enlace.sobe(unidade, contexto)
        eventos_total.extend(eventos)
        if pacote is None:
            return None, eventos_total

        segmento, eventos = self.rede.sobe(pacote, contexto)
        eventos_total.extend(eventos)
        if segmento is None:
            return None, eventos_total

        mensagem, eventos = self.transporte.sobe(segmento, contexto)
        eventos_total.extend(eventos)
        if mensagem is None:
            return None, eventos_total

        mensagem, eventos = self.sessao.sobe(mensagem, contexto)
        eventos_total.extend(eventos)

        mensagem, eventos = self.apresentacao.sobe(mensagem, contexto)
        eventos_total.extend(eventos)

        mensagem, eventos = self.aplicacao.sobe(mensagem, contexto)
        eventos_total.extend(eventos)

        return mensagem, eventos_total

    def reiniciar(self) -> None:
        """Esvazia o buffer de remontagem entre duas execucoes."""
        self.transporte.limpar()


class Roteador:
    """Dispositivo com apenas as tres primeiras camadas.

    A unidade sobe ate a camada 3, onde a rota e decidida, e desce de novo
    pela camada 2. O quadro que chegou e descartado e um quadro inteiramente
    novo, com outro par de enderecos fisicos e outra verificacao de erro, e
    construido na saida.
    """

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.rede = CamadaRede()
        self.enlace = CamadaEnlace()
        self.fisica = CamadaFisica()

    def encaminhar(self, unidade: UnidadeDados,
                   contexto: dict[str, Any]) -> tuple[UnidadeDados | None, list[Evento]]:
        """Sobe L1-L2-L3, decide a rota e desce L2-L1 com um quadro novo."""
        contexto["dispositivo"] = self.nome
        eventos_total: list[Evento] = []

        unidade, eventos = self.fisica.sobe(unidade, contexto)
        eventos_total.extend(eventos)

        pacote, eventos = self.enlace.sobe(unidade, contexto)
        eventos_total.extend(eventos)
        if pacote is None:
            return None, eventos_total

        pacote, eventos = self.rede.encaminha(pacote, contexto)
        eventos_total.extend(eventos)
        if contexto.get("saida") is None:
            return None, eventos_total

        quadro, eventos = self.enlace.desce(pacote, contexto)
        eventos_total.extend(eventos)

        bits, eventos = self.fisica.desce(quadro, contexto)
        eventos_total.extend(eventos)

        return bits, eventos_total

    def reiniciar(self) -> None:
        """Mantido por simetria com `Computador`; o roteador nao guarda estado."""
        return None
