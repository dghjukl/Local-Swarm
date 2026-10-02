@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - resume evaluation
echo Continuing the most recent evaluation where it stopped (finished runs are kept)...
call "%~dp0Run-Evals.bat" --resume last
