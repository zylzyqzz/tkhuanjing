from __future__ import annotations

from collections import Counter
from typing import Any


LAUNCH_BLOCKING_CHECKS = {
    "streaming.launch", "streaming.configuration_integrity", "system.clock_integrity",
    "network.proxy_connectivity", "network.dns_connectivity",
    "devices.required_capture_permission", "devices.required_microphone_permission",
}


def authoritative_report(items: list[Any]) -> dict[str, Any]:
    """Recompute launch readiness; client-supplied blocking flags are ignored."""
    tags: set[str] = set()
    blockers = 0
    network_fail = network_warning = network_unknown = 0
    hardware_advice = False
    repairable_environment = False
    for item in items:
        check_id = item.check_id
        status = item.status
        item.blocking = check_id in LAUNCH_BLOCKING_CHECKS and status == "FAIL"
        item.priority = "BLOCKING" if item.blocking else "ADVISORY" if check_id.startswith("network.") or status in {"FAIL", "WARNING"} else "INFORMATIONAL"
        blockers += int(item.blocking)
        if check_id.startswith("network."):
            network_fail += int(status == "FAIL")
            network_warning += int(status == "WARNING")
            network_unknown += int(status == "UNKNOWN")
        elif check_id.startswith(("performance.", "devices.")):
            hardware_advice = hardware_advice or status != "PASS"
        else:
            repairable_environment = repairable_environment or bool(item.repairable and status in {"FAIL", "WARNING"})
        if status != "PASS":
            if item.blocking: tags.add("电脑环境异常")
            elif check_id.startswith("network."): tags.add("网络问题" if status == "FAIL" else "网络待关注" if status == "WARNING" else "网络待核实")
            elif check_id.startswith(("performance.", "devices.")): tags.add("硬件参考")
            else: tags.add("电脑环境建议")
    environment = "暂不建议开播" if blockers else "需要一键修复" if repairable_environment else "正常"
    network = "待核实" if network_unknown else "建议联系服务商或更换线路" if network_fail else "建议关注" if network_warning else "稳定"
    hardware = "参考建议" if hardware_advice else "正常"
    next_action = "先修复电脑环境并复测" if blockers else "持续测试或联系服务商" if network in {"建议关注", "建议联系服务商或更换线路"} else "可以直接开播"
    readiness = "NOT_READY" if blockers else "READY_WITH_RISK" if network != "稳定" or repairable_environment or hardware_advice else "READY"
    overall = "FAIL" if blockers else "WARNING" if readiness == "READY_WITH_RISK" else "PASS"
    conclusion = f"当前不建议开播 · {blockers} 个电脑环境阻断问题需要先处理" if blockers else f"电脑环境正常，可以开播 · 网络情况：{network}"
    return {"blocking_count": blockers, "high_risk_count": network_fail + network_warning, "readiness_level": readiness,
            "overall_status": overall, "conclusion": conclusion, "issue_tags": sorted(tags),
            "environment_summary": environment, "network_summary": network,
            "hardware_summary": hardware, "next_action": next_action}


def percentile(values: list[float], pct: float) -> float | None:
    if not values: return None
    ordered = sorted(values); index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return round(ordered[index], 2)


def confidence_for_samples(valid: int) -> str:
    return "high" if valid >= 30 else "medium" if valid >= 10 else "low"
