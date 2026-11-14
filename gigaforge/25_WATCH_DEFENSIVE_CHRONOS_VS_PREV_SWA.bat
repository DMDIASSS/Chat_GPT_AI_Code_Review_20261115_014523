@echo off
setlocal
cd /d "%~dp0"
echo Launching rlviser: New Defensive Chronos (research04 Trial 1, Breakout) vs Previous Preview (chronos_lowtemp_swa)...
".\.venv_native\Scripts\python.exe" -u watch_custom.py --run research04 --trial 1 --opponent chronos_lowtemp_swa --profile match
if errorlevel 1 pause
exit /b %errorlevel%
