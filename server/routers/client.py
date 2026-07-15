from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CheckItem, CheckProfile, CheckReport, Code, Device, LicenseEvent, now_iso
from ..schemas import ActivateRequest, AuthorizeRequest, RegisterRequest, ReportIn
from ..security import current_device, hash_token
from ..services import DEFAULT_PROFILE, release_manifest
from client_v2.regions import REGIONS


router = APIRouter(tags=["client-v1"])


def license_view(device: Device, db: Session) -> dict:
    code = db.get(Code, device.license_code) if device.license_code else None
    if not code:
        return {"tier": "FREE", "credits": device.free_uses_remaining, "status": "active", "expires_at": device.free_trial_expires_at}
    return {"code": code.code, "tier": code.tier, "plan_code": code.plan_code, "credits": code.credits, "status": code.status, "expires_at": code.expires_at}


@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    token = secrets.token_urlsafe(32)
    device = db.get(Device, payload.device_id)
    if not device:
        started = datetime.now(timezone.utc); device = Device(device_id=payload.device_id, token_hash=hash_token(token), free_uses_remaining=1, free_trial_started_at=started.isoformat(), free_trial_expires_at=(started + timedelta(days=1)).isoformat())
        db.add(device)
    else:
        device.token_hash = hash_token(token)
    device.customer_name = payload.customer_name
    device.room_name = payload.room_name
    device.app_version = payload.app_version
    device.target_region_id = payload.target_region_id
    device.last_seen = now_iso()
    db.commit()
    return {"device_token": token, "device_id": device.device_id, "license": license_view(device, db)}


@router.get("/profile")
@router.get("/check-profile", include_in_schema=False)
def profile(device: Device = Depends(current_device), db: Session = Depends(get_db)) -> dict:
    device.last_seen = now_iso()
    row = db.scalar(select(CheckProfile).where(CheckProfile.active.is_(True)).order_by(CheckProfile.id.desc()))
    db.commit()
    return json.loads(row.rules_json) if row else DEFAULT_PROFILE


@router.post("/activate")
def activate(payload: ActivateRequest, device: Device = Depends(current_device), db: Session = Depends(get_db)) -> dict:
    code = db.get(Code, payload.code.strip().upper())
    if not code or code.status in {"revoked", "exhausted"}:
        raise HTTPException(status_code=400, detail="激活码无效或已停用")
    if code.bound_device_id and code.bound_device_id != device.device_id:
        raise HTTPException(status_code=409, detail="激活码已绑定其他设备")
    code.bound_device_id = device.device_id
    now = datetime.now(timezone.utc)
    code.activated_at = code.activated_at or now.isoformat()
    if code.plan_code and code.duration_days:
        current_expiry = datetime.fromisoformat(code.expires_at) if code.expires_at else now
        code.expires_at = (max(now, current_expiry) + timedelta(days=code.duration_days)).isoformat()
    code.status = "used"
    code.updated_at = now_iso()
    device.license_code = code.code
    db.commit()
    return {"ok": True, "license": license_view(device, db)}


@router.post("/authorize")
@router.post("/authorize-check", include_in_schema=False)
def authorize(payload: AuthorizeRequest, device: Device = Depends(current_device), db: Session = Depends(get_db)) -> dict:
    existing = db.get(LicenseEvent, payload.event_id)
    if existing:
        return {"authorized": True, "idempotent": True, "credits": existing.credits_after}
    code = db.get(Code, device.license_code) if device.license_code else None
    if code:
        if code.status == "revoked" or code.credits == 0:
            raise HTTPException(status_code=402, detail="授权已失效或次数已用完")
        if code.plan_code and code.expires_at:
            if datetime.fromisoformat(code.expires_at) <= datetime.now(timezone.utc):
                code.status = "expired"; db.commit(); raise HTTPException(status_code=402, detail="授权已到期，请续费后继续检测")
        elif code.credits > 0:
            code.credits -= 1
            code.used_count += 1
            if code.credits == 0:
                code.status = "exhausted"
        remaining = code.credits
    else:
        if not device.free_trial_expires_at:
            if device.free_uses_remaining <= 0:
                raise HTTPException(status_code=402, detail="免费体验已结束，请选择套餐继续检测")
            started = datetime.now(timezone.utc); device.free_trial_started_at = started.isoformat(); device.free_trial_expires_at = (started + timedelta(days=1)).isoformat()
        if datetime.fromisoformat(device.free_trial_expires_at) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=402, detail="免费体验已结束，请选择套餐继续检测")
        # Keep the legacy numeric field for old clients; expiry is the source of truth.
        remaining = 0
    db.add(LicenseEvent(event_id=payload.event_id, device_id=device.device_id, code=device.license_code, event_type="check", credits_after=remaining))
    db.commit()
    return {"authorized": True, "idempotent": False, "credits": remaining, "expires_at": code.expires_at if code else device.free_trial_expires_at}


@router.post("/reports")
@router.post("/setup-reports")
def upload_report(payload: ReportIn, device: Device = Depends(current_device), db: Session = Depends(get_db)) -> dict:
    if db.get(CheckReport, payload.report_id):
        return {"ok": True, "idempotent": True, "report_id": payload.report_id}
    report = CheckReport(
        report_id=payload.report_id, device_id=device.device_id, customer_name=payload.customer_name,
        room_name=payload.room_name, app_version=payload.app_version, checked_at=payload.checked_at,
        overall_status=payload.overall_status, conclusion=payload.conclusion,
        schema_version=payload.schema_version, run_mode=payload.run_mode, target_region_id=payload.target_region_id,
        network_snapshot_json=json.dumps(payload.network_snapshot, ensure_ascii=False),
        ip_profile_json=json.dumps(payload.ip_profile, ensure_ascii=False),
        streaming_profiles_json=json.dumps(payload.streaming_profiles, ensure_ascii=False),
        data_sources_json=json.dumps(payload.data_sources, ensure_ascii=False),
        repair_events_json=json.dumps(payload.repair_events, ensure_ascii=False),
        environment_snapshot_json=json.dumps(payload.environment_snapshot, ensure_ascii=False),
        device_snapshot_json=json.dumps(payload.device_snapshot, ensure_ascii=False),
        check_logs_json=json.dumps(payload.check_logs, ensure_ascii=False),
        before_snapshot_json=json.dumps(payload.before_snapshot, ensure_ascii=False),
        after_snapshot_json=json.dumps(payload.after_snapshot, ensure_ascii=False),
        confidence_summary_json=json.dumps(payload.confidence_summary, ensure_ascii=False),
    )
    report.items = [CheckItem(
        check_id=item.check_id, category=item.category, status=item.status, title=item.title,
        value=item.value, reason=item.reason, action=item.action, repairable=item.repairable,
        details_json=json.dumps(item.details, ensure_ascii=False),
        evidence_json=json.dumps(item.evidence, ensure_ascii=False), metrics_json=json.dumps(item.metrics, ensure_ascii=False),
        diagnosis=item.diagnosis, impact=item.impact, solutions_json=json.dumps(item.solutions, ensure_ascii=False),
        data_source=item.data_source, confidence=item.confidence, repair_id=item.repair_id,
        repair_level=item.repair_level, verification_json=json.dumps(item.verification_check_ids, ensure_ascii=False),
        duration_ms=item.duration_ms, error_code=item.error_code,
    ) for item in payload.items]
    db.add(report)
    device.last_seen = now_iso()
    db.commit()
    return {"ok": True, "idempotent": False, "report_id": payload.report_id}


@router.get("/reports/latest")
def latest_report(device: Device = Depends(current_device), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(CheckReport).where(CheckReport.device_id == device.device_id).order_by(CheckReport.checked_at.desc()))
    return {"report": None} if not row else {"report": {
        "report_id": row.report_id, "checked_at": row.checked_at,
        "overall_status": row.overall_status, "conclusion": row.conclusion,
    }}


@router.get("/update")
def update(channel: str = "stable", db: Session = Depends(get_db)) -> dict:
    return release_manifest(db, channel)


@router.get("/regions")
def regions() -> dict:
    return {"regions": [{
        "id": item.region_id, "label": item.label, "country_code": item.country_code,
        "windows_timezone": item.windows_timezone, "iana_timezone": item.iana_timezone,
    } for item in REGIONS]}


@router.get("/network-intelligence/status")
def network_intelligence_status() -> dict:
    return {"providers": [
        {"name": "PingIP", "role": "IP 归属与辅助情报", "mode": "primary"},
        {"name": "Cloudflare + GeoIP", "role": "公网 IP 与测速降级链路", "mode": "fallback"},
    ], "policy": "第三方数据失败时返回 UNKNOWN，不把服务失败判定为客户网络故障"}


@router.post("/upload-test")
async def upload_test(request: Request) -> dict:
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="测速数据过大")
    return {"ok": True, "bytes": size, "received": size}
