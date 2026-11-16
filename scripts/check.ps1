$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONPATH = 'backend'
& ./.venv/Scripts/python.exe -m ruff check backend
if ($LASTEXITCODE -ne 0) { throw 'Backend lint failed' }
& ./.venv/Scripts/python.exe -m pytest backend/app/tests -q
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
foreach ($script in @('lint', 'typecheck', 'test', 'build')) {
    npm.cmd run $script --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw "Frontend $script failed" }
}
