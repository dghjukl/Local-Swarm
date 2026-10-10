@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - J7b: fresh 3-attempt vote run, then Qwen3.8-27B resolves the split questions in one batch
rem J7 (live escalation) ran 27 questions fine, then the PC hard-froze at about 03:30-04:06. No WHEA or GPU-driver
rem event was logged. The new factor vs the long runs that never froze (vote study, 8-attempt study) was the
rem model churn: every escalation unloaded and reloaded all models twice (76 loads in 2 hours).
rem J7b gets the same measurement without the churn:
rem   1. mgr-vote3-same on all 100 FRAMES questions (fresh attempts; the swarm stays loaded, like the vote study)
rem   2. Qwen3.8-27B then resolves every split question in ONE session (one load) - same packet, same prompt
rem   3. the vote and the resolver answers are graded together
rem It also logs the GPU (utilisation, VRAM, temperature, power, clocks) and RAM every 15 s to runtime\logs,
rem so if anything freezes again the last lines show what the machine was doing.
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%t
if not exist runtime\logs mkdir runtime\logs
set GPULOG=runtime\logs\gpu-%STAMP%.csv
set RAMLOG=runtime\logs\ram-%STAMP%.csv
echo.
echo  J7b. Nothing else on the GPU; close other big apps. Expect about 7-8 hours.
echo  GPU log: %GPULOG%   RAM log: %RAMLOG%
echo.
start "gpu-log" /min nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.sm,clocks_throttle_reasons.active --format=csv -l 15 -f %GPULOG%
start "ram-log" /min typeperf "\Memory\Available MBytes" "\Memory\Committed Bytes" "\Processor(_Total)\%% Processor Time" -si 15 -o %RAMLOG% -y
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs mgr-vote3-same --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retry
if "%rc%"=="0" goto resolve
set /a tries+=1
if %tries% GTR 5 goto done
echo  The run stopped unexpectedly (code %rc%). Continuing in 20 seconds (attempt %tries% of 5)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retry
:resolve
for /f "delims=" %%d in ('powershell -NoProfile -Command "(Get-ChildItem runtime\evals -Directory | Where-Object { $_.Name -match '^\d{8}-\d{4}$' -and (Test-Path (Join-Path $_.FullName 'results.jsonl')) } | Sort-Object Name | Select-Object -Last 1).Name"') do set RUN=%%d
set OUT=runtime/evals/resolver-j7b-%RUN%
echo.
echo  Resolving the split questions of %RUN% with Qwen3.8-27B (one load) into %OUT% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench make runtime/evals/%RUN% --config mgr-vote3-same --model Qwen3.8-27B --out %OUT% --ctx 16384 --no-mmap; exit $LASTEXITCODE"
if errorlevel 3 (echo   STOPPED by the RAM guard or repeated failures - not grading. Report the STOPPED line.& goto done)
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --regrade %OUT% --no-open; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench compare %OUT%; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench overall %OUT% | Out-File -Encoding utf8 %OUT%\overall.md; Get-Content %OUT%\overall.md; exit 0"
:done
taskkill /FI "WINDOWTITLE eq gpu-log*" /T /F >nul 2>&1
taskkill /IM nvidia-smi.exe /F >nul 2>&1
taskkill /IM typeperf.exe /F >nul 2>&1
echo.
echo Finished. Run report: runtime\evals\%RUN%\report.md ; resolver: %OUT%\resolver_report.md and overall.md
pause
