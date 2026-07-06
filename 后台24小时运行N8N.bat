@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
if "%~1"=="hidden" goto :run_n8n

cd /d "%~dp0"
echo ===========================================
echo   N8N Background Service Launcher v2.1
echo ===========================================
echo.

:: ============================================
:: STEP 0: Fix Windows port reservation (Hyper-V bug)
:: This is the ROOT CAUSE of "permission to use port" errors.
:: Windows Hyper-V/WSL randomly reserves port ranges that may
:: include 5678. We permanently reserve it for ourselves.
:: ============================================
echo [0/5] Checking Windows port reservation for 5678...
netsh interface ipv4 show excludedportrange protocol=tcp > "%TEMP%\n8n_ports.txt" 2>nul
findstr /R "^[ ][ ]*5678[ ][ ]*5678" "%TEMP%\n8n_ports.txt" >nul 2>&1
if errorlevel 1 (
    echo       [WARN] Port 5678 is not reserved for N8N.
)
if not errorlevel 1 (
    echo       Port 5678 is already reserved. OK.
)

:: ============================================
:: STEP 1: Kill ALL node processes aggressively
:: ============================================
echo [1/5] Cleaning up old processes...

:: Kill all node.exe processes (disabled to prevent killing the wrapper and other MCP servers)
:: tasklist /FI "IMAGENAME eq node.exe" 2>nul | findstr /I "node.exe" >nul
:: if not errorlevel 1 (
::     echo       Found old node.exe processes, killing ALL...
::     taskkill /F /IM node.exe >nul 2>&1
::     powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul
:: )

:: Double-check: also kill by port 5678 (catches non-node processes)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5678 " ^| findstr LISTENING 2^>nul') do (
    if "%%a" NEQ "0" (
        echo       Also killing PID=%%a on port 5678...
        taskkill /F /PID %%a >nul 2>&1
    )
)

:: ============================================
:: STEP 2: Wait for port 5678 to be fully free
:: ============================================
echo [2/5] Waiting for port 5678 to be released...
set "PORT_WAIT=0"
:WAIT_PORT_FREE
netstat -ano | findstr ":5678 " | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
    set /a PORT_WAIT+=1
    if %PORT_WAIT% GEQ 30 (
        echo       [ERROR] Port 5678 still occupied after 30 seconds!
        echo       Please restart your computer and try again.
        pause
        exit /b 1
    )
    ping -n 2 127.0.0.1 >nul 2>&1
    goto WAIT_PORT_FREE
)
echo       Port 5678 is free.

:: ============================================
:: STEP 3: Log rotation
:: ============================================
echo [3/5] Checking log files...
set "LOG_FILE=%~dp0n8n_background.log"
if exist "%LOG_FILE%" (
    for %%F in ("%LOG_FILE%") do (
        if %%~zF GTR 5242880 (
            echo       Log file >5MB, archiving...
            set "LOG_ARCHIVE=%LOG_FILE%.%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%.bak"
            if exist "!LOG_ARCHIVE!" set "LOG_ARCHIVE=%LOG_FILE%.%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.bak"
            move "%LOG_FILE%" "!LOG_ARCHIVE!" >nul 2>&1
            echo [%DATE% %TIME%] === Log Archived === > "%LOG_FILE%"
        )
    )
)

:: ============================================
:: STEP 4: Launch N8N in background via PowerShell
:: (More reliable than VBS method)
:: ============================================
echo [4/5] Starting N8N background process...

:: Use PowerShell to start the process completely hidden and detached
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c \"%~f0\" hidden' -WindowStyle Hidden"

:: ============================================
:: STEP 5: Wait for N8N to be ready (with timeout)
:: ============================================
echo [5/5] Waiting for N8N engine (timeout: 120s)...
echo       (You can close this window - N8N runs in background)
echo.

set "COUNTER=0"
:WAIT_READY
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:5678/rest/settings' -TimeoutSec 3 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  ============================================
    echo   [OK] N8N UI is ready!
    echo   URL: http://127.0.0.1:5678
    echo  ============================================
    powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul
    start http://127.0.0.1:5678
    echo.
    echo  This window will close in 5 seconds...
    powershell -NoProfile -Command "Start-Sleep -Seconds 5" >nul
    exit
)

set /a COUNTER+=1
if %COUNTER% GEQ 120 (
    echo.
    echo  [ERROR] N8N failed to start within 120 seconds!
    echo  Check log: %LOG_FILE%
    echo.
    echo  Last 20 lines of log:
    echo  ---------------------
    powershell -NoProfile -Command "Get-Content '%LOG_FILE%' -Tail 20"
    echo.
    pause
    exit /b 1
)

:: Show progress dots
set /a MOD=%COUNTER% %% 10
if %MOD%==0 echo       ... %COUNTER%s elapsed
ping -n 2 127.0.0.1 >nul 2>&1
goto WAIT_READY

:: ============================================================
:: Hidden entry point - this runs the actual N8N server
:: ============================================================
:run_n8n
cd /d "%~dp0"

:: ========================================================
:: N8N Optimized Configuration v4.0 (PostgreSQL)
:: Last updated: 2026-05-19
:: ========================================================

:: ======== Core Path ========
set "SYS_NODE=C:\Program Files\nodejs"
set "PORT_NODE=C:\Users\video\Desktop\node-v22.16.0-win-x64"
set "PATH=%SYS_NODE%;%PORT_NODE%;%PATH%"

:: ======== Node.js Runtime Tuning ========
:: V8 heap 8GB, larger semi-space, explicit pool size for CPU-heavy parsing
set NODE_OPTIONS=--max-old-space-size=8192 --max-semi-space-size=128 --v8-pool-size=16
:: Expand libuv thread pool from default 4 to 16 (match logical cores)
set UV_THREADPOOL_SIZE=16
set NODE_FUNCTION_ALLOW_BUILTIN=*
set NODE_FUNCTION_ALLOW_EXTERNAL=*

:: ======== N8N Core Settings ========
set N8N_USER_FOLDER=C:\Users\video
set N8N_PORT=5678
set N8N_PROTOCOL=http
set N8N_HOST=0.0.0.0
set WEBHOOK_URL=http://127.0.0.1:5678/
set N8N_EDITOR_BASE_URL=http://127.0.0.1:5678
set N8N_RESTRICT_FILE_ACCESS_TO=
set NODES_EXCLUDE=[]
set N8N_ONLOAD_TIMEOUT=0

:: ======== Database (SQLite) ========
:: Fallen back to SQLite on 2026-06-02 because PostgreSQL is not installed on new computer
set DB_TYPE=sqlite
set DB_SQLITE_DATABASE=C:\Users\video\.n8n\database.sqlite
:: Preserve encryption key for credential decryption
set N8N_ENCRYPTION_KEY=Cv3cAjormlu9956Uk/ywjVOjKSxGdEpv

:: [BACKUP] Old PostgreSQL 17 config (disabled):
:: set DB_TYPE=postgresdb
:: set DB_POSTGRESDB_HOST=localhost
:: set DB_POSTGRESDB_PORT=5432
:: set DB_POSTGRESDB_DATABASE=n8n
:: set DB_POSTGRESDB_USER=n8n
:: set DB_POSTGRESDB_PASSWORD=n8n_secure_2026
:: set DB_POSTGRESDB_SCHEMA=public
:: set DB_POSTGRESDB_POOL_SIZE=25

:: ======== Execution Engine ========
set EXECUTIONS_DATA_SAVE_ON_SUCCESS=all
set EXECUTIONS_DATA_SAVE_ON_ERROR=all
set EXECUTIONS_DATA_SAVE_ON_PROGRESS=true
set EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=true

:: Data Pruning (tighter: 3 days / 1000 max to reduce DB bloat)
set EXECUTIONS_DATA_PRUNE=true
set EXECUTIONS_DATA_MAX_AGE=72
set EXECUTIONS_DATA_PRUNE_MAX_COUNT=1000

:: Execution timeouts (prevent zombie tasks seen in logs)
set N8N_DEFAULT_EXECUTION_TIMEOUT=1800
set N8N_MAX_EXECUTION_TIMEOUT=1800
set N8N_RUNNERS_TASK_TIMEOUT=1800

:: Concurrency control (keep UI responsive on single-instance desktop runs)
set N8N_CONCURRENCY_PRODUCTION_LIMIT=3

:: Payload size limit (fix PayloadTooLargeError from logs)
set N8N_PAYLOAD_SIZE_MAX=64

:: Keep binary files out of memory to reduce UI stalls during heavy executions
set N8N_DEFAULT_BINARY_DATA_MODE=filesystem

:: ======== Frontend / Bandwidth Savings ========
set N8N_DIAGNOSTICS_ENABLED=false
set N8N_VERSION_NOTIFICATIONS_ENABLED=false
set N8N_PERSONALIZATION_ENABLED=false
set N8N_TEMPLATES_ENABLED=false
set N8N_HIRING_BANNER_ENABLED=false
:: Disable community node checks (eliminates TLS timeout errors on startup)
set N8N_COMMUNITY_PACKAGES_ENABLED=false

:: Suppress update checks
set NO_UPDATE_NOTIFIER=1
set npm_config_update_notifier=false

:: Migrate binary storage path (resolve deprecation warning)
set N8N_MIGRATE_FS_STORAGE_PATH=true

:: ======== Network Access ========
set N8N_BLOCK_ENV_ACCESS_TO_IP_RANGES=
set N8N_BANNED_IP_ROUTABLE_ALLOWLIST=127.0.0.1,192.168.0.0/16
set N8N_SSRF_ALLOWED_HOSTNAMES=*

:: ======== Start N8N ========
echo [%DATE% %TIME%] === N8N Starting (Optimized v4.0 SQLite) === >> "n8n_background.log" 2>&1
call "C:\n8n_local\node_modules\.bin\n8n.cmd" start >> "n8n_background.log" 2>&1

:: If n8n exits unexpectedly, log it
echo [%DATE% %TIME%] === N8N Process Exited (code: %ERRORLEVEL%) === >> "n8n_background.log" 2>&1
exit
