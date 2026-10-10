@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - overnight live study
echo.
echo  OVERNIGHT LIVE STUDY - every run plans, searches the web (web, news, papers) and reads for itself.
echo    - the coordinator alone, best swarms, and swarms that research each part of the question separately
echo    - one small model spending a swarm-sized budget (4 and 8 drafts)
echo    - the big models alone (9B to 35B; the biggest run split between graphics card and RAM)
echo    - swarms where a big model writes the final answer
echo  Then it grades everything, then re-grades yesterdays big study with the fixed grader.
echo  Expect 10-12 hours. Close Chrome, Start-Swarm and other programs first.
echo  If it stops (power, restart), run Resume-Last-Eval.bat and it continues where it left off.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs overnight-live --set evals/research_v3.yaml --live --no-open"
echo.
echo  Now re-grading yesterdays big study with the fixed grader...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade runtime\evals\20260927-1155 --no-open"
set rc=%ERRORLEVEL%
echo.
echo Finished. Reports are in runtime\evals\
call "%~dp0scripts\notify.bat" "Overnight-Live" %rc% "study finished; see runtime\evals"
pause
