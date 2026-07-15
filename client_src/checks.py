from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Callable

from api import ClientApi, ApiError
from models import CheckResult


Progress = Callable[[str], None]


DEFAULT_PROFILE = {
    "profile_name": "TikTok 直播默认标准",
    "upload_multiplier": 2.0,
    "packet_loss_warning": 1.0,
    "packet_loss_fail": 3.0,
    "jitter_warning_ms": 30.0,
    "jitter_fail_ms": 60.0,
    "latency_warning_ms": 150.0,
    "latency_fail_ms": 250.0,
    "upload_test_bytes": 2 * 1024 * 1024,
    "min_free_disk_gb": 10.0,
}


def run_command(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    flags = 0x08000000 if os.name == "nt" else 0
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=flags,
        check=False,
    )


def powershell(script: str, timeout: int = 25) -> str:
    executable = shutil.which("powershell.exe") or shutil.which("powershell")
    if not executable:
        raise RuntimeError("未找到 PowerShell")
    result = run_command(
        [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell 执行失败")
    return result.stdout.strip()


def ps_json(script: str, timeout: int = 25):
    text = powershell(f"$ProgressPreference='SilentlyContinue'; {script} | ConvertTo-Json -Compress -Depth 5", timeout)
    return json.loads(text) if text else None


def _grade(value: float, warning: float, fail: float, lower_is_better: bool = True) -> str:
    if lower_is_better:
        return "FAIL" if value > fail else "WARNING" if value > warning else "PASS"
    return "FAIL" if value < fail else "WARNING" if value < warning else "PASS"


def check_network(api: ClientApi, profile: dict, bitrate_kbps: int, target_host: str, progress: Progress) -> list[CheckResult]:
    rows: list[CheckResult] = []
    progress("检查 DNS 解析")
    try:
        ip = socket.gethostbyname(target_host)
        rows.append(CheckResult("network.dns", "网络", "PASS", "DNS 解析", ip, "域名解析正常"))
    except OSError as exc:
        rows.append(CheckResult("network.dns", "网络", "FAIL", "DNS 解析失败", "无法解析", str(exc), "检查 DNS 或切换网络", True, "flush_dns"))
        return rows

    progress("测试延迟、丢包和抖动")
    try:
        result = run_command(["ping", "-n", "8", "-w", "1500", target_host], 20)
        output = result.stdout + "\n" + result.stderr
        loss_match = re.search(r"\((\d+)%\s*(?:loss|丢失)\)", output, re.I)
        if not loss_match:
            loss_match = re.search(r"(\d+)%\s*(?:loss|丢失)", output, re.I)
        loss = float(loss_match.group(1)) if loss_match else (100.0 if result.returncode else 0.0)
        times = [float(x) for x in re.findall(r"(?:time[=<]|时间[=<])\s*(\d+)\s*ms", output, re.I)]
        latency = sum(times) / len(times) if times else 999.0
        if len(times) > 1:
            mean = latency
            jitter = math.sqrt(sum((x - mean) ** 2 for x in times) / len(times))
        else:
            jitter = 999.0

        loss_status = _grade(loss, float(profile["packet_loss_warning"]), float(profile["packet_loss_fail"]))
        rows.append(
            CheckResult(
                "network.packet_loss", "网络", loss_status, "网络丢包", f"{loss:.1f}%",
                "持续丢包可能导致直播卡顿或断流" if loss_status != "PASS" else "丢包率正常",
                "切换直播线路后重新检测" if loss_status != "PASS" else "",
            )
        )
        latency_status = _grade(latency, float(profile["latency_warning_ms"]), float(profile["latency_fail_ms"]))
        rows.append(CheckResult("network.latency", "网络", latency_status, "网络延迟", f"{latency:.0f} ms", "延迟越低越稳定", "延迟过高时更换更接近目标地区的合规线路" if latency_status != "PASS" else ""))
        jitter_status = _grade(jitter, float(profile["jitter_warning_ms"]), float(profile["jitter_fail_ms"]))
        rows.append(CheckResult("network.jitter", "网络", jitter_status, "网络抖动", f"{jitter:.1f} ms", "抖动过大会造成画面和声音不稳定" if jitter_status != "PASS" else "抖动正常", "优先使用有线网络并排查线路负载" if jitter_status != "PASS" else ""))
    except Exception as exc:
        rows.extend([
            CheckResult("network.packet_loss", "网络", "UNKNOWN", "网络丢包", "未完成", str(exc), "检查网络后重试"),
            CheckResult("network.latency", "网络", "UNKNOWN", "网络延迟", "未完成", str(exc), "检查网络后重试"),
            CheckResult("network.jitter", "网络", "UNKNOWN", "网络抖动", "未完成", str(exc), "检查网络后重试"),
        ])

    progress("测试持续上传能力")
    try:
        mbps = api.upload_test(int(profile.get("upload_test_bytes", 2 * 1024 * 1024)))
        required = bitrate_kbps / 1000 * float(profile["upload_multiplier"])
        status = "PASS" if mbps >= required else "FAIL"
        rows.append(CheckResult("network.upload", "网络", status, "持续上传能力", f"{mbps:.2f} Mbps", f"当前直播码率建议至少 {required:.1f} Mbps 稳定上传", "降低直播码率或更换直播线路" if status == "FAIL" else "", details={"required_mbps": required}))
    except ApiError as exc:
        rows.append(CheckResult("network.upload", "网络", "UNKNOWN", "持续上传能力", "未完成", str(exc), "连接检测服务器后重新检测"))
    return rows


class MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def check_performance(profile: dict, progress: Progress) -> list[CheckResult]:
    rows: list[CheckResult] = []
    progress("检查电脑性能和硬件编码器")
    cpu_count = os.cpu_count() or 0
    cpu_status = "PASS" if cpu_count >= 8 else "WARNING" if cpu_count >= 4 else "FAIL"
    rows.append(CheckResult("performance.cpu", "性能", cpu_status, "处理器线程", f"{cpu_count} 线程", "直播编码需要稳定的处理器资源", "关闭高占用软件或升级电脑" if cpu_status != "PASS" else ""))

    mem = MemoryStatus(); mem.dwLength = ctypes.sizeof(MemoryStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    total_gb = mem.ullTotalPhys / 1024**3
    available_gb = mem.ullAvailPhys / 1024**3
    mem_status = "PASS" if total_gb >= 16 and available_gb >= 4 else "WARNING" if total_gb >= 8 and available_gb >= 2 else "FAIL"
    rows.append(CheckResult("performance.memory", "性能", mem_status, "内存", f"总计 {total_gb:.1f} GB，可用 {available_gb:.1f} GB", "可用内存不足会导致直播软件卡顿", "关闭不需要的软件" if mem_status != "PASS" else ""))

    free_gb = shutil.disk_usage(Path.home()).free / 1024**3
    disk_status = "PASS" if free_gb >= float(profile["min_free_disk_gb"]) else "WARNING" if free_gb >= 3 else "FAIL"
    rows.append(CheckResult("performance.disk", "性能", disk_status, "系统盘空间", f"可用 {free_gb:.1f} GB", "空间不足会影响缓存和更新", "清理系统盘空间" if disk_status != "PASS" else ""))

    try:
        adapters = ps_json("Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion")
        if isinstance(adapters, dict): adapters = [adapters]
        names = [str(x.get("Name", "")) for x in (adapters or [])]
        text = "、".join(x for x in names if x) or "未识别"
        encoder = any(re.search(r"NVIDIA|GeForce|Quadro|Intel.*(?:UHD|Iris|Arc)|AMD|Radeon", name, re.I) for name in names)
        rows.append(CheckResult("performance.encoder", "性能", "PASS" if encoder else "FAIL", "硬件编码器", text, "已识别可用显卡编码设备" if encoder else "未识别 NVENC、Quick Sync 或 AMF 兼容设备", "安装正确显卡驱动或更换支持硬件编码的显卡" if not encoder else "", details={"adapters": adapters or []}))
    except Exception as exc:
        rows.append(CheckResult("performance.encoder", "性能", "UNKNOWN", "硬件编码器", "未完成", str(exc), "检查显卡驱动后重试"))
    return rows


def _app_candidates() -> dict[str, list[Path]]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
    return {
        "OBS Studio": [program_files / "obs-studio/bin/64bit/obs64.exe"],
        "TikTok LIVE Studio": [
            local / "TikTok LIVE Studio/launcher.exe",
            local / "Programs/TikTok LIVE Studio/launcher.exe",
            program_files / "TikTok LIVE Studio/launcher.exe",
        ],
    }


def check_streaming_software(progress: Progress) -> list[CheckResult]:
    progress("检查直播软件")
    found: list[str] = []
    details: dict[str, str] = {}
    for name, paths in _app_candidates().items():
        for path in paths:
            if path.exists():
                found.append(name); details[name] = str(path); break
    if not found:
        return [CheckResult("software.installed", "直播软件", "WARNING", "直播软件", "未识别", "没有找到常见直播软件", "安装或在技术支持中确认所用直播工具")]
    rows = [CheckResult("software.installed", "直播软件", "PASS", "直播软件", "、".join(found), "已找到直播软件", details=details)]
    obs_profile = Path(os.environ.get("APPDATA", "")) / "obs-studio/basic/profiles"
    if "OBS Studio" in found:
        profiles = list(obs_profile.glob("*/basic.ini")) if obs_profile.exists() else []
        rows.append(CheckResult("software.obs_profile", "直播软件", "PASS" if profiles else "WARNING", "OBS 配置", f"{len(profiles)} 个配置", "已找到 OBS 推流配置" if profiles else "OBS 尚未创建直播配置", "先在 OBS 中完成场景、码率、分辨率和编码器配置" if not profiles else ""))
    return rows


def check_devices(progress: Progress) -> list[CheckResult]:
    progress("检查摄像头、采集卡和音频设备")
    try:
        devices = ps_json("Get-PnpDevice -PresentOnly | Where-Object {$_.Status -eq 'OK' -and $_.Class -in @('Camera','Image','Media','AudioEndpoint')} | Select-Object Class,FriendlyName,Status")
        if isinstance(devices, dict): devices = [devices]
        devices = devices or []
    except Exception as exc:
        return [CheckResult("device.enumeration", "设备", "UNKNOWN", "音视频设备", "未完成", str(exc), "检查系统设备管理器")]
    cameras = [x for x in devices if str(x.get("Class", "")).lower() in {"camera", "image"} or re.search(r"camera|webcam|capture|摄像|采集", str(x.get("FriendlyName", "")), re.I)]
    audio = [x for x in devices if str(x.get("Class", "")).lower() in {"media", "audioendpoint"}]
    microphones = [x for x in audio if re.search(r"microphone|mic|麦克风|输入", str(x.get("FriendlyName", "")), re.I)]
    rows = [
        CheckResult("device.camera", "设备", "PASS" if cameras else "FAIL", "摄像头/采集卡", "、".join(str(x.get("FriendlyName", "")) for x in cameras) or "未找到", "设备已连接" if cameras else "未找到可用视频采集设备", "连接摄像头或采集卡后重试" if not cameras else "", details={"devices": cameras}),
        CheckResult("device.microphone", "设备", "PASS" if microphones else "FAIL", "麦克风", "、".join(str(x.get("FriendlyName", "")) for x in microphones) or "未找到", "设备已连接" if microphones else "未找到可用麦克风", "连接麦克风并在系统中启用" if not microphones else "", details={"devices": microphones}),
        CheckResult("device.audio", "设备", "PASS" if audio else "WARNING", "音频设备", f"{len(audio)} 个", "音频设备枚举正常" if audio else "未找到音频设备", "检查声卡驱动" if not audio else ""),
    ]
    rows.extend(_sample_camera_and_microphone(bool(cameras), bool(microphones)))
    return rows


def _sample_camera_and_microphone(has_camera: bool, has_microphone: bool) -> list[CheckResult]:
    rows: list[CheckResult] = []
    if has_camera:
        try:
            import cv2  # type: ignore
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            ok, frame = cap.read(); cap.release()
            if not ok or frame is None:
                rows.append(CheckResult("device.camera_frame", "设备", "FAIL", "摄像头画面", "无法读取", "设备可能被占用或驱动异常", "关闭占用摄像头的软件后重试"))
            else:
                brightness = float(frame.mean())
                status = "FAIL" if brightness < 3 else "WARNING" if brightness < 12 else "PASS"
                rows.append(CheckResult("device.camera_frame", "设备", status, "摄像头画面", f"亮度 {brightness:.1f}", "画面接近全黑" if status == "FAIL" else "画面偏暗" if status == "WARNING" else "画面读取正常", "检查镜头遮挡和灯光" if status != "PASS" else ""))
        except ImportError:
            rows.append(CheckResult("device.camera_frame", "设备", "UNKNOWN", "摄像头画面", "未采样", "当前安装包未包含视频采样组件", "在正式安装版中重新检测"))
        except Exception as exc:
            rows.append(CheckResult("device.camera_frame", "设备", "UNKNOWN", "摄像头画面", "未完成", str(exc), "关闭占用摄像头的软件后重试"))
    if has_microphone:
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore
            recording = sd.rec(int(1.2 * 16000), samplerate=16000, channels=1, dtype="float32")
            sd.wait()
            rms = float(np.sqrt(np.mean(np.square(recording))))
            status = "FAIL" if rms < 0.0005 else "WARNING" if rms < 0.003 else "PASS"
            rows.append(CheckResult("device.microphone_level", "设备", status, "麦克风声音", f"RMS {rms:.4f}", "没有检测到有效声音" if status == "FAIL" else "声音偏低" if status == "WARNING" else "声音输入正常", "检查麦克风静音、权限和输入音量" if status != "PASS" else ""))
        except ImportError:
            rows.append(CheckResult("device.microphone_level", "设备", "UNKNOWN", "麦克风声音", "未采样", "当前安装包未包含音频采样组件", "在正式安装版中重新检测"))
        except Exception as exc:
            rows.append(CheckResult("device.microphone_level", "设备", "UNKNOWN", "麦克风声音", "未完成", str(exc), "检查麦克风权限后重试"))
    return rows


def check_system(progress: Progress) -> list[CheckResult]:
    progress("检查系统设置")
    rows: list[CheckResult] = []
    try:
        adapters = ps_json("Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object Name,LinkSpeed,InterfaceDescription")
        if isinstance(adapters, dict): adapters = [adapters]
        rows.append(CheckResult("system.adapter", "系统", "PASS" if adapters else "FAIL", "网络适配器", f"{len(adapters or [])} 个已连接", "网络适配器工作正常" if adapters else "没有已连接的网络适配器", "检查网线或网络连接", details={"adapters": adapters or []}))
    except Exception as exc:
        rows.append(CheckResult("system.adapter", "系统", "UNKNOWN", "网络适配器", "未完成", str(exc), "打开网络设置检查"))
    try:
        scheme = run_command(["powercfg", "/getactivescheme"], 10).stdout.strip()
        high = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c" in scheme.lower() or "高性能" in scheme
        rows.append(CheckResult("system.power", "系统", "PASS" if high else "WARNING", "电源模式", scheme or "未识别", "高性能模式有利于直播稳定" if high else "当前不是高性能模式", "切换到高性能电源模式", True, "high_performance"))
    except Exception as exc:
        rows.append(CheckResult("system.power", "系统", "UNKNOWN", "电源模式", "未完成", str(exc)))
    try:
        sleep = run_command(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE"], 10).stdout
        values = re.findall(r"Current (?:AC|DC) Power Setting Index:\s*0x([0-9a-f]+)", sleep, re.I)
        enabled = any(int(x, 16) > 0 for x in values)
        rows.append(CheckResult("system.sleep", "系统", "WARNING" if enabled else "PASS", "自动休眠", "已启用" if enabled else "已关闭", "直播期间休眠会导致中断" if enabled else "自动休眠已关闭", "关闭接通电源时的自动休眠" if enabled else "", enabled, "disable_sleep" if enabled else ""))
    except Exception as exc:
        rows.append(CheckResult("system.sleep", "系统", "UNKNOWN", "自动休眠", "未完成", str(exc)))
    try:
        firewall = ps_json("Get-NetFirewallProfile | Select-Object Name,Enabled")
        if isinstance(firewall, dict): firewall = [firewall]
        enabled = any(bool(x.get("Enabled")) for x in (firewall or []))
        rows.append(CheckResult("system.firewall", "系统", "PASS" if enabled else "WARNING", "系统防火墙", "已启用" if enabled else "已关闭", "防火墙启用状态正常" if enabled else "系统防火墙已关闭", "建议启用防火墙；如直播软件被阻止，请单独添加允许规则" if not enabled else ""))
    except Exception as exc:
        rows.append(CheckResult("system.firewall", "系统", "UNKNOWN", "系统防火墙", "未完成", str(exc)))
    return rows


def check_client(resource_dir: Path, app_version: str, api_online: bool, progress: Progress) -> list[CheckResult]:
    progress("检查客户端完整性")
    assets = ["收款码.jpg", "客服二维码.png", "app_icon.ico"]
    missing = [name for name in assets if not (resource_dir / name).exists()]
    return [
        CheckResult("client.assets", "客户端", "PASS" if not missing else "FAIL", "资源完整性", "完整" if not missing else "缺少 " + "、".join(missing), "二维码和品牌资源已就绪" if not missing else "安装资源不完整", "重新运行正式安装程序修复" if missing else "", details={"missing": missing}),
        CheckResult("client.version", "客户端", "PASS", "客户端版本", app_version, "当前版本可识别"),
        CheckResult("client.service", "客户端", "PASS" if api_online else "WARNING", "后台服务", "在线" if api_online else "离线", "可以同步配置和报告" if api_online else "当前只能使用本地功能", "检查网络或稍后重试" if not api_online else ""),
    ]


REPAIRS = {
    "flush_dns": (["ipconfig", "/flushdns"], "刷新 DNS 缓存"),
    "high_performance": (["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"], "切换高性能电源模式"),
    "disable_sleep": (["powercfg", "/change", "standby-timeout-ac", "0"], "关闭接通电源时自动休眠"),
}


def run_repair(repair_id: str) -> tuple[bool, str]:
    entry = REPAIRS.get(repair_id)
    if not entry:
        return False, "该项目不支持自动修复"
    command, title = entry
    try:
        result = run_command(command, 20)
        if result.returncode != 0:
            return False, result.stderr.strip() or f"{title}失败，可能需要管理员权限"
        return True, f"{title}完成"
    except Exception as exc:
        return False, str(exc)


def merged_profile(remote: dict | None) -> dict:
    value = dict(DEFAULT_PROFILE)
    if remote:
        for key in value:
            if key in remote:
                value[key] = remote[key]
    return value

