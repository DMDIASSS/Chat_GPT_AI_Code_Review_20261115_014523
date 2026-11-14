@echo off
setlocal
cd /d "%~dp0"
echo Launching rlviser: New Galactus (galactus_apex_v1, Octane) vs Original Galactus...
call "%~dp0_RUN.bat" run watch --run research03 --family galactus --candidate --opponent galactus
if errorlevel 1 pause
exit /b %errorlevel%
