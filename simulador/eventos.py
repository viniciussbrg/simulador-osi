# -*- coding: utf-8 -*-
"""Evento de registro e colecao de eventos.

Cada passo produz um evento com dispositivo, camada, acao e tamanho corrente
da unidade. E essa lista que a interface consome para desenhar a tela.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from .pdu import UnidadeDados

# Largura reservada para a descricao antes do tamanho, para alinhar as linhas.
_LARGURA_DESCRICAO = 62


@dataclass
class Evento:
    """Uma acao de uma camada de um dispositivo."""

    passo: int
    dispositivo: str          # H1, R1, ...
    camada: str               # L1 a L7
    acao: str                 # GERA, ROTEIA, ENQUADRA, DESCARTA, ...
    descricao: str
    tamanho: int              # octetos da unidade neste ponto
    unidade: UnidadeDados | None = None
    enlace: tuple[str, str] | None = None
    caminho: list[str] = field(default_factory=list)
    estado: str = "normal"    # normal, sucesso ou erro; define a cor na tela
    metadados: dict[str, Any] = field(default_factory=dict)

    @property
    def numero_camada(self) -> int:
        """Devolve a camada como inteiro (L3 -> 3)."""
        return int(self.camada[1:]) if self.camada[1:].isdigit() else 0

    @property
    def linha(self) -> str:
        """Linha formatada no padrao exigido pela Secao 5.1 do enunciado."""
        prefixo = (
            f"{self.passo:03d} | "
            f"{self.dispositivo:<2s} | "
            f"{self.camada} | "
            f"{self.acao:<12s} | "
            f"{self.descricao}"
        )
        espacos = max(1, _LARGURA_DESCRICAO - len(self.descricao))
        return f"{prefixo}{' ' * espacos}{self.tamanho} B"


class RegistroEventos:
    """Colecao ordenada de eventos produzidos por uma simulacao."""

    def __init__(self) -> None:
        self._eventos: list[Evento] = []

    # escrita

    def adicionar(self, evento: Evento) -> None:
        self._eventos.append(evento)

    def estender(self, eventos: list[Evento]) -> None:
        self._eventos.extend(eventos)

    def limpar(self) -> None:
        self._eventos.clear()

    def renumerar(self) -> None:
        """Renumera os passos de 1 em diante, apos eventuais intercalacoes."""
        for indice, evento in enumerate(self._eventos, start=1):
            evento.passo = indice

    # leitura

    def linhas(self) -> list[str]:
        return [evento.linha for evento in self._eventos]

    def texto(self) -> str:
        return "\n".join(self.linhas())

    def salvar(self, caminho: str, cabecalho: list[str] | None = None) -> None:
        """Grava o registro completo em arquivo de texto."""
        with open(caminho, "w", encoding="utf-8") as arquivo:
            for linha in cabecalho or []:
                arquivo.write(f"# {linha}\n")
            if cabecalho:
                arquivo.write("#\n")
            for linha in self.linhas():
                arquivo.write(linha + "\n")

    # iteracao

    def __iter__(self) -> Iterator[Evento]:
        return iter(self._eventos)

    def __len__(self) -> int:
        return len(self._eventos)

    def __getitem__(self, indice: int) -> Evento:
        return self._eventos[indice]

    def __repr__(self) -> str:  # pragma: no cover
        return f"RegistroEventos({len(self._eventos)} eventos)"
