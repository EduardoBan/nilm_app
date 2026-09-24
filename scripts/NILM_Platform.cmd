@echo off
setlocal
set "APP_HOME=%~dp0"
set "NILM_APP_HOME=%APP_HOME%"
set "PYTHONPATH=%APP_HOME%;%APP_HOME%runtime\python\Lib\site-packages;%APP_HOME%runtime\user-site"
set "NILM_PORT=8000"
cd /d "%APP_HOME%"
"%APP_HOME%runtime\python\python.exe" "%APP_HOME%start_server.py"
endlocal
