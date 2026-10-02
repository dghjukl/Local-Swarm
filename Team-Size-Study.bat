@echo off
setlocal
cd /d "%~dp0"
title Local Swarm - team size study
echo.
echo  Team-size study: 20 questions x (coordinator alone, then 1,2,3,4,5 workers).
echo  Expect roughly 1.5 hours. Close Start-Swarm first. You can leave it running.
echo.
call "%~dp0Run-Evals.bat" --configs team-size
