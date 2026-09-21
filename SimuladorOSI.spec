# -*- mode: python ; coding: utf-8 -*-
"""Empacotamento do simulador com o PyInstaller, igual no Windows e no macOS.

Gerar o executavel:

    pyinstaller SimuladorOSI.spec

Nada precisa ser editado entre um sistema e outro. O separador de --add-data
("topologia.json:." no macOS e no Linux, "topologia.json;." no Windows) e uma
particularidade da linha de comando: dentro do spec, datas recebe pares
(origem, destino) ja separados, e o PyInstaller monta o caminho com o
separador do sistema em que roda. Por isso este arquivo dispensa o if de
plataforma que a forma de linha de comando exigiria.

O topologia.json embutido aqui e apenas a copia de reserva do R10. O programa
procura primeiro o arquivo ao lado do executavel (ver simulador/recursos.py):
trocar a rede simulada continua sendo editar o topologia.json ao lado do
SimuladorOSI, sem gerar outro executavel.

console=True e proposital. O modo texto de main.py e a reserva de quando o
tkinter nao consegue abrir a janela, e ele precisa de um console para mostrar
o menu e a mensagem final; sem console, uma falha na abertura da janela seria
invisivel, que e o que o R10 proibe.
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # (origem no projeto, pasta de destino dentro do pacote). O "." poe o
    # arquivo na raiz da pasta temporaria, que e onde recursos.py o procura.
    datas=[('topologia.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SimuladorOSI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
