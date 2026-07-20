from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class Status(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


SEVERITY = {Status.FAIL: 0, Status.WARNING: 1, Status.UNKNOWN: 2, Status.PASS: 3}
PRIORITIES = {"BLOCKING", "HIGH_RISK", "ADVISORY", "INFORMATIONAL"}
# Only software/environment failures may prevent a user from starting a
# broadcast. Network quality, provider intelligence, and hardware readings are
# advisory by design: they must be explained and recorded, never treated as a
# binary eligibility gate.
LAUNCH_BLOCKING_CHECKS: set[str] = set()


@dataclass(slots=True)
class CheckResult:
    check_id: str
    category: str
    status: Status
    title: str
    value: str = ""
    reason: str = ""
    action: str = ""
    repairable: bool = False
    repair_id: str = ""
    repair_level: str = "manual"
    details: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    diagnosis: str = ""
    impact: str = ""
    solutions: list[str] = field(default_factory=list)
    data_source: str = "local"
    confidence: str = "high"
    verification_check_ids: list[str] = field(default_factory=list)
    duration_ms: int = 0
    error_code: str = ""
    priority: str = "INFORMATIONAL"
    blocking: bool = False
    repair_outcome: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # V2 checkers remain readable while every result gains the V3 problem model.
        if not self.diagnosis:
            self.diagnosis = self.reason
        if not self.solutions and self.action:
            self.solutions = [self.action]
        if self.priority not in PRIORITIES:
            self.priority = "INFORMATIONAL"
        # Never trust a caller-supplied priority/blocking flag. Launch blocking
        # is a small auditable allow-list of deterministic software failures.
        self.blocking = self.check_id.startswith(("system.", "environment.")) and self.status == Status.FAIL
        if self.blocking:
            self.priority = "BLOCKING"
        elif self.check_id.startswith("network."):
            self.priority = "ADVISORY"
        elif self.check_id.startswith("performance."):
            self.priority = "INFORMATIONAL"
        elif self.status in {Status.FAIL, Status.WARNING}:
            self.priority = "ADVISORY"
        else:
            self.priority = "INFORMATIONAL"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class CheckReport:
    device_id: str
    app_version: str
    items: list[CheckResult]
    target_region_id: str = "us-los-angeles"
    network_snapshot: dict[str, Any] = field(default_factory=dict)
    ip_profile: dict[str, Any] = field(default_factory=dict)
    streaming_profiles: list[dict[str, Any]] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    repair_events: list[dict[str, Any]] = field(default_factory=list)
    run_mode: str = "daily_preflight"
    environment_snapshot: dict[str, Any] = field(default_factory=dict)
    device_snapshot: dict[str, Any] = field(default_factory=dict)
    check_logs: list[dict[str, Any]] = field(default_factory=list)
    before_snapshot: dict[str, Any] = field(default_factory=dict)
    after_snapshot: dict[str, Any] = field(default_factory=dict)
    confidence_summary: dict[str, Any] = field(default_factory=dict)
    readiness_level: str = "INCOMPLETE"
    blocking_count: int = 0
    high_risk_count: int = 0
    test_mode: str = "standard"
    baseline_delta: dict[str, Any] = field(default_factory=dict)
    source_health: dict[str, Any] = field(default_factory=dict)
    issue_tags: list[str] = field(default_factory=list)
    environment_summary: str = "检测未完成"
    network_summary: str = "检测未完成"
    hardware_summary: str = "仅供参考"
    next_action: str = "完成检测后生成建议"
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_status: Status = Status.UNKNOWN
    conclusion: str = "检测未完成"
    uploaded: bool = False

    def finalize(self) -> None:
        self.blocking_count = sum(1 for item in self.items if item.blocking and item.status == Status.FAIL)
        system_incomplete = any(item.status == Status.UNKNOWN and item.check_id.startswith(("system.", "environment.")) for item in self.items)
        self.high_risk_count = sum(1 for item in self.items if item.check_id.startswith("network.") and item.status in {Status.FAIL, Status.WARNING})
        advisory_risk = any(item.priority == "ADVISORY" and item.status in {Status.FAIL, Status.WARNING} for item in self.items)
        if system_incomplete:
            self.readiness_level, self.overall_status = "INCOMPLETE", Status.UNKNOWN
            self.conclusion = "系统环境检测未完成，暂不建议开播"
        elif self.blocking_count:
            self.readiness_level, self.overall_status = "NOT_READY", Status.FAIL
            self.conclusion = f"当前不建议开播 · {self.blocking_count} 个阻断问题需要先处理"
        elif self.high_risk_count or advisory_risk:
            # Advisory network/provider findings do not change the launch
            # decision. Keep the report actionable while confirming that the
            # software environment itself is ready.
            self.readiness_level, self.overall_status = "READY_WITH_RISK", Status.WARNING
            self.conclusion = "电脑环境检查通过，可以开播 · 网络或硬件存在需要关注的建议"
        elif self.items:
            self.readiness_level, self.overall_status = "READY", Status.PASS
            self.conclusion = "技术准备检查通过，可以开始直播"
        unknown = sum(1 for item in self.items if item.status == Status.UNKNOWN)
        self.issue_tags = sorted({tag for item in self.items for tag in _issue_tags(item)})
        self.environment_summary = "暂不建议开播" if self.blocking_count else "需要一键修复" if any(i.repairable and i.status in {Status.FAIL, Status.WARNING} for i in self.items if not i.check_id.startswith(("network.", "performance.", "devices."))) else "正常"
        network_items = [i for i in self.items if i.check_id.startswith("network.")]
        if any(i.status == Status.UNKNOWN for i in network_items):
            self.network_summary = "待核实"
        elif any(i.status == Status.FAIL for i in network_items):
            self.network_summary = "建议联系服务商或更换线路"
        elif any(i.status == Status.WARNING for i in network_items):
            self.network_summary = "建议关注"
        else:
            self.network_summary = "稳定"
        hardware_items = [i for i in self.items if i.check_id.startswith("performance.")]
        self.hardware_summary = "参考建议" if any(i.status != Status.PASS for i in hardware_items) else "正常"
        self.next_action = "先修复电脑环境并复测" if self.blocking_count else "持续测试或联系服务商" if self.network_summary in {"建议关注", "建议联系服务商或更换线路"} else "可以直接开播"
        self.source_health = self.source_health or {"unknown_items": unknown, "total_items": len(self.items), "healthy": unknown == 0}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 5, "report_id": self.report_id, "device_id": self.device_id,
            "app_version": self.app_version, "checked_at": self.checked_at,
            "run_mode": self.run_mode,
            "target_region_id": self.target_region_id,
            "network_snapshot": self.network_snapshot, "ip_profile": self.ip_profile,
            "streaming_profiles": self.streaming_profiles, "data_sources": self.data_sources,
            "repair_events": self.repair_events,
            "environment_snapshot": self.environment_snapshot,
            "device_snapshot": self.device_snapshot,
            "check_logs": self.check_logs,
            "before_snapshot": self.before_snapshot,
            "after_snapshot": self.after_snapshot,
            "confidence_summary": self.confidence_summary,
            "readiness_level": self.readiness_level, "blocking_count": self.blocking_count,
            "high_risk_count": self.high_risk_count, "test_mode": self.test_mode,
            "baseline_delta": self.baseline_delta, "source_health": self.source_health,
            "issue_tags": self.issue_tags,
            "environment_summary": self.environment_summary, "network_summary": self.network_summary,
            "hardware_summary": self.hardware_summary, "next_action": self.next_action,
            "overall_status": self.overall_status.value, "conclusion": self.conclusion,
            "uploaded": self.uploaded, "items": [x.to_dict() for x in self.items],
            "disclaimer": "本报告仅说明网络环境、系统环境和电脑性能，不代表平台账号审核、流量或开播权限结果。",
        }


def _issue_tags(item: CheckResult) -> list[str]:
    if item.status == Status.PASS:
        return []
    if item.check_id.startswith(("system.", "environment.", "streaming.", "client.")):
        return ["电脑环境异常" if item.status == Status.FAIL else "电脑环境建议"]
    if item.check_id.startswith("network."):
        return ["网络问题" if item.status == Status.FAIL else "网络待关注" if item.status == Status.WARNING else "网络待核实"]
    return ["其他待关注"]
