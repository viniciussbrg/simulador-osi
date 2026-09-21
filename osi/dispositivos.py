from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .camadas import (
    CamadaAplicacao, CamadaApresentacao, CamadaSessao, CamadaTransporte,
    CamadaRede, CamadaEnlace, CamadaFisica,
)


@dataclass(frozen=True)
class Interface:
    nome: str
    ip: str
    mac: str
    rede: str | None = None


class Computador:
    def __init__(self, nome: str, interfaces: Dict[str, Interface], posicao=None):
        self.nome = nome
        self.interfaces = interfaces
        self.posicao = posicao or [0, 0]
        self.camadas = {
            7: CamadaAplicacao(),
            6: CamadaApresentacao(),
            5: CamadaSessao(),
            4: CamadaTransporte(),
            3: CamadaRede(),
            2: CamadaEnlace(),
            1: CamadaFisica(),
        }


class Roteador:
    def __init__(self, nome: str, interfaces: Dict[str, Interface], posicao=None):
        self.nome = nome
        self.interfaces = interfaces
        self.posicao = posicao or [0, 0]
        self.camadas = {
            3: CamadaRede(),
            2: CamadaEnlace(),
            1: CamadaFisica(),
        }
