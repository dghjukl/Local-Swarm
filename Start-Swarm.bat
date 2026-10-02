@echo off
setlocal
cd /d "%~dp0"
title Local Swarm
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo The swarm stopped with an error. Tell Claude, and include the text above.
)
pause
