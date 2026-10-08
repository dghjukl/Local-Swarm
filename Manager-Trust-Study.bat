@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - manager trust study (FRAMES-100)
echo.
echo  TRUST CHECK STUDY on all 100 FRAMES questions (same sources as the last runs).
echo  Before finishing, MiMo must lay out the chain its answer rests on; code checks the citations and
echo  the arithmetic, and gaps send the team back to work.
echo   - MiMo alone with the wide evidence (anchor)
echo   - the base team (control)
echo   - the base team with the partner charter as a short nudge in every prompt (MiMo and workers)
echo   - the base team + trust check (Qwen3.5-4B re-checks the steps MiMo calls supported)
echo   - the base team + trust check + the charter nudge in every prompt
echo   - the base team + trust check on MiMo's own judgment (no second model)
echo  Needs the internet. Expect about 10-13 hours. If it crashes it restarts itself;
echo  after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs manager-trust --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
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
