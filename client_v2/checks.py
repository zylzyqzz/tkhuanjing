from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from typing import Callable

import psutil

from .api import ClientApi
from .events import EventSink, emit
from .models import CheckResult, Status
from .network_intelligence import lookup_public_ip, measure_throughput, tls_probe
from .provider_knowledge import assess_provider
from .regions import RegionProfile
from .streaming_config import discover_streaming_profiles  # compatibility only; not used by network checks


DEFAULT_PROFILE = {
    "upload_multiplier": 2.0, "packet_loss_warning": 1.0, "packet_loss_fail": 3.0,
    "jitter_warning_ms": 30.0, "jitter_fail_ms": 60.0,
    "latency_warning_ms": 150.0, "latency_fail_ms": 250.0, "min_free_disk_gb": 10.0,
}


@dataclass(slots=True)
class CheckContext:
    profile: dict
    target_region: RegionProfile
    target_host: str
    api: ClientApi
    resource_dir: Path
    app_version: str
    api_online: bool
    cancelled: threading.Event
    event_sink: EventSink | None = None
    paused: threading.Event | None = None
    test_mode: str = "standard"


@dataclass(slots=True)
class CheckPlugin:
    plugin_id: str
    title: str
    timeout: int
    run: Callable[[CheckContext], list[CheckResult]]


def command(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def powershell(script: str, timeout: int = 20) -> str:
    result = command(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "系统命令执行失败")
    return result.stdout.strip()


def threshold(value: float, warning: float, fail: float) -> Status:
    return Status.FAIL if value > fail else Status.WARNING if value > warning else Status.PASS


def ping_metrics(host: str, count: int = 8) -> tuple[float, float, float, int]:
    output = command(["ping", "-n", str(count), host], max(12, count * 3)).stdout
    times = [float(x) for x in re.findall(r"(?:time|时间)[=<]?\s*(\d+)\s*ms", output, re.I)]
    loss_matches = re.findall(r"(\d+(?:\.\d+)?)%", output)
    loss = float(loss_matches[-1]) if loss_matches else (100.0 if not times else 0.0)
    latency = sum(times) / len(times) if times else 999.0
    jitter = max(times) - min(times) if len(times) > 1 else 999.0
    return latency, loss, jitter, len(times)


def _priority(check_id: str, status: Status) -> str:
    # The launch gate is intentionally limited to software/environment
    # failures. Network quality, IP/provider intelligence and hardware are
    # reported as advice only, even when their measurements are poor.
    if check_id.startswith(("system.", "environment.")):
        return "BLOCKING" if status == Status.FAIL else "ADVISORY"
    if check_id.startswith("network."):
        return "ADVISORY"
    return "INFORMATIONAL"


def _result(check_id: str, category: str, status: Status, title: str, value: str, *, evidence: list[str], diagnosis: str, impact: str, solutions: list[str] | None = None, metrics: dict | None = None, source: str = "本机实测", confidence: str = "high", repair_id: str = "", repair_level: str = "manual", verify: list[str] | None = None, priority: str = "") -> CheckResult:
    solutions = solutions or []
    return CheckResult(
        check_id=check_id, category=category, status=status, title=title, value=value,
        reason=diagnosis, action="；".join(solutions), repairable=bool(repair_id), repair_id=repair_id,
        repair_level=repair_level, evidence=evidence, metrics=metrics or {}, diagnosis=diagnosis,
        impact=impact, solutions=solutions, data_source=source, confidence=confidence,
        verification_check_ids=verify or [check_id],
        priority=priority or _priority(check_id, status),
    )


def network_checks(ctx: CheckContext) -> list[CheckResult]:
    rows: list[CheckResult] = []
    region = ctx.target_region
    emit(ctx.event_sink, "check_log", "network", "正在获取公网 IP、归属地、ISP 与 ASN", progress=4)
    profile = lookup_public_ip()
    ip = profile.get("ip") or "未获取"
    country = profile.get("country_code") or "未知"
    match = country == region.country_code
    location_status = Status.PASS if match else Status.WARNING if country != "未知" else Status.UNKNOWN
    rows.append(_result(
        "network.public_ip", "网络环境", location_status, "公网 IP 与目标地区", f"{ip} · {country}",
        evidence=[f"公网 IP：{ip}", f"IP 归属：{profile.get('country','')} {profile.get('region','')} {profile.get('city','')}", f"选择地区：{region.label}"],
        diagnosis="公网 IP 归属与所选直播地区一致" if match else "公网 IP 归属与所选直播地区不一致" if country != "未知" else "IP 情报服务未能确认归属地",
        impact="地区不一致可能造成直播内容分发、登录验证或网络时延异常；该结果不代表账号风控结论。",
        solutions=[] if match else ["切换到目标地区对应的直播线路", "切换后重新检测 IP、时区和线路质量"],
        metrics=profile, source=profile.get("source", "IP 情报服务"), confidence=profile.get("confidence", "low"),
    ))
    clean = profile.get("cleanliness") or {}
    network_type = profile.get("network_type") or "unknown"
    provider = assess_provider(profile)
    provider_status = Status.WARNING if provider["level"] == "caution" else Status.PASS if provider["level"] == "suitable" else Status.UNKNOWN
    rows.append(_result(
        "network.ip_quality", "网络环境", provider_status,
        "IP 服务商与线路类型", f"{provider['provider']} · {provider['asn']}",
        evidence=[f"服务商：{provider['provider']}", f"ASN：{provider['asn']}", f"线路分类：{provider['category']}", f"情报源：{profile.get('source','未知')}"] + provider["evidence"],
        diagnosis=provider["summary"],
        impact="机房、共享或高风险 IP 可能提高登录验证概率；纯净度只能作为辅助信息，不能承诺平台结果。",
        solutions=[] if clean else ["使用可信的独享住宅线路", "在服务入口进一步核验 IP 类型与历史"],
        metrics={"cleanliness": clean, "suitability": profile.get("suitability", {}), "provider_assessment": provider, "network_type": network_type}, source=profile.get("source", "IP 情报服务"), confidence=provider["confidence"],
    ))

    gateway = ""
    try:
        gateway = powershell("(Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway} | Select-Object -First 1 -ExpandProperty IPv4DefaultGateway).NextHop")
    except Exception:
        pass
    probes: list[dict] = []
    for label, host in (("本地网关", gateway), ("国内公共节点", "223.5.5.5"), ("公共 DNS", "1.1.1.1")):
        if not host:
            continue
        latency, loss, jitter, samples = ping_metrics(host, 6)
        probes.append({"label": label, "host": host, "latency_ms": round(latency, 1), "loss_percent": loss, "jitter_ms": round(jitter, 1), "samples": samples})
    gateway_probe = next((x for x in probes if x["label"] == "本地网关"), None)
    gateway_loss = gateway_probe["loss_percent"] if gateway_probe else 100
    rows.append(_result(
        "network.local_gateway", "网络环境", threshold(gateway_loss, 1, 3) if gateway_probe else Status.UNKNOWN,
        "本机到路由器", f"丢包 {gateway_loss:.1f}%" if gateway_probe else "未识别网关",
        evidence=[f"网关：{gateway or '未识别'}", f"样本：{gateway_probe['samples'] if gateway_probe else 0} 次"],
        diagnosis="本机到路由器链路正常" if gateway_loss <= 1 else "问题已出现在本机到路由器之间，优先检查 Wi-Fi、网线或路由器",
        impact="本地链路丢包会影响所有直播线路，可能造成卡顿、掉帧和断流。",
        solutions=[] if gateway_loss <= 1 else ["优先改用有线网络", "检查网线、路由器负载和 Wi-Fi 信号", "完成后只复检网络模块"], metrics={"probes": probes},
    ))

    target_probes = []
    for index, host in enumerate(region.probes):
        emit(ctx.event_sink, "metric_sampled", "network", f"正在测试目标地区节点 {index + 1}/{len(region.probes)} · {host}", progress=10 + index * 2)
        target_probes.append(tls_probe(host))
    ok_times = [x["connect_ms"] for x in target_probes if x.get("ok") and x.get("connect_ms") is not None]
    target_latency = sum(ok_times) / len(ok_times) if ok_times else None
    if target_latency is None:
        target_status = Status.UNKNOWN
    else:
        target_status = Status.PASS if target_latency <= ctx.profile["latency_warning_ms"] else Status.WARNING
    rows.append(_result(
        "network.target_route", "网络环境", target_status, "目标地区线路响应", f"{target_latency:.0f} ms" if target_latency is not None else "探测未完成",
        evidence=[f"{x['host']}：{x.get('connect_ms','失败')} ms" for x in target_probes],
        diagnosis="目标地区探测响应处于直播可参考范围" if target_status == Status.PASS else "本地网关正常，但目标地区响应偏高，问题更可能在运营商或跨境线路" if gateway_loss <= 1 else "本地链路异常会影响目标地区探测",
        impact="目标地区响应过高会增加推流抖动和控制指令延迟，但单个探测点失败不等于网络不可用。",
        solutions=[] if target_status == Status.PASS else ["切换备用直播线路后复检", "联系线路服务商确认目标地区节点", "不要仅凭单一服务器失败判定本机断网"], metrics={"target_probes": target_probes},
    ))

    def speed_progress(kind: str, index: int, total: int, value: float | None) -> None:
        label = "下载" if kind == "download" else "上传"
        suffix = f" · {value:.2f} Mbps" if value is not None else " · 节点未返回结果"
        level = "info" if value is not None else "fallback"
        emit(ctx.event_sink, "metric_sampled", "network", f"{label}速度采样 {index}/{total}{suffix}", level=level, progress=18 + index * 3)

    try:
        samples = {"quick": 2, "standard": 3, "deep": 5}.get(ctx.test_mode, 3)
        sample_bytes = {"quick": 1_000_000, "standard": 2_000_000, "deep": 3_000_000}.get(ctx.test_mode, 2_000_000)
        speed = measure_throughput(samples=samples, sample_bytes=sample_bytes, progress=speed_progress)
    except TypeError as exc:
        # Keep compatibility with older provider adapters and test doubles.
        speed = measure_throughput()
    upload = speed.get("upload_mbps")
    download = speed.get("download_mbps")
    variation = speed.get("upload_variation_percent")
    latency = speed.get("latency_ms")
    jitter = speed.get("jitter_ms")
    baseline_required = float(ctx.profile.get("min_upload_mbps", 8.0))
    required = baseline_required
    if upload is None:
        speed_status = Status.UNKNOWN
    else:
        unstable = variation is not None and variation > 50
        speed_status = Status.PASS if upload >= required and not unstable else Status.WARNING if upload >= max(5.0, required * .7) else Status.FAIL
    evidence = [f"下载中位数：{download if download is not None else '未完成'} Mbps", f"稳定上传：{upload if upload is not None else '未完成'} Mbps", f"空载延迟：{latency if latency is not None else '未完成'} ms", f"抖动中位数：{jitter if jitter is not None else '未完成'} ms", f"上传波动：{variation if variation is not None else '样本不足'}%"]
    evidence.append(f"按通用直播稳定上传基线 {baseline_required:.1f} Mbps 判定")
    rows.append(_result(
        "network.throughput", "网络环境", speed_status, "上下行速度与直播承载", f"↓ {download or 0:.1f} / ↑ {upload or 0:.1f} Mbps",
        evidence=evidence,
        diagnosis="当前线路满足直播上传与稳定性要求" if speed_status == Status.PASS else "上传基本可用但余量或稳定性不足，建议优化后开播" if speed_status == Status.WARNING else "稳定上传低于直播所需基线" if speed_status == Status.FAIL else "测速节点未返回足够数据",
        impact="稳定上传不足或波动过大会造成编码缓存增长、掉帧、卡顿或断流。",
        solutions=[] if speed_status == Status.PASS else ["关闭占用上传带宽的程序", "切换稳定线路", "在直播软件中降低码率后复检"], metrics=speed, source=speed.get("source", "Cloudflare Speed"),
    ))
    return rows


def performance_checks(ctx: CheckContext) -> list[CheckResult]:
    cpu_name = os.environ.get("PROCESSOR_IDENTIFIER", "")
    if os.name == "nt":
        try:
            cpu_name = powershell("(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)") or cpu_name
        except Exception:
            pass
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(Path.home().anchor)
    rows = [
        _result("performance.cpu", "电脑性能", Status.WARNING if cpu >= 80 else Status.PASS, "CPU 与实时占用", f"{cpu:.0f}%", evidence=[cpu_name or "CPU 型号未读取", f"1 秒采样占用 {cpu:.0f}%"], diagnosis="CPU 负载正常" if cpu < 80 else "后台负载可能挤占直播编码资源", impact="持续高负载可能造成编码过载和掉帧，仅作为性能建议。", solutions=[] if cpu < 80 else ["关闭非直播高占用程序后复检"], metrics={"percent": cpu, "model": cpu_name}),
        _result("performance.memory", "电脑性能", Status.WARNING if memory.percent >= 85 else Status.PASS, "物理内存与占用", f"{memory.percent:.0f}%", evidence=[f"总计 {memory.total / 2**30:.1f} GB", f"可用 {memory.available / 2**30:.1f} GB"], diagnosis="可用内存正常" if memory.percent < 85 else "可用内存偏低", impact="内存不足可能引起卡顿，仅作为性能建议。", solutions=[] if memory.percent < 85 else ["关闭非直播程序"], metrics={"percent": memory.percent, "total_gb": memory.total / 2**30}),
        _result("performance.disk", "电脑性能", Status.WARNING if disk.free / 2**30 < ctx.profile["min_free_disk_gb"] else Status.PASS, "系统盘空间", f"{disk.free / 2**30:.1f} GB", evidence=[f"建议至少 {ctx.profile['min_free_disk_gb']} GB"], diagnosis="磁盘空间充足" if disk.free / 2**30 >= ctx.profile["min_free_disk_gb"] else "系统盘空间偏低", impact="空间偏低可能影响缓存或录制，仅作为参考。", solutions=["方便时清理系统盘"] if disk.free / 2**30 < ctx.profile["min_free_disk_gb"] else [], metrics={"free_gb": disk.free / 2**30}),
    ]
    try:
        gpu = powershell("(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ' / '")
        encoder = any(x in gpu.lower() for x in ("nvidia", "amd", "intel", "arc", "radeon", "geforce"))
        rows.append(_result("performance.encoder", "电脑性能", Status.PASS if encoder else Status.UNKNOWN, "GPU 与硬件编码能力", gpu or "未识别", evidence=[gpu or "系统没有返回显卡名称"], diagnosis="已识别常见硬件编码平台" if encoder else "仅凭显卡名称无法确认硬件编码器可用性", impact="未启用硬件编码可能显著增加 CPU 压力。", solutions=[] if encoder else ["更新显卡驱动并在直播软件中选择硬件编码器"]))
    except Exception as exc:
        rows.append(_result("performance.encoder", "电脑性能", Status.UNKNOWN, "GPU 与硬件编码能力", "未完成", evidence=[str(exc)], diagnosis="系统未能读取显卡信息", impact="无法确认编码能力。", solutions=["在设备管理器确认显卡和驱动状态"]))
    return rows


def device_checks(ctx: CheckContext) -> list[CheckResult]:
    try:
        script = "$d=Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue; @($d|? {$_.Class -match 'Camera|Image'}).Count; @($d|? {$_.Class -match 'AudioEndpoint|MEDIA'}).Count"
        counts = [int(x) for x in powershell(script).splitlines()[-2:]]
        camera, audio = counts if len(counts) == 2 else (0, 0)
    except Exception:
        camera = audio = -1
    rows = []
    for check_id, title, count, settings in (("devices.camera", "摄像头 / 采集卡", camera, "open_camera_settings"), ("devices.microphone", "麦克风 / 音频设备", audio, "open_microphone_settings")):
        status = Status.PASS if count > 0 else Status.WARNING if count == 0 else Status.UNKNOWN
        rows.append(_result(check_id, "直播设备", status, title, f"发现 {count} 个" if count >= 0 else "枚举失败", evidence=[f"Windows 即插即用设备数量：{max(count, 0)}"], diagnosis="Windows 已识别设备" if count > 0 else "未发现设备；可能未连接、驱动异常或权限关闭" if count == 0 else "系统设备枚举失败", impact="视频设备异常会造成黑屏；音频设备异常会造成无声。", solutions=[] if count > 0 else ["检查连接和驱动", "打开 Windows 隐私权限设置后复检"], repair_id=settings if count <= 0 else "", repair_level="safe"))
    return rows


def streaming_checks(ctx: CheckContext) -> list[CheckResult]:
    profiles = discover_streaming_profiles()
    if not profiles:
        return [_result("streaming.configuration", "直播软件", Status.UNKNOWN, "直播参数识别", "未检测到配置", evidence=["未在标准目录读取到 OBS 或 TikTok LIVE Studio 可用配置"], diagnosis="没有可验证的真实码率、分辨率和帧率数据", impact="无法根据实际码率判断上传带宽是否足够。", solutions=["启动并配置直播软件后重新检测", "如使用便携版，请确认配置目录"]) ]
    rows = []
    for index, profile in enumerate(profiles):
        bitrate = profile.get("bitrate_kbps")
        status = Status.PASS if bitrate else Status.UNKNOWN
        rows.append(_result(f"streaming.profile.{index}", "直播软件", status, f"{profile['software']} · {profile.get('profile','默认配置')}", f"{bitrate} Kbps" if bitrate else "码率未读取", evidence=[f"编码器：{profile.get('encoder') or '未读取'}", f"分辨率：{profile.get('resolution') or '未读取'}", f"帧率：{profile.get('fps') or '未读取'}", f"配置源：{profile.get('source')}"], diagnosis="已读取真实直播配置" if bitrate else "配置存在，但未找到有效视频码率", impact="码率过高会提高线路和编码压力，码率过低会影响画质。", solutions=[] if bitrate else ["在直播软件输出设置中确认视频码率"] , metrics=profile, source="本地直播软件配置"))
    return rows


def system_checks(ctx: CheckContext) -> list[CheckResult]:
    rows = []
    region = ctx.target_region
    try:
        timezone = powershell("(Get-TimeZone).Id")
        match = timezone == region.windows_timezone
        rows.append(_result("system.timezone", "系统环境", Status.PASS if match else Status.FAIL, "系统时区与目标地区", timezone, evidence=[f"当前时区：{timezone}", f"目标时区：{region.windows_timezone}"], diagnosis="系统时区与目标直播地区一致" if match else "系统时区与所选目标地区不一致", impact="时区不一致可能影响直播软件时间、日志和登录环境一致性。", solutions=[] if match else [f"一键修复为 {region.label} 对应时区"], repair_id="set_target_timezone" if not match else "", repair_level="safe"))
    except Exception as exc:
        rows.append(_result("system.timezone", "系统环境", Status.UNKNOWN, "系统时区与目标地区", "未读取", evidence=[str(exc)], diagnosis="无法读取 Windows 时区", impact="无法完成地区一致性判断。", solutions=["检查 Windows 时间和语言设置"]))
    try:
        scheme = powershell("powercfg /getactivescheme")
        high = any(x in scheme.lower() for x in ("high performance", "高性能", "ultimate"))
        rows.append(_result("system.power", "系统环境", Status.PASS if high else Status.FAIL, "电源模式", "高性能" if high else "非高性能", evidence=[scheme], diagnosis="电源策略适合持续直播" if high else "节能策略可能限制 CPU/GPU 持续性能", impact="节能降频可能造成长时间直播编码波动。", solutions=[] if high else ["一键切换高性能电源模式"], repair_id="high_performance" if not high else "", repair_level="safe"))
    except Exception as exc:
        rows.append(_result("system.power", "系统环境", Status.UNKNOWN, "电源模式", "未读取", evidence=[str(exc)], diagnosis="无法读取电源模式", impact="无法确认持续性能策略。"))
    try:
        sleep = powershell("powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE")
        values = re.findall(r"0x([0-9a-fA-F]+)", sleep)
        ac_seconds = int(values[-1], 16) if values else -1
        disabled = ac_seconds == 0
        rows.append(_result("system.sleep", "系统环境", Status.PASS if disabled else Status.FAIL if ac_seconds > 0 else Status.UNKNOWN, "接通电源睡眠策略", "已关闭" if disabled else f"{ac_seconds // 60} 分钟" if ac_seconds > 0 else "未读取", evidence=["直播期间建议接通电源且不自动睡眠"], diagnosis="长时间直播不会因系统睡眠中断" if disabled else "电脑可能在直播期间进入睡眠", impact="睡眠会直接中断推流、采集和网络连接。", solutions=[] if disabled else ["一键关闭接通电源时的睡眠和休眠"], repair_id="disable_sleep" if ac_seconds > 0 else "", repair_level="safe"))
    except Exception as exc:
        rows.append(_result("system.sleep", "系统环境", Status.UNKNOWN, "接通电源睡眠策略", "未读取", evidence=[str(exc)], diagnosis="无法读取睡眠策略", impact="请在 Windows 电源设置中人工确认。"))
    try:
        status = powershell("(Get-Service W32Time).Status")
        running = status.lower() == "running"
        rows.append(_result("system.time_sync", "系统环境", Status.PASS if running else Status.FAIL, "Windows 时间同步", status, evidence=[f"W32Time 服务：{status}"], diagnosis="时间同步服务运行正常" if running else "时间同步服务未运行", impact="系统时间偏差可能造成连接证书或登录验证异常。", solutions=[] if running else ["启动时间服务并立即同步"], repair_id="sync_time" if not running else "", repair_level="safe"))
    except Exception as exc:
        rows.append(_result("system.time_sync", "系统环境", Status.UNKNOWN, "Windows 时间同步", "未读取", evidence=[str(exc)], diagnosis="无法读取时间服务", impact="无法验证系统时间同步状态。"))
    try:
        culture = powershell("(Get-Culture).Name")
        locale = powershell("(Get-WinSystemLocale).Name")
        matched = culture.lower() == region.culture.lower() and locale.lower() == region.culture.lower()
        rows.append(_result(
            "system.region_consistency", "系统环境", Status.PASS if matched else Status.FAIL,
            "Windows 地区与区域格式", f"{culture} / {locale}",
            evidence=[f"区域格式：{culture}", f"系统区域：{locale}", f"目标：{region.culture}"],
            diagnosis="Windows 区域设置与目标地区一致" if matched else "Windows 区域设置与目标地区存在差异",
            impact="区域不一致可能影响日期、语言和直播软件本地化行为，但不代表平台风控结论。",
            solutions=[] if matched else ["一键修复区域格式和系统区域"], repair_id="set_region" if not matched else "", repair_level="safe",
            metrics={"culture": culture, "system_locale": locale, "target": region.culture},
        ))
    except Exception as exc:
        rows.append(_result("system.region_consistency", "系统环境", Status.UNKNOWN, "Windows 地区与区域格式", "未读取", evidence=[str(exc)], diagnosis="无法读取 Windows 区域设置", impact="无法完成环境一致性判断。"))
    try:
        processes = powershell("(Get-Process | Where-Object {$_.Name -match 'TikTok|obs|LiveStudio'} | Select-Object -ExpandProperty Name -Unique) -join ', '")
        rows.append(_result("environment.tiktok_processes", "系统环境", Status.WARNING if processes else Status.PASS, "TikTok LIVE Studio 进程", processes or "未占用", evidence=[f"活动进程：{processes or '无'}"], diagnosis="检测到直播软件正在运行" if processes else "未发现直播程序占用", impact="修复系统环境时活动进程可能锁定缓存。", solutions=[] if not processes else ["一键修复时自动关闭"], repair_id="close_tiktok_processes" if processes else "", repair_level="safe", metrics={"processes": processes.split(", ") if processes else []}))
    except Exception as exc:
        rows.append(_result("environment.tiktok_processes", "系统环境", Status.UNKNOWN, "直播相关进程", "未读取", evidence=[str(exc)], diagnosis="进程检测未完成", impact="无法确认配置文件是否被占用。"))
    cache_root = Path(os.environ.get("LOCALAPPDATA", "")) / "TikTok LIVE Studio" / "Cache"
    try:
        files = [p for p in cache_root.rglob("*") if p.is_file()] if cache_root.exists() else []
        total = sum(p.stat().st_size for p in files)
        rows.append(_result("environment.tiktok_cache", "系统环境", Status.WARNING if total > 1_000_000_000 else Status.PASS, "TikTok LIVE Studio 临时缓存", f"{total / 2**20:.1f} MB", evidence=[f"路径：{cache_root}", f"文件：{len(files)} 个"], diagnosis="已完成白名单缓存目录盘点", impact="过大的临时缓存可能占用磁盘并影响软件启动。", solutions=["一键修复时只清理白名单临时文件"] if total > 1_000_000_000 else [], repair_id="clean_tiktok_cache" if total > 1_000_000_000 else "", repair_level="safe", metrics={"path": str(cache_root), "files": len(files), "bytes": total}))
    except OSError as exc:
        rows.append(_result("environment.tiktok_cache", "系统环境", Status.UNKNOWN, "TikTok 临时缓存", "未读取", evidence=[str(exc)], diagnosis="缓存盘点未完成", impact="未对直播数据做任何删除。"))
    try:
        dns = powershell("(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses} | ForEach-Object {$_.ServerAddresses}) -join ', '")
        expected = {region.preferred_dns, region.alternate_dns}
        configured = {part.strip() for part in dns.split(",") if part.strip()}
        matched = expected.issubset(configured)
        rows.append(_result("environment.dns_arp", "系统环境", Status.PASS if matched else Status.FAIL, "DNS 与 ARP 网络缓存", dns or "未识别 DNS", evidence=[f"当前 DNS：{dns or '未识别'}", f"目标 DNS：{region.preferred_dns}, {region.alternate_dns}"], diagnosis="DNS 配置符合目标地区" if matched else "DNS 与目标地区推荐配置不一致", impact="DNS 或缓存异常可能导致解析延迟。", solutions=[] if matched else ["一键配置活动物理网卡 DNS 并刷新缓存"], repair_id="configure_dns" if not matched else "", repair_level="safe", metrics={"dns_servers": dns, "target_dns": sorted(expected)}))
    except Exception as exc:
        rows.append(_result("environment.dns_arp", "系统环境", Status.UNKNOWN, "DNS 与 ARP 网络缓存", "未读取", evidence=[str(exc)], diagnosis="网络缓存检查未完成", impact="不影响其他检查项继续。"))
    return rows


def client_checks(ctx: CheckContext) -> list[CheckResult]:
    from .storage import CONFIG_FILE
    required = ["logo.png", "客服二维码.png", "app_icon.ico"]
    missing = [name for name in required if not (ctx.resource_dir / name).is_file()]
    return [
        _result("client.assets", "客户端", Status.FAIL if missing else Status.PASS, "离线资源完整性", "缺少：" + "、".join(missing) if missing else "完整", evidence=["品牌 Logo、客服二维码和产品图标均随安装包部署" if not missing else f"缺少 {len(missing)} 个资源"], diagnosis="客户端资源完整" if not missing else "安装目录资源缺失", impact="资源缺失会造成品牌图标或客服二维码无法显示。", solutions=[] if not missing else ["使用正式安装包覆盖安装"]),
        _result("client.service", "客户端", Status.PASS if ctx.api_online else Status.WARNING, "产品服务连接", "在线" if ctx.api_online else "离线", evidence=["授权、规则、报告和更新服务连接状态"], diagnosis="可以读取规则和同步产品数据" if ctx.api_online else "产品服务暂时不可用，本地检查仍可继续", impact="离线时无法激活、同步报告或检查更新。", solutions=[] if ctx.api_online else ["检查网络后重试；本地检测和历史报告仍可使用"]),
        _result("client.configuration", "客户端", Status.PASS if CONFIG_FILE.is_file() else Status.WARNING, "客户端配置文件", "完整" if CONFIG_FILE.is_file() else "缺失", evidence=[str(CONFIG_FILE)], diagnosis="客户端配置可正常读取" if CONFIG_FILE.is_file() else "配置文件缺失或尚未生成", impact="配置缺失会造成目标地区、主题和检测偏好无法保存。", solutions=[] if CONFIG_FILE.is_file() else ["重新生成安全默认配置"], repair_id="repair_client_config" if not CONFIG_FILE.is_file() else "", repair_level="safe"),
    ]


PLUGINS = [
    CheckPlugin("network",   "网络环境", 90, network_checks),
    CheckPlugin("system",    "系统环境", 30, system_checks),
    CheckPlugin("performance", "电脑性能", 30, performance_checks),
]


def validate_plugins() -> None:
    allowed = {"network", "system", "performance"}
    identifiers = [plugin.plugin_id for plugin in PLUGINS]
    if set(identifiers) != allowed or len(identifiers) != len(allowed):
        raise RuntimeError(f"invalid check registry: {identifiers}")
    for plugin in PLUGINS:
        if not plugin.title or plugin.timeout <= 0 or not callable(plugin.run):
            raise RuntimeError(f"invalid check plugin: {plugin.plugin_id}")


validate_plugins()


def run_checks(ctx: CheckContext, progress: Callable[[int, str], None]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for index, plugin in enumerate(PLUGINS):
        if ctx.cancelled.is_set():
            break
        while ctx.paused and ctx.paused.is_set() and not ctx.cancelled.is_set():
            time.sleep(.12)
        percent = int(index / len(PLUGINS) * 100)
        progress(percent, f"正在检查 · {plugin.title}")
        emit(ctx.event_sink, "module_started", plugin.plugin_id, f"正在检查 · {plugin.title}", progress=percent)
        started = time.perf_counter()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"check-{plugin.plugin_id}")
        future = executor.submit(plugin.run, ctx)
        try:
            plugin_results = future.result(timeout=plugin.timeout)
            duration = int((time.perf_counter() - started) * 1000)
            for item in plugin_results:
                item.duration_ms = duration
                emit(ctx.event_sink, "check_result", plugin.plugin_id, f"{item.title}：{item.value}", level=item.status.value.lower(), progress=percent)
            results.extend(plugin_results)
            emit(ctx.event_sink, "module_finished", plugin.plugin_id, f"{plugin.title}检查完成", level="success", progress=percent)
        except FutureTimeout:
            emit(ctx.event_sink, "module_finished", plugin.plugin_id, f"{plugin.title}检查超时", level="unknown", progress=percent)
            results.append(_result(f"{plugin.plugin_id}.timeout", plugin.title, Status.UNKNOWN, f"{plugin.title}检查", "超时", evidence=[f"超过 {plugin.timeout} 秒"], diagnosis="该模块未在规定时间内完成，其他模块不受影响", impact="该模块结果暂时未知。", solutions=["稍后单独复检该模块"]))
        except Exception as exc:
            emit(ctx.event_sink, "module_finished", plugin.plugin_id, f"{plugin.title}检查异常：{exc}", level="fail", progress=percent)
            results.append(_result(f"{plugin.plugin_id}.error", plugin.title, Status.UNKNOWN, f"{plugin.title}检查", "异常", evidence=[str(exc)], diagnosis="该模块发生隔离异常，其他模块不受影响", impact="该模块结果暂时未知。", solutions=["查看本地日志或联系技术支持"]))
        finally:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
    progress(100, "检查完成")
    emit(ctx.event_sink, "check_finished", "all", "检查完成，正在生成一致性报告", level="success", progress=100)
    return results


def run_repair_all(target_timezone: str = "") -> tuple[bool, str, list]:
    """
    一键修复所有可自动处理的系统环境问题。
    按顺序执行：时区 -> 电源 -> 睡眠 -> 时间同步 -> DNS缓存。
    不需要用户确认，直接执行。
    返回 (成功与否, 汇总消息, 每个修复的结果列表)。
    """
    results = []
    ordered_repairs = [
        ("set_target_timezone", "系统时区", target_timezone),
        ("high_performance", "高性能电源模式", ""),
        ("disable_sleep", "关闭睡眠和休眠", ""),
        ("sync_time", "Windows 时间同步", ""),
        ("reset_network_cache", "DNS 与 ARP 缓存", ""),
    ]
    success_count = 0
    messages = []
    for repair_id, title, tz in ordered_repairs:
        ok, msg, recovery = run_repair(repair_id, target_timezone=tz)
        results.append({"repair_id": repair_id, "title": title, "ok": ok, "message": msg, "recovery": recovery})
        if ok:
            success_count += 1
            messages.append(f"✓ {title}：{msg}")
        else:
            messages.append(f"✕ {title}：{msg}")
    summary = f"完成 {success_count}/{len(ordered_repairs)} 项修复" if success_count < len(ordered_repairs) else "全部修复完成"
    return (success_count == len(ordered_repairs), summary, results)


ALL_SYSTEM_REPAIRS = [
    ("set_target_timezone", "系统时区"),
    ("high_performance", "高性能电源模式"),
    ("disable_sleep", "关闭睡眠和休眠"),
    ("sync_time", "Windows 时间同步"),
    ("reset_network_cache", "DNS 与 ARP 缓存"),
]


def run_repair(repair_id: str, *, target_timezone: str = "") -> tuple[bool, str, dict]:
    try:
        if repair_id == "flush_dns":
            before = powershell("Get-DnsClientCache | Measure-Object | Select-Object -ExpandProperty Count")
            result = command(["ipconfig", "/flushdns"], 20)
            return result.returncode == 0, "DNS 缓存已刷新" if result.returncode == 0 else "刷新 DNS 失败", {"before_entries": before, "command": ["ipconfig", "/flushdns"]}
        if repair_id == "reset_network_cache":
            for args in (["ipconfig", "/flushdns"], ["arp", "-d", "*"]):
                command(list(args), 20)
            return True, "DNS 与 ARP 网络缓存已重置", {"commands": ["ipconfig /flushdns", "arp -d *"]}
        if repair_id == "high_performance":
            before = powershell("powercfg /getactivescheme")
            result = command(["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"], 20)
            return result.returncode == 0, "已切换高性能电源模式" if result.returncode == 0 else "切换失败，可能需要管理员权限", {"before": before}
        if repair_id == "disable_sleep":
            before = powershell("powercfg /query SCHEME_CURRENT SUB_SLEEP")
            for args in (["powercfg", "/change", "standby-timeout-ac", "0"], ["powercfg", "/change", "hibernate-timeout-ac", "0"]):
                command(list(args), 20)
            return True, "接通电源时的睡眠和休眠已关闭", {"before": before}
        if repair_id == "sync_time":
            powershell("Set-Service W32Time -StartupType Automatic; Start-Service W32Time; w32tm /resync /force", 30)
            return True, "Windows 时间服务已启动并同步", {"command": "w32tm /resync /force"}
        if repair_id == "set_target_timezone" and target_timezone:
            before = powershell("(Get-TimeZone).Id")
            powershell(f"Set-TimeZone -Id '{target_timezone.replace(chr(39), chr(39)*2)}'")
            return True, f"系统时区已切换为 {target_timezone}", {"before": before, "after": target_timezone}
        if repair_id in ("open_camera_settings", "open_microphone_settings"):
            uri = "ms-settings:privacy-webcam" if repair_id == "open_camera_settings" else "ms-settings:privacy-microphone"
            os.startfile(uri)  # type: ignore[attr-defined]
            return True, "已打开 Windows 权限设置，请开启权限后复检", {"uri": uri}
        if repair_id == "open_sound_settings":
            os.startfile("ms-settings:sound")  # type: ignore[attr-defined]
            return True, "已打开 Windows 声音设备设置", {"uri": "ms-settings:sound"}
        if repair_id == "repair_client_config":
            from .storage import load_config, save_config
            value = load_config(); save_config(value)
            return True, "客户端安全默认配置已重新生成", {"config_schema": value.get("schema_version")}
        return False, "该项目不支持自动修复，请按卡片步骤人工处理", {}
    except Exception as exc:
        return False, str(exc), {}
