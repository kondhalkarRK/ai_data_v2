# Starts the API and the frontend together for local development.
# Ctrl+C stops the frontend; the finally block stops the API.
#
# Optional:
#   $env:ASKDB_API_RELOAD = "1"   # enable uvicorn --reload

#Requires -Version 5.1
param(
    [ValidateSet("local", "hosted")]
    [string]$Profile = "local"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Stop-AskDbApiOnPort {
    param([int]$Port = 8000)

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match "uvicorn app\.main:app" -or
                $_.CommandLine -match "run_dev\.py"
            )
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($row in @($listeners)) {
        $procId = $row.OwningProcess
        if ($procId -and $procId -gt 0) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
            $cmd = if ($proc) { [string]$proc.CommandLine } else { "" }
            $name = if ($proc) { [string]$proc.Name } else { "" }
            if ($name -match "(?i)python|uvicorn" -or $cmd -match "(?i)uvicorn|app\.main:app|run_dev\.py") {
                Write-Host "Stopping PID $procId on :$Port ($name)" -ForegroundColor DarkGray
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Start-Sleep -Milliseconds 700
}

function Test-TcpPortFree {
    param([int]$Port)
    $rows = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($rows.Count -eq 0) { return $true }
    # A LISTEN row with a dead PID is not free on Windows (WinError 10048).
    return $false
}

function Get-AskDbApiPort {
    foreach ($candidate in 8000, 8010, 8011, 8020) {
        if (Test-TcpPortFree -Port $candidate) { return $candidate }
        $owner = @(Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue)[0].OwningProcess
        $alive = if ($owner) { Get-Process -Id $owner -ErrorAction SilentlyContinue } else { $null }
        if (-not $alive) {
            Write-Host "Port $candidate is a ghost listener (PID $owner gone). Skipping." -ForegroundColor Yellow
        } else {
            Write-Host "Port $candidate is in use by PID $owner ($($alive.ProcessName)). Skipping." -ForegroundColor Yellow
        }
    }
    throw "No free API port (tried 8000, 8010, 8011, 8020). Close the leftover process or reboot if Windows left a dead LISTEN."
}

function Test-ApiHealth {
    param([int]$Port = 8000)
    try {
        $ErrorActionPreference = "Continue"
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        return ($r.status -eq "ok")
    } catch {
        return $false
    }
}

function Show-BackendStatus {
    param([int]$Port = 8000)
    Write-Host ""
    Write-Host "Backend checks:" -ForegroundColor Cyan
    try {
        $ErrorActionPreference = "Continue"
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
        Write-Host "  /health  OK ($($h.service))" -ForegroundColor Green
    } catch {
        Write-Host "  /health  FAIL" -ForegroundColor Red
        return
    }

    try {
        $ErrorActionPreference = "Continue"
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/ready" -TimeoutSec 8
        Write-Host "  /ready   $($ready.status)" -ForegroundColor $(if ($ready.status -eq "ready") { "Green" } else { "Yellow" })
        foreach ($dep in $ready.dependencies) {
            $color = if ($dep.status -eq "ok") { "DarkGray" } elseif ($dep.status -eq "not_configured") { "DarkGray" } else { "Red" }
            Write-Host ("    - {0}: {1} {2}" -f $dep.name, $dep.status, $dep.detail) -ForegroundColor $color
        }
        if ($ready.status -eq "not_ready") {
            $iface = @($ready.dependencies | Where-Object { $_.detail -match "InterfaceError" })
            Write-Host ""
            if ($iface.Count -gt 0) {
                Write-Host "Windows asyncio/psycopg issue (InterfaceError). Start API via run_dev.py, not raw uvicorn." -ForegroundColor Yellow
            } else {
                Write-Host "Postgres is not reachable with the passwords in askdb/.env." -ForegroundColor Yellow
                Write-Host "Fix: run database bootstrap (needs your postgres superuser password):" -ForegroundColor Yellow
                Write-Host '  $env:PGPASSWORD = "YOUR_POSTGRES_PASSWORD"' -ForegroundColor White
                Write-Host "  & `"C:\Program Files\PostgreSQL\18\bin\psql.exe`" -U postgres -h 127.0.0.1 -f database\app\00_bootstrap.sql" -ForegroundColor White
            }
        }
    } catch {
        Write-Host "  /ready   FAIL ($($_.Exception.Message))" -ForegroundColor Red
    }

    try {
        $ErrorActionPreference = "Continue"
        $me = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/auth/me" -TimeoutSec 5
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
    if ($Profile -eq "hosted") {
        $hosted = Join-Path $root ".env.hosted"
        if (-not (Test-Path $hosted)) {
            if (Test-Path (Join-Path $root ".env.hosted.example")) {
                Copy-Item (Join-Path $root ".env.hosted.example") $hosted
                Write-Error "Created .env.hosted from the example. Put your Supabase URI in .env.hosted, then re-run: .\scripts\dev.ps1 -Profile hosted"
            }
            Write-Error "Missing .env.hosted. Copy .env.hosted.example and paste the Supabase direct URI."
        }
        $env:ASKDB_ENV_FILE = $hosted
        Write-Host "Database profile: HOSTED (Supabase via .env.hosted)" -ForegroundColor Magenta
        Write-Host "Local Postgres is unused for this process. Your .env file is unchanged." -ForegroundColor DarkGray
    } else {
        Remove-Item Env:ASKDB_ENV_FILE -ErrorAction SilentlyContinue
        Write-Host "Database profile: LOCAL (Postgres via .env)" -ForegroundColor Cyan
        Write-Host "Supabase is unused. For a manager demo: .\scripts\dev.ps1 -Profile hosted" -ForegroundColor DarkGray
    }

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
    Write-Host "Clearing leftover API processes ..." -ForegroundColor DarkGray
    Stop-AskDbApiOnPort -Port 8000
    Stop-AskDbApiOnPort -Port 8010

    $apiPort = Get-AskDbApiPort
    $env:API_REWRITE_TARGET = "http://localhost:$apiPort"
    $env:API_PORT = "$apiPort"

    # Use run_dev.py so WindowsSelectorEventLoopPolicy is set BEFORE Uvicorn creates the loop.
    if ($reloadOn) {
        $uvicornArgs = "run_dev.py --host 127.0.0.1 --port $apiPort --reload"
        Write-Host "API reload: ON" -ForegroundColor DarkGray
    } else {
        $uvicornArgs = "run_dev.py --host 127.0.0.1 --port $apiPort"
        Write-Host "API reload: OFF (set ASKDB_API_RELOAD=1 to enable)" -ForegroundColor DarkGray
    }

    Write-Host "Starting API on http://127.0.0.1:$apiPort ..." -ForegroundColor Cyan
    if ($env:ASKDB_ENV_FILE) {
        Write-Host "ASKDB_ENV_FILE=$($env:ASKDB_ENV_FILE)" -ForegroundColor DarkGray
    }
    Write-Host "Web rewrite target: $($env:API_REWRITE_TARGET)" -ForegroundColor DarkGray
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $python
    $psi.Arguments = $uvicornArgs
    $psi.WorkingDirectory = Join-Path $root "apps\api"
    $psi.UseShellExecute = $false
    if ($env:ASKDB_ENV_FILE) {
        $psi.EnvironmentVariables["ASKDB_ENV_FILE"] = $env:ASKDB_ENV_FILE
    }
    $api = New-Object System.Diagnostics.Process
    $api.StartInfo = $psi
    [void]$api.Start()

    $alive = $false
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 500
        $api.Refresh()
        if ($api.HasExited) {
            throw "The API exited during startup (exit $($api.ExitCode)). Check the uvicorn output above."
        }
        if (Test-ApiHealth -Port $apiPort) {
            $alive = $true
            Write-Host "API process is up (/health OK on :$apiPort)." -ForegroundColor Green
            break
        }
    }
    if (-not $alive) {
        Stop-AskDbApiOnPort -Port $apiPort
        throw "API did not answer http://127.0.0.1:$apiPort/health within 30s."
    }

    Show-BackendStatus -Port $apiPort

    if ($Profile -eq "hosted") {
        $env:NEXT_PUBLIC_AUTH_BYPASS = "false"
        Write-Host "Web auth bypass: OFF (sign in with the Supabase admin)." -ForegroundColor Magenta
    }

    Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
    npm run dev
} finally {
    Write-Host "Stopping API ..." -ForegroundColor DarkGray
    if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-AskDbApiOnPort -Port 8000
    Stop-AskDbApiOnPort -Port 8010
    Pop-Location
}
