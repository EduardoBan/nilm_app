@echo off
title NILM Energy Analytics Platform
echo ============================================================
echo   Iniciando Servidor NILM y Cliente TypeScript...
echo ============================================================
cd /d "C:\Users\local\Documents\IA\Energia\nilm_app"
if exist ".venv\Scripts\python.exe" (
	".venv\Scripts\python.exe" start_server.py
) else (
	python start_server.py
)
pause
