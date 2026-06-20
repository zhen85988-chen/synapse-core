@echo off
chcp 65001 >nul 2>&1
title Synapse Core — Setup Wizard
echo.
echo   Running Synapse Core Setup Wizard...
echo.
echo   卸载: uninstall.bat
echo.
python "%~dp0setup_wizard.py"
pause
