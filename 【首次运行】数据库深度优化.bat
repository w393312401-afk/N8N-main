@echo off
chcp 65001 >nul
echo ------------------------------------------
echo 🔧 N8N SQLite 数据库一键深度优化工具
echo ------------------------------------------
echo.
echo ⚠️  请确保 N8N 已完全关闭后再运行此脚本！
echo.
pause

set "NODE_EXE=C:\Users\video\Desktop\node-v22.16.0-win-x64\node.exe"
set "DB_PATH=C:\Users\video\.n8n\database.sqlite"
set "SCRIPT=%~dp0tools\optimize_db.js"

if not exist "%NODE_EXE%" (
    echo ❌ 找不到 Node.js: %NODE_EXE%
    pause & exit
)

if not exist "%DB_PATH%" (
    echo ❌ 找不到数据库文件: %DB_PATH%
    pause & exit
)

if not exist "%SCRIPT%" (
    echo ❌ 找不到优化脚本: %SCRIPT%
    pause & exit
)

echo.
echo 📊 正在运行数据库优化...
echo.

set DB_PATH=%DB_PATH%
"%NODE_EXE%" "%SCRIPT%"

echo.
echo 窗口将在 8 秒后关闭...
timeout /t 8 >nul 2>&1
exit
