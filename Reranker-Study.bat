@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - reranker study
echo.
echo  RERANKER STUDY - does picking passages with a reranker model help? (FRAMES, live research)
echo    4B alone, and our best small swarm, with keyword ranking vs Qwen3-Reranker (0.6B and 4B).
echo  Needs Sync-Models.bat first (Qwen3-Reranker-4B). Expect about 6 hours.
echo  If it crashes it restarts itself; after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs reranker-study --set runtime/benchmarks/frames-100.yaml --live --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retryA
if "%rc%"=="0" goto doneA
set /a tries+=1
if %tries% GTR 5 goto doneA
echo.
echo  The run stopped unexpectedly (code %rc%). Continuing where it left off in 20 seconds (attempt %tries% of 5)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retryA
:doneA
echo.
echo Finished. The report is in runtime\evals\ (newest folders).
pause
