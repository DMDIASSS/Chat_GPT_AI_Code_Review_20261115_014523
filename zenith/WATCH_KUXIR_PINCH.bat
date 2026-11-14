@echo off
title Zenith Kuxir Pinch 3D Live Spectator (RLViser)
color 0a
cd /d "%~dp0"

set PYTHON_BIN=E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe
set PYTHONPATH=%~dp0;%~dp0..;%PYTHONPATH%
set PYTHONIOENCODING=utf-8

echo ===============================================================================
echo                ZENITH KUXIR PINCH 3D REAL-TIME SPECTATOR
echo ===============================================================================
echo  * Visualizer    : Standalone RLViser 3D Window (Single-Instance Follow-Cam)
echo  * Camera        : Ball-Cam Locked on Learner Bot (Wall Tracking)
echo  * Hot-Reloading : Auto-detects newly saved training checkpoints in real-time
echo  * Live Telemetry: Terminal HUD displays ball speed (km/h), pinches, and goals
echo  * Spacebar      : Pause/Resume inside RLViser window
echo ===============================================================================
echo.

"%PYTHON_BIN%" -u "%~dp0watch_kuxir.py" %*
pause
