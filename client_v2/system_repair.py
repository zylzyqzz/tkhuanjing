from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
import subprocess
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
        "-and $_.NetAdapter.HardwareInterface -eq $true}; "
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
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    failures += 1
    if failures:
        raise RuntimeError(f"已清理 {removed} 个临时文件，{failures} 个文件被占用")
    return f"已清理 {removed} 个白名单临时文件", {"files_removed": removed, "roots": [str(x) for x in TIKTOK_CACHE_ROOTS]}, False


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
            result = RepairResult(action_id, title, True, message, recovery, restart)
        except Exception as exc:
            result = RepairResult(action_id, title, False, str(exc))
        results.append(result)
        if progress:
            progress(int((index + 1) / len(steps) * 100), title, result)
    return results

