@echo off
title Zenith 3D Live Spectator (RLViser)
color 0a
cd /d "%~dp0"

set PYTHON_BIN=E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe
set PYTHONPATH=%~dp0;%PYTHONPATH%

echo ===============================================================================
echo                    ZENITH 3D REAL-TIME LIVE SPECTATOR
echo ===============================================================================
echo  * Visualizer    : Native 3D RLViser Window (No Rocket League game required)
echo  * Match Type    : Zenith Self-Play 1v1 (Blue vs Orange)
echo  * Hot-Reloading : Live policy update whenever background training saves
echo  * Performance   : ~1%% CPU (Completely safe while training runs in background)
echo  * Camera        : Left-click drag to rotate, right-click to pan, scroll to zoom
echo  * Simulation    : Spacebar inside 3D window to pause/unpause
echo ===============================================================================
echo.
"%PYTHON_BIN%" -u "%~dp0watch_live.py" %*
pause
