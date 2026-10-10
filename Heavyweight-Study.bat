@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - heavyweight study
echo.
echo  Heavyweight study: the biggest models this PC can run, each alone, vs the swarm. LIVE: every run plans,
echo  searches the web (web, news, papers) and reads for itself - the real task, so it is noisier.
echo    - 7 big models (14B to 35B). The ones bigger than the graphics card run split between GPU and RAM.
echo    - 2 swarms where a big model writes the final answer (taking turns with the team on the GPU)
echo    - the current best swarm and the coordinator alone, for comparison
echo  Expect roughly 2-4 hours including grading, then ~3 hours re-grading the big study with the fixed grader. The PC will be working hard while the big models run:
echo  close Chrome and other programs first, and close Start-Swarm.
echo  If it stops (power, restart), run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs heavyweight-study --set evals/research_v3.yaml --live"
echo.
echo  Now re-grading the big study with the fixed grader (about 3 hours)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade runtime\evals\20260927-1155 --no-open"
set rc=%ERRORLEVEL%
echo.
echo Finished. The report is in the newest folder in runtime\evals\
call "%~dp0scripts\notify.bat" "Heavyweight-Study" %rc% "study finished; see runtime\evals"
pause
