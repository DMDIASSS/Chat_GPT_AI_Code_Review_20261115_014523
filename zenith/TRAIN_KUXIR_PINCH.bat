@echo off
title Zenith Autonomous Kuxir Pinch Engine
color 0b
cd /d "%~dp0"

set PYTHON_BIN=E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe
set PYTHONPATH=%~dp0;%~dp0..;%PYTHONPATH%
set PYTHONIOENCODING=utf-8

echo ===============================================================================
echo                    ZENITH AUTONOMOUS KUXIR PINCH ENGINE
echo ===============================================================================
echo  * Base Model     : Nexto Student (Warm-Start with SSL Car-Control Mechanics)
echo  * Mechanics Focus: 1) Wall-Roll Setup + 2) Supersonic Kuxir Pinch Shots
echo  * Reward Metric  : Quadratic Scaling with Ball Exit Velocity (Faster = Better!)
echo  * Protection     : Frozen Nexto KL Divergence Anchor (Zero Skill Degradation)
echo  * Simulation     : 16 Parallel RocketSim Soccar Arenas (Multi-Threaded)
echo  * Hot-Reloading  : Live checkpointers stream straight to 3D RLViser
echo  * Pause / Stop   : Press Ctrl+C at any time to pause and save weights
echo ===============================================================================
echo.

"%PYTHON_BIN%" -u "%~dp0train_kuxir.py" %*
pause
