@echo off
setlocal
cd /d "%~dp0"
echo Launching rlviser [DEFENSIVE DRILLS]: New Defensive Chronos (research04 Trial 1, Breakout) vs Original Chronos...
".\.venv_native\Scripts\python.exe" -u watch_custom.py --run research04 --trial 1 --opponent original_chronos --profile defense
if errorlevel 1 pause
exit /b %errorlevel%
