$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = "C:\tkv2env\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = Join-Path $Root ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "Build dependencies are not installed" }
Push-Location $Root
try {
    & $Python -m pytest --cov=server --cov=client_v2 --cov-report=term-missing --cov-fail-under=80
    if ($LASTEXITCODE -ne 0) { throw "Automated tests failed" }
    $env:PATH = "C:\Program Files\nodejs;" + $env:PATH
    Push-Location "$Root\admin"; try { npm.cmd install; npm.cmd run build } finally { Pop-Location }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist_client_v2 --workpath build_client_product client_v2.spec
    if ($LASTEXITCODE -ne 0) { throw "Client build failed" }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist_updater_v2 --workpath build_updater_product updater_v2.spec
    if ($LASTEXITCODE -ne 0) { throw "Updater build failed" }
    $Iscc = @("C:\Program Files (x86)\Inno Setup 6\ISCC.exe", "C:\Program Files\Inno Setup 6\ISCC.exe", (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) { throw "Inno Setup 6 was not found" }
    & $Iscc installer_v2_product.iss
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
} finally { Pop-Location }
