"""Simulador do modelo OSI em uma rede com multiplos roteadores.

O pacote esta dividido segundo a mesma separacao de responsabilidades que o
modelo OSI propoe para a rede:

``pdu``
    a unidade de dados e os cabecalhos;
``camadas``
    as sete classes de camada;
``dispositivos``
    computador, roteador e a pilha de cada um;
``rede``
    topologia, enlaces, custos e tabelas de encaminhamento;
``cenarios``
    os sete casos obrigatorios;
``motor``
    o laco da simulacao, que produz a lista de eventos;
``registro``
    o formato do registro de eventos e o quadro de eficiencia;
``visual``
    a interface grafica, que apenas le os eventos produzidos pelo motor.
"""

from .cenarios import Cenario, Fluxo, cenarios_padrao, por_codigo
from .motor import ResultadoSimulacao, Simulacao, comparar_eficiencias, executar_cenario
from .rede import ErroDeTopologiaError, Topologia
from .registro import Evento, ResumoComunicacao

__all__ = [
    "Cenario",
    "ErroDeTopologiaError",
    "Evento",
    "Fluxo",
    "ResultadoSimulacao",
    "ResumoComunicacao",
    "Simulacao",
    "Topologia",
    "cenarios_padrao",
    "comparar_eficiencias",
    "executar_cenario",
    "por_codigo",
]

__version__ = "1.0.0"
