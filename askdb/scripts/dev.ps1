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

$api = $null
$reuseApi = $false
$apiLogOut = Join-Path $env:TEMP "askdb-api-dev.out.log"
$apiLogErr = Join-Path $env:TEMP "askdb-api-dev.err.log"

function Stop-AskDbApi {
    param([System.Diagnostics.Process]$Process)
    if ($Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match "uvicorn app\.main:app") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 400
}

function Test-AskDbHealth {
    try {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -ErrorAction Stop
        $ErrorActionPreference = $prev
        return ($null -ne $response -and "$($response.status)" -eq "ok")
    } catch {
        return $false
    }
}

function Test-PortListening {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return [bool]$conn
    } catch {
        # Fallback when Get-NetTCPConnection is unavailable
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(300) -and $client.Connected
            $client.Close()
            return $ok
        } catch {
            return $false
        }
    }
}

function Show-AskDbApiLog {
    param([string]$Title)
    Write-Host "----- $Title -----" -ForegroundColor Red
    foreach ($log in @($script:apiLogErr, $script:apiLogOut)) {
        if (Test-Path $log) {
            Write-Host "($log)" -ForegroundColor DarkGray
            Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 50
        }
    }
}

function Start-AskDbApiProcess {
    param(
        [string]$PythonPath,
        [string]$WorkingDirectory,
        [string]$ArgumentList,
        [string]$StdOutLog,
        [string]$StdErrLog
    )
    Remove-Item $StdOutLog, $StdErrLog -Force -ErrorAction SilentlyContinue
    return Start-Process -PassThru -NoNewWindow `
        -WorkingDirectory $WorkingDirectory `
        -FilePath $PythonPath `
        -ArgumentList $ArgumentList `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog
}

try {
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Host "Created .env from .env.example - update DB passwords / JWT if needed." -ForegroundColor Yellow
        } else {
            throw "No .env found. Copy .env.example to .env and set JWT_SECRET_KEY first."
        }
    }

    $python = Join-Path $root "apps\api\.venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "No API virtualenv. Run: cd apps/api; python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
    }

    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found on PATH. Install Node.js 20+ and retry."
    }

    # Fail fast if the package cannot import (clearer than a hung /health wait).
    Write-Host "Checking API import ..." -ForegroundColor DarkGray
    $apiDir = Join-Path $root "apps\api"
    Push-Location $apiDir
    try {
        $importCheck = & $python -c "from app.main import app; print('ok')" 2>&1
    } finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0 -or ("$importCheck" -notmatch "ok")) {
        Write-Host "$importCheck" -ForegroundColor Red
        throw "API failed to import. Fix the error above, then retry."
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

    if (Test-PortListening -Port 8000) {
        Write-Host "Port 8000 already in use. Checking /health ..." -ForegroundColor Yellow
        if (Test-AskDbHealth) {
            Write-Host "Existing API on :8000 is healthy - reusing it." -ForegroundColor Green
            $reuseApi = $true
        } else {
            Write-Host "Port 8000 is busy but unhealthy. Stopping stale Ask DB uvicorn processes ..." -ForegroundColor Yellow
            Stop-AskDbApi -Process $null
            if (Test-PortListening -Port 8000) {
                throw "Port 8000 is still busy after clearing Ask DB uvicorn. Stop the other process manually, then retry."
            }
        }
    }

    if (-not $reuseApi) {
        Write-Host "Starting API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
        Write-Host "API logs: $apiLogOut | $apiLogErr" -ForegroundColor DarkGray

        $api = Start-AskDbApiProcess `
            -PythonPath $python `
            -WorkingDirectory (Join-Path $root "apps\api") `
            -ArgumentList $uvicornArgList `
            -StdOutLog $apiLogOut `
            -StdErrLog $apiLogErr

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
            $api = $null
            throw "API did not answer http://127.0.0.1:8000/health in $([math]::Round($maxAttempts * 0.5))s. Fix the error in the log above, then retry."
        }
    }

    Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
    npm run dev
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend exited with code $LASTEXITCODE."
    }
} catch {
    Write-Host ""
    Write-Host "dev.ps1 failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if (-not $reuseApi) {
        Write-Host "Stopping API ..." -ForegroundColor DarkGray
        Stop-AskDbApi -Process $api
    }
    Pop-Location
}
