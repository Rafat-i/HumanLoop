param([switch]$ConfirmLocalReset)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $ConfirmLocalReset) { throw 'This removes local demo database data. Re-run with -ConfirmLocalReset after reviewing the target.' }
# Fixed local Compose database; never reads a production DATABASE_URL.
docker compose exec postgres psql -U humanloop -d postgres -c 'DROP DATABASE humanloop WITH (FORCE);' -c 'CREATE DATABASE humanloop OWNER humanloop;'
if ($LASTEXITCODE -ne 0) { throw 'Local database reset failed' }
Write-Host 'Local database reset. Apply migrations and seed again. Existing upload/mail volumes were retained.'
