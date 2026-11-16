param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked { param([scriptblock]$Command) & $Command; if ($LASTEXITCODE -ne 0) { throw "Verification command failed (exit $LASTEXITCODE)" } }
# Restore test configuration as well as temp paths when dot-sourced or invoked in a caller shell.
$verificationVariables = @('PYTHONPATH', 'DATABASE_URL', 'TEST_DATABASE_URL', 'ENVIRONMENT', 'DEMO_MODE', 'PAYMENT_PROVIDER', 'COOKIE_SECURE', 'BACKEND_URL')
$previousEnvironment = @{}
foreach ($name in $verificationVariables) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$testRoot = Join-Path $PWD 'test-temp'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
if ((Get-Item -LiteralPath $testRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'test-temp must not be a junction or symlink' }
$runTemp = Join-Path $testRoot ('verify-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runTemp | Out-Null
$pytestBase = Join-Path $runTemp 'pytest'
try {
$env:TEMP = $runTemp
$env:TMP = $runTemp
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Invoke-Checked { docker info }
Invoke-Checked { docker compose config --quiet }
Invoke-Checked { docker compose up -d --wait postgres }
Invoke-Checked { docker compose exec -T postgres pg_isready -U humanloop -d humanloop }
$exists = docker compose exec -T postgres psql -U humanloop -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='humanloop_test'"
if ($LASTEXITCODE -ne 0) { throw 'Database inspection failed' }
if ("$exists".Trim() -ne '1') {Invoke-Checked {docker compose exec -T postgres createdb -U humanloop humanloop_test}}
if (-not $SkipInstall) {
Invoke-Checked { ./.venv/Scripts/python.exe -m pip install -e './backend[dev]' -r mcp-server/requirements.txt }
Invoke-Checked { npm.cmd ci --prefix frontend --no-audit --no-fund }
Invoke-Checked { npm.cmd exec --prefix frontend -- playwright install chromium }
}
$env:PYTHONPATH = 'backend'
$env:DATABASE_URL = 'postgresql+asyncpg://humanloop:humanloop@127.0.0.1:5432/humanloop_test'
$env:TEST_DATABASE_URL = $env:DATABASE_URL
$env:ENVIRONMENT = 'development'
$env:DEMO_MODE = 'true'
$env:PAYMENT_PROVIDER = 'mock'
$env:COOKIE_SECURE = 'false'
$env:BACKEND_URL = 'http://127.0.0.1:8000'
Invoke-Checked { ./.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head }
Invoke-Checked { ./.venv/Scripts/python.exe -m alembic -c backend/alembic.ini check }
Invoke-Checked { ./.venv/Scripts/python.exe -m pytest backend/app/tests -q --basetemp=$pytestBase -p no:cacheprovider }
Invoke-Checked { ./.venv/Scripts/python.exe -m ruff check backend }
Invoke-Checked { ./.venv/Scripts/python.exe -m ruff format --check backend }
Invoke-Checked { npm.cmd run lint --prefix frontend }
Invoke-Checked { npm.cmd run typecheck --prefix frontend }
Invoke-Checked { npm.cmd run typecheck:e2e --prefix frontend }
Invoke-Checked { npm.cmd run test --prefix frontend }
Invoke-Checked { npm.cmd run build --prefix frontend }
Invoke-Checked { ./.venv/Scripts/python.exe scripts/run_e2e.py }
Write-Host 'Local verification passed, including PostgreSQL, browser lifecycle and MCP. No real payment was made.'

} finally {
    foreach ($name in $verificationVariables) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
}
