@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - roles study
echo.
echo  Step 1: re-grade the team-size study (120 answers) with the new answer keys (about 15 min).
echo  Step 2: roles study - 20 questions x (coordinator alone, 2 answerers,
echo          2 answerers + fact sheet / premise check / skeptic), same web sources as before.
echo  Expect roughly 1 hour in total. Close Start-Swarm first. You can leave it running.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade runtime\evals\20260926-1759 --no-open"
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs roles-study --reuse-evidence runtime\evals\20260926-1759"
set rc=%ERRORLEVEL%
echo.
echo Finished. Both reports are in runtime\evals\
call "%~dp0scripts\notify.bat" "Roles-Study" %rc% "study finished; see runtime\evals"
pause
