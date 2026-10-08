@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - manager study (FRAMES)
echo.
echo  MANAGER STUDY on the same 40 FRAMES questions and starting sources as the notebook v3 run.
echo  MiMo-9B acts like a person directing assistants: each turn it gives one teammate one task (with a
echo  web search if needed), can hand the same task to the other teammate, and stops when satisfied.
echo   - MiMo alone with the wide evidence (yesterday's winner, the anchor)
echo   - the manager loop with no team (MiMo does every step itself)
echo   - MiMo directing two copies of Qwen3.5-4B
echo   - MiMo directing Qwen3.5-4B and Gemma-4-E4B
echo  Every question runs twice (the web searches differ run to run). Needs the internet.
echo  Expect about 8-9 hours. If it crashes it restarts itself; after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs manager-study --set runtime/benchmarks/frames-100.yaml --repeats 2 --reuse-evidence runtime/evals/20261004-0935 --questions frames-0,frames-1,frames-9,frames-16,frames-25,frames-29,frames-32,frames-48,frames-59,frames-64,frames-92,frames-93,frames-96,frames-100,frames-103,frames-108,frames-131,frames-137,frames-171,frames-173,frames-177,frames-183,frames-192,frames-200,frames-212,frames-213,frames-219,frames-225,frames-238,frames-243,frames-246,frames-248,frames-257,frames-266,frames-276,frames-284,frames-286,frames-295,frames-331,frames-343 --no-open; exit $LASTEXITCODE"
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
