# Starts the API and the frontend together for local development.
# Ctrl+C stops the frontend; the finally block stops the API.
#
# Optional:
#   $env:ASKDB_API_RELOAD = "1"   # enable uvicorn --reload

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Stop-AskDbApiOnPort {
    # Prefer command-line match; fall back to whatever owns :8000 (stale listeners).
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match "uvicorn app\.main:app") } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    $listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    foreach ($row in @($listeners)) {
        $procId = $row.OwningProcess
        if ($procId -and $procId -gt 0) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
            $cmd = if ($proc) { [string]$proc.CommandLine } else { "" }
            $name = if ($proc) { [string]$proc.Name } else { "" }
            # Only kill python/uvicorn-looking owners, never system pid 0/4.
            if ($name -match "(?i)python|uvicorn" -or $cmd -match "(?i)uvicorn|app\.main:app") {
                Write-Host "Stopping PID $procId on :8000 ($name)" -ForegroundColor DarkGray
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Start-Sleep -Milliseconds 700
}

function Test-ApiHealth {
    try {
        $ErrorActionPreference = "Continue"
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
        return ($r.status -eq "ok")
    } catch {
        return $false
    }
}

function Show-BackendStatus {
    Write-Host ""
    Write-Host "Backend checks:" -ForegroundColor Cyan
    try {
        $ErrorActionPreference = "Continue"
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
        Write-Host "  /health  OK ($($h.service))" -ForegroundColor Green
    } catch {
        Write-Host "  /health  FAIL" -ForegroundColor Red
        return
    }

    try {
        $ErrorActionPreference = "Continue"
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8000/ready" -TimeoutSec 8
        Write-Host "  /ready   $($ready.status)" -ForegroundColor $(if ($ready.status -eq "ready") { "Green" } else { "Yellow" })
        foreach ($dep in $ready.dependencies) {
            $color = if ($dep.status -eq "ok") { "DarkGray" } elseif ($dep.status -eq "not_configured") { "DarkGray" } else { "Red" }
            Write-Host ("    - {0}: {1} {2}" -f $dep.name, $dep.status, $dep.detail) -ForegroundColor $color
        }
        if ($ready.status -eq "not_ready") {
            Write-Host ""
            Write-Host "Postgres is not reachable with the passwords in askdb/.env." -ForegroundColor Yellow
            Write-Host "Fix: run database bootstrap (needs your postgres superuser password):" -ForegroundColor Yellow
            Write-Host '  $env:PGPASSWORD = "YOUR_POSTGRES_PASSWORD"' -ForegroundColor White
            Write-Host "  & `"C:\Program Files\PostgreSQL\18\bin\psql.exe`" -U postgres -h 127.0.0.1 -f database\app\00_bootstrap.sql" -ForegroundColor White
            Write-Host "Then reset role passwords if roles already existed:" -ForegroundColor Yellow
            Write-Host "  ALTER ROLE askdb_app WITH PASSWORD 'askdb_app';" -ForegroundColor White
            Write-Host "  ALTER ROLE askdb_reader WITH PASSWORD 'askdb_reader';" -ForegroundColor White
            Write-Host "  ALTER ROLE askdb_owner WITH PASSWORD 'askdb_owner';" -ForegroundColor White
        }
    } catch {
        Write-Host "  /ready   FAIL ($($_.Exception.Message))" -ForegroundColor Red
    }

    try {
        $ErrorActionPreference = "Continue"
        $me = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/me" -TimeoutSec 5
        Write-Host "  /auth/me OK ($($me.email))" -ForegroundColor Green
    } catch {
        $msg = $_.Exception.Message
        Write-Host "  /auth/me FAIL ($msg)" -ForegroundColor Red
        Write-Host "  If AUTH_BYPASS=true, create an admin then restart API:" -ForegroundColor Yellow
        Write-Host "    cd apps\api; .\.venv\Scripts\python.exe ..\..\scripts\create_admin.py --generate" -ForegroundColor White
    }
    Write-Host ""
}

try {
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Host "Created .env from .env.example" -ForegroundColor Yellow
        } else {
            Write-Error "No .env found. Copy .env.example to .env first."
        }
    }

    # Guard against leftover placeholder passwords from older .env.example copies.
    $envText = Get-Content ".env" -Raw
    if ($envText -match "CHANGE_ME") {
        Write-Host "Replacing CHANGE_ME DB passwords in .env with local bootstrap defaults..." -ForegroundColor Yellow
        $envText = $envText.Replace("askdb_app:CHANGE_ME@", "askdb_app:askdb_app@")
        $envText = $envText.Replace("askdb_reader:CHANGE_ME@", "askdb_reader:askdb_reader@")
        $envText = $envText.Replace("askdb_owner:CHANGE_ME@", "askdb_owner:askdb_owner@")
        Set-Content -Path ".env" -Value $envText -NoNewline
    }

    $python = Join-Path $root "apps\api\.venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Write-Error "No API venv. Run: cd apps\api; python -m venv .venv; .\.venv\Scripts\pip install -e `".[dev]`""
    }

    $reloadOn = $env:ASKDB_API_RELOAD -eq "1"
    if ($reloadOn) {
        $uvicornArgs = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --reload-exclude .venv --reload-exclude __pycache__"
        Write-Host "API reload: ON" -ForegroundColor DarkGray
    } else {
        $uvicornArgs = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        Write-Host "API reload: OFF (set ASKDB_API_RELOAD=1 to enable)" -ForegroundColor DarkGray
    }

    Write-Host "Clearing port 8000 ..." -ForegroundColor DarkGray
    Stop-AskDbApiOnPort

    # If something non-python still holds the port, fail clearly.
    $still = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($still) {
        $busyPid = ($still | Select-Object -First 1).OwningProcess
        throw "Port 8000 is still in use by PID $busyPid. Stop that process and retry."
    }

    Write-Host "Starting API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
    $api = Start-Process -PassThru -NoNewWindow `
        -WorkingDirectory (Join-Path $root "apps\api") `
        -FilePath $python `
        -ArgumentList $uvicornArgs

    $alive = $false
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 500
        if ($api.HasExited) {
            throw "The API exited during startup (exit $($api.ExitCode)). Check the uvicorn output above."
        }
        if (Test-ApiHealth) {
            $alive = $true
            Write-Host "API process is up (/health OK)." -ForegroundColor Green
            break
        }
    }
    if (-not $alive) {
        Stop-AskDbApiOnPort
        throw "API did not answer http://127.0.0.1:8000/health within 30s."
    }

    Show-BackendStatus

    Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
    npm run dev
} finally {
    Write-Host "Stopping API ..." -ForegroundColor DarkGray
    if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-AskDbApiOnPort
    Pop-Location
}
