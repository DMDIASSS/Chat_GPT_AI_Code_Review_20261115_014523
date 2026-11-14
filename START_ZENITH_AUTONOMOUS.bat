@echo off
title Zenith Autonomous RL Engine (From Scratch)
color 0b
cd /d "%~dp0zenith"

set PYTHON_BIN=E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe
set PYTHONPATH=%~dp0zenith;%PYTHONPATH%

echo ===============================================================================
echo                 ZENITH AUTONOMOUS FROM-SCRATCH RL ENGINE
echo ===============================================================================
echo  * Initialization : 100%% Fresh Orthogonal Weights (Zero Pretrained Dependencies)
echo  * Architecture   : Compact 256-width Dual-Trunk Actor-Critic (~231k params)
echo  * Simulator      : Native RocketSim C++ Multi-Arena Pool (32 Arenas / 64 Cars)
echo  * Self-Pacing    : Automatic SPS ^& Rollout Scaling (32k -^> 64k -^> 128k -^> 256k)
echo  * Protection     : Live Regression Detection + Auto-Rollback to Best Checkpoint
echo  * Live Export    : Auto-exports ready-to-run bot to zenith\export\zenith_rlbot\
echo  * Pause / Save   : Press Ctrl+C or run PAUSE_ZENITH.bat at any time to pause
echo ===============================================================================
echo.

:loop
echo [%date% %time%] Launching / Resuming Zenith Autonomous Engine...
"%PYTHON_BIN%" -u -m zenith.autonomous --arenas 32 --target-steps 100000000
echo.
echo [Zenith] Engine paused or completed. Progress has been saved.
echo Press any key to resume training, or close this window to exit.
pause
goto loop
