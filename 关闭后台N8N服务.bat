@echo off
chcp 65001 >nul
echo ------------------------------------------
echo 🛑 正在关闭 N8N 后台服务...
echo ------------------------------------------

set "PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5678 ^| findstr LISTENING') do (
    if "%%a" NEQ "0" set PID=%%a
)

if "%PID%"=="" (
    echo ⚠️ 端口 5678 上没有正在运行的 N8N 服务，服务已自动关闭。
) else (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5678 ^| findstr LISTENING') do (
        if "%%a" NEQ "0" (
            echo 🔪 正在关闭进程 PID: %%a ...
            taskkill /F /PID %%a >nul 2>&1
        )
    )
    echo ✅ N8N 服务已成功彻底关闭！
)

echo.
echo 窗口将在 3 秒后关闭...
timeout /t 3 >nul 2>&1
exit
