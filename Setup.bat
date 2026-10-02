@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\logs" mkdir "runtime\logs"
echo Setting up Local Swarm (first run downloads about 60 MB)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" > "runtime\logs\setup.log" 2>&1
if errorlevel 1 (
  echo.
  echo Setup hit a problem. Tell Claude - details are in runtime\logs\setup.log
) else (
  echo.
  echo Setup finished OK. Details are in runtime\logs\setup.log
)
pause
