# Starts the API and the frontend together for local development.
#
# Both run in this window. Ctrl+C stops the frontend and the trap stops the API, so no
# orphaned uvicorn is left holding port 8000.

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

$api = $null
try {
    Write-Host "Starting API on http://localhost:8000 ..." -ForegroundColor Cyan
    $api = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\apps\api" `
        -FilePath $python `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"

    # Wait for liveness rather than sleeping a fixed amount, so a slow start is not a
    # confusing connection-refused in the browser.
    $ready = $false
    foreach ($attempt in 1..40) {
        Start-Sleep -Milliseconds 500
        try {
            Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2 | Out-Null
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
    }
    Pop-Location
}
