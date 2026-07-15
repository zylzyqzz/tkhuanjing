$ErrorActionPreference = "Stop"
$Python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $Python)) { throw "Python 3.12 not found" }

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $Root
try {
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist_client --workpath build_client_v2 client_v1.spec
    if ($LASTEXITCODE -ne 0) { throw "Client build failed" }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist_updater --workpath build_updater_v3 updater.spec
    if ($LASTEXITCODE -ne 0) { throw "Updater build failed" }

    $Iscc = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) { throw "Inno Setup 6 not found" }
    & $Iscc installer_v2.iss
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
} finally {
    Pop-Location
}
