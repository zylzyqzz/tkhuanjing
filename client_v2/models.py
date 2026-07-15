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
CRITICAL_CHECKS = {"network.throughput", "devices.camera", "devices.microphone", "performance.encoder", "streaming.configuration"}


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
        if self.priority == "INFORMATIONAL":
            if self.check_id in CRITICAL_CHECKS:
                self.priority = "BLOCKING"
            elif self.check_id.startswith(("network.public_ip", "network.ip_quality", "network.target_route", "system.timezone", "system.region_consistency")):
                self.priority = "ADVISORY"
            elif self.status in {Status.FAIL, Status.WARNING}:
                self.priority = "HIGH_RISK"
        self.blocking = self.blocking or self.priority == "BLOCKING"

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
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_status: Status = Status.UNKNOWN
    conclusion: str = "检测未完成"
    uploaded: bool = False

    def finalize(self) -> None:
        self.blocking_count = sum(1 for item in self.items if item.blocking and item.status == Status.FAIL)
        self.high_risk_count = sum(1 for item in self.items if item.priority == "HIGH_RISK" and item.status in {Status.FAIL, Status.WARNING})
        critical_unknown = [item for item in self.items if item.check_id in CRITICAL_CHECKS and item.status == Status.UNKNOWN]
        advisory_risk = any(item.priority == "ADVISORY" and item.status in {Status.FAIL, Status.WARNING} for item in self.items)
        if self.blocking_count:
            self.readiness_level, self.overall_status = "NOT_READY", Status.FAIL
            self.conclusion = f"当前不建议开播 · {self.blocking_count} 个阻断问题需要先处理"
        elif critical_unknown:
            self.readiness_level, self.overall_status = "INCOMPLETE", Status.UNKNOWN
            self.conclusion = f"关键检测未完成 · 还有 {len(critical_unknown)} 项需要复检"
        elif self.high_risk_count or advisory_risk or any(item.status == Status.UNKNOWN for item in self.items):
            self.readiness_level, self.overall_status = "READY_WITH_RISK", Status.WARNING
            self.conclusion = f"可以尝试开播 · 存在 {self.high_risk_count or 1} 个明确风险"
        elif self.items:
            self.readiness_level, self.overall_status = "READY", Status.PASS
            self.conclusion = "技术准备检查通过，可以开始直播"
        unknown = sum(1 for item in self.items if item.status == Status.UNKNOWN)
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
            "overall_status": self.overall_status.value, "conclusion": self.conclusion,
            "uploaded": self.uploaded, "items": [x.to_dict() for x in self.items],
            "disclaimer": "本报告仅判断电脑、网络、设备和直播软件的技术准备情况，不代表平台账号审核、流量或开播权限结果。",
        }
