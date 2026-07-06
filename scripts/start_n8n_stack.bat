@echo off
setlocal

set "ROOT_DIR=%~dp0.."
cd /d "%ROOT_DIR%"

set "RUNTIME_DIR=%ROOT_DIR%\runtime"
set "N8N_ENV_FILE=%RUNTIME_DIR%\n8n.env"
set "N8N_LOG=%RUNTIME_DIR%\n8n.log"
set "API_WIN_DIR=%ROOT_DIR%\Adspower\AI\win"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

if exist "%N8N_ENV_FILE%" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%N8N_ENV_FILE%") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

if "%NODE_FUNCTION_ALLOW_BUILTIN%"=="" (
  set "NODE_FUNCTION_ALLOW_BUILTIN=os,path,fs,http,https,url,child_process"
)
if "%N8N_RUNNERS_TASK_REQUEST_TIMEOUT%"=="" set "N8N_RUNNERS_TASK_REQUEST_TIMEOUT=7200"
if "%N8N_RUNNERS_TASK_TIMEOUT%"=="" set "N8N_RUNNERS_TASK_TIMEOUT=7200"

echo [INFO] Starting local API in a separate window...
start "Adspower AI API" cmd /c "cd /d ""%API_WIN_DIR%"" && start_server.bat"

echo [INFO] Starting n8n with NODE_FUNCTION_ALLOW_BUILTIN=%NODE_FUNCTION_ALLOW_BUILTIN%
echo [INFO] n8n log: %N8N_LOG%
n8n start >> "%N8N_LOG%" 2>&1
