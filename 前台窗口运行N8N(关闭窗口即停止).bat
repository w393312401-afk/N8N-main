@echo off
chcp 65001 >nul
title N8N 前台运行服务 (关闭此窗口即停止服务)

cd /d "%~dp0"
echo ===========================================
echo   N8N Foreground Service Launcher
echo   提示：关闭当前窗口即可直接停止 N8N 服务
echo ===========================================
echo.

:: ============================================
:: 步骤 1: 清理旧的 N8N 进程，防止端口占用
:: ============================================
echo [1/3] 正在检查并清理旧的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5678 " ^| findstr LISTENING 2^>nul') do (
    if "%%a" NEQ "0" (
        echo       发现端口 5678 已被占用，正在结束 PID 为 %%a 的进程...
        taskkill /F /PID %%a >nul 2>&1
    )
)

:: 稍微等待端口释放
ping -n 2 127.0.0.1 >nul 2>&1

:: ============================================
:: 步骤 2: 环境变量配置 (与后台运行配置完全一致)
:: ============================================
echo [2/3] 配置运行环境...
set "PATH=C:\Users\video\Desktop\node-v22.16.0-win-x64;%PATH%"
set NODE_OPTIONS=--max-old-space-size=8192 --max-semi-space-size=128 --v8-pool-size=16
set UV_THREADPOOL_SIZE=16
set NODE_FUNCTION_ALLOW_BUILTIN=*
set NODE_FUNCTION_ALLOW_EXTERNAL=*

set N8N_USER_FOLDER=C:\Users\video
set N8N_PORT=5678
set N8N_PROTOCOL=http
set N8N_HOST=0.0.0.0
set WEBHOOK_URL=http://127.0.0.1:5678/
set N8N_EDITOR_BASE_URL=http://127.0.0.1:5678
set N8N_RESTRICT_FILE_ACCESS_TO=
set NODES_EXCLUDE=[]
set N8N_ONLOAD_TIMEOUT=0

set DB_TYPE=sqlite
set DB_SQLITE_DATABASE=C:\Users\video\.n8n\database.sqlite
set N8N_ENCRYPTION_KEY=Cv3cAjormlu9956Uk/ywjVOjKSxGdEpv

set EXECUTIONS_DATA_SAVE_ON_SUCCESS=all
set EXECUTIONS_DATA_SAVE_ON_ERROR=all
set EXECUTIONS_DATA_SAVE_ON_PROGRESS=true
set EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=true
set EXECUTIONS_DATA_MAX_AGE=72
set EXECUTIONS_DATA_PRUNE_MAX_COUNT=1000

set N8N_DEFAULT_EXECUTION_TIMEOUT=1800
set N8N_MAX_EXECUTION_TIMEOUT=1800
set N8N_RUNNERS_TASK_TIMEOUT=1800
set N8N_CONCURRENCY_PRODUCTION_LIMIT=3
set N8N_PAYLOAD_SIZE_MAX=64
set N8N_DEFAULT_BINARY_DATA_MODE=filesystem

set N8N_DIAGNOSTICS_ENABLED=false
set N8N_VERSION_NOTIFICATIONS_ENABLED=false
set N8N_PERSONALIZATION_ENABLED=false
set N8N_TEMPLATES_ENABLED=false
set N8N_HIRING_BANNER_ENABLED=false
set N8N_COMMUNITY_PACKAGES_ENABLED=false

set NO_UPDATE_NOTIFIER=1
set npm_config_update_notifier=false
set N8N_MIGRATE_FS_STORAGE_PATH=true
set N8N_BLOCK_ENV_ACCESS_TO_IP_RANGES=
set N8N_BANNED_IP_ROUTABLE_ALLOWLIST=127.0.0.1,192.168.0.0/16
set N8N_SSRF_ALLOWED_HOSTNAMES=*

:: ============================================
:: 步骤 3: 启动 N8N 并保持窗口打开
:: ============================================
echo [3/3] 正在前台启动 N8N...
echo       启动成功后，浏览器会自动打开 http://127.0.0.1:5678
echo       【注意】请勿关闭此窗口，关闭此窗口即代表停止 N8N。
echo.

:: 自动打开浏览器
start http://127.0.0.1:5678

:: 启动 N8N
call "C:\n8n_local\node_modules\.bin\n8n.cmd" start

echo.
echo === N8N 服务已停止 ===
pause
