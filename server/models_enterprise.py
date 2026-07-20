from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    role: Mapped[str] = mapped_column(String(30), default="viewer", index=True)
    permissions_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OrganizationMemberSession(Base):
    __tablename__ = "organization_member_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("organization_members.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LiveAccount(Base):
    __tablename__ = "live_accounts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("live_rooms.id", ondelete="SET NULL"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(30), default="tiktok")
    display_name: Mapped[str] = mapped_column(String(120), index=True)
    platform_account_ref: Mapped[str] = mapped_column(String(160), default="")
    target_region_id: Mapped[str] = mapped_column(String(80), default="us-los-angeles")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AnchorProfile(Base):
    __tablename__ = "anchor_profiles"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(120), index=True)
    employee_ref: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    labels_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DeviceRoomBinding(Base):
    __tablename__ = "device_room_bindings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(String(80), ForeignKey("devices.device_id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("live_rooms.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("live_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    anchor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("anchor_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    binding_type: Mapped[str] = mapped_column(String(20), default="primary", index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    bound_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("organization_members.id", ondelete="RESTRICT"), index=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("uq_active_primary_device", "device_id", unique=True, sqlite_where=text("status='active' AND binding_type='primary'"), postgresql_where=text("status='active' AND binding_type='primary'")),
        Index("uq_active_primary_room", "room_id", unique=True, sqlite_where=text("status='active' AND binding_type='primary'"), postgresql_where=text("status='active' AND binding_type='primary'")),
    )


class DeviceHeartbeatV2(Base):
    __tablename__ = "device_heartbeats_v2"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(String(80), ForeignKey("devices.device_id", ondelete="CASCADE"), index=True)
    binding_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("device_room_bindings.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_version: Mapped[str] = mapped_column(String(40), default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    device_status: Mapped[str] = mapped_column(String(20), default="online")
    live_software_json: Mapped[str] = mapped_column(Text, default="{}")
    collection_json: Mapped[str] = mapped_column(Text, default="{}")
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    upload_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    stream_bitrate_kbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropped_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("device_id", "sent_at", name="uq_device_heartbeat_sent_at"),)
