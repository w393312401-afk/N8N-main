@echo off
chcp 65001 >nul
title 关闭所有后台服务

echo ===========================================
echo   🛑 正在关闭所有 N8N 和 AI 后台服务...
echo ===========================================
echo.

:: ============================================
:: 1. 关闭 N8N 服务 (端口 5678)
:: ============================================
echo [1/2] 正在检测并关闭 N8N 服务 (Port: 5678)...
set "N8N_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5678 ^| findstr LISTENING 2^>nul') do (
    if "%%a" NEQ "0" set N8N_PID=%%a
)

if "%N8N_PID%"=="" (
    echo      [OK] 端口 5678 未被占用，N8N 已处于关闭状态。
) else (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5678 ^| findstr LISTENING 2^>nul') do (
        if "%%a" NEQ "0" (
            echo      🔪 正在关闭 N8N 进程 (PID: %%a)...
            taskkill /F /PID %%a >nul 2>&1
        )
    )
    echo      [OK] N8N 服务已成功关闭。
)
echo.

:: ============================================
:: 2. 关闭 AI 服务 (端口 8000)
:: ============================================
echo [2/2] 正在检测并关闭 AI 服务 (Port: 8000)...
set "AI_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING 2^>nul') do (
    if "%%a" NEQ "0" set AI_PID=%%a
)

if "%AI_PID%"=="" (
    echo      [OK] 端口 8000 未被占用，AI 服务已处于关闭状态。
) else (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING 2^>nul') do (
        if "%%a" NEQ "0" (
            echo      🔪 正在关闭 AI 服务进程 (PID: %%a)...
            taskkill /F /PID %%a >nul 2>&1
        )
    )
    echo      [OK] AI 服务已成功关闭。
)

:: ============================================
:: 3. 清理残留的 Playwright/Chromium 浏览器进程 (可选)
:: ============================================
echo.
echo 正在清理残留的浏览器驱动进程 (Chrome/Chromium)...
taskkill /F /IM chrome.exe /FI "WINDOWTITLE eq about:blank" >nul 2>&1
taskkill /F /IM msplaywright.exe >nul 2>&1

echo.
echo ===========================================
echo  ✅ 所有服务已彻底关闭！
echo ===========================================
echo.
echo 窗口将在 3 秒后关闭...
timeout /t 3 >nul 2>&1
exit
