@echo off
py -m pip install pyinstaller
cd /d "%~dp0"
py -m PyInstaller --noconfirm --onefile --windowed --name SimuladorOSI --add-data "src\topologia.json;." --paths src src\main.py
echo.
echo Executavel criado em dist\SimuladorOSI.exe
pause
