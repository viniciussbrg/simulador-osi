"""Registro de eventos e quadro numerico da comunicacao.

O registro e a saida textual do nucleo da simulacao. Cada linha corresponde a
uma acao de uma camada de um dispositivo, no formato de cinco campos separados
por barra vertical definido no enunciado, encerrada pelo tamanho corrente da
unidade de dados em octetos.

A interface grafica consome a lista de eventos produzida aqui e nao conhece a
implementacao das camadas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Largura reservada ao corpo da linha antes da coluna de tamanho.
LARGURA_CORPO = 96


@dataclass(frozen=True)
class Evento:
    """Uma linha do registro, com tudo o que a interface precisa desenhar."""

    passo: int
    dispositivo: str
    camada: int
    acao: str
    descricao: str
    tamanho: int
    unidade: str
    identificador: str = ""
    blocos: Tuple[Dict[str, Any], ...] = ()
    logicos: Optional[Tuple[str, str]] = None
    fisicos: Optional[Tuple[str, str]] = None
    portas: Optional[Tuple[int, int]] = None
    processos: Optional[Tuple[str, str]] = None
    enlace: Optional[str] = None
    caminho: Tuple[Tuple[str, str], ...] = ()
    fluxo: str = ""
    descarte: bool = False

    @property
    def linha(self) -> str:
        """Linha formatada do registro, no formato da Secao 5.1 do enunciado."""
        corpo = (
            f"{self.passo:03d} | {self.dispositivo:<2} | L{self.camada} | "
            f"{self.acao:<12} | {self.descricao}"
        )
        return f"{corpo:<{LARGURA_CORPO}}{self.tamanho:>4} B"

    def __str__(self) -> str:  # pragma: no cover - conveniencia
        return self.linha


@dataclass
class ResumoComunicacao:
    """Quadro numerico exigido na secao 'Custo do empilhamento'."""

    cenario: str
    titulo: str
    octetos_uteis: int = 0
    octetos_transmitidos: int = 0
    quadros: int = 0
    enlaces: int = 0
    entregue: bool = False
    observacao: str = ""
    detalhes_por_enlace: Dict[str, int] = field(default_factory=dict)

    @property
    def eficiencia(self) -> float:
        """Fracao da transmissao ocupada por dados uteis."""
        if self.octetos_transmitidos == 0:
            return 0.0
        return self.octetos_uteis / self.octetos_transmitidos

    @property
    def sobrecarga(self) -> float:
        return 1.0 - self.eficiencia

    @property
    def eficiencia_percentual(self) -> str:
        return f"{self.eficiencia * 100:.1f}%"

    @property
    def sobrecarga_percentual(self) -> str:
        return f"{self.sobrecarga * 100:.1f}%"

    def como_linhas(self) -> List[str]:
        linhas = [
            f"Cenário ................ {self.cenario} - {self.titulo}",
            f"Octetos úteis .......... {self.octetos_uteis}",
            f"Octetos transmitidos ... {self.octetos_transmitidos}",
            f"Quadros transmitidos ... {self.quadros}",
            f"Enlaces percorridos .... {self.enlaces}",
            f"Eficiência ............. {self.eficiencia_percentual}",
            f"Sobrecarga ............. {self.sobrecarga_percentual}",
            f"Mensagem entregue ...... {'sim' if self.entregue else 'não'}",
        ]
        if self.observacao:
            linhas.append(f"Observação ............. {self.observacao}")
        return linhas


def montar_texto(
    eventos: Sequence[Evento],
    resumo: Optional[ResumoComunicacao] = None,
    titulo: str = "Simulador do modelo OSI",
) -> str:
    """Monta o texto completo do registro, pronto para ser gravado."""
    partes = [
        f"{titulo}",
        f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        "",
        # Os rotulos sao abreviados para alinhar exatamente com os campos das
        # linhas: 3 caracteres de passo, 2 de dispositivo e 2 de camada.
        f"{'PAS':<3} | {'EQ':<2} | {'CA'} | {'AÇÃO':<12} | DESCRIÇÃO",
        "-" * (LARGURA_CORPO + 6),
    ]
    partes.extend(evento.linha for evento in eventos)
    if resumo is not None:
        partes.append("-" * (LARGURA_CORPO + 6))
        partes.append("Custo do empilhamento")
        partes.extend(resumo.como_linhas())
    return "\n".join(partes) + "\n"


def salvar(
    caminho: str,
    eventos: Sequence[Evento],
    resumo: Optional[ResumoComunicacao] = None,
    titulo: str = "Simulador do modelo OSI",
) -> str:
    """Grava o registro completo em arquivo de texto.

    :returns: o caminho absoluto do arquivo gravado.
    :raises OSError: quando o arquivo nao pode ser escrito.
    """
    texto = montar_texto(eventos, resumo, titulo)
    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta and not os.path.isdir(pasta):
        os.makedirs(pasta, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    return os.path.abspath(caminho)
