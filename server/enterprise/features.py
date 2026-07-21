from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Customer, Device, Setting
from ..models_enterprise import (
    DeviceFeatureOverride,
    FeatureDefinition,
    FeatureRollout,
    OrganizationFeature,
    PlanFeature,
    RoleFeaturePermission,
)
from .common import ROLE_PERMISSIONS, TenantContext, api_error, require_permission
from .security import current_member


DEFAULT_FEATURES = (
    ("environment_check", "开播环境检测", "client", "windows_client", True, "enabled"),
    ("environment_repair", "系统环境修复", "client", "windows_client", True, "enabled"),
    ("device_binding", "设备与直播间绑定", "device", "all", True, "enabled"),
    ("device_heartbeat", "设备实时状态", "device", "all", True, "enabled"),
    ("device_center", "设备中心", "enterprise", "enterprise_admin", True, "enabled"),
    ("member_management", "成员与权限", "enterprise", "enterprise_admin", True, "enabled"),
    ("alert_center", "告警中心", "enterprise", "enterprise_admin", True, "enabled"),
    ("report_center", "检测报告", "enterprise", "enterprise_admin", True, "enabled"),
    ("live_dashboard", "实时直播大屏", "live", "enterprise_admin", False, "beta"),
    ("live_data_collection", "直播数据采集", "live", "windows_client", False, "internal"),
    ("session_report", "直播场次复盘", "analysis", "enterprise_admin", False, "internal"),
    ("ai_review", "AI 复盘建议", "analysis", "enterprise_admin", False, "internal"),
    ("audit_logs", "操作日志", "enterprise", "enterprise_admin", True, "enabled"),
)


def _json(value: str, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for item in (value or "0").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple((parts + [0, 0, 0])[:3])


def validate_feature_config(feature: FeatureDefinition, config: dict) -> None:
    schema = _json(feature.config_schema_json, {})
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if not properties:
        return
    type_map={"string":str,"integer":int,"number":(int,float),"boolean":bool,"object":dict,"array":list}
    if schema.get("additionalProperties") is False:
        unknown=set(config)-set(properties)
        if unknown:
            raise api_error("VALIDATION_ERROR", "功能配置包含未定义字段", {"fields": sorted(unknown)})
    for key,value in config.items():
        expected=type_map.get((properties.get(key) or {}).get("type"))
        if expected and (not isinstance(value,expected) or isinstance(value,bool) and expected in {int,(int,float)}):
            raise api_error("VALIDATION_ERROR", "功能配置字段类型不正确", {"field": key})


def seed_feature_definitions(db: Session) -> None:
    existing = set(db.scalars(select(FeatureDefinition.feature_code)).all())
    changed = False
    for code, name, category, client_type, enabled, status in DEFAULT_FEATURES:
        if code not in existing:
            db.add(FeatureDefinition(feature_code=code, feature_name=name, category=category, client_type=client_type, default_enabled=enabled, status=status))
            changed = True
    if changed:
        db.commit()
    else:
        db.flush()


ROLE_ACTION_DEFAULTS = {
    "owner": {"read": True, "create": True, "update": True, "delete": True, "manage": True},
    "manager": {"read": True, "create": True, "update": True, "delete": False, "manage": True},
    "operator": {"read": True, "create": False, "update": True, "delete": False, "manage": False},
    "viewer": {"read": True, "create": False, "update": False, "delete": False, "manage": False},
}


def feature_config_epoch(db: Session) -> int:
    row = db.get(Setting, "feature_config_epoch")
    try:
        return max(1, int(row.value)) if row else 1
    except (TypeError, ValueError):
        return 1


def bump_feature_config_epoch(db: Session) -> int:
    row = db.get(Setting, "feature_config_epoch")
    value = feature_config_epoch(db) + 1
    if row:
        row.value = str(value)
    else:
        db.add(Setting(key="feature_config_epoch", value=str(value)))
    return value


def effective_config_version(db: Session, organization: Customer, device: Device | None = None) -> int:
    return feature_config_epoch(db) * 1_000_000_000_000 + organization.feature_config_version * 1_000_000 + (device.feature_config_version if device else 0)


CLIENT_CONFIG_KEYS = {
    "heartbeat_interval_seconds",
    "heartbeat_queue_max_items",
    "heartbeat_queue_max_age_hours",
    "minimum_client_version",
}


def client_runtime_config(db: Session) -> dict:
    settings = get_settings()
    values = {
        "heartbeat_interval_seconds": settings.heartbeat_interval_seconds,
        "heartbeat_queue_max_items": settings.heartbeat_queue_max_items,
        "heartbeat_queue_max_age_hours": settings.heartbeat_queue_max_age_hours,
        "minimum_client_version": settings.minimum_client_version,
    }
    rows = {row.key: row.value for row in db.scalars(select(Setting).where(Setting.key.in_(CLIENT_CONFIG_KEYS))).all()}
    for key in ("heartbeat_interval_seconds", "heartbeat_queue_max_items", "heartbeat_queue_max_age_hours"):
        if key in rows:
            try:
                parsed = int(rows[key])
                if parsed > 0:
                    values[key] = parsed
            except (TypeError, ValueError):
                continue
    if rows.get("minimum_client_version", "").strip():
        values["minimum_client_version"] = rows["minimum_client_version"].strip()
    return values


class FeatureService:
    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self.organization = db.get(Customer, organization_id)
        if not self.organization:
            raise api_error("TENANT_RESOURCE_NOT_FOUND", "企业不存在")

    def _rollout_result(self, feature: FeatureDefinition, rows: list[FeatureRollout], device_id: str | None, client_version: str) -> tuple[bool, bool, str]:
        now = datetime.now(timezone.utc)
        if not rows:
            return False, False, ""
        eligible = []
        for row in sorted(rows, key=lambda item: item.id, reverse=True):
            if _aware(row.starts_at) and _aware(row.starts_at) > now: continue
            if _aware(row.ends_at) and _aware(row.ends_at) <= now: continue
            minimum = row.minimum_version or feature.minimum_client_version
            if minimum and _version_tuple(client_version) < _version_tuple(minimum): continue
            eligible.append(row)
        if not eligible:
            return True, False, "rollout_not_selected"
        for row in eligible:
            org_ids = set(_json(row.organization_ids_json, [])); device_ids = set(_json(row.device_ids_json, []))
            if row.rollout_type == "all": return True, True, "rollout_all"
            if row.rollout_type == "organizations" and self.organization_id in org_ids: return True, True, "rollout_organization"
            if row.rollout_type == "devices" and device_id and device_id in device_ids: return True, True, "rollout_device"
            if row.rollout_type == "internal" and (self.organization_id in org_ids or bool(device_id and device_id in device_ids)):
                return True, True, "rollout_internal"
            if row.rollout_type == "percentage":
                key = f"{feature.feature_code}:{device_id or self.organization_id}".encode()
                if int(hashlib.sha256(key).hexdigest()[:8], 16) % 100 < max(0, min(100, row.percentage)):
                    return True, True, "rollout_percentage"
        return True, False, "rollout_not_selected"

    def _effective_features(self, role: str, client_version: str, device: Device | None) -> dict[str, dict]:
        seed_feature_definitions(self.db)
        definitions = self.db.scalars(select(FeatureDefinition).order_by(FeatureDefinition.category, FeatureDefinition.feature_code)).all()
        plans = {x.feature_id: x for x in self.db.scalars(select(PlanFeature).where(PlanFeature.plan_id == self.organization.plan_code)).all()}
        overrides = {x.feature_id: x for x in self.db.scalars(select(OrganizationFeature).where(OrganizationFeature.organization_id == self.organization_id)).all()}
        device_overrides = {x.feature_id: x for x in self.db.scalars(select(DeviceFeatureOverride).where(DeviceFeatureOverride.organization_id == self.organization_id, DeviceFeatureOverride.device_id == device.device_id)).all()} if device else {}
        permissions = {x.feature_id: x for x in self.db.scalars(select(RoleFeaturePermission).where(RoleFeaturePermission.organization_id == self.organization_id, RoleFeaturePermission.role == role)).all()}
        rollout_rows: dict[int, list[FeatureRollout]] = {}
        for row in self.db.scalars(select(FeatureRollout).where(FeatureRollout.status == "active")).all():
            rollout_rows.setdefault(row.feature_id, []).append(row)
        now = datetime.now(timezone.utc); result = {}
        for feature in definitions:
            plan = plans.get(feature.id)
            override = overrides.get(feature.id)
            device_override = device_overrides.get(feature.id)
            plan_config = _json(plan.config_json, {}) if plan else {}
            limits = _json(plan.limits_json, {}) if plan else {}
            config = dict(plan_config)
            reason = ""
            rollout_applied = False
            rollout_hit = False
            active_org_override = bool(override and (not _aware(override.starts_at) or _aware(override.starts_at) <= now) and (not _aware(override.expires_at) or _aware(override.expires_at) > now))
            active_device_override = bool(device_override and (not _aware(device_override.expires_at) or _aware(device_override.expires_at) > now))

            if feature.status in {"disabled", "deprecated"}:
                enabled, source, reason = False, "definition", "feature_disabled"
            elif feature.minimum_client_version and client_version and _version_tuple(client_version) < _version_tuple(feature.minimum_client_version):
                enabled, source, reason = False, "definition", "minimum_version"
            elif active_device_override:
                enabled, source, reason = bool(device_override.enabled), "device", device_override.reason or "device_override"
                config.update(_json(device_override.config_json, {}))
            elif active_org_override:
                enabled, source, reason = bool(override.enabled), override.source or "organization", "organization_override"
                config.update(_json(override.config_json, {}))
            elif plan:
                enabled, source = bool(plan.enabled), "plan"
                if override and _aware(override.expires_at) and _aware(override.expires_at) <= now:
                    reason = "expired"
            else:
                rollout_applied, rollout_hit, rollout_reason = self._rollout_result(feature, rollout_rows.get(feature.id, []), device.device_id if device else None, client_version)
                if rollout_applied:
                    enabled, source, reason = rollout_hit, "rollout", rollout_reason
                else:
                    enabled, source = bool(feature.default_enabled and feature.status in {"enabled", "beta"}), "default"
                if override and _aware(override.expires_at) and _aware(override.expires_at) <= now:
                    reason = "expired" if not reason else reason
            permission = permissions.get(feature.id)
            defaults=ROLE_ACTION_DEFAULTS.get(role,{"read":False,"create":False,"update":False,"delete":False,"manage":False})
            actions = {name: bool(getattr(permission, f"can_{name}")) if permission else defaults[name] for name in ("read", "create", "update", "delete", "manage")}
            if enabled and not actions["read"]: enabled = False; reason = "role_forbidden"
            result[feature.feature_code] = {"enabled":enabled,"name":feature.feature_name,"category":feature.category,"source":source,"status":feature.status,"reason":reason,"minimum_version":feature.minimum_client_version,"limits":limits,"config":config,"permissions":actions,"rollout":{"applied":rollout_applied,"matched":rollout_hit}}
        return result

    def get_effective_features_for_organization(self, role: str = "owner", client_version: str = "") -> dict[str, dict]:
        return self._effective_features(role, client_version, None)

    def get_effective_features_for_device(self, device: Device, client_version: str = "") -> dict[str, dict]:
        return self._effective_features("owner", client_version, device)

    def is_feature_enabled(self, feature_code: str, *, role: str = "owner", device: Device | None = None, client_version: str = "") -> bool:
        features = self.get_effective_features_for_device(device, client_version) if device else self.get_effective_features_for_organization(role, client_version)
        return bool(features.get(feature_code, {}).get("enabled"))

    def get_feature_limits(self, feature_code: str, role: str = "owner") -> dict:
        return self.get_effective_features_for_organization(role).get(feature_code, {}).get("limits", {})

    def get_feature_config(self, feature_code: str, role: str = "owner") -> dict:
        return self.get_effective_features_for_organization(role).get(feature_code, {}).get("config", {})


def authorize_feature_action(ctx: TenantContext, db: Session, feature_code: str, action: str, base_permission: str | None = None) -> dict:
    if base_permission:
        require_permission(ctx, base_permission)
    item = FeatureService(db, ctx.organization_id).get_effective_features_for_organization(ctx.role).get(feature_code, {})
    if not item.get("enabled"):
        raise api_error("FEATURE_NOT_ENABLED", "当前企业尚未开通该功能", {"feature_code": feature_code, "reason": item.get("reason", "")})
    if action and not item.get("permissions", {}).get(action):
        raise api_error("PERMISSION_DENIED", "当前角色没有此操作权限", {"feature_code": feature_code, "action": action})
    return item


def feature_action(feature_code: str, action: str, base_permission: str | None = None):
    def dependency(ctx: TenantContext = Depends(current_member), db: Session = Depends(get_db)) -> dict:
        return authorize_feature_action(ctx, db, feature_code, action, base_permission)
    return dependency


def require_feature(feature_code: str):
    def dependency(ctx: TenantContext = Depends(current_member), db: Session = Depends(get_db)) -> dict:
        return authorize_feature_action(ctx, db, feature_code, "read")
    return dependency


def require_feature_permission(feature_code: str, action: str):
    def dependency(ctx: TenantContext = Depends(current_member), db: Session = Depends(get_db)) -> dict:
        return authorize_feature_action(ctx, db, feature_code, action)
    return dependency
