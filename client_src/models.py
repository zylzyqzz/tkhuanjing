from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


STATUSES = {"PASS", "WARNING", "FAIL", "UNKNOWN"}


@dataclass(slots=True)
class CheckResult:
    check_id: str
    category: str
    status: str
    title: str
    value: str = ""
    reason: str = ""
    action: str = ""
    repairable: bool = False
    repair_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid check status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CheckReport:
    customer_name: str
    room_name: str
    device_id: str
    app_version: str
    results: list[CheckResult]
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_status: str = "UNKNOWN"
    conclusion: str = "检测未完成"
    uploaded: bool = False

    def finalize(self) -> None:
        statuses = {item.status for item in self.results}
        if "FAIL" in statuses:
            self.overall_status = "FAIL"
            self.conclusion = "不建议开播，请先处理失败项目"
        elif "WARNING" in statuses or "UNKNOWN" in statuses:
            self.overall_status = "WARNING"
            self.conclusion = "存在风险，建议处理后再开播"
        elif self.results:
            self.overall_status = "PASS"
            self.conclusion = "技术准备检查通过，可以开始直播"
        else:
            self.overall_status = "UNKNOWN"
            self.conclusion = "检测未完成"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "customer_name": self.customer_name,
            "room_name": self.room_name,
            "device_id": self.device_id,
            "app_version": self.app_version,
            "checked_at": self.checked_at,
            "overall_status": self.overall_status,
            "conclusion": self.conclusion,
            "uploaded": self.uploaded,
            "items": [item.to_dict() for item in self.results],
            "disclaimer": "本报告仅判断电脑、网络、设备和直播软件的技术准备情况，不代表平台账号审核、流量或开播权限结果。",
        }

