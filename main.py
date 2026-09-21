"""Ponto de entrada do simulador do modelo OSI.

Este e o arquivo que recebe o duplo clique. Ele nao exige argumentos de linha
de comando e mantem a janela aberta mesmo diante de um erro: qualquer falha e
apresentada em uma caixa de mensagem e, se nem isso for possivel, o programa
aguarda uma tecla antes de encerrar.
"""

from __future__ import annotations

import os
import sys
import traceback


def _relatar(titulo: str, mensagem: str) -> None:
    """Mostra o erro sem deixar a janela fechar sozinha."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror(titulo, mensagem)
        raiz.destroy()
    except Exception:  # pragma: no cover - ambiente sem interface grafica
        print(f"\n{titulo}\n{'-' * len(titulo)}\n{mensagem}\n", file=sys.stderr)
        try:
            input("Pressione Enter para fechar...")
        except (EOFError, KeyboardInterrupt):
            pass


def principal() -> int:
    """Abre a interface grafica. Devolve o codigo de saida do processo."""
    pasta = os.path.dirname(os.path.abspath(__file__))
    if pasta not in sys.path:
        sys.path.insert(0, pasta)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        _relatar(
            "Interface grafica indisponivel",
            "Este programa usa a biblioteca tkinter, que faz parte da instalacao\n"
            "padrao do Python. Reinstale o Python marcando a opcao 'tcl/tk and IDLE',\n"
            "ou execute o arquivo SimuladorOSI.exe, que ja traz tudo embutido.",
        )
        return 1

    try:
        from simulador.visual import executar

        executar()
    except Exception:  # pragma: no cover - salvaguarda do duplo clique
        _relatar(
            "O simulador encontrou um erro",
            "O programa nao pode continuar. Detalhes tecnicos:\n\n"
            + traceback.format_exc(limit=6),
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
