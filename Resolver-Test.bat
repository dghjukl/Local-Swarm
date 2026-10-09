@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - resolver test (plan step 4)
rem A bigger model settles the questions where the team got stuck in the 8-attempt study
rem (attempts disagree, or no attempt passed the trust check). No new research: it reads the saved
rem research packet. Its answers sit next to the team's own vote on the same questions, and both are
rem graded together (judge with the second look on). See swarm/resolver_bench.py.
set SRC=runtime/evals/20261008-0650-recheck
set CFG=mgr-scale8-trust
set OUT=runtime/evals/resolver-20261009
echo.
echo  RESOLVER TEST on the 86 stuck questions of the 8-attempt study.
echo  Four resolvers, one at a time, nothing else on the GPU:
echo    1. MiMo-9B (the coordinator itself, as a control: does the packet alone help?)
echo    2. gpt-oss-20b (fits on the GPU)
echo    3. Gemma-4-26B-A4B (about 6 GB runs from RAM)
echo    4. Qwen3.6-35B-A3B (about 12 GB runs from RAM - tight with 16 GB; run last on purpose)
echo  Then everything is graded and the rescue / break table is written to %OUT%\resolver_report.md
echo  Expect about 5-7 hours. Safe to stop and start again: finished questions are kept.
echo.
rem MiMo thinks, as it does when it coordinates; the others answer directly
call :one MiMo-V2.6-Distill-Qwen-9B --think --max-tokens 6000
call :one gpt-oss-20b
call :one Gemma-4-26B-A4B-it
call :one Qwen3.6-35B-A3B
echo.
echo  Grading all resolver answers and the team's vote on the same questions...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade %OUT% --no-open; exit $LASTEXITCODE"
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench compare %OUT%; exit $LASTEXITCODE"
echo.
echo Finished. Results: %OUT%\resolver_report.md and %OUT%\report.md
pause
exit /b 0

:one
echo.
echo  === Resolver: %1 ===
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench make %SRC% --config %CFG% --model %1 --out %OUT% %2 %3 %4; exit $LASTEXITCODE"
if errorlevel 1 echo   %1 stopped with an error - continuing with the next resolver (its finished answers are kept)
exit /b 0
