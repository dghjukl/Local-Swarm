@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - resolver test 2: does it work with 3 attempts? (J5, Gemma)
rem J4 showed Qwen3.6-35B-A3B as resolver lifts the 8-attempt study from 56% to 67%. The default team
rem uses 3 attempts, so this checks the resolver on 3-attempt material, then tries it with thinking on.
rem J5 first try: Qwen3.6-35B took available RAM to 0.17 GB and was stopped. Gemma-4-26B-A4B was
rem nearly as good in J4 (+9 vs +11 net) with ~6 GB less in RAM, so it is the resolver here.
set QWEN=Gemma-4-26B-A4B-it
echo.
echo  RESOLVER TEST 2 (Gemma-4-26B-A4B, nothing else on the GPU; close other big apps):
echo    A. the 3-attempt vote study (its own vote got 60%%): resolve the questions where the 3 disagree
echo    B. the 8-attempt study, but showing the resolver only the first 3 attempts
echo  Expect about 1-1.5 hours. It stops by itself if free RAM drops under 1.5 GB. Safe to start again.
echo.
call :make runtime/evals/20261006-1714-recheck mgr-vote3-same runtime/evals/resolver-vote3-20261009 || goto stopped
call :grade runtime/evals/resolver-vote3-20261009
call :make runtime/evals/20261008-0650-recheck mgr-scale8-trust runtime/evals/resolver-k3-20261009 --k 3 || goto stopped
call :grade runtime/evals/resolver-k3-20261009
echo.
echo Finished. Reports: resolver_report.md and overall.md in the two resolver-* folders above.
pause
exit /b 0

:stopped
echo.
echo Stopped early. Finished answers are kept; run this again later to continue.
pause
exit /b 1

:make
echo.
echo  === %QWEN% on %1 (%2) %4 %5 %6 %7 ===
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench make %1 --config %2 --model %QWEN% --out %3 --no-mmap %4 %5 %6 %7; exit $LASTEXITCODE"
if errorlevel 3 (echo   STOPPED by the RAM guard or repeated failures - not grading. Report the STOPPED line.& exit /b 1)
if errorlevel 1 echo   stopped with an error - continuing (finished answers are kept)
exit /b 0

:grade
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade %1 --no-open; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench compare %1; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench overall %1 | Tee-Object -FilePath %1\overall.md; exit 0"
exit /b 0
