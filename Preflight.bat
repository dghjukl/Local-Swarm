@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - preflight
echo.
echo  PREFLIGHT - load every model the planned studies use and ask each two small questions,
echo  so a model that cannot run is found now instead of in the middle of a long run.
echo  About 30 seconds per model. Models that passed before are skipped. Close Start-Swarm first.
echo  (Every evaluation also does this by itself before it starts.)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.preflight --configs round2-screen,round3-screen,reranker-study,external-v1 --judge2 %*"
echo.
pause
