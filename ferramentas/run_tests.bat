@echo off
:: Define o terminal para UTF-8 para exibir acentos corretamente
chcp 65001 > nul

echo ==========================================
echo Entrando na pasta 'ferramentas'...
echo ==========================================
cd ferramentas

echo.
echo ==========================================
echo Executando: conferir_interface.py
echo ==========================================
python conferir_interface.py
if %ERRORLEVEL% NEQ 0 echo [AVISO] Ocorreu um erro neste teste.

echo.
echo ==========================================
echo Executando: rodar_testes.py
echo ==========================================
python rodar_testes.py
if %ERRORLEVEL% NEQ 0 echo [AVISO] Ocorreu um erro neste teste.

echo.
echo ==========================================
echo Processo concluído!
echo ==========================================
pause