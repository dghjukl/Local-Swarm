@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - FRAMES study
echo.
echo  FRAMES: 100 questions that each need facts from several Wikipedia articles combined.
echo  The 6 configurations frozen in evals\frozen\external-v1.json run UNCHANGED (it refuses to
echo  start if any of them was changed): one 4B pass, the 4B with 8 drafts, 9B alone, 35B alone,
echo  the best small swarm, and that swarm with the 35B coordinating. Every run does its own live
echo  web research; the sites that publish the answer keys are blocked.
echo  Expect about 9-10 hours. Close Chrome, Start-Swarm and other programs first.
echo  If the program crashes it restarts itself where it left off; after a power cut or restart,
echo  run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs external-v1 --frozen external-v1 --set runtime/benchmarks/frames-100.yaml --live --no-open; exit $LASTEXITCODE"
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
