@echo off
title Zenith Non-Stop RL Master Trainer
cd /d "E:\Downloads\Chat_GPT_AI\zenith"

set PYTHON_BIN=E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe
set PYTHONPATH=E:\Downloads\Chat_GPT_AI\zenith;%PYTHONPATH%

echo =====================================================================
echo                     ZENITH NON-STOP RL MASTER TRAINER
echo =====================================================================
echo Launching Zenith non-stop training loop with:
echo   - Native RocketSim C++ multi-arena simulation (24 arenas / 48 agents)
echo   - Student Policy (145 dims, 90 actions) with Top-p nucleus sampling (p=0.90)
echo   - 12 decomposed reward components
echo   - KL Distillation kickstarting against Chronos & Galactus
echo   - 5 curriculum skill drills (Flip Reset Musty, Prejump saves, Anti-fake)
echo   - Prioritized Fictitious Self-Play (PFSP)
echo   - Continuous Referee gauntlet with automatic rollback guard
echo =====================================================================

:loop
echo [%date% %time%] Starting Zenith Trainer...
"%PYTHON_BIN%" -u -m zenith.train --arenas 24 --rollout 128 --eval-interval 30000 --snapshot-interval 15000 --target-steps 20000000
echo [%date% %time%] Process ended with exit code %ERRORLEVEL%.
echo Restarting in 5 seconds... Press Ctrl+C to abort.
timeout /t 5
goto loop
