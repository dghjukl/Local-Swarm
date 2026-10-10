@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - manager both study (FRAMES-100)
echo.
echo  MANAGER "BOTH" STUDY on all 100 FRAMES questions (40 reuse their sources, 60 are searched first).
echo  Every task goes to BOTH teammates at once, so MiMo sees two independent answers:
echo   - MiMo alone with the wide evidence (anchor)
echo   - MiMo + two copies of Qwen3.5-4B (no diversity)
echo   - MiMo + Qwen3.5-4B and Gemma-4-E4B (diverse pair)
echo   - MiMo + two Qwen3.5-4B, MiMo using its built-in thinking
echo   - MiMo + two Qwen3.5-4B, MiMo stepping back before each decision
echo  Needs the internet. Expect about 10-11 hours. If it crashes it restarts itself;
echo  after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs manager-both --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-0935 --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "Manager-Both-Study" %rc% "study finished; see runtime\evals"
pause
