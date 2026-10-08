@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - notebook v3 FRAMES study
echo.
echo  NOTEBOOK v3 on 40 FRAMES questions (answers need facts from 2-15 Wikipedia articles).
echo  First the sources are searched once (shared by every setup, about 1 hour), then:
echo   - MiMo-9B alone, reading the usual 6 passages per part
echo   - MiMo-9B alone, reading 15 per part (can one model use more?)
echo   - notebook v3: Apertus, EXAONE, Gemma read 15 per part and take notes; MiMo reads its usual
echo     6 per part PLUS the notebook (the notebook can only add)
echo   - the same with 3 copies of Apertus (no diversity)
echo   - the same 3 models answering separately from 15 per part (no collaboration)
echo  Expect about 7-8 hours. If it crashes it restarts itself; after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs notebook-v3 --set runtime/benchmarks/frames-100.yaml --questions frames-0,frames-1,frames-9,frames-16,frames-25,frames-29,frames-32,frames-48,frames-59,frames-64,frames-92,frames-93,frames-96,frames-100,frames-103,frames-108,frames-131,frames-137,frames-171,frames-173,frames-177,frames-183,frames-192,frames-200,frames-212,frames-213,frames-219,frames-225,frames-238,frames-243,frames-246,frames-248,frames-257,frames-266,frames-276,frames-284,frames-286,frames-295,frames-331,frames-343 --no-open; exit $LASTEXITCODE"
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
