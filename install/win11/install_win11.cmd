@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: =========================================================================
::  NILM Energy Analytics Platform — Instalador para Windows 11
:: =========================================================================

title NILM Energy Platform - Instalador Windows 11
color 0A

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR..\.."
set "INSTALL_BASE=%LOCALAPPDATA%\Programs\NILM_Energy_Platform"
set "VENV_DIR=%INSTALL_BASE%\.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\NILM"
set "DESKTOP=%USERPROFILE%\Desktop"

echo.
echo ========================================================================
echo   NILM Energy Analytics Platform
echo   Instalador para Windows 11
echo ========================================================================
echo.

ver | findstr /i "10.0" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Este instalador requiere Windows 10 o Windows 11.
    pause
    exit /b 1
)

echo [1/6] Verificando Python...
where python.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo   Instale Python 3.10+ desde https://python.org y vuelva a ejecutar.
    echo.
    pause
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se pudo obtener la version de Python.
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] %PY_VER% detectado.

python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if errorlevel 1 (
    echo [ERROR] Se requiere Python 3.10 o superior.
    exit /b 1
)

echo [2/6] Creando directorio de instalacion...
if not exist "%INSTALL_BASE%" mkdir "%INSTALL_BASE%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se pudo crear: %INSTALL_BASE%
    exit /b 1
)
echo [OK] %INSTALL_BASE%
echo [3/6] Copiando archivos de la aplicacion...

if exist "%PROJECT_ROOT%\backend" (
    xcopy /E /I /Y /Q "%PROJECT_ROOT%\backend\*" "%INSTALL_BASE%\backend\"
    echo [OK] backend/
) else (
    echo [ERROR] No se encontro backend/
    exit /b 1
)

if exist "%PROJECT_ROOT%\frontend" (
    xcopy /E /I /Y /Q "%PROJECT_ROOT%\frontend\*" "%INSTALL_BASE%\frontend\"
    echo [OK] frontend/
) else (
    echo [ERROR] No se encontro frontend/
    exit /b 1
)

copy /Y "%PROJECT_ROOT%\requirements.txt" "%INSTALL_BASE%\requirements.txt" >nul 2>&1
copy /Y "%PROJECT_ROOT%\server.py" "%INSTALL_BASE%\server.py" >nul 2>&1
echo [OK] Archivos raiz copiados.

echo [4/6] Creando entorno virtual e instalando dependencias...
python -m venv "%VENV_DIR%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual.
    exit /b 1
)
echo [OK] Entorno virtual creado.

echo [4/6] Actualizando pip...
"%PIP_EXE%" install --upgrade pip >nul 2>&1

echo [4/6] Instalando dependencias (puede tardar varios minutos)...
"%PIP_EXE%" install -r "%INSTALL_BASE%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Error instalando dependencias.
    exit /b 1
)
echo [5/6] Configurando directorios de datos...
for %%d in (Data cache reports backend) do (
    if not exist "%INSTALL_BASE%\%%d" mkdir "%INSTALL_BASE%\%%d" >nul 2>&1
)
if not exist "%INSTALL_BASE%\backend\load_labels.json" echo {}>"%INSTALL_BASE%\backend\load_labels.json"
echo [OK] Directorios listos.

echo [6/6] Creando accesos directos...

(
    echo @echo off
    echo setlocal EnableExtensions
    echo set "NILM_APP_HOME=%INSTALL_BASE%"
    echo cd /d "%INSTALL_BASE%"
    echo "%PYTHON_EXE%" server.py
) > "%INSTALL_BASE%\NILM_Platform.cmd"

if not exist "%STARTMENU%" mkdir "%STARTMENU%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s=New-Object -ComObject WScript.Shell;" ^
    "$l=$s.CreateShortcut('%STARTMENU%\NILM Energy Platform.lnk');" ^
    "$l.TargetPath='%INSTALL_BASE%\NILM_Platform.cmd';" ^
    "$l.WorkingDirectory='%INSTALL_BASE%';" ^
    "$l.Description='NILM Energy Analytics Platform';" ^
    "$l.Save()" >nul 2>&1
echo [OK] Acceso directo en Menu Inicio.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s=New-Object -ComObject WScript.Shell;" ^
    "$l=$s.CreateShortcut('%DESKTOP%\NILM Energy Platform.lnk');" ^
    "$l.TargetPath='%INSTALL_BASE%\NILM_Platform.cmd';" ^
    "$l.WorkingDirectory='%INSTALL_BASE%';" ^
    "$l.Description='NILM Energy Analytics Platform';" ^
    "$l.Save()" >nul 2>&1
echo [OK] Acceso directo en Escritorio.

(
    echo @echo off
    echo setlocal EnableExtensions
    echo echo Desinstalando NILM Energy Analytics Platform...
    echo rd /s /q "%INSTALL_BASE%"
    echo if exist "%STARTMENU%\NILM Energy Platform.lnk" del "%STARTMENU%\NILM Energy Platform.lnk"
    echo if exist "%DESKTOP%\NILM Energy Platform.lnk" del "%DESKTOP%\NILM Energy Platform.lnk"
    echo echo Desinstalacion completada.
    echo pause
) > "%INSTALL_BASE%\uninstall.cmd"

echo.
echo ========================================================================
echo [INSTALACION COMPLETADA]
echo ========================================================================
echo.
echo Ubicacion: %INSTALL_BASE%
echo Ejecutable: %INSTALL_BASE%\NILM_Platform.cmd
echo.
echo Para iniciar: haga doble clic en "NILM Energy Platform" (Escritorio o Menu Inicio)
echo.
pause
echo [OK] Dependencias instaladas.