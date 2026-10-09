@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - regrade the last three studies with the judge's second look (J3)
echo.
echo  J3: regrade with judge.recheck on (evals/configs.yaml). Nothing new is run; only grading.
echo  The originals are left untouched: each study is copied to a "-recheck" folder first and the
echo  copy is regraded (final answers AND every individual attempt).
echo    20261008-0650  scaling study, 8 attempts
echo    20261006-1714  vote study
echo    20261007-1559  trust study
echo  Uses the GPU (the judge). Do not start another study at the same time. Expect about 2-4 hours.
echo.
for %%R in (20261008-0650 20261006-1714 20261007-1559) do call :one %%R
echo.
echo Finished. Compare runtime\evals\^<run^>\report.md with runtime\evals\^<run^>-recheck\report.md
pause
exit /b 0

:one
set RUN=runtime\evals\%1
set COPY=runtime\evals\%1-recheck
if not exist "%COPY%\results.jsonl" (
  echo Copying %RUN% to %COPY% ...
  robocopy "%RUN%" "%COPY%" /E /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 (echo   copy FAILED for %1 - skipping & exit /b 1)
)
echo Regrading %COPY% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade %COPY:\=/% --no-open; exit $LASTEXITCODE"
if errorlevel 1 (
  echo   grading stopped for %1 - running it once more to finish ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade %COPY:\=/% --no-open; exit $LASTEXITCODE"
)
exit /b 0
