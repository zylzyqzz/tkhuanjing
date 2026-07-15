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

    def __post_init__(self) -> None:
        # V2 checkers remain readable while every result gains the V3 problem model.
        if not self.diagnosis:
            self.diagnosis = self.reason
        if not self.solutions and self.action:
            self.solutions = [self.action]

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
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_status: Status = Status.UNKNOWN
    conclusion: str = "检测未完成"
    uploaded: bool = False

    def finalize(self) -> None:
        statuses = {item.status for item in self.items}
        if Status.FAIL in statuses:
            self.overall_status, self.conclusion = Status.FAIL, "不建议开播，请先处理失败项目"
        elif Status.WARNING in statuses or Status.UNKNOWN in statuses:
            self.overall_status, self.conclusion = Status.WARNING, "存在风险，建议处理后再开播"
        elif self.items:
            self.overall_status, self.conclusion = Status.PASS, "技术准备检查通过，可以开始直播"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 4, "report_id": self.report_id, "device_id": self.device_id,
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
            "overall_status": self.overall_status.value, "conclusion": self.conclusion,
            "uploaded": self.uploaded, "items": [x.to_dict() for x in self.items],
            "disclaimer": "本报告仅判断电脑、网络、设备和直播软件的技术准备情况，不代表平台账号审核、流量或开播权限结果。",
        }
