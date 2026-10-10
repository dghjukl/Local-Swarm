@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - live escalation study (J7): 3 attempts + vote, then Qwen3.8-27B when they disagree
rem J6: on the 3-attempt vote study's split questions, Qwen3.8-27B (all on the GPU) rescued 7 and broke 1
rem (+6 net, 60%% -> 66%% overall). This runs it LIVE: mgr-vote3-resolve-q38 = mgr-vote3-same, and when the
rem 3 attempts disagree the workers are unloaded and Qwen3.8-27B answers from the research packet.
rem The vote's own pick is graded as one of the attempts, so this one run gives "vote alone" and
rem "vote + resolver" on the very same attempts (paired), without a second control run.
echo.
echo  LIVE ESCALATION STUDY on the 100 FRAMES questions (same saved sources as the vote study).
echo  Config: mgr-vote3-resolve-q38. Nothing else on the GPU; close other big apps.
echo  Expect about 7-9 hours. If it crashes it restarts itself; after a power cut run Resume-Last-Eval.bat.
echo  The resolver skips (keeps the vote) if free RAM is under 1.5 GB.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs mgr-vote3-resolve-q38 --set runtime/benchmarks/frames-100.yaml --reuse-evidence runtime/evals/20261004-2126 --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retry
if "%rc%"=="0" goto report
set /a tries+=1
if %tries% GTR 5 goto done
echo.
echo  The run stopped unexpectedly (code %rc%). Continuing where it left off in 20 seconds (attempt %tries% of 5)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retry
:report
echo.
echo  Vote alone vs vote + resolver (paired, same attempts):
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; $d = (Get-ChildItem runtime\evals -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'results.jsonl') } | Sort-Object Name | Select-Object -Last 1).FullName; & '%~dp0.venv\Scripts\python.exe' -m swarm.resolver_bench live $d --config mgr-vote3-resolve-q38; exit 0"
:done
echo.
echo Finished. Reports: the newest folder in runtime\evals\ (report.md and live_mgr-vote3-resolve-q38.md)
pause
