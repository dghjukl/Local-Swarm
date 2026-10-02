@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - speed check
echo Re-running the mixed swarm on the same sources as the 26 Sep 16:36 evaluation (was 32s per question)...
call "%~dp0Run-Evals.bat" --configs swarm-mixed --reuse-evidence runtime\evals\20260926-1636
