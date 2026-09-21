"""Fixtures compartilhadas pelos testes."""

from __future__ import annotations

import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from simulador.rede import Topologia  # noqa: E402


def caminho_topologia() -> str:
    """Caminho do arquivo de topologia de referencia."""
    return os.path.join(RAIZ, "topologia.json")


@pytest.fixture
def topologia() -> Topologia:
    """Topologia de referencia da Figura 1 do enunciado."""
    return Topologia.carregar(caminho_topologia())
