@echo off
cd /d "%~dp0"
title Local Swarm - round 2: Nemotron redo
echo  Redoes Nemotron-Nano-9B in the round 2 study (fixed thinking switch), then grades.
call "%~dp0Run-Evals.bat" --resume runtime/evals/20261001-0717 --no-open
