@echo off
title Pause Zenith
color 0e
cd /d "%~dp0"

echo ===============================================================================
echo                           PAUSE ZENITH TRAINING
echo ===============================================================================
echo Sending pause signal to Zenith...
if not exist "%~dp0zenith\runs\zenith_scratch_01" mkdir "%~dp0zenith\runs\zenith_scratch_01"
echo pause > "%~dp0zenith\runs\zenith_scratch_01\PAUSE"

echo.
echo [OK] Pause signal sent!
echo Zenith will finish its current rollout, safely save full progress, and exit.
echo To resume training later, simply run START_AUTONOMOUS_ZENITH.bat.
echo ===============================================================================
echo.
timeout /t 5
