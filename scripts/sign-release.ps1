param(
    [Parameter(Mandatory=$true)][string]$CertificateThumbprint,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SignTool = (Get-Command signtool.exe -ErrorAction Stop).Source
$Targets = @(
    (Join-Path $Root "dist_client_v2\VDLiveCheck\VDLiveCheck.exe"),
    (Join-Path $Root "dist_updater_v2\TKUpdater.exe"),
    (Join-Path $Root "dist_setup_v2\VD开播助手安装程序-2.1.0.exe")
)
foreach ($Target in $Targets) {
    if (-not (Test-Path $Target)) { throw "签名目标不存在: $Target" }
    & $SignTool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Target
    if ($LASTEXITCODE -ne 0) { throw "签名失败: $Target" }
    & $SignTool verify /pa /v $Target
    if ($LASTEXITCODE -ne 0) { throw "签名验证失败: $Target" }
}
