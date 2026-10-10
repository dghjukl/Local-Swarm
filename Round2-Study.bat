@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - round 2 study
echo.
echo  ROUND 2 STUDY (needs Sync-Models.bat first):
echo   1. New worker candidates - Olmo-3, Nemotron-Nano-9B, Falcon-H1R, MiMo (Xiaomi), Granite-4.2 3B/8B,
echo      Kanana-2 (Kakao), Jamba2 (AI21), Apertus (Swiss AI), rnj-1.5 (Essential AI) - each alone,
echo      answering directly and with step back / self-ask, on the SAME saved pages and 23 questions as
echo      the strategy study, so they line up with Qwen3.5-9B, Gemma and Ministral.
echo   2. Verifier bench: real claims from the strategy study, checked by each fact-checker candidate
echo      (Granite 4.1/4.2, Granite Guardian, and others) against two reference judges.
echo  Expect about 5 hours. If it crashes it restarts itself; after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs round2-screen --set evals/research_v4.yaml --questions lz-2026,pah-pathway-2026,stair-climbing-2026,tilcayo-cat-2026,gpnmb-cart-2026,roman-first-images-trap-2026,ai-brain-surgery-2026,antarctica-ice-gain-2026,gaia20ehk-collision-2026,ross-318-b-2026,youngest-planet-2026,lhc-disconnection-2026,tianwen-2-samples-trap-2026,ocean-census-2026,ptau217-blood-test-2026,hiv-apex-antibodies-2026,pig-kidney-bridge-2026,retatrutide-approval-trap-2026,antarctica-first-dinosaur-bone-2026,dom-van-keulen-2026,glacier-loss-2025-2026,robot-half-marathon-2026,sparc-first-plasma-trap-2026 --reuse-evidence runtime/evals/20260928-1323 --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retryA
if "%rc%"=="0" goto doneA
set /a tries+=1
if %tries% GTR 5 goto doneA
echo.
echo  The run stopped unexpectedly (code %rc%). Continuing where it left off in 20 seconds (attempt %tries% of 5)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retryA
:doneA
echo.
echo  Step 2: verifier bench...
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.verifier_bench --from runtime/evals/20260928-1323; exit $LASTEXITCODE"
echo.
echo Finished. The report is in runtime\evals\ (newest folders).
call "%~dp0scripts\notify.bat" "Round2-Study" %rc% "study finished; see runtime\evals"
pause
