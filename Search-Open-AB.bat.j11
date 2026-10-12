@echo off
rem J11: mgr-ex-base vs the same team with open_entities + short_retry, 100 questions, same saved sources.
setlocal
cd /d "%~dp0"
title Local Swarm - J11: search A/B (entity-open + short-query retry) on frames-100
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%t
if not exist runtime\logs mkdir runtime\logs
set GPULOG=runtime\logs\gpu-%STAMP%.csv
set RAMLOG=runtime\logs\ram-%STAMP%.csv
echo.
echo  J11. Nothing else on the GPU. Expect 4-5 hours. GPU log: %GPULOG%   RAM log: %RAMLOG%
echo.
start "gpu-log" /min nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.sm,clocks_throttle_reasons.active --format=csv -l 15 -f %GPULOG%
start "ram-log" /min typeperf "\Memory\Available MBytes" "\Memory\Committed Bytes" "\Processor(_Total)\%% Processor Time" -si 15 -o %RAMLOG% -y
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs mgr-ex-base,mgr-ex-base-open --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retry
if "%rc%"=="0" goto done
set /a tries+=1
if %tries% GTR 3 goto done
echo  The run stopped unexpectedly (code %rc%). Continuing in 20 seconds (attempt %tries% of 3)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retry
:done
taskkill /FI "WINDOWTITLE eq gpu-log*" /T /F >nul 2>&1
taskkill /IM nvidia-smi.exe /F >nul 2>&1
taskkill /IM typeperf.exe /F >nul 2>&1
echo.
echo Finished. See the newest folder in runtime\evals (report.md, events.log).
call "%~dp0scripts\notify.bat" "J11" %rc% "search A/B finished; see report.md"
pause
