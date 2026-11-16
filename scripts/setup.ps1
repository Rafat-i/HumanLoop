$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
if (-not (Test-Path .venv/Scripts/python.exe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
& ./.venv/Scripts/python.exe -m pip install -e './backend[dev]' -r mcp-server/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
npm.cmd ci --prefix frontend --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
Write-Host 'Installed. Start PostgreSQL, apply migrations, and follow README.md.'
