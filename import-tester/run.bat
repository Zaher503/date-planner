@echo off
setlocal
cd /d "%~dp0"

rem First run: create the venv and install the backend's own requirements
if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    python -m venv .venv || goto :fail
)
if not exist .venv\.installed (
    echo Installing dependencies, this takes a minute the first time...
    .venv\Scripts\python.exe -m pip install --quiet -r ..\backend\requirements.txt || goto :fail
    echo ok> .venv\.installed
)

rem Stop a test server left over from an earlier run
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8899 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"

rem Tunnel to the Zephyrus: AI hub, browser, search and geocoder
powershell -NoProfile -ExecutionPolicy Bypass -File tunnel.ps1
if exist .tunnel.pid (
    set /p TUNNEL_PID=<.tunnel.pid
)

set OLLAMA_URL=http://127.0.0.1:11434
set BROWSER_URL=
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',3000); $c.Close(); exit 0 } catch { exit 1 }" && set BROWSER_URL=ws://127.0.0.1:3000
set SEARXNG_URL=http://127.0.0.1:8080
set PHOTON_URL=http://127.0.0.1:2322

.venv\Scripts\python.exe server.py
if errorlevel 1 (
    echo.
    echo The server stopped with an error, see above.
    pause
)

if defined TUNNEL_PID taskkill /PID %TUNNEL_PID% /F >nul 2>&1
del .tunnel.pid >nul 2>&1
exit /b 0

:fail
echo Setup failed.
pause
exit /b 1
