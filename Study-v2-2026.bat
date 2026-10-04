@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - v2 swarm on 2026
echo.
echo  MID-SIZE SWARM v2 on the 63 questions about 2026 events (same set as Study-2026).
echo   - v2 swarm: MiMo-9B coordinates; MiMo, Apertus-8B, EXAONE-1.2B and Gemma-4-E4B answer;
echo     Gemma checks the facts
echo   - the same with the 4B reranker choosing the passages
echo   - MiMo alone, MiMo coordinating the old roles team (bake-off winner), and the 4B alone (anchor)
echo  The four are frozen (evals\frozen\external-v2.json) the first time this runs, before any result.
echo  Expect about 5-6 hours. If it crashes it restarts itself; after a power cut run Resume-Last-Eval.bat.
echo.
if not exist "evals\frozen\external-v2.json" powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --freeze external-v2 --configs external-v2"
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs external-v2 --frozen external-v2 --set evals/research_v4.yaml --live --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retry
if "%rc%"=="0" goto done
set /a tries+=1
if %tries% GTR 5 goto done
echo.
echo  The run stopped unexpectedly (code %rc%). Continuing where it left off in 20 seconds (attempt %tries% of 5)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retry
:done
echo.
echo Finished. The report is in runtime\evals\ (newest folder).
pause
