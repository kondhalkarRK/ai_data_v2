# Starts the API and the frontend together for local development.
#
# Both run in this window. Ctrl+C stops the frontend and the trap stops the API, so no
# orphaned uvicorn is left holding port 8000.
#
# If the API keeps shutting down while you browse (especially on OneDrive / network
# folders), reload is auto-disabled when the path contains OneDrive. Override with:
#   $env:ASKDB_API_RELOAD = "1"; .\scripts\dev.ps1
# Or force off anywhere:
#   $env:ASKDB_API_RELOAD = "0"; .\scripts\dev.ps1

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

if (-not (Test-Path ".env")) {
    Write-Error "No .env found. Copy .env.example to .env and set JWT_SECRET_KEY first."
}

$python = "$root\apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "No API virtualenv. Run: cd apps/api; python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
}

# Default: reload on, except under OneDrive (file watchers flap). Override with ASKDB_API_RELOAD=0|1.
if ($null -eq $env:ASKDB_API_RELOAD -or $env:ASKDB_API_RELOAD -eq "") {
    $reloadEnabled = $root -notmatch "OneDrive"
} else {
    $reloadEnabled = $env:ASKDB_API_RELOAD -ne "0"
}

# Build one ArgumentList string. Do not use unquoted * globs - PowerShell expands them
# (e.g. .venv/* -> .venv\Lib .venv\Scripts) and uvicorn then fails.
$uvicornArgList = "-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
if ($reloadEnabled) {
    # Single-quoted so PowerShell does not expand *.pyc / *.log
    $uvicornArgList += ' --reload --reload-dir app --reload-exclude .venv --reload-exclude __pycache__ --reload-exclude "*.pyc" --reload-exclude "*.log"'
    Write-Host "API reload is ON (watching apps/api/app only)." -ForegroundColor DarkGray
} else {
    Write-Host "API reload is OFF - stable for OneDrive/synced folders. Set ASKDB_API_RELOAD=1 to force reload." -ForegroundColor Yellow
}

$api = $null
try {
    Write-Host "Starting API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
    $api = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\apps\api" `
        -FilePath $python `
        -ArgumentList $uvicornArgList

    # Wait for liveness rather than sleeping a fixed amount, so a slow start is not a
    # confusing connection-refused in the browser.
    $ready = $false
    foreach ($attempt in 1..40) {
        Start-Sleep -Milliseconds 500
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch {
            if ($api.HasExited) { throw "The API exited during startup. Check the output above." }
        }
    }
    if (-not $ready) { Write-Warning "API did not answer /health in 20s; starting the frontend anyway." }

    Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Cyan
    npm run dev
} finally {
    if ($api -and -not $api.HasExited) {
        Write-Host "Stopping API ..." -ForegroundColor DarkGray
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
        # uvicorn --reload spawns a child; kill the tree if the parent already exited.
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "uvicorn app\.main:app" } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    Pop-Location
}
