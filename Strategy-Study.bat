@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - strategy study
echo.
echo  STRATEGY STUDY - which way of thinking suits each answer model?
echo    - Qwen3.5-9B, Gemma-4-E4B and Ministral-3-8B, each ALONE as the worker
echo    - each tries all 8 ways of thinking (direct, linear, chain of thought, self-ask,
echo      step back, self-consistency, tree of thoughts, scratchpad)
echo    - the 9B and Gemma also try their own built-in thinking mode
echo    - 23 questions from the new set; web research is done ONCE at the start and saved,
echo      so every model and every way of thinking reads exactly the same pages
echo    - no coordinator: each worker's own answers are graded, so the grade measures the worker
echo  Expect about 9-11 hours. Close Chrome, Start-Swarm and other programs first.
echo  If it stops (power, restart), run Resume-Last-Eval.bat and it continues where it left off.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs strategy-study --set evals/research_v4.yaml --questions lz-2026,pah-pathway-2026,stair-climbing-2026,tilcayo-cat-2026,gpnmb-cart-2026,roman-first-images-trap-2026,ai-brain-surgery-2026,antarctica-ice-gain-2026,gaia20ehk-collision-2026,ross-318-b-2026,youngest-planet-2026,lhc-disconnection-2026,tianwen-2-samples-trap-2026,ocean-census-2026,ptau217-blood-test-2026,hiv-apex-antibodies-2026,pig-kidney-bridge-2026,retatrutide-approval-trap-2026,antarctica-first-dinosaur-bone-2026,dom-van-keulen-2026,glacier-loss-2025-2026,robot-half-marathon-2026,sparc-first-plasma-trap-2026 --no-open"
set rc=%ERRORLEVEL%
echo.
echo Finished. The report is in runtime\evals\ (newest folder) - see the "Strategy screen" section.
call "%~dp0scripts\notify.bat" "Strategy-Study" %rc% "study finished; see runtime\evals"
pause
