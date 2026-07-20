$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "C:\tkv2env\Scripts\python.exe" }
if (-not (Test-Path $Python)) { $Python = "python" }
Push-Location $Root
try {
    & $Python -m pytest --cov=server --cov=client_v2 --cov-report=term-missing --cov-fail-under=75
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
} finally { Pop-Location }
