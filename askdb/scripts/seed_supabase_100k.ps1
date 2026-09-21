# Seed Ask DB on one Supabase Postgres: 100k automotive + 100k insurance.
# Usage (from askdb/):
#   $env:SUPABASE_DIRECT_URI = "postgresql://postgres:PASSWORD@db.REF.supabase.co:5432/postgres?sslmode=require"
#   .\scripts\seed_supabase_100k.ps1
#
# Requires: Python (API venv). psql is optional for role bootstrap.

param(
    [string]$DirectUri = $env:SUPABASE_DIRECT_URI,
    [int]$AutoRows = 100000,
    [int]$Claims = 100000,
    [int]$Policies = 20000,
    [int]$MonthlySample = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $DirectUri) {
    Write-Error "Set SUPABASE_DIRECT_URI to the Supabase direct URI (port 5432, sslmode=require)."
}

function To-SqlAlchemy([string]$uri) {
    if ($uri -like "postgresql+psycopg://*") { return $uri }
    if ($uri -like "postgresql://*") {
        return $uri -replace "^postgresql://", "postgresql+psycopg://"
    }
    return "postgresql+psycopg://$uri"
}

$sa = To-SqlAlchemy $DirectUri
$env:APP_DATABASE_URL = $sa
$env:AUTOMOTIVE_DATABASE_URL = $sa
$env:INSURANCE_DATABASE_URL = $sa
$env:AUTOMOTIVE_MIGRATE_DATABASE_URL = $sa
$env:INSURANCE_MIGRATE_DATABASE_URL = $sa
$env:ASKDB_ENV_FILE = Join-Path $Root ".env.hosted"

$python = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$bootstrap = Join-Path $Root "database\supabase\00_bootstrap.sql"
$psql = Get-Command psql -ErrorAction SilentlyContinue
if ($psql) {
    Write-Host "Creating roles (askdb_app / reader / owner)..."
    & psql $DirectUri -v ON_ERROR_STOP=1 -f $bootstrap
} else {
    Write-Host "psql not found - creating roles with Python..."
    & $python scripts/ensure_analytics_roles.py
    if ($LASTEXITCODE -ne 0) { throw "ensure analytics roles failed" }
}

Write-Host "Migrating app + automotive + insurance..."
& $python scripts/migrate.py app upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "App upgrade skipped or already applied. Stamping app head on this database..."
    & $python scripts/migrate.py app stamp head
    if ($LASTEXITCODE -ne 0) { throw "migrate app stamp failed" }
}
& $python scripts/migrate.py automotive upgrade head
if ($LASTEXITCODE -ne 0) { throw "migrate automotive failed" }
& $python scripts/migrate.py insurance upgrade head
if ($LASTEXITCODE -ne 0) { throw "migrate insurance failed" }

Write-Host "Seeding $AutoRows automotive fact_sales..."
& $python scripts/seed_automotive.py --rows $AutoRows --replace --database-url $sa
if ($LASTEXITCODE -ne 0) { throw "seed automotive failed" }

Write-Host "Seeding $Claims insurance fact_claims..."
& $python scripts/seed_insurance.py --claims $Claims --policies $Policies --monthly-sample $MonthlySample --replace --database-url $sa
if ($LASTEXITCODE -ne 0) { throw "seed insurance failed" }

Write-Host "Done. Create an admin with:"
Write-Host "  `$env:ASKDB_ENV_FILE = (Resolve-Path .env.hosted).Path"
Write-Host "  python scripts/create_admin.py --email admin@example.com --name Admin"
Write-Host "Then start: .\scripts\dev.ps1 -Profile hosted"
