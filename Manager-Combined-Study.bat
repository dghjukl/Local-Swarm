@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - manager combined study (FRAMES-100)
echo.
echo  MANAGER COMBINED STUDY on all 100 FRAMES questions (same sources as last night's run).
echo  MiMo thinks before each decision; every task goes to BOTH teammates:
echo   - MiMo alone with the wide evidence (anchor)
echo   - thinking MiMo + two copies of Qwen3.5-4B
echo   - thinking MiMo + Qwen3.5-4B and Gemma-4-E4B (diverse pair)
echo   - the same two teams with a fact-checker (Granite-4.1-3B) for facts only one teammate found
echo  Needs the internet. Expect about 9-10 hours. If it crashes it restarts itself;
echo  after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs manager-combined --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "Manager-Combined-Study" %rc% "study finished; see runtime\evals"
pause
