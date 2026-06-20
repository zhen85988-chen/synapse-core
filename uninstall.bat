@echo off
chcp 65001 >nul 2>&1
title Synapse Core — Uninstall
echo.
echo   Uninstalling Synapse Core MCP config...
echo.
python "%~dp0uninstall.py"
pause
