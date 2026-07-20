from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
import threading
from typing import Callable

from .checks import command, powershell
from .regions import RegionProfile


@dataclass(slots=True)
class RepairResult:
    action_id: str
    title: str
    ok: bool
    message: str
    recovery: dict = field(default_factory=dict)
    restart_required: bool = False
    verified: bool = False
    before: object = None
    after: object = None
    error_code: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


TIKTOK_CACHE_ROOTS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "TikTok LIVE Studio" / "Cache",
    Path(os.environ.get("LOCALAPPDATA", "")) / "TikTok LIVE Studio" / "Code Cache",
    Path(os.environ.get("LOCALAPPDATA", "")) / "TikTok LIVE Studio" / "GPUCache",
)


def _checked(args: list[str], timeout: int = 30) -> str:
    result = command(args, timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"命令失败（{result.returncode}）")
    return result.stdout.strip()


def _close_tiktok() -> tuple[str, dict, bool]:
    before = powershell("(Get-Process | Where-Object {$_.Name -match 'TikTok|LiveStudio'} | Select-Object -ExpandProperty Name -Unique) -join ', '")
    if before:
        powershell("Get-Process | Where-Object {$_.Name -match 'TikTok|LiveStudio'} | Stop-Process -Force")
    return ("已关闭 TikTok LIVE Studio 占用进程" if before else "未发现占用进程", {"before": before}, False)


def _set_timezone(region: RegionProfile) -> tuple[str, dict, bool]:
    before = powershell("(Get-TimeZone).Id")
    powershell(f"Set-TimeZone -Id '{region.windows_timezone.replace(chr(39), chr(39) * 2)}'")
    return f"时区已设置为 {region.windows_timezone}", {"before": before, "after": region.windows_timezone}, False


def _set_region(region: RegionProfile) -> tuple[str, dict, bool]:
    before = {"culture": powershell("(Get-Culture).Name"), "system_locale": powershell("(Get-WinSystemLocale).Name")}
    safe = region.culture.replace("'", "''")
    powershell(f"Set-Culture -CultureInfo '{safe}'; Set-WinSystemLocale -SystemLocale '{safe}'")
    return f"区域格式和系统区域已设置为 {region.culture}", {"before": before, "after": region.culture}, True


def _configure_dns(region: RegionProfile) -> tuple[str, dict, bool]:
    script = (
        "$items=Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' "
        "-and $_.NetAdapter.HardwareInterface -eq $true -and $_.NetAdapter.Virtual -eq $false "
        "-and $_.InterfaceAlias -notmatch 'VPN|Virtual|VMware|Hyper-V|vEthernet|Loopback|Docker|WSL|TAP|TUN'}; "
        "if(-not $items){throw '未找到带默认网关的活动物理网卡'}; "
        "$before=@(); foreach($item in $items){$old=(Get-DnsClientServerAddress -InterfaceIndex $item.InterfaceIndex -AddressFamily IPv4).ServerAddresses; "
        "$before += [pscustomobject]@{Index=$item.InterfaceIndex;Alias=$item.InterfaceAlias;Servers=$old}; "
        f"Set-DnsClientServerAddress -InterfaceIndex $item.InterfaceIndex -ServerAddresses @('{region.preferred_dns}','{region.alternate_dns}')" + "}; "
        "$before | ConvertTo-Json -Compress"
    )
    before = powershell(script, 35)
    return f"DNS 已设置为 {region.preferred_dns} / {region.alternate_dns}", {"before": before}, False


def _flush_network() -> tuple[str, dict, bool]:
    _checked(["ipconfig", "/flushdns"])
    _checked(["arp", "-d", "*"])
    return "DNS 与 ARP 缓存已刷新", {"commands": ["ipconfig /flushdns", "arp -d *"]}, False


def _sync_time() -> tuple[str, dict, bool]:
    powershell("Set-Service W32Time -StartupType Automatic; Start-Service W32Time; w32tm /resync /force", 35)
    return "Windows 时间已同步", {"command": "w32tm /resync /force"}, False


def _power() -> tuple[str, dict, bool]:
    before = powershell("powercfg /getactivescheme")
    _checked(["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"])
    return "已切换高性能电源模式", {"before": before}, False


def _sleep() -> tuple[str, dict, bool]:
    before = powershell("powercfg /query SCHEME_CURRENT SUB_SLEEP")
    _checked(["powercfg", "/change", "standby-timeout-ac", "0"])
    _checked(["powercfg", "/change", "hibernate-timeout-ac", "0"])
    return "接通电源时的睡眠和休眠已关闭", {"before": before}, False


def _clean_cache() -> tuple[str, dict, bool]:
    removed = 0
    failures = 0
    for root in TIKTOK_CACHE_ROOTS:
        root = root.resolve(strict=False)
        if not root.is_dir() or root.is_symlink():
            continue
        for path in root.rglob("*"):
            resolved = path.resolve(strict=False)
            if path.is_symlink() or root not in resolved.parents:
                failures += 1
                continue
            if resolved.is_file():
                try:
                    resolved.unlink()
                    removed += 1
                except OSError:
                    failures += 1
    if failures:
        raise RuntimeError(f"已清理 {removed} 个临时文件，{failures} 个文件被占用")
    return f"已清理 {removed} 个白名单临时文件", {"files_removed": removed, "roots": [str(x) for x in TIKTOK_CACHE_ROOTS]}, False


def _verify(action_id: str, region: RegionProfile) -> tuple[bool, object]:
    if action_id == "close_tiktok_processes":
        value = powershell("(Get-Process | Where-Object {$_.Name -match 'TikTok|LiveStudio'}).Count")
        return value.strip() in {"", "0"}, value
    if action_id == "set_target_timezone":
        value = powershell("(Get-TimeZone).Id")
        return value == region.windows_timezone, value
    if action_id == "set_region":
        value = {"culture": powershell("(Get-Culture).Name"), "system_locale": powershell("(Get-WinSystemLocale).Name")}
        return all(str(item).lower() == region.culture.lower() for item in value.values()), value
    if action_id == "configure_dns":
        value = powershell("(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses} | ForEach-Object {$_.ServerAddresses}) -join ', '")
        servers = {item.strip() for item in value.split(",")}
        return {region.preferred_dns, region.alternate_dns}.issubset(servers), value
    if action_id == "sync_time":
        value = powershell("(Get-Service W32Time).Status")
        return value.lower() == "running", value
    if action_id == "high_performance":
        value = powershell("powercfg /getactivescheme")
        return "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c" in value.lower(), value
    if action_id == "disable_sleep":
        value = powershell("powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE")
        values = [line.strip().lower() for line in value.splitlines() if "current ac power setting index" in line.lower()]
        return bool(values) and all(line.endswith("0x00000000") for line in values), value
    return True, "verified by successful atomic operation"


def run_system_repair(region: RegionProfile, progress: Callable[[int, str, RepairResult | None], None] | None = None, cancelled: threading.Event | None = None) -> list[RepairResult]:
    steps = [
        ("close_tiktok_processes", "关闭占用进程", _close_tiktok),
        ("set_target_timezone", "设置目标时区", lambda: _set_timezone(region)),
        ("set_region", "设置地区与区域格式", lambda: _set_region(region)),
        ("configure_dns", "配置活动网卡 DNS", lambda: _configure_dns(region)),
        ("reset_network_cache", "刷新 DNS 与 ARP", _flush_network),
        ("sync_time", "同步 Windows 时间", _sync_time),
        ("high_performance", "切换高性能模式", _power),
        ("disable_sleep", "关闭睡眠与休眠", _sleep),
        ("clean_tiktok_cache", "清理 LIVE Studio 临时缓存", _clean_cache),
    ]
    results: list[RepairResult] = []
    for index, (action_id, title, action) in enumerate(steps):
        if cancelled and cancelled.is_set():
            break
        if progress:
            progress(int(index / len(steps) * 100), title, None)
        try:
            message, recovery, restart = action()
            verified, after = _verify(action_id, region)
            if not verified:
                raise RuntimeError("命令已执行，但系统状态验证未通过")
            before = recovery.get("before", recovery)
            result = RepairResult(action_id, title, True, message, recovery, restart, True, before, after)
        except Exception as exc:
            result = RepairResult(action_id, title, False, "系统修复未完成", error_code=f"REPAIR_{action_id.upper()}_FAILED", after=str(exc))
        results.append(result)
        if progress:
            progress(int((index + 1) / len(steps) * 100), title, result)
    return results
