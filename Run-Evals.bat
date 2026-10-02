@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - evaluation
echo.
echo  Runs every test question through each configuration on the real models,
echo  grades the answers, and opens a report. Takes roughly 10 minutes for 4 questions.
echo  Close Start-Swarm first (they would share the GPU).
echo.
echo  Extra options can be added after the file name, for example:
echo    Run-Evals.bat --configs swarm-mixed --repeats 2
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals %*"
echo.
echo Finished. Reports are in runtime\evals\
pause
