@echo off
setlocal
cd /d "%~dp0"
echo Launching rlviser: New Chronos (chronos_lowtemp_swa, Breakout) vs Original Chronos...
call "%~dp0_RUN.bat" run watch --run research03 --family chronos --trial 1 --opponent chronos
if errorlevel 1 pause
exit /b %errorlevel%
