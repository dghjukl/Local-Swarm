@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - coordinator bake-off
echo.
echo  COORDINATOR BAKE-OFF - our best small swarm, with only the coordinator changed:
echo    Qwen3.5-4B (today's), Qwen3.5-9B, Gemma-4-12B, Qwen3.8-27B (3-bit), Bonsai-2-27B (ternary),
echo    Ministral-3-14B - plus the three new models answering alone.
echo  Every candidate fits entirely on the graphics card (nothing spills into RAM).
echo  63 questions about 2026 discoveries, live web research. Every answer is graded twice:
echo  by the usual judge (Ministral-14B) and by gpt-oss-20b, so Ministral is not only grading itself.
echo  Needs the new models: run Sync-Models.bat first. Expect about 11-12 hours.
echo  Close Chrome, Start-Swarm and other programs first. If the program crashes it restarts
echo  itself where it left off; after a power cut or restart, run Resume-Last-Eval.bat.
echo.
if not exist "Bin\llama-prism\llama-server.exe" (
  echo  Bin\llama-prism is missing - run Sync-Models.bat first. Bonsai will be skipped otherwise.
  echo.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs coordinator-bakeoff --set evals/research_v4.yaml --live --judge2 --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "Coordinator-Bakeoff" %rc% "study finished; see runtime\evals"
pause
