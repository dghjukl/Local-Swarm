@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - manager experts study (FRAMES-100)
echo.
echo  MANAGER EXPERTS STUDY on all 100 FRAMES questions (same sources as the last two runs).
echo  Base team: thinking MiMo + Qwen3.5-4B and Gemma-4-E4B, every task to both.
echo   - MiMo alone with the wide evidence (anchor)
echo   - the base team (bigger context windows)
echo   - + structured worker reports (what was said, what's missing, suggested next step, confidence)
echo   - + reports, 10 turns and more thinking (try-harder control)
echo   - + reports and an expert MiMo can call when stuck: Qwen3.5-9B / Gemma-4-12B (Q5) / Ornith-1.5-9B
echo  Run Sync-Models.bat FIRST (it downloads Gemma-4-12B Q5 and Ornith).
echo  Needs the internet. Expect about 14-16 hours. If it crashes it restarts itself;
echo  after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs manager-experts --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "Manager-Experts-Study" %rc% "study finished; see runtime\evals"
pause
