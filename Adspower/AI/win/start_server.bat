@echo off
chcp 65001 >nul
REM ============================================================
REM  🚀 AdsPower AI 服务 — Windows 启动脚本
REM  双击此文件即可启动服务
REM ============================================================

echo.
echo  ========================================================
echo   AdsPower AI 服务启动器 (Windows)
echo  ========================================================
echo.
echo  📋 启动前请确认：
echo     1. AdsPower 客户端已打开
echo     2. Python 3 已安装
echo.

REM 获取脚本所在目录（即 win\ 目录）
set SCRIPT_DIR=%~dp0
REM 项目根目录（AI\ 目录）
set PROJECT_DIR=%SCRIPT_DIR%..
set CORE_DIR=%PROJECT_DIR%\core

echo  🔍 检查并安装 Python 依赖...
pip install python-multipart playwright fastapi uvicorn requests python-dotenv 2>nul
if errorlevel 1 (
  echo  ❌ 依赖安装失败，请确认 Python 和 pip 已正确安装
  pause
  exit /b 1
)

echo  🔍 检查 Playwright Chromium...
python -m playwright install chromium 2>nul

echo.
echo  🚀 正在启动服务，请稍等...
echo  📡 服务地址: http://127.0.0.1:8000
echo  📁 生成文件: %USERPROFILE%\Desktop\AI生成\
echo.
echo  ⚠️  请保持此窗口不要关闭，关闭则服务停止
echo  💡 健康检查: 打开浏览器访问 http://127.0.0.1:8000/
echo.

set PYTHONPATH=%CORE_DIR%
cd /d "%CORE_DIR%"
python app.py

echo.
echo  服务已停止。
pause
