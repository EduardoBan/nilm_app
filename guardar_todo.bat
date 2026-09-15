@echo off
title NILM - Guardar todo (Git + Respaldo ZIP)
echo ============================================================
echo   Guardando TODO: Git commit + Respaldo ZIP automatico
echo ============================================================
cd /d "C:\Users\local\Documents\IA\Energia\nilm_app"
if exist ".venv\Scripts\python.exe" (
	".venv\Scripts\python.exe" scripts\backup.py --auto
) else (
	python scripts\backup.py --auto
)
pause