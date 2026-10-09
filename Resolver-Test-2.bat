@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - resolver test 2: does it work with 3 attempts? (J5)
rem J4 showed Qwen3.6-35B-A3B as resolver lifts the 8-attempt study from 56% to 67%. The default team
rem uses 3 attempts, so this checks the resolver on 3-attempt material, then tries it with thinking on.
set QWEN=Qwen3.6-35B-A3B
echo.
echo  RESOLVER TEST 2 (Qwen3.6-35B-A3B only, nothing else on the GPU):
echo    A. the 3-attempt vote study (its own vote got 60%%): resolve the questions where the 3 disagree
echo    B. the 8-attempt study, but showing the resolver only the first 3 attempts
echo    C. the 8-attempt study again with thinking on (slower; run last, safe to stop)
echo  Expect about 1.5 hours for A+B and 2-4 more for C. Safe to stop and start again.
echo.
call :make runtime/evals/20261006-1714-recheck mgr-vote3-same runtime/evals/resolver-vote3-20261009
call :grade runtime/evals/resolver-vote3-20261009
call :make runtime/evals/20261008-0650-recheck mgr-scale8-trust runtime/evals/resolver-k3-20261009 --k 3
call :grade runtime/evals/resolver-k3-20261009
call :make runtime/evals/20261008-0650-recheck mgr-scale8-trust runtime/evals/resolver-20261009 --think --max-tokens 8000
call :grade runtime/evals/resolver-20261009
echo.
echo Finished. Reports: resolver_report.md and overall.md in each of the three resolver-* folders above.
pause
exit /b 0

:make
echo.
echo  === %QWEN% on %1 (%2) %4 %5 %6 %7 ===
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench make %1 --config %2 --model %QWEN% --out %3 %4 %5 %6 %7; exit $LASTEXITCODE"
if errorlevel 1 echo   stopped with an error - continuing (finished answers are kept)
exit /b 0

:grade
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade %1 --no-open; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench compare %1; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench overall %1 | Tee-Object -FilePath %1\overall.md; exit 0"
exit /b 0
