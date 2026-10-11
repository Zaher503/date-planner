@echo off
rem One-click deploy: ships the committed HEAD to the Zephyrus and rebuilds the stack.
rem Needs Git for Windows (bash) and working "ssh zephyrus".
setlocal
set "BASH=C:\Program Files\Git\bin\bash.exe"
if not exist "%BASH%" (
  echo Git Bash not found at %BASH%
  pause
  exit /b 1
)
cd /d "%~dp0.."
"%BASH%" scripts/deploy.sh %*
set RC=%ERRORLEVEL%
echo.
if %RC%==0 (echo Deploy finished.) else (echo Deploy FAILED with exit code %RC%.)
pause
exit /b %RC%
