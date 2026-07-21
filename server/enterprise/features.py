from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Device
from ..models_enterprise import (
    DeviceFeatureOverride,
    FeatureDefinition,
    FeatureRollout,
    OrganizationFeature,
    PlanFeature,
    RoleFeaturePermission,
)
from .common import TenantContext
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
            raise HTTPException(422,{"code":"VALIDATION_ERROR","message":"功能配置包含未定义字段","details":{"fields":sorted(unknown)}})
    for key,value in config.items():
        expected=type_map.get((properties.get(key) or {}).get("type"))
        if expected and (not isinstance(value,expected) or isinstance(value,bool) and expected in {int,(int,float)}):
            raise HTTPException(422,{"code":"VALIDATION_ERROR","message":"功能配置字段类型不正确","details":{"field":key}})


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


class FeatureService:
    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self.organization = db.get(Customer, organization_id)
        if not self.organization:
            raise HTTPException(404, {"code": "TENANT_RESOURCE_NOT_FOUND", "message": "企业不存在"})

    def _rollout_allows(self, feature: FeatureDefinition, device_id: str | None, client_version: str) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        rows = self.db.scalars(select(FeatureRollout).where(FeatureRollout.feature_id == feature.id, FeatureRollout.status == "active")).all()
        if not rows:
            return True, "definition"
        for row in rows:
            if _aware(row.starts_at) and _aware(row.starts_at) > now: continue
            if _aware(row.ends_at) and _aware(row.ends_at) <= now: continue
            minimum = row.minimum_version or feature.minimum_client_version
            if minimum and _version_tuple(client_version) < _version_tuple(minimum): continue
            org_ids = set(_json(row.organization_ids_json, [])); device_ids = set(_json(row.device_ids_json, []))
            if row.rollout_type == "all": return True, "rollout"
            if row.rollout_type == "organizations" and self.organization_id in org_ids: return True, "rollout"
            if row.rollout_type == "devices" and device_id and device_id in device_ids: return True, "rollout"
            if row.rollout_type == "percentage":
                key = f"{feature.feature_code}:{device_id or self.organization_id}".encode()
                if int(hashlib.sha256(key).hexdigest()[:8], 16) % 100 < max(0, min(100, row.percentage)):
                    return True, "rollout"
        return False, "rollout_not_selected"

    def get_effective_features_for_organization(self, role: str = "owner", client_version: str = "") -> dict[str, dict]:
        seed_feature_definitions(self.db)
        definitions = self.db.scalars(select(FeatureDefinition).order_by(FeatureDefinition.category, FeatureDefinition.feature_code)).all()
        plans = {x.feature_id: x for x in self.db.scalars(select(PlanFeature).where(PlanFeature.plan_id == self.organization.plan_code)).all()}
        overrides = {x.feature_id: x for x in self.db.scalars(select(OrganizationFeature).where(OrganizationFeature.organization_id == self.organization_id)).all()}
        permissions = {x.feature_id: x for x in self.db.scalars(select(RoleFeaturePermission).where(RoleFeaturePermission.organization_id == self.organization_id, RoleFeaturePermission.role == role)).all()}
        now = datetime.now(timezone.utc); result = {}
        for feature in definitions:
            enabled = bool(feature.default_enabled and feature.status in {"enabled", "beta"}); source = "default"; limits = {}; config = {}; reason = ""
            plan = plans.get(feature.id)
            if plan:
                enabled = plan.enabled; source = "plan"; limits = _json(plan.limits_json, {}); config = _json(plan.config_json, {})
            override = overrides.get(feature.id)
            if override and (not _aware(override.starts_at) or _aware(override.starts_at) <= now) and (not _aware(override.expires_at) or _aware(override.expires_at) > now):
                enabled = override.enabled; source = override.source; config.update(_json(override.config_json, {}))
            elif override and _aware(override.expires_at) and _aware(override.expires_at) <= now:
                reason = "expired"
            if feature.status in {"disabled", "deprecated"}: enabled = False; reason = "feature_disabled"
            if feature.minimum_client_version and client_version and _version_tuple(client_version) < _version_tuple(feature.minimum_client_version): enabled = False; reason = "minimum_version"
            rollout, rollout_reason = self._rollout_allows(feature, None, client_version)
            if enabled and not rollout: enabled = False; reason = rollout_reason
            permission = permissions.get(feature.id)
            defaults={
                "owner":{"read":True,"create":True,"update":True,"delete":True,"manage":True},
                "manager":{"read":True,"create":True,"update":True,"delete":False,"manage":True},
                "operator":{"read":True,"create":False,"update":True,"delete":False,"manage":False},
                "viewer":{"read":True,"create":False,"update":False,"delete":False,"manage":False},
            }.get(role,{"read":False,"create":False,"update":False,"delete":False,"manage":False})
            actions = {name: bool(getattr(permission, f"can_{name}")) if permission else defaults[name] for name in ("read", "create", "update", "delete", "manage")}
            if enabled and not actions["read"]: enabled = False; reason = "role_forbidden"
            result[feature.feature_code] = {"enabled":enabled,"name":feature.feature_name,"category":feature.category,"source":source,"status":feature.status,"reason":reason,"minimum_version":feature.minimum_client_version,"limits":limits,"config":config,"permissions":actions}
        return result

    def get_effective_features_for_device(self, device: Device, client_version: str = "") -> dict[str, dict]:
        features = self.get_effective_features_for_organization("owner", client_version)
        definitions = {x.id:x for x in self.db.scalars(select(FeatureDefinition)).all()}
        now = datetime.now(timezone.utc)
        rows = self.db.scalars(select(DeviceFeatureOverride).where(DeviceFeatureOverride.organization_id == self.organization_id, DeviceFeatureOverride.device_id == device.device_id)).all()
        for row in rows:
            feature = definitions.get(row.feature_id)
            if not feature or (_aware(row.expires_at) and _aware(row.expires_at) <= now): continue
            item = features.get(feature.feature_code, {}); item.update({"enabled":row.enabled,"source":"device","reason":row.reason,"config":{**item.get("config",{}),**_json(row.config_json,{})}}); features[feature.feature_code]=item
        for code, item in features.items():
            feature = next((x for x in definitions.values() if x.feature_code == code), None)
            if feature and item.get("enabled"):
                allowed, reason = self._rollout_allows(feature, device.device_id, client_version)
                if not allowed: item.update({"enabled":False,"reason":reason})
        return features

    def is_feature_enabled(self, feature_code: str, *, role: str = "owner", device: Device | None = None, client_version: str = "") -> bool:
        features = self.get_effective_features_for_device(device, client_version) if device else self.get_effective_features_for_organization(role, client_version)
        return bool(features.get(feature_code, {}).get("enabled"))

    def get_feature_limits(self, feature_code: str, role: str = "owner") -> dict:
        return self.get_effective_features_for_organization(role).get(feature_code, {}).get("limits", {})

    def get_feature_config(self, feature_code: str, role: str = "owner") -> dict:
        return self.get_effective_features_for_organization(role).get(feature_code, {}).get("config", {})


def require_feature(feature_code: str):
    def dependency(ctx: TenantContext = Depends(current_member), db: Session = Depends(get_db)) -> dict:
        item = FeatureService(db, ctx.organization_id).get_effective_features_for_organization(ctx.role).get(feature_code, {})
        if not item.get("enabled"):
            raise HTTPException(403, {"code":"FEATURE_NOT_ENABLED","message":"当前企业尚未开通该功能","details":{"feature_code":feature_code}})
        return item
    return dependency


def require_feature_permission(feature_code: str, action: str):
    def dependency(ctx: TenantContext = Depends(current_member), db: Session = Depends(get_db)) -> dict:
        item = FeatureService(db, ctx.organization_id).get_effective_features_for_organization(ctx.role).get(feature_code, {})
        if not item.get("enabled"):
            raise HTTPException(403, {"code":"FEATURE_NOT_ENABLED","message":"当前企业尚未开通该功能","details":{"feature_code":feature_code}})
        if not item.get("permissions", {}).get(action):
            raise HTTPException(403, {"code":"PERMISSION_DENIED","message":"当前角色没有此操作权限","details":{"feature_code":feature_code,"action":action}})
        return item
    return dependency
