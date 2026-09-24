@echo off
setlocal EnableExtensions
set "TARGET=%LOCALAPPDATA%\Programs\NILM_Energy_Platform"
set "PAYLOAD=%~dp0payload.zip"
if not exist "%PAYLOAD%" (
  echo No se encontro payload.zip
  exit /b 1
)
if not exist "%TARGET%" mkdir "%TARGET%" >nul 2>&1

rem Extrae el payload en la instalacion portable.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%PAYLOAD%' -DestinationPath '%TARGET%' -Force" >nul 2>&1
if errorlevel 1 (
  echo Error al extraer la aplicacion
  exit /b 1
)

rem Conserva el estado editable del usuario al reinstalar.
if not exist "%TARGET%\backend\load_labels.json" echo {}>"%TARGET%\backend\load_labels.json"
if not exist "%TARGET%\Data" mkdir "%TARGET%\Data" >nul
if not exist "%TARGET%\cache" mkdir "%TARGET%\cache" >nul
if not exist "%TARGET%\reports" mkdir "%TARGET%\reports" >nul

rem Crea un acceso directo en Inicio para el lanzador portable.
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\NILM"
if not exist "%STARTMENU%" mkdir "%STARTMENU%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut('%STARTMENU%\NILM Energy Platform.lnk'); $l.TargetPath='%TARGET%\NILM_Platform.cmd'; $l.WorkingDirectory='%TARGET%'; $l.Description='NILM Energy Analytics Platform'; $l.Save()" >nul 2>&1

echo.
echo Instalacion completada en:
echo %TARGET%
echo.
echo Use "NILM_Platform.cmd" para iniciar la aplicacion.
exit /b 0

