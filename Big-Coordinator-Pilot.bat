@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - J9: big-coordinator pilot (Gemma-4-12B directs; alone vs 4 teammates in two sets), 8 questions
rem Pilot, not the study: 8 FRAMES questions, two configs, to measure what the swap-heavy loop COSTS and whether it works
rem (time per question, model loads per question, RAM and VRAM, any freeze) before the 100-question study.
rem   big12-alone : Gemma-4-12B-it does every step itself
rem   big12-team4 : Gemma-4-12B-it directs Qwen3.5-4B + Qwen3.5-9B (set 1), then Gemma-4-E4B + Apertus-8B (set 2)
rem Same saved sources as the vote runs (runtime/evals/20261004-2126). GPU and RAM are logged every 15 s like J7b.
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%t
if not exist runtime\logs mkdir runtime\logs
set GPULOG=runtime\logs\gpu-%STAMP%.csv
set RAMLOG=runtime\logs\ram-%STAMP%.csv
echo.
echo  J9 pilot. Nothing else on the GPU. Expect 1-3 hours. GPU log: %GPULOG%   RAM log: %RAMLOG%
echo.
start "gpu-log" /min nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,temperature.gpu,power.draw,clocks.sm,clocks_throttle_reasons.active --format=csv -l 15 -f %GPULOG%
start "ram-log" /min typeperf "\Memory\Available MBytes" "\Memory\Committed Bytes" "\Processor(_Total)\%% Processor Time" -si 15 -o %RAMLOG% -y
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs big12-alone,big12-team4 --set runtime/benchmarks/frames-100.yaml --questions frames-0,frames-1,frames-9,frames-16,frames-25,frames-29,frames-32,frames-48 --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
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
call "%~dp0scripts\notify.bat" "J9" %rc% "big-coordinator pilot finished; see report.md"
pause
