@echo off
title HireTrace Live Dashboard Launcher
echo ===================================================================
echo                     HIRETRACE LIVE LAUNCHER
echo              Zero Paid API Calls - 100%% Offline Evaluator
echo ===================================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH!
    echo Please make sure Python is installed and accessible in your environment.
    pause
    exit /b 1
)

set HIRETRACE_DEV_MODE=1
python run_live.py
if %errorlevel% neq 0 (
    echo.
    echo Server stopped with exit code %errorlevel%.
    pause
)
