@echo off
setlocal enabledelayedexpansion

echo   PremiumNumber Miner v3.0 - One-click Build Tool
echo   Adapted for v3 Contracts (CREATE2 Address Mining)
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo [2/3] Building .exe executable...
REM Build PyInstaller command arguments
set PYI_ARGS=--onefile --noconsole --name PremiumNumberMiner --icon=icon.ico

REM Check GPU module
if exist gpu_miner.py (
    echo        Including GPU mining module...
    set PYI_ARGS=!PYI_ARGS! --add-data "gpu_miner.py;."
)

REM Check config.yaml
if exist config.yaml (
    echo        Including default config file...
    set PYI_ARGS=!PYI_ARGS! --add-data "config.yaml;."
)

pyinstaller !PYI_ARGS! premium_miner.py
if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [3/3] Build completed!
echo   EXE Location: dist\PremiumNumberMiner.exe
echo.
echo   Usage:
echo   1. Double-click dist\PremiumNumberMiner.exe to run.
echo   2. For the first run, fill in your private key and connect wallet in the UI.
echo   3. Or edit config.yaml to configure your private key.
echo   4. Switch to the "Mine" tab and click "Start Mining".
echo.
pause
