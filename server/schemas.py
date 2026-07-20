from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from client_v2.product import CURRENT_CHECK_PREFIXES, REPORT_SCHEMA_VERSION, SUPPORTED_REPORT_SCHEMAS


Status = Literal["PASS", "WARNING", "FAIL", "UNKNOWN"]


class RegisterRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=80)
    customer_name: str = Field(default="", max_length=120)
    room_name: str = Field(default="", max_length=120)
    app_version: str = Field(default="", max_length=40)
    target_region_id: str = Field(default="us-los-angeles", max_length=80)


class ActivateRequest(BaseModel):
    code: str = Field(min_length=8, max_length=80)


class AuthorizeRequest(BaseModel):
    event_id: str = Field(min_length=8, max_length=80)


class CheckItemIn(BaseModel):
    check_id: str = Field(min_length=3, max_length=100)
    category: str = Field(default="", max_length=50)
    status: Status
    title: str = Field(default="", max_length=160)
    value: str = Field(default="", max_length=160)
    reason: str = Field(default="", max_length=2000)
    action: str = Field(default="", max_length=2000)
    repairable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    metrics: dict[str, Any] = Field(default_factory=dict)
    diagnosis: str = Field(default="", max_length=5000)
    impact: str = Field(default="", max_length=5000)
    solutions: list[str] = Field(default_factory=list, max_length=50)
    data_source: str = Field(default="local", max_length=160)
    confidence: str = Field(default="high", max_length=20)
    repair_id: str = Field(default="", max_length=100)
    repair_level: str = Field(default="manual", max_length=30)
    verification_check_ids: list[str] = Field(default_factory=list, max_length=50)
    duration_ms: int = Field(default=0, ge=0, le=3_600_000)
    error_code: str = Field(default="", max_length=100)
    priority: Literal["BLOCKING", "HIGH_RISK", "ADVISORY", "INFORMATIONAL"] = "INFORMATIONAL"
    blocking: bool = False
    repair_outcome: dict[str, Any] = Field(default_factory=dict)
    sampled_at: str = Field(default="", max_length=50)
    recheck_of: str = Field(default="", max_length=80)
    retryable: bool = False
    technical_error: str = Field(default="", max_length=5000)
    restart_required: bool = False



class ReportIn(BaseModel):
    report_id: str = Field(min_length=8, max_length=80)
    customer_name: str = Field(default="", max_length=120)
    room_name: str = Field(default="", max_length=120)
    app_version: str = Field(default="", max_length=40)
    checked_at: str = Field(max_length=50)
    overall_status: Status
    conclusion: str = Field(default="", max_length=2000)
    schema_version: int = Field(default=REPORT_SCHEMA_VERSION, ge=1, le=REPORT_SCHEMA_VERSION)
    run_mode: Literal["daily_preflight", "environment_setup"] = "daily_preflight"
    target_region_id: str = Field(default="us-los-angeles", max_length=80)
    network_snapshot: dict[str, Any] = Field(default_factory=dict)
    ip_profile: dict[str, Any] = Field(default_factory=dict)
    streaming_profiles: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    data_sources: list[str] = Field(default_factory=list, max_length=50)
    repair_events: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    environment_snapshot: dict[str, Any] = Field(default_factory=dict)
    device_snapshot: dict[str, Any] = Field(default_factory=dict)
    check_logs: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    before_snapshot: dict[str, Any] = Field(default_factory=dict)
    after_snapshot: dict[str, Any] = Field(default_factory=dict)
    confidence_summary: dict[str, Any] = Field(default_factory=dict)
    readiness_level: Literal["READY", "READY_WITH_RISK", "NOT_READY", "INCOMPLETE"] = "INCOMPLETE"
    blocking_count: int = Field(default=0, ge=0, le=300)
    high_risk_count: int = Field(default=0, ge=0, le=300)
    test_mode: Literal["quick", "standard", "deep"] = "standard"
    baseline_delta: dict[str, Any] = Field(default_factory=dict)
    source_health: dict[str, Any] = Field(default_factory=dict)
    issue_tags: list[str] = Field(default_factory=list, max_length=30)
    environment_summary: str = Field(default="检测未完成", max_length=100)
    network_summary: str = Field(default="检测未完成", max_length=160)
    hardware_summary: str = Field(default="仅供参考", max_length=100)
    next_action: str = Field(default="", max_length=1000)
    items: list[CheckItemIn] = Field(max_length=300)

    @field_validator("schema_version")
    @classmethod
    def supported_schema(cls, value: int) -> int:
        if value not in SUPPORTED_REPORT_SCHEMAS:
            raise ValueError("不支持的报告 Schema")
        return value

    @model_validator(mode="after")
    def current_schema_scope(self):
        if self.schema_version == REPORT_SCHEMA_VERSION and any(not item.check_id.startswith(CURRENT_CHECK_PREFIXES) for item in self.items):
            raise ValueError("当前报告只允许网络、系统环境和电脑性能检查")
        return self


class CodeGenerateRequest(BaseModel):
    tier: Literal["TK-MONTH", "TK-QUARTER", "TK-HALF-YEAR", "TK-YEAR", "TK1", "TKX", "TKV"]
    count: int = Field(ge=1, le=500)
    note: str = Field(default="", max_length=300)
    batch: str = Field(default="", max_length=80)


class CodeStatusRequest(BaseModel):
    code: str = Field(max_length=80)
    status: Literal["available", "distributed", "used", "exhausted", "expired", "revoked"]


class CustomerIn(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    contact: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=2000)
    status: Literal["active", "inactive"] = "active"
    tenant_code: str = Field(default="", max_length=40)
    short_name: str = Field(default="", max_length=80)
    timezone: str = Field(default="Asia/Shanghai", max_length=80)
    plan_code: str = Field(default="trial", max_length=40)
    device_limit: int = Field(default=3, ge=1, le=100000)
    member_limit: int = Field(default=3, ge=1, le=10000)
    subscription_starts_at: str | None = Field(default=None, max_length=40)
    subscription_expires_at: str | None = Field(default=None, max_length=40)


class RoomIn(BaseModel):
    id: int | None = None
    customer_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    region: str = Field(default="", max_length=80)
    bitrate_kbps: int = Field(default=6000, ge=500, le=100000)
    notes: str = Field(default="", max_length=2000)
    status: Literal["active", "inactive"] = "active"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class SettingsIn(BaseModel):
    values: dict[str, str]

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 50 or any(len(k) > 80 or len(v) > 10000 for k, v in value.items()):
            raise ValueError("产品资料超出允许长度")
        return value


class DeviceIn(BaseModel):
    device_id: str = Field(max_length=80)
    customer_id: int | None = None
    room_id: int | None = None
    status: Literal["active", "inactive"] = "active"
    notes: str = Field(default="", max_length=2000)
    unbind_license: bool = False
    streaming_account_id: int | None = None
    display_name: str = Field(default="", max_length=120)
    store_name: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=160)
    owner_name: str = Field(default="", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=30)


class AdminMemberIn(BaseModel):
    id: int | None = None
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(default="", max_length=256)
    display_name: str = Field(default="", max_length=80)
    phone: str = Field(default="", max_length=30)
    role: Literal["tenant_owner", "tenant_operator", "tenant_viewer"] = "tenant_viewer"
    active: bool = True


class TenantProvisionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    short_name: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=160)
    timezone: str = Field(default="Asia/Shanghai", max_length=80)
    plan_code: Literal["trial", "basic", "pro", "custom"] = "trial"
    device_limit: int = Field(default=3, ge=1, le=100000)
    member_limit: int = Field(default=3, ge=1, le=10000)
    subscription_days: int = Field(default=30, ge=1, le=3650)
    owner_username: str = Field(min_length=3, max_length=80)
    owner_password: str = Field(min_length=8, max_length=256)
    owner_name: str = Field(default="", max_length=80)


class StreamingAccountIn(BaseModel):
    id: int | None = None
    room_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(default="TikTok", max_length=40)
    owner_name: str = Field(default="", max_length=80)
    target_region_id: str = Field(default="us-los-angeles", max_length=80)
    notes: str = Field(default="", max_length=2000)
    status: Literal["active", "inactive"] = "active"


class BindingCodeIn(BaseModel):
    room_id: int | None = None
    streaming_account_id: int | None = None


class BindDeviceIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class HeartbeatIn(BaseModel):
    client_at: str = Field(default="", max_length=50)
    app_version: str = Field(default="", max_length=40)
    live_state: Literal["idle", "checking", "repairing", "rechecking", "ready", "risk", "failed"] = "idle"
    readiness_state: Literal["ready", "warning", "blocked", "incomplete", "unknown"] = "unknown"
    studio_state: Literal["not_running", "running", "crashed", "unknown"] = "unknown"
    target_region_id: str = Field(default="", max_length=80)
    last_report_id: str | None = Field(default=None, max_length=80)
    last_report_at: str | None = Field(default=None, max_length=50)
    module_summary: dict[str, Any] = Field(default_factory=dict)


class DeviceEventIn(BaseModel):
    event_id: str = Field(min_length=8, max_length=80)
    event_type: Literal["online", "offline", "check_started", "check_failed", "repair_started", "repair_finished", "recheck_finished", "studio_started", "studio_stopped", "studio_crashed"]
    severity: Literal["info", "warning", "critical"] = "info"
    client_at: str = Field(default="", max_length=50)
    payload: dict[str, Any] = Field(default_factory=dict)


class DeviceEventsIn(BaseModel):
    events: list[DeviceEventIn] = Field(min_length=1, max_length=100)


class AlertUpdateIn(BaseModel):
    status: Literal["open", "acknowledged", "processing", "resolved", "closed"]


class WorkOrderIn(BaseModel):
    id: int | None = None
    alert_id: int | None = None
    device_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["open", "processing", "resolved", "closed"] = "open"
    owner: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=5000)
    resolution: str = Field(default="", max_length=5000)


class TenantDeviceUpdateIn(BaseModel):
    display_name: str = Field(default="", max_length=120)
    room_id: int | None = None
    streaming_account_id: int | None = None
    store_name: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=160)
    owner_name: str = Field(default="", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=30)


class TenantAlertSettingsIn(BaseModel):
    wecom_webhook: str = Field(default="", max_length=1000)
    enabled_types: list[str] = Field(default_factory=lambda: ["system_blocked", "device_offline", "studio_crashed"], max_length=20)
    minimum_severity: Literal["warning", "critical"] = "critical"
    quiet_start: str = Field(default="", max_length=5)
    quiet_end: str = Field(default="", max_length=5)


class SupportIn(BaseModel):
    id: int | None = None
    report_id: str | None = Field(default=None, max_length=80)
    device_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    status: Literal["open", "processing", "resolved", "closed"] = "open"
    owner: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=5000)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    region: str = Field(default="*", max_length=80)
    bitrate_kbps: int = Field(default=6000, ge=500, le=100000)
    rules: dict[str, float | int | str]


class ReleaseActivateIn(BaseModel):
    version: str = Field(min_length=1, max_length=40)


class UserRegisterRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=30)
    phone_country: str = Field(default="CN", max_length=10)
    password: str = Field(min_length=8, max_length=256)
    password_confirm: str = Field(min_length=8, max_length=256)
    email: str = Field(min_length=5, max_length=255)
    code: str = Field(min_length=4, max_length=10)

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("两次密码不一致")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
            raise ValueError("密码需包含数字和字母")
        return v


class UserLoginRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=30)
    password: str = Field(min_length=1, max_length=256)


class ForgotPasswordRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=30)


class ResetPasswordRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=30)
    code: str = Field(min_length=4, max_length=10)
    password: str = Field(min_length=8, max_length=256)
    password_confirm: str = Field(min_length=8, max_length=256)

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("两次密码不一致")
        return v


class SendCodeRequest(BaseModel):
    target: str = Field(min_length=5, max_length=255)
    purpose: str = Field(default="register", max_length=30)


class UserProfileUpdate(BaseModel):
    company_name: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=80)
    business_types: list[str] | None = Field(default=None)
    email: str | None = Field(default=None, max_length=255)
    wechat_id: str | None = Field(default=None, max_length=80)
    platform_account: str | None = Field(default=None, max_length=120)

    @field_validator("business_types")
    @classmethod
    def limit_business_types(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (len(value) > 20 or any(len(item) > 80 for item in value)):
            raise ValueError("业务类型数量或长度超出限制")
        return value
