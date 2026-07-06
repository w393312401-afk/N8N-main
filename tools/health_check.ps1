# N8N Health Check & Auto-Restart Script (PostgreSQL Edition)
# Usage: powershell -ExecutionPolicy Bypass -File tools\health_check.ps1
# Schedule this with Task Scheduler every 5 minutes for auto-recovery

param(
    [string]$Url = "http://localhost:5678/healthz",
    [int]$TimeoutSec = 15,
    [switch]$AutoRestart
)

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# ========== Check PostgreSQL Service ==========
$pgService = Get-Service -Name "postgresql-x64-17" -ErrorAction SilentlyContinue
if ($pgService) {
    if ($pgService.Status -ne "Running") {
        Write-Host "[$timestamp] [ALERT] PostgreSQL service is NOT running! Starting..." -ForegroundColor Red
        Start-Service -Name "postgresql-x64-17" -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
        $pgService = Get-Service -Name "postgresql-x64-17"
        if ($pgService.Status -eq "Running") {
            Write-Host "[$timestamp] [OK] PostgreSQL service started successfully" -ForegroundColor Green
        } else {
            Write-Host "[$timestamp] [FAIL] Could not start PostgreSQL!" -ForegroundColor Red
            exit 4
        }
    } else {
        Write-Host "[$timestamp] [OK] PostgreSQL service is running" -ForegroundColor Green
    }
} else {
    Write-Host "[$timestamp] [WARN] PostgreSQL service not found" -ForegroundColor Yellow
}

# ========== Check PostgreSQL Connectivity ==========
$env:PGPASSWORD = "n8n_secure_2026"
$pgBin = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
if (Test-Path $pgBin) {
    try {
        $pgCheck = & $pgBin -U n8n -d n8n -c "SELECT 1;" 2>&1
        if ($pgCheck -match "1 row") {
            Write-Host "[$timestamp] [OK] PostgreSQL n8n database is accessible" -ForegroundColor Green
        } else {
            Write-Host "[$timestamp] [WARN] PostgreSQL query returned unexpected result" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[$timestamp] [ALERT] Cannot connect to PostgreSQL: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# ========== Check N8N HTTP Health ==========
try {
    $resp = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
        Write-Host "[$timestamp] [OK] n8n is healthy (HTTP $($resp.StatusCode))" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "[$timestamp] [WARN] n8n returned HTTP $($resp.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[$timestamp] [ALERT] n8n is DOWN! Error: $($_.Exception.Message)" -ForegroundColor Red
    
    if ($AutoRestart) {
        Write-Host "[$timestamp] [ACTION] Auto-restarting n8n..." -ForegroundColor Yellow
        
        # Kill existing node processes
        Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 3
        
        # Restart via the background launcher
        $scriptDir = Split-Path -Parent $PSScriptRoot
        $launcher = Get-ChildItem -LiteralPath $scriptDir -Filter "*N8N.bat" |
            Where-Object { $_.Name -like "*24*N8N.bat" } |
            Select-Object -First 1 -ExpandProperty FullName
        
        if (Test-Path $launcher) {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$launcher`" hidden" -WindowStyle Hidden
            Write-Host "[$timestamp] [OK] Restart command issued. Waiting 30s for n8n to come up..." -ForegroundColor Cyan
            Start-Sleep -Seconds 30
            
            # Verify restart
            try {
                $check = Invoke-WebRequest -Uri $Url -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
                if ($check.StatusCode -eq 200) {
                    Write-Host "[$timestamp] [OK] n8n successfully restarted!" -ForegroundColor Green
                    exit 0
                }
            } catch {
                Write-Host "[$timestamp] [FAIL] n8n failed to restart. Manual intervention needed." -ForegroundColor Red
                exit 2
            }
        } else {
            Write-Host "[$timestamp] [ERROR] Launcher not found: $launcher" -ForegroundColor Red
            exit 3
        }
    }
    
    exit 1
}
