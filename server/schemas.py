from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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


class ReportIn(BaseModel):
    report_id: str = Field(min_length=8, max_length=80)
    customer_name: str = Field(default="", max_length=120)
    room_name: str = Field(default="", max_length=120)
    app_version: str = Field(default="", max_length=40)
    checked_at: str = Field(max_length=50)
    overall_status: Status
    conclusion: str = Field(default="", max_length=2000)
    schema_version: int = Field(default=4, ge=1, le=10)
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
    items: list[CheckItemIn] = Field(max_length=300)


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
