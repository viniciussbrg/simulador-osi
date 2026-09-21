# -*- coding: utf-8 -*-
"""Simulador do Modelo OSI.

Modulos, na ordem em que os dados os atravessam:

    pdu.py           unidade de dados e cabecalhos
    camadas.py       as sete classes de camada
    dispositivos.py  computador (7 camadas) e roteador (3 camadas)
    rede.py          enlaces, topologia e tabelas de encaminhamento
    eventos.py       registro de eventos consumido pela interface
    motor.py         relogio e laco de simulacao
    cenarios.py      os sete casos obrigatorios de validacao
    relatorio.py     exportacao do resultado em HTML
    visual.py        interface grafica
    config.py        convencoes de simulacao
"""

from .config import AUTORIA, INTEGRANTES, NOME_PROGRAMA, VERSAO

__all__ = ["AUTORIA", "INTEGRANTES", "NOME_PROGRAMA", "VERSAO"]
