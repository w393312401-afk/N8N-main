# Install or update n8n as a Windows service via NSSM.
# Usage: powershell -ExecutionPolicy Bypass -File tools\install_n8n_service.ps1

param(
    [string]$ServiceName = "N8N",
    [string]$NssmPath = "nssm.exe",
    [string]$NodePath = "C:\Users\video\Desktop\node-v22.16.0-win-x64\node.exe",
    [string]$N8nBinPath = "C:\Users\video\Desktop\node-v22.16.0-win-x64\node_modules\n8n\bin\n8n",
    [string]$WorkingDirectory = "C:\Users\video\Desktop\N8N-main",
    [string]$WebhookUrl = "http://192.168.5.10:5678/"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command $NssmPath -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] NSSM not found. Install it first: winget install NSSM.NSSM" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $NodePath)) {
    Write-Host "[ERROR] node.exe not found: $NodePath" -ForegroundColor Red
    exit 2
}

if (-not (Test-Path -LiteralPath $N8nBinPath)) {
    Write-Host "[ERROR] n8n bin not found: $N8nBinPath" -ForegroundColor Red
    exit 3
}

$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $existingService) {
    & $NssmPath install $ServiceName $NodePath $N8nBinPath "start"
}

& $NssmPath set $ServiceName AppDirectory $WorkingDirectory
& $NssmPath set $ServiceName AppStdout (Join-Path $WorkingDirectory "n8n_service.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $WorkingDirectory "n8n_service_err.log")
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateBytes 10485760
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppRestartDelay 5000

& $NssmPath set $ServiceName AppEnvironmentExtra `
    "PATH=C:\Users\video\Desktop\node-v22.16.0-win-x64;%PATH%" `
    "NODE_OPTIONS=--max-old-space-size=8192 --max-semi-space-size=128 --optimize-for-size=false --v8-pool-size=16" `
    "UV_THREADPOOL_SIZE=16" `
    "NODE_FUNCTION_ALLOW_BUILTIN=*" `
    "NODE_FUNCTION_ALLOW_EXTERNAL=*" `
    "N8N_USER_FOLDER=C:\Users\video" `
    "N8N_PORT=5678" `
    "N8N_PROTOCOL=http" `
    "N8N_HOST=0.0.0.0" `
    "WEBHOOK_URL=$WebhookUrl" `
    "N8N_RESTRICT_FILE_ACCESS_TO=" `
    "NODES_EXCLUDE=[]" `
    "N8N_ONLOAD_TIMEOUT=0" `
    "DB_TYPE=postgresdb" `
    "DB_POSTGRESDB_HOST=localhost" `
    "DB_POSTGRESDB_PORT=5432" `
    "DB_POSTGRESDB_DATABASE=n8n" `
    "DB_POSTGRESDB_USER=n8n" `
    "DB_POSTGRESDB_PASSWORD=n8n_secure_2026" `
    "DB_POSTGRESDB_SCHEMA=public" `
    "DB_POSTGRESDB_POOL_SIZE=25" `
    "N8N_ENCRYPTION_KEY=Cv3cAjormlu9956Uk/ywjVOjKSxGdEpv" `
    "EXECUTIONS_DATA_SAVE_ON_SUCCESS=all" `
    "EXECUTIONS_DATA_SAVE_ON_ERROR=all" `
    "EXECUTIONS_DATA_SAVE_ON_PROGRESS=true" `
    "EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=true" `
    "EXECUTIONS_DATA_PRUNE=true" `
    "EXECUTIONS_DATA_MAX_AGE=72" `
    "EXECUTIONS_DATA_PRUNE_MAX_COUNT=1000" `
    "N8N_DEFAULT_EXECUTION_TIMEOUT=1800" `
    "N8N_MAX_EXECUTION_TIMEOUT=1800" `
    "N8N_RUNNERS_TASK_TIMEOUT=1800" `
    "N8N_CONCURRENCY_PRODUCTION_LIMIT=3" `
    "N8N_PAYLOAD_SIZE_MAX=64" `
    "N8N_DIAGNOSTICS_ENABLED=false" `
    "N8N_VERSION_NOTIFICATIONS_ENABLED=false" `
    "N8N_PERSONALIZATION_ENABLED=false" `
    "N8N_TEMPLATES_ENABLED=false" `
    "N8N_HIRING_BANNER_ENABLED=false" `
    "N8N_COMMUNITY_PACKAGES_ENABLED=false" `
    "NO_UPDATE_NOTIFIER=1" `
    "npm_config_update_notifier=false" `
    "N8N_MIGRATE_FS_STORAGE_PATH=true" `
    "N8N_BLOCK_ENV_ACCESS_TO_IP_RANGES=" `
    "N8N_BANNED_IP_ROUTABLE_ALLOWLIST=127.0.0.1,192.168.0.0/16" `
    "N8N_SSRF_ALLOWED_HOSTNAMES=*"

Write-Host "[OK] Windows service configured: $ServiceName" -ForegroundColor Green
Write-Host "Start it with: nssm start $ServiceName"
