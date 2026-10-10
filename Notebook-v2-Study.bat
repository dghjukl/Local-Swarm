@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - notebook v2 study
echo.
echo  NOTEBOOK v2 + LEADER BAKE-OFF on the same saved pages and 23 questions as the first notebook study.
echo  v2 fixes: the same fact found by two members is merged, junk notes are dropped, failed fact-checks
echo  are retried, and the writer cites only sources. The team is the same every time; only the LEADER
echo  (who writes the answer from the notebook) changes:
echo   - MiMo-9B on the GPU (the reference)
echo   - Qwen3.5-4B, Qwen3.5-2B, LFM2.5-1.2B on the CPU (they never take VRAM)
echo   - MiMo alone and the 4B alone (anchors)
echo  Expect about 4-5 hours. If it crashes it restarts itself; after a power cut run Resume-Last-Eval.bat.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --configs notebook-v2 --set evals/research_v4.yaml --questions lz-2026,pah-pathway-2026,stair-climbing-2026,tilcayo-cat-2026,gpnmb-cart-2026,roman-first-images-trap-2026,ai-brain-surgery-2026,antarctica-ice-gain-2026,gaia20ehk-collision-2026,ross-318-b-2026,youngest-planet-2026,lhc-disconnection-2026,tianwen-2-samples-trap-2026,ocean-census-2026,ptau217-blood-test-2026,hiv-apex-antibodies-2026,pig-kidney-bridge-2026,retatrutide-approval-trap-2026,antarctica-first-dinosaur-bone-2026,dom-van-keulen-2026,glacier-loss-2025-2026,robot-half-marathon-2026,sparc-first-plasma-trap-2026 --reuse-evidence runtime/evals/20260928-1323 --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
set tries=0
:retry
if "%rc%"=="0" goto done
set /a tries+=1
if %tries% GTR 5 goto done
echo.
echo  The run stopped unexpectedly (code %rc%). Continuing where it left off in 20 seconds (attempt %tries% of 5)...
timeout /t 20 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0scripts\env.ps1'; & '%~dp0tools\uv\uv.exe' sync --quiet; & '%~dp0.venv\Scripts\python.exe' -m swarm.evals --resume last --no-open; exit $LASTEXITCODE"
set rc=%ERRORLEVEL%
goto retry
:done
echo.
echo Finished. The report is in runtime\evals\ (newest folder).
call "%~dp0scripts\notify.bat" "Notebook-v2-Study" %rc% "study finished; see runtime\evals"
pause
