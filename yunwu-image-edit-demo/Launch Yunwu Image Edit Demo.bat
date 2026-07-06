@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Yunwu Image Edit Demo

where python >nul 2>nul
if %errorlevel%==0 (
  python launcher.py
) else (
  py launcher.py
)

if errorlevel 1 (
  echo.
  echo Launch failed. Check Python availability or port usage.
  pause
)
