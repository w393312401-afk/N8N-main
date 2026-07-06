@echo off
chcp 65001 >nul
title AdsPower AI Service

echo ============================================
echo   AdsPower All-in-One AI Service Starting
echo ============================================
echo.

REM Check Python
python --version >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install python-multipart playwright fastapi uvicorn requests 2>nul

echo.
echo [2/3] Installing Playwright browser driver...
python -m playwright install chromium 2>nul

echo.
echo [3/3] Starting AI service...
echo.
echo     Address: http://127.0.0.1:8000
echo     Close this window to stop the service.
echo.

REM Set PYTHONPATH to core directory
set "SCRIPT_DIR=%~dp0"
set "PYTHONPATH=%SCRIPT_DIR%core"

REM Change to core directory for uvicorn module discovery
cd /d "%SCRIPT_DIR%core"
python app.py

pause