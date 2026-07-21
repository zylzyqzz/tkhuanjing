from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Code(Base):
    __tablename__ = "codes"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    tier: Mapped[str] = mapped_column(String(8), index=True)
    credits: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True, default="available")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    customer_note: Mapped[str] = mapped_column(Text, default="")
    bound_device_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    activated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    batch: Mapped[str] = mapped_column(String(80), default="")
    plan_code: Mapped[str] = mapped_column(String(30), default="")
    duration_days: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Release(Base):
    __tablename__ = "releases"
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    installer_filename: Mapped[str] = mapped_column(String(255), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    channel: Mapped[str] = mapped_column(String(20), default="stable")
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    minimum_version: Mapped[str] = mapped_column(String(40), default="")
    signature: Mapped[str] = mapped_column(Text, default="")


class DownloadStat(Base):
    __tablename__ = "download_stats"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    contact: Mapped[str] = mapped_column(String(160), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    tenant_code: Mapped[str] = mapped_column(String(40), default="", index=True)
    organization_code: Mapped[str] = mapped_column(String(40), default="", index=True)
    short_name: Mapped[str] = mapped_column(String(80), default="")
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Shanghai")
    plan_code: Mapped[str] = mapped_column(String(40), default="trial")
    device_limit: Mapped[int] = mapped_column(Integer, default=3)
    member_limit: Mapped[int] = mapped_column(Integer, default=3)
    subscription_starts_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subscription_expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    grace_ends_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    wecom_webhook_encrypted: Mapped[str] = mapped_column(Text, default="")
    alert_settings_json: Mapped[str] = mapped_column(Text, default="{}")
    feature_config_version: Mapped[int] = mapped_column(Integer, default=1)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=1)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    rooms: Mapped[list[LiveRoom]] = relationship(back_populates="customer")


class LiveRoom(Base):
    __tablename__ = "live_rooms"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120), index=True)
    region: Mapped[str] = mapped_column(String(80), default="")
    bitrate_kbps: Mapped[int] = mapped_column(Integer, default=6000)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    status: Mapped[str] = mapped_column(String(20), default="active")
    customer: Mapped[Customer | None] = relationship(back_populates="rooms")


class Device(Base):
    __tablename__ = "devices"
    device_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    room_id: Mapped[int | None] = mapped_column(ForeignKey("live_rooms.id", ondelete="SET NULL"))
    customer_name: Mapped[str] = mapped_column(String(120), default="")
    room_name: Mapped[str] = mapped_column(String(120), default="")
    app_version: Mapped[str] = mapped_column(String(40), default="")
    target_region_id: Mapped[str] = mapped_column(String(80), default="us-los-angeles")
    license_code: Mapped[str | None] = mapped_column(ForeignKey("codes.code", ondelete="SET NULL"))
    free_uses_remaining: Mapped[int] = mapped_column(Integer, default=1)
    free_trial_started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    free_trial_expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    last_seen: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    streaming_account_id: Mapped[int | None] = mapped_column(ForeignKey("streaming_accounts.id", ondelete="SET NULL"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    store_name: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(160), default="")
    owner_name: Mapped[str] = mapped_column(String(80), default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    live_state: Mapped[str] = mapped_column(String(30), default="idle", index=True)
    readiness_state: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    studio_state: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    last_heartbeat_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    last_report_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_report_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    module_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    online_state: Mapped[str] = mapped_column(String(20), default="offline", index=True)
    collector_state: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    upload_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    stream_bitrate_kbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropped_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clock_skew_seconds: Mapped[int] = mapped_column(Integer, default=0)
    feature_config_version: Mapped[int] = mapped_column(Integer, default=1)


class StreamingAccount(Base):
    __tablename__ = "streaming_accounts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("live_rooms.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    platform: Mapped[str] = mapped_column(String(40), default="TikTok")
    owner_name: Mapped[str] = mapped_column(String(80), default="")
    target_region_id: Mapped[str] = mapped_column(String(80), default="us-los-angeles")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class DeviceBindingCode(Base):
    __tablename__ = "device_binding_codes"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("live_rooms.id", ondelete="SET NULL"), nullable=True)
    streaming_account_id: Mapped[int | None] = mapped_column(ForeignKey("streaming_accounts.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"))
    expires_at: Mapped[str] = mapped_column(String(40), index=True)
    used_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    used_device_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class CheckReport(Base):
    __tablename__ = "check_reports"
    report_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id", ondelete="CASCADE"), index=True)
    customer_name: Mapped[str] = mapped_column(String(120), default="")
    room_name: Mapped[str] = mapped_column(String(120), default="")
    app_version: Mapped[str] = mapped_column(String(40), default="")
    checked_at: Mapped[str] = mapped_column(String(40), index=True)
    overall_status: Mapped[str] = mapped_column(String(16), index=True)
    conclusion: Mapped[str] = mapped_column(Text, default="")
    schema_version: Mapped[int] = mapped_column(Integer, default=4)
    run_mode: Mapped[str] = mapped_column(String(30), default="daily_preflight", index=True)
    target_region_id: Mapped[str] = mapped_column(String(80), default="us-los-angeles", index=True)
    network_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    ip_profile_json: Mapped[str] = mapped_column(Text, default="{}")
    streaming_profiles_json: Mapped[str] = mapped_column(Text, default="[]")
    data_sources_json: Mapped[str] = mapped_column(Text, default="[]")
    repair_events_json: Mapped[str] = mapped_column(Text, default="[]")
    environment_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    device_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    check_logs_json: Mapped[str] = mapped_column(Text, default="[]")
    before_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    after_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    confidence_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    readiness_level: Mapped[str] = mapped_column(String(30), default="INCOMPLETE", index=True)
    blocking_count: Mapped[int] = mapped_column(Integer, default=0)
    high_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    test_mode: Mapped[str] = mapped_column(String(20), default="standard")
    baseline_delta_json: Mapped[str] = mapped_column(Text, default="{}")
    source_health_json: Mapped[str] = mapped_column(Text, default="{}")
    issue_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    environment_summary: Mapped[str] = mapped_column(String(80), default="检测未完成")
    network_summary: Mapped[str] = mapped_column(String(100), default="检测未完成")
    hardware_summary: Mapped[str] = mapped_column(String(80), default="仅供参考")
    next_action: Mapped[str] = mapped_column(Text, default="")
    ai_analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    uploaded_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    items: Mapped[list[CheckItem]] = relationship(cascade="all, delete-orphan")


class CheckItem(Base):
    __tablename__ = "check_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("check_reports.report_id", ondelete="CASCADE"), index=True)
    check_id: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    value: Mapped[str] = mapped_column(String(160), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    repairable: Mapped[bool] = mapped_column(Boolean, default=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    diagnosis: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[str] = mapped_column(Text, default="")
    solutions_json: Mapped[str] = mapped_column(Text, default="[]")
    data_source: Mapped[str] = mapped_column(String(160), default="local")
    confidence: Mapped[str] = mapped_column(String(20), default="high")
    repair_id: Mapped[str] = mapped_column(String(100), default="")
    repair_level: Mapped[str] = mapped_column(String(30), default="manual")
    verification_json: Mapped[str] = mapped_column(Text, default="[]")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(100), default="")
    priority: Mapped[str] = mapped_column(String(30), default="INFORMATIONAL")
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    repair_outcome_json: Mapped[str] = mapped_column(Text, default="{}")
    sampled_at: Mapped[str] = mapped_column(String(50), default="")
    recheck_of: Mapped[str] = mapped_column(String(80), default="")
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    technical_error: Mapped[str] = mapped_column(Text, default="")
    restart_required: Mapped[bool] = mapped_column(Boolean, default=False)


class CheckProfile(Base):
    __tablename__ = "check_profiles"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(80), default="*")
    bitrate_kbps: Mapped[int] = mapped_column(Integer, default=6000)
    rules_json: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class SupportCase(Base):
    __tablename__ = "support_cases"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    owner: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class DeviceEvent(Base):
    __tablename__ = "device_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)
    client_at: Mapped[str] = mapped_column(String(40), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id", ondelete="CASCADE"), index=True)
    alert_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    title: Mapped[str] = mapped_column(String(160))
    root_cause: Mapped[str] = mapped_column(String(80), default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    last_seen_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
    acknowledged_by: Mapped[str] = mapped_column(String(80), default="")
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.device_id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    owner: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(30), default="wecom")
    event_type: Mapped[str] = mapped_column(String(30), default="opened")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    sent_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    device_limit: Mapped[int] = mapped_column(Integer)
    member_limit: Mapped[int] = mapped_column(Integer)
    report_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    wecom_alerts: Mapped[bool] = mapped_column(Boolean, default=False)
    advanced_stats: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    plan_code: Mapped[str] = mapped_column(ForeignKey("subscription_plans.code"))
    order_no: Mapped[str] = mapped_column(String(80), default="", index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    device_limit: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    grace_ends_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str] = mapped_column(String(60), default="")
    target_id: Mapped[str] = mapped_column(String(100), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)


class LicenseEvent(Base):
    __tablename__ = "license_events"
    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80), index=True)
    code: Mapped[str | None] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(40))
    credits_after: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(30), default="platform_super", index=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    last_login_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_login_ip: Mapped[str] = mapped_column(String(80), default="")
    password_changed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    phone_country: Mapped[str] = mapped_column(String(10), default="CN")
    password_hash: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    business_types: Mapped[str | None] = mapped_column(Text, nullable=True, default="[]")
    wechat_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    platform_account: Mapped[str | None] = mapped_column(String(120), nullable=True)
    profile_completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    trial_granted: Mapped[int] = mapped_column(Integer, default=0)
    trial_expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    last_active_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    expires_at: Mapped[str] = mapped_column(String(40))
    revoked: Mapped[int] = mapped_column(Integer, default=0)
    user: Mapped["User"] = relationship(back_populates="sessions")


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    code: Mapped[str] = mapped_column(String(10))
    purpose: Mapped[str] = mapped_column(String(30))
    used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    expires_at: Mapped[str] = mapped_column(String(40))
