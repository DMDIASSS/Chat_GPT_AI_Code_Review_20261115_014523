@echo off
setlocal
cd /d "%~dp0"
echo Exporting research03 candidate actors (chronos_lowtemp_swa + galactus_apex_v1) to exports\research03...
call "%~dp0_RUN.bat" run export --run research03 --candidate
if errorlevel 1 goto failed
echo.
echo RLBot v5 bundles exported to: %~dp0exports\research03
pause
exit /b 0
:failed
echo EXPORT_FAILED
pause
exit /b 1
