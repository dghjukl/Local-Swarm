@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - grade last evaluation
echo Grading the most recent evaluation again (no new runs)...
call "%~dp0Run-Evals.bat" --regrade last
