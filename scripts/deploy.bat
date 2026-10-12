@echo off
rem Re-run the deploy of what is on main (every push to main already deploys itself).
rem Needs the GitHub CLI (gh) logged in.
setlocal
cd /d "%~dp0.."
gh workflow run CD --repo Zaher503/date-planner
if errorlevel 1 (echo Could not start the deploy. & pause & exit /b 1)
echo Started. Watching the run (Ctrl+C to stop watching, the deploy keeps going)...
timeout /t 5 /nobreak >nul
gh run watch --repo Zaher503/date-planner --exit-status
set RC=%ERRORLEVEL%
echo.
if %RC%==0 (echo Deploy finished.) else (echo Deploy FAILED with exit code %RC%.)
pause
exit /b %RC%
