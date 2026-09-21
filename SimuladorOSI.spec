# -*- mode: python ; coding: utf-8 -*-
"""Receita de empacotamento do simulador (F7, issue #57).

    pyinstaller SimuladorOSI.spec

Equivale a `pyinstaller --onefile --windowed --name SimuladorOSI app.py`, mas
fica versionada: as decisões de empacotamento passam a ser lidas e revisadas
como código, em vez de viverem numa linha de comando que alguém precisa
lembrar de digitar igual.

Precisa rodar **no Windows**. O PyInstaller não faz compilação cruzada: ele
empacota o interpretador da máquina onde roda, então um `.exe` de Windows só
sai de um Python de Windows.

Três decisões, e a razão de cada uma:

- **o alvo é `app.py`, não `simulador.py`.** A tabela de módulos do projeto
  proíbe o motor de importar a interface; `app.py` é o único que reúne os dois
  lados, e por isso é ele que vira executável. `simulador.py` continua sendo o
  modo textual e continua sem enxergar a tela;

- **`topologia.json` NÃO entra em `datas`.** É deliberado, e é o ponto inteiro
  da seção 5.8: o arquivo fica ao lado do executável, editável, e
  `rede.pasta_base()` o procura lá. Embutido no pacote, ele iria para a pasta
  temporária que o `--onefile` descompacta e some ao fechar — e trocar a rede
  passaria a exigir recompilar, que é justamente o que o projeto promete não
  exigir. A distribuição copia o arquivo para junto do `.exe`, não para dentro
  dele;

- **`console=False`** é o `--windowed`: o usuário abre por duplo clique e não
  vê terminal nenhum. Consequência a lembrar: mensagens em `stderr` deixam de
  aparecer, e é por isso que erro de topologia precisa chegar ao usuário pela
  janela, não só pela saída padrão.
"""

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    # Vazio de propósito — ver a nota sobre `topologia.json` no cabeçalho.
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # O projeto usa só a biblioteca padrão. Estes três vêm junto com o
    # interpretador e não têm uso aqui; tirá-los encolhe o executável sem
    # risco de faltar alguma coisa.
    excludes=["unittest", "pydoc", "doctest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SimuladorOSI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX aumenta o falso positivo de antivírus; não compensa
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
