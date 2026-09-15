# Starts the API and the frontend together for local development.
# Ctrl+C stops the frontend; the finally block stops the API.
#
# Optional:
#   $env:ASKDB_API_RELOAD = "1"   # enable uvicorn --reload
#   $env:ASKDB_API_RELOAD = "0"   # force reload off (default)

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Stop-AskDbUvicorn {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match "uvicorn app\.main:app") } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Milliseconds 500
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

try {
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Host "Created .env from .env.example" -ForegroundColor Yellow
        } else {
            Write-Error "No .env found. Copy .env.example to .env first."
        }
    }

    $python = Join-Path $root "apps\api\.venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Write-Error "No API venv. Run: cd apps\api; python -m venv .venv; .\.venv\Scripts\pip install -e `".[dev]`""
    }

    # Default: reload OFF (stable). Set ASKDB_API_RELOAD=1 only if you need auto-reload.
    $reloadOn = $env:ASKDB_API_RELOAD -eq "1"

    # IMPORTANT: do not put * globs in these args. PowerShell expands them and
    # uvicorn then fails with "Got unexpected extra arguments (.venv\Lib ...)".
    if ($reloadOn) {
        $uvicornArgs = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --reload-exclude .venv --reload-exclude __pycache__"
        Write-Host "API reload: ON" -ForegroundColor DarkGray
    } else {
        $uvicornArgs = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        Write-Host "API reload: OFF (set ASKDB_API_RELOAD=1 to enable)" -ForegroundColor DarkGray
    }

    # Always start clean so a stale process cannot block :8000.
    if (Test-ApiHealth) {
        Write-Host "Stopping previous Ask DB API on :8000 ..." -ForegroundColor DarkGray
    }
    Stop-AskDbUvicorn

    Write-Host "Starting API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
    $api = Start-Process -PassThru -NoNewWindow `
        -WorkingDirectory (Join-Path $root "apps\api") `
        -FilePath $python `
        -ArgumentList $uvicornArgs

    $ready = $false
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 500
        if ($api.HasExited) {
            throw "The API exited during startup (exit $($api.ExitCode)). Check the uvicorn output above."
        }
        if (Test-ApiHealth) {
            $ready = $true
            Write-Host "API is ready." -ForegroundColor Green
            break
        }
    }
    if (-not $ready) {
        Stop-AskDbUvicorn
        throw "API did not answer http://127.0.0.1:8000/health within 30s. Is Postgres running? Check uvicorn output above."
    }

    Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
    npm run dev
} finally {
    Write-Host "Stopping API ..." -ForegroundColor DarkGray
    if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-AskDbUvicorn
    Pop-Location
}
