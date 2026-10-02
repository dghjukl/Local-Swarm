@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - verifier bench
echo.
echo  VERIFIER BENCH - which model is the best fact checker?
echo  400 real worker claims, each checked by every candidate verifier; two big judges
echo  (Ministral-14B and gpt-oss-20b) give the reference answer. About 1-2 hours.
echo  Close Start-Swarm first.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.verifier_bench --from runtime/evals/20260928-1323; exit $LASTEXITCODE"
echo.
echo Finished. The report is in runtime\evals\verifier-bench-(newest)\report.md
pause
