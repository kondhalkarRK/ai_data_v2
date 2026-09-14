# Starts the API and the frontend together for local development.
#
# Both run in this window. Ctrl+C stops the frontend and the trap stops the API, so no
# orphaned uvicorn is left holding port 8000.
#
# If the API keeps shutting down while you browse (especially on OneDrive / network
# folders), start without reload:
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

# Default: reload on. Set ASKDB_API_RELOAD=0 when file watchers flap (OneDrive, antivirus).
$reloadEnabled = $env:ASKDB_API_RELOAD -ne "0"
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
if ($reloadEnabled) {
    $uvicornArgs += @(
        "--reload",
        "--reload-dir", "app",
        "--reload-exclude", "*.pyc",
        "--reload-exclude", "__pycache__/*",
        "--reload-exclude", ".venv/*",
        "--reload-exclude", "*.log"
    )
    Write-Host "API reload is ON (watching apps/api/app only)." -ForegroundColor DarkGray
} else {
    Write-Host "API reload is OFF (ASKDB_API_RELOAD=0) — stable for OneDrive/synced folders." -ForegroundColor Yellow
}

$api = $null
try {
    Write-Host "Starting API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
    $api = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\apps\api" `
        -FilePath $python `
        -ArgumentList $uvicornArgs

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
