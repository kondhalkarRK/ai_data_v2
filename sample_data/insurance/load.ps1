# Load scale_1_5m CSVs into askdb_dev (client-side \copy).
# Usage (from this folder):
#   .\load.ps1
# Or: .\load.ps1 -User postgres -Database askdb_dev

param(
    [string]$User = "postgres",
    [string]$Database = "askdb_dev",
    [string]$HostName = "localhost"
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$psql = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psql) {
    Write-Host "psql not in PATH. In pgAdmin Query Tool (askdb_dev as postgres), run load_copy.sql instead."
    exit 1
}

Write-Host "Loading CSVs into $Database via psql \copy ..."
& psql -h $HostName -U $User -d $Database -v ON_ERROR_STOP=1 -f ".\load_psql.sql"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Load complete. Check: SELECT COUNT(*) FROM insurance.fact_claims;"
}
