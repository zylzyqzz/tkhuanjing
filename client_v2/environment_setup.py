from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import uuid

from .checks import command, powershell, run_repair
from .regions import RegionProfile
from .streaming_config import discover_streaming_profiles


@dataclass(slots=True)
class SetupAction:
    action_id: str
    title: str
    level: str
    before: str = ""
    target: str = ""
    status: str = "pending"
    message: str = ""
    recovery: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_ps(script: str) -> str:
    try:
        return powershell(script)
    except Exception as exc:
        return f"读取失败：{exc}"


def _process_names() -> list[str]:
    result = _safe_ps("Get-Process | Where-Object {$_.Name -match 'TikTok|obs|LiveStudio'} | Select-Object -ExpandProperty Name -Unique")
    return [line.strip() for line in result.splitlines() if line.strip() and not line.startswith("读取失败")]


def _cache_inventory() -> list[dict]:
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "TikTok LIVE Studio" / "Cache",
        Path(os.environ.get("APPDATA", "")) / "obs-studio" / "plugin_config",
    ]
    rows: list[dict] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            files = [p for p in root.rglob("*") if p.is_file()]
            rows.append({"path": str(root), "files": len(files), "bytes": sum(p.stat().st_size for p in files)})
        except OSError:
            rows.append({"path": str(root), "files": 0, "bytes": 0, "error": "无法读取"})
    return rows


def capture_environment_snapshot(region: RegionProfile, resource_dir: Path) -> dict:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target_region_id": region.region_id,
        "timezone": _safe_ps("(Get-TimeZone).Id"),
        "culture": _safe_ps("(Get-Culture).Name"),
        "system_locale": _safe_ps("(Get-WinSystemLocale).Name"),
        "home_location": _safe_ps("(Get-WinHomeLocation).GeoId"),
        "dns_servers": _safe_ps("(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses} | ForEach-Object {$_.ServerAddresses}) -join ', '") ,
        "winhttp_proxy": _safe_ps("netsh winhttp show proxy"),
        "default_gateway": _safe_ps("(Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway} | Select-Object -First 1 -ExpandProperty IPv4DefaultGateway).NextHop"),
        "network_adapters": _safe_ps("Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object Name,InterfaceDescription,LinkSpeed | ConvertTo-Json -Compress"),
        "tiktok_processes": _process_names(),
        "cache_inventory": _cache_inventory(),
        "streaming_profiles": discover_streaming_profiles(),
        "resources": {name: (resource_dir / name).exists() for name in ("收款码.jpg", "客服二维码.png", "app_icon.ico")},
        "defender_status": _safe_ps("(Get-MpComputerStatus -ErrorAction SilentlyContinue).RealTimeProtectionEnabled"),
        "windows_search": _safe_ps("(Get-Service WSearch -ErrorAction SilentlyContinue).Status"),
    }


def planned_actions(snapshot: dict, region: RegionProfile) -> list[SetupAction]:
    actions = [
        SetupAction("set_target_timezone", "匹配 Windows 时区", "confirm", snapshot.get("timezone", ""), region.windows_timezone),
        SetupAction("set_culture", "匹配区域格式", "confirm", snapshot.get("culture", ""), region.culture),
        SetupAction("set_system_locale", "匹配系统区域", "confirm", snapshot.get("system_locale", ""), region.culture),
        SetupAction("reset_network_cache", "刷新 DNS 与 ARP", "safe", snapshot.get("dns_servers", ""), "保留 DNS 设置并刷新缓存"),
        SetupAction("sync_time", "同步 Windows 时间", "safe", "当前时间服务", "立即同步"),
    ]
    if snapshot.get("tiktok_processes"):
        actions.append(SetupAction("close_tiktok_processes", "关闭占用中的直播进程", "confirm", "、".join(snapshot["tiktok_processes"]), "关闭后再配置"))
    if snapshot.get("cache_inventory"):
        actions.append(SetupAction("clean_safe_cache", "清理已识别临时缓存", "confirm", json.dumps(snapshot["cache_inventory"], ensure_ascii=False), "只清理白名单缓存"))
    return actions


def execute_setup_action(action: SetupAction, region: RegionProfile) -> SetupAction:
    action.status = "running"
    try:
        if action.action_id in {"set_target_timezone", "reset_network_cache", "sync_time"}:
            ok, message, recovery = run_repair(action.action_id, target_timezone=region.windows_timezone)
        elif action.action_id == "set_culture":
            before = _safe_ps("(Get-Culture).Name")
            powershell(f"Set-Culture -CultureInfo '{region.culture}'")
            ok, message, recovery = True, f"区域格式已设置为 {region.culture}", {"before": before}
        elif action.action_id == "set_system_locale":
            before = _safe_ps("(Get-WinSystemLocale).Name")
            powershell(f"Set-WinSystemLocale -SystemLocale '{region.culture}'")
            ok, message, recovery = True, f"系统区域已设置为 {region.culture}，部分程序可能需要重启", {"before": before, "restart_required": True}
        elif action.action_id == "close_tiktok_processes":
            before = _process_names()
            powershell("Get-Process | Where-Object {$_.Name -match 'TikTok|obs|LiveStudio'} | Stop-Process -Force")
            ok, message, recovery = True, "已关闭占用中的直播相关进程", {"before": before, "recovery": "重新启动直播软件"}
        elif action.action_id == "clean_safe_cache":
            removed = 0
            for item in _cache_inventory():
                root = Path(item["path"])
                if root.name.lower() != "cache":
                    continue
                for path in root.rglob("*"):
                    if path.is_file():
                        try:
                            path.unlink()
                            removed += 1
                        except OSError:
                            pass
            ok, message, recovery = True, f"已清理 {removed} 个白名单临时缓存文件", {"files_removed": removed, "recoverable": False}
        else:
            ok, message, recovery = False, "不支持的配置动作", {}
        action.status = "success" if ok else "failed"
        action.message = message
        action.recovery = recovery
    except Exception as exc:
        action.status = "failed"
        action.message = str(exc)
    return action


def new_setup_record(device_id: str, region: RegionProfile, before: dict) -> dict:
    return {
        "setup_id": str(uuid.uuid4()),
        "device_id": device_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "target_region_id": region.region_id,
        "before_snapshot": before,
        "actions": [],
        "status": "running",
    }
