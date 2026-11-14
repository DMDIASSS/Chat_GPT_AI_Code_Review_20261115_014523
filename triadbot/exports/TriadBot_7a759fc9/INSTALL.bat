@echo off
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo TRIAD_INSTALLED - add bot.portable.bot.toml in RLBot v5.
pause
exit /b 0
:failed
echo INSTALL_FAILED
pause
exit /b 1
