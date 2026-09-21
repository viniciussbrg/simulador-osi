"""Gera o executavel do simulador com o PyInstaller.

Este script empacota `main.py`, a pasta `simulador/` e o arquivo
`topologia.json` em um unico `SimuladorOSI.exe`, que abre com duplo clique e
nao depende de Python instalado na maquina.

Como usar (no Windows, com Python instalado):

    py -m pip install pyinstaller
    py build_exe.py

O executavel aparece em `dist/SimuladorOSI.exe`. O arquivo `topologia.json`
vai embutido, mas o programa procura primeiro uma copia ao lado do executavel:
basta deixar um `topologia.json` na mesma pasta para trocar a rede simulada
sem gerar o executavel de novo.

Observacao: o PyInstaller produz um executavel para o sistema em que e
executado. Para obter um `.exe` de Windows, rode este script no Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
NOME = "SimuladorOSI"


def _separador() -> str:
    """O PyInstaller usa `;` no Windows e `:` nos demais sistemas."""
    return ";" if os.name == "nt" else ":"


def montar_comando() -> list[str]:
    """Monta a linha de comando do PyInstaller."""
    topologia = os.path.join(RAIZ, "topologia.json")
    dados = f"{topologia}{_separador()}."
    comando = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",  # sem janela de console atras da interface
        "--name",
        NOME,
        "--add-data",
        dados,
        "--distpath",
        os.path.join(RAIZ, "dist"),
        "--workpath",
        os.path.join(RAIZ, "build"),
        "--specpath",
        os.path.join(RAIZ, "build"),
        os.path.join(RAIZ, "main.py"),
    ]
    icone = os.path.join(RAIZ, "recursos", "icone.ico")
    if os.path.isfile(icone):
        comando[-1:-1] = ["--icon", icone]
        # Embute o .ico para o iconbitmap encontrar em tempo de execução.
        comando[-1:-1] = ["--add-data", f"{icone}{_separador()}recursos"]
    return comando


def principal() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "O PyInstaller nao esta instalado.\n"
            "Instale com:  py -m pip install pyinstaller\n",
            file=sys.stderr,
        )
        return 1

    comando = montar_comando()
    print("Executando:\n  " + " ".join(comando) + "\n")
    codigo = subprocess.call(comando, cwd=RAIZ)
    if codigo == 0:
        destino = os.path.join(RAIZ, "dist", NOME + (".exe" if os.name == "nt" else ""))
        print(f"\nExecutavel gerado em: {destino}")
    return codigo


if __name__ == "__main__":
    sys.exit(principal())
