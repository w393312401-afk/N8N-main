@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===========================================
echo          N8N Upgrade Tool
echo ===========================================
echo.
echo [1/4] Stopping N8N service...

tasklist /FI "IMAGENAME eq node.exe" 2>nul | findstr /I "node.exe" >nul
if not errorlevel 1 (
    taskkill /F /IM node.exe >nul 2>&1
    timeout /t 3 /nobreak >nul
    echo       Done - node.exe killed.
) else (
    echo       N8N is not running, skipped.
)

echo.
echo [2/4] Backing up PostgreSQL database...
set "PG_BIN=C:\Program Files\PostgreSQL\17\bin"
set "PATH=%PG_BIN%;%PATH%"
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DT=%%I"
set "DT=%DT: =%"
set "BACKUP_PATH=C:\Users\video\.n8n\n8n_pg_backup_%DT:~0,8%_%DT:~8,6%.sql"
set "PGPASSWORD=n8n_secure_2026"
pg_dump -U n8n -d n8n -F c -f "%BACKUP_PATH%" 2>nul
if not errorlevel 1 (
    echo       PostgreSQL backup saved: %BACKUP_PATH%
) else (
    echo       [WARN] PostgreSQL backup failed, continuing anyway...
)

echo.
echo [3/4] Installing latest N8N via npm...
echo       This may take a few minutes. Do NOT close this window.
echo.

set "SYS_NODE=C:\Program Files\nodejs"
set "PORT_NODE=C:\Users\video\Desktop\node-v22.16.0-win-x64"
set "PATH=%SYS_NODE%;%PORT_NODE%;%PATH%"

call "%SYS_NODE%\npm.cmd" install -g n8n@latest --legacy-peer-deps --ignore-scripts
if errorlevel 1 (
    echo.
    echo [ERROR] Global npm install failed!
    echo         Check network or try running as Administrator.
    echo.
    pause
    exit /b 1
)

echo.
echo [3b/4] Installing latest N8N locally...
cd /d C:\n8n_local
call "%SYS_NODE%\npm.cmd" install n8n@latest --legacy-peer-deps --ignore-scripts
if errorlevel 1 (
    echo.
    echo [ERROR] Local npm install failed!
    echo         Check network or try running as Administrator.
    echo.
    pause
    exit /b 1
)

echo.
echo [3c/4] Patching and rebuilding local N8N...
powershell -NoProfile -ExecutionPolicy Bypass -File .\patch_and_build.ps1
cd /d "%~dp0"

echo.
echo [4/4] Upgrade complete!
echo.
echo Current installed N8N version:
call "%SYS_NODE%\npm.cmd" list -g n8n --depth=0
echo.
echo No red errors above = upgrade successful.
echo Double-click [N8N 24h Background Runner] to restart the service.
echo.
pause