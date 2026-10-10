@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - GAIA study
echo.
echo  GAIA: questions for a web-searching assistant, each with one exact answer.
echo  The 6 configurations frozen in evals\frozen\external-v1.json run UNCHANGED (it refuses to
echo  start if any of them was changed): one 4B pass, the 4B with 8 drafts, 9B alone, 35B alone,
echo  and the best small swarm. (The swarm with the 35B coordinating is left out: it restarted this PC.) Every run does its own live
echo  web research; the sites that publish the answer keys are blocked.
echo  Expect about 9-10 hours. Close Chrome, Start-Swarm and other programs first.
echo  If the program crashes it restarts itself where it left off; after a power cut or restart,
echo  run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs coordinator-only,solo-x8-Qwen3.5-4B,solo-Qwen3.5-9B,solo-Qwen3.6-35B-A3B,roles-2ways-split --frozen external-v1 --set runtime/benchmarks/gaia-l12-text.yaml --live --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "Study-GAIA" %rc% "study finished; see runtime\evals"
pause
