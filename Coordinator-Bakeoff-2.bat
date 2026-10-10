@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - coordinator bake-off 2
echo.
echo  COORDINATOR BAKE-OFF ROUND 2 - same swarm, coordinators from the second-tier labs:
echo    MiMo-9B (Xiaomi), HyperCLOVAX-Think-14B (NAVER), Apriel-1.6-15B (ServiceNow),
echo    Phi-4-reasoning-vision-15B (Microsoft), ERNIE-4.5-21B-A3B (Baidu, 3-bit) - plus each alone.
echo  All fit on the graphics card. 63 questions, live research, graded by two judges.
echo  Needs the optional models from Sync-Models.bat. Expect about 9-10 hours.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs coordinator-bakeoff2 --set evals/research_v4.yaml --live --judge2 --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "Coordinator-Bakeoff-2" %rc% "study finished; see runtime\evals"
pause
