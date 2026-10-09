@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - resolver test 3: GPU-only resolvers on 3-attempt material (J6)
rem J5/J5b: the split GPU+RAM resolvers (Qwen3.6-35B, Gemma-4-26B) ran system RAM down to almost nothing.
rem J6 tries resolvers that fit entirely on the GPU (Codex's suggestion: Bonsai-2-27B), then Gemma-4-26B
rem again with --no-mmap so its RAM use is honest. Every model gets the RAM guard (stops at 1.5 GB free).
echo.
echo  RESOLVER TEST 3. Nothing else on the GPU; close other big apps.
echo   Part A: the 3-attempt vote study (its own vote: 60%%) - the 73 questions where the 3 attempts disagree
echo     1. Bonsai-2-27B   (ternary, 7.2 GB, all on the GPU, PrismML server)
echo     2. Qwen3.8-27B    (IQ3_XXS, 10.9 GB, all on the GPU)
echo     3. Gemma-4-26B    (split GPU + about 6 GB RAM, --no-mmap) - last, because it is the RAM risk
echo   Part B: the same three on the 8-attempt study shown only its first 3 attempts (74 stuck questions)
echo  Each part is graded when its three models are done. Expect about 2.5-3 h per part.
echo  Safe to stop and start again: finished answers are kept, failed ones are asked again.
echo.
set A_SRC=runtime/evals/20261006-1714-recheck
set A_CFG=mgr-vote3-same
set A_OUT=runtime/evals/resolver-vote3-20261009
set B_SRC=runtime/evals/20261008-0650-recheck
set B_CFG=mgr-scale8-trust
set B_OUT=runtime/evals/resolver-k3-20261009
for %%M in (Bonsai-2-27B Qwen3.8-27B Gemma-4-26B-A4B-it) do (
  call :make %A_SRC% %A_CFG% %A_OUT% %%M || goto stopped
)
call :grade %A_OUT%
for %%M in (Bonsai-2-27B Qwen3.8-27B Gemma-4-26B-A4B-it) do (
  call :make %B_SRC% %B_CFG% %B_OUT% %%M --k 3 || goto stopped
)
call :grade %B_OUT%
echo.
echo Finished. Reports: resolver_report.md and overall.md in %A_OUT% and %B_OUT%
pause
exit /b 0

:stopped
echo.
echo Stopped early. Finished answers are kept; run this again later to continue.
pause
exit /b 1

:make
echo.
echo  === %4 on %1 (%2) %5 %6 ===
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench make %1 --config %2 --model %4 --out %3 --ctx 16384 --no-mmap %5 %6; exit $LASTEXITCODE"
if errorlevel 3 (echo   STOPPED by the RAM guard or repeated failures - not grading. Report the STOPPED line.& exit /b 1)
if errorlevel 1 echo   %4 stopped with an error - continuing with the next model (finished answers are kept)
exit /b 0

:grade
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade %1 --no-open; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench compare %1; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench overall %1 | Tee-Object -FilePath %1\overall.md; exit 0"
exit /b 0
