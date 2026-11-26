@echo off
rem Um clique para abrir o AssetFlow (lote 10): sobe a API e a tela, espera as
rem duas responderem e abre o navegador no endereco certo, mesmo com a porta
rem 5173 ocupada por outro programa. O trabalho esta em backend\scripts\iniciar.py.
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Falta o ambiente do backend ^(backend\.venv^): veja o SETUP.md.
  pause
  exit /b 1
)
"backend\.venv\Scripts\python.exe" "backend\scripts\iniciar.py" %*
if errorlevel 1 pause
