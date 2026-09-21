@echo off
REM Abre o simulador com duplo clique, sem janela de console.
REM Requer Python 3.10 ou superior instalado no Windows.
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py
    exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
    start "" py -3 -w main.py
    exit /b 0
)

echo Python nao foi encontrado no sistema.
echo Instale o Python a partir de https://www.python.org/downloads/
echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
pause
