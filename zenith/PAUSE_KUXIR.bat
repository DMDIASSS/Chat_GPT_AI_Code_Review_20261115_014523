@echo off
title Pause Zenith Kuxir Pinch Training
color 0e
cd /d "%~dp0"

echo ===============================================================================
echo                    PAUSING ZENITH KUXIR PINCH TRAINING
echo ===============================================================================
echo Stopping background training and spectator processes gracefully...

taskkill /F /FI "WINDOWTITLE eq Zenith Autonomous Kuxir Pinch Engine*" /T 2>nul
taskkill /F /FI "WINDOWTITLE eq Zenith Kuxir Pinch 3D Live Spectator*" /T 2>nul
taskkill /F /IM "rlviser.exe" 2>nul
taskkill /F /IM "rlviser-rs.exe" 2>nul

echo Done! Training progress is saved in zenith\runs\kuxir_pinch\checkpoints\
echo.
pause
