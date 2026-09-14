# Starts the API and the frontend together for local development.
#
# Both run in this window. Ctrl+C stops the frontend and the trap stops the API, so no
# orphaned uvicorn is left holding port 8000.
#
# Reload is auto-disabled when the path contains OneDrive (file watchers flap). Override:
#   $env:ASKDB_API_RELOAD = "1"; .\scripts\dev.ps1
# Force reload off anywhere:
#   $env:ASKDB_API_RELOAD = "0"; .\scripts\dev.ps1

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Stop-AskDbApi {
    param([System.Diagnostics.Process]$Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "uvicorn app\.main:app" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Test-AskDbHealth {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
        return ($null -ne $response -and $response.status -eq "ok")
    } catch {
        return $false
    }
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example - update DB passwords / JWT if needed." -ForegroundColor Yellow
    } else {
        Write-Error "No .env found. Copy .env.example to .env and set JWT_SECRET_KEY first."
    }
}

$python = "$root\apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "No API virtualenv. Run: cd apps/api; python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
}

$onOneDrive = $root -match "OneDrive"
if ($null -eq $env:ASKDB_API_RELOAD -or $env:ASKDB_API_RELOAD -eq "") {
    $reloadEnabled = -not $onOneDrive
} else {
    $reloadEnabled = $env:ASKDB_API_RELOAD -ne "0"
}

# Single ArgumentList string. Never use bare * globs - PowerShell expands them
# (e.g. .venv/* -> .venv\Lib ...) and uvicorn fails with "unexpected extra arguments".
$uvicornArgList = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
if ($reloadEnabled) {
    $uvicornArgList += " --reload --reload-dir app --reload-exclude .venv --reload-exclude __pycache__"
    Write-Host "API reload is ON (watching apps/api/app only)." -ForegroundColor DarkGray
} else {
    Write-Host "API reload is OFF - stable for OneDrive/synced folders. Set ASKDB_API_RELOAD=1 to force reload." -ForegroundColor Yellow
}

$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $owner = $busy | Select-Object -First 1 -ExpandProperty OwningProcess
    Write-Host "Port 8000 already in use (PID $owner). Checking /health ..." -ForegroundColor Yellow
    if (Test-AskDbHealth) {
        Write-Host "Existing API on :8000 is healthy - reusing it." -ForegroundColor Green
        $api = $null
        $reuseApi = $true
    } else {
        Write-Error "Port 8000 is busy (PID $owner) but /health does not respond. Stop that process and retry."
    }
} else {
    $reuseApi = $false
}

$apiLogOut = Join-Path $env:TEMP "askdb-api-dev.out.log"
$apiLogErr = Join-Path $env:TEMP "askdb-api-dev.err.log"
$api = $null

function Show-AskDbApiLog {
    param([string]$Title)
    Write-Host "----- $Title -----" -ForegroundColor Red
    foreach ($log in @($apiLogErr, $apiLogOut)) {
        if (Test-Path $log) {
            Write-Host "($log)" -ForegroundColor DarkGray
            Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 40
        }
    }
}

try {
    if (-not $reuseApi) {
        Remove-Item $apiLogOut, $apiLogErr -Force -ErrorAction SilentlyContinue

        Write-Host "Starting API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
        Write-Host "API logs: $apiLogOut | $apiLogErr" -ForegroundColor DarkGray

        # Separate out/err files - Windows Start-Process cannot redirect both to one path.
        $api = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\apps\api" `
            -FilePath $python `
            -ArgumentList $uvicornArgList `
            -RedirectStandardOutput $apiLogOut `
            -RedirectStandardError $apiLogErr

        # OneDrive / cold venv can take well over 20s before the first request works.
        $maxAttempts = if ($onOneDrive) { 90 } else { 60 }
        $ready = $false
        foreach ($attempt in 1..$maxAttempts) {
            Start-Sleep -Milliseconds 500
            if ($api.HasExited) {
                Show-AskDbApiLog "API log (process exited)"
                throw "The API exited during startup (exit $($api.ExitCode)). See log above."
            }
            if (Test-AskDbHealth) {
                $ready = $true
                Write-Host "API is healthy." -ForegroundColor Green
                break
            }
            if ($attempt % 10 -eq 0) {
                Write-Host "Waiting for API /health ... ($([math]::Round($attempt * 0.5))s)" -ForegroundColor DarkGray
            }
        }

        if (-not $ready) {
            Show-AskDbApiLog "API log (timed out waiting for /health)"
            Stop-AskDbApi -Process $api
            throw "API did not answer http://127.0.0.1:8000/health in $([math]::Round($maxAttempts * 0.5))s. Fix the error in the log above, then retry."
        }
    }

    Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
    npm run dev
} finally {
    if (-not $reuseApi) {
        Write-Host "Stopping API ..." -ForegroundColor DarkGray
        Stop-AskDbApi -Process $api
    }
    Pop-Location
}
