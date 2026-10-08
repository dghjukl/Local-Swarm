@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - network node speed check
echo.
echo  Checks a model server on another machine (default: the laptop at 192.168.68.70:8090)
echo  with fact-check-sized prompts, and shows how fast it reads and writes.
echo  To check another machine:  Test-Network-Node.bat http://ADDRESS:PORT
echo.
set "NODE=%~1"
if "%NODE%"=="" set "NODE=http://192.168.68.70:8090"
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.nodecheck '%NODE%'"
echo.
pause
