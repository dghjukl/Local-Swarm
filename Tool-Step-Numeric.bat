@echo off
rem J14: mgr-ex-base vs mgr-ex-base-tools on the 63 numeric/date questions from J11, same saved sources.
setlocal
cd /d "%~dp0"
title Local Swarm - J14: tool step (calculator, dates, units) vs base on the 63 numeric questions
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%t
if not exist runtime\logs mkdir runtime\logs
set GPULOG=runtime\logs\gpu-%STAMP%.csv
set RAMLOG=runtime\logs\ram-%STAMP%.csv
echo.
echo  J14. Nothing else on the GPU. Expect about 2.5 hours. GPU log: %GPULOG%   RAM log: %RAMLOG%
echo.
start "gpu-log" /min nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.sm,clocks_throttle_reasons.active --format=csv -l 15 -f %GPULOG%
start "ram-log" /min typeperf "\Memory\Available MBytes" "\Memory\Committed Bytes" "\Processor(_Total)\%% Processor Time" -si 15 -o %RAMLOG% -y
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs mgr-ex-base,mgr-ex-base-tools --set runtime/benchmarks/frames-100.yaml --questions frames-1,frames-9,frames-16,frames-25,frames-29,frames-32,frames-64,frames-92,frames-93,frames-100,frames-103,frames-137,frames-171,frames-173,frames-177,frames-183,frames-192,frames-200,frames-219,frames-238,frames-243,frames-248,frames-266,frames-284,frames-295,frames-331,frames-364,frames-370,frames-378,frames-411,frames-432,frames-435,frames-439,frames-455,frames-473,frames-489,frames-518,frames-523,frames-549,frames-562,frames-572,frames-579,frames-580,frames-605,frames-636,frames-637,frames-638,frames-644,frames-668,frames-685,frames-691,frames-695,frames-703,frames-704,frames-705,frames-725,frames-740,frames-745,frames-750,frames-807,frames-808,frames-817,frames-818 --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "J14" %rc% "tool step run finished; see report.md"
pause
