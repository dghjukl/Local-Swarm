@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - big study
echo.
echo  Big study (overnight, roughly 8-10 hours). Uses the saved web sources, so no web searching.
echo    1. every research model as the only worker        (30 models)
echo    2. every research model alone writing the answer  (31 models)
echo    3. 7 reasoning strategies x 2 worker models
echo    4. team variety: clones vs different models vs different ways of thinking vs roles
echo  Then the judge grades everything (the longest part).
echo.
echo  Close Start-Swarm first. If the power goes out, run Resume-Last-Eval.bat - it continues
echo  where it stopped, including half-finished grading.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs big-study --reuse-evidence runtime\evals\20260926-1759"
echo.
echo Finished. The report is in the newest folder in runtime\evals\
pause
