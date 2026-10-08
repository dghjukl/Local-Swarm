@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - scaling study, 8 attempts (FRAMES-100)
rem The team setup to scale: set after the trust study to the variant that won.
rem   mgr-scale8 (plain), mgr-scale8-charter, mgr-scale8-trust, mgr-scale8-trust-all, mgr-scale8-trust-self
set CONFIG=mgr-scale8-trust
echo.
echo  SCALING STUDY on all 100 FRAMES questions (same sources as the last runs).
echo   - MiMo alone with the wide evidence (anchor)
echo   - %CONFIG%: the team answers every question 8 separate times, then MiMo votes over all 8
echo  Every attempt is saved and graded on its own, so the curve for 1 to 8 attempts, the oracle and
echo  other ways of choosing can all be worked out afterwards without running anything again.
echo  At the end it also grades the individual attempts of the earlier vote study (20261006-1714).
echo  Needs the internet. Expect about 18-25 hours. If it crashes it restarts itself;
echo  after a power cut run Resume-Last-Eval.bat (it grades the attempts too).
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs solo-MiMo-wide,%CONFIG% --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retry
if "%rc%"=="0" goto votestudy
set /a tries+=1
if %tries% GTR 5 goto done
echo.
echo  The run stopped unexpectedly (code %rc%). Continuing where it left off in 20 seconds (attempt %tries% of 5)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retry
:votestudy
echo.
echo  Grading the individual attempts of the earlier vote study...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade runtime/evals/20261006-1714 --attempts-only --no-open; exit $LASTEXITCODE"
:done
echo.
echo Finished. The reports are in runtime\evals\ (newest folder, and 20261006-1714 updated).
pause
