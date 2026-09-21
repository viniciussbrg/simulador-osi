"""Localizacao dos arquivos que acompanham o programa.

O enunciado proibe caminhos absolutos no codigo e exige que o arquivo de
topologia fique ao lado do executavel. Este modulo resolve os dois casos de
execucao: a partir do codigo-fonte e a partir do executavel gerado por
PyInstaller, em que ``sys.frozen`` esta definido.
"""

from __future__ import annotations

import os
import sys

#: Nome do arquivo de topologia procurado ao lado do programa.
ARQUIVO_TOPOLOGIA = "topologia.json"


def pasta_do_programa() -> str:
    """Pasta onde o programa foi aberto.

    Com o executavel gerado, e a pasta do proprio executavel; a partir do
    codigo-fonte, e a pasta que contem ``main.py``.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def caminho_ao_lado(nome: str) -> str:
    """Caminho de um arquivo que acompanha o programa."""
    return os.path.join(pasta_do_programa(), nome)


def topologia_padrao() -> str:
    """Caminho do arquivo de topologia distribuido com o programa."""
    return caminho_ao_lado(ARQUIVO_TOPOLOGIA)
