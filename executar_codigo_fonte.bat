@echo off
REM ---------------------------------------------------------------------
REM  Simulador do Modelo OSI - execucao a partir do codigo-fonte
REM
REM  Este arquivo e uma alternativa para quem tem Python instalado e quer
REM  rodar o codigo-fonte. Para apenas usar o programa, de dois cliques em
REM  SimuladorOSI.exe, que nao precisa de Python nem de instalacao alguma.
REM ---------------------------------------------------------------------
cd /d "%~dp0"
title Simulador do Modelo OSI

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Python nao foi encontrado neste computador.
    echo.
    echo  Use SimuladorOSI.exe, que nao precisa de Python,
    echo  ou instale o Python 3.10 ou superior de python.org.
    echo.
    pause
    exit /b 1
)

python main.py
if errorlevel 1 (
    echo.
    echo  O programa terminou com erro. A mensagem acima descreve a causa.
    echo.
    pause
)
