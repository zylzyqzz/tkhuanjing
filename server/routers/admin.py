from __future__ import annotations

import csv
import io
import json
import shutil
from datetime import date, datetime, timedelta, timezone
import statistics
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Admin, AuditLog, CheckItem, CheckProfile, CheckReport, Code, Customer, Device, DownloadStat, LiveRoom, Release, Setting, SupportCase, User, UserSession, now_iso
from ..schemas import CodeGenerateRequest, CodeStatusRequest, CustomerIn, DeviceIn, LoginRequest, ProfileIn, ReleaseActivateIn, RoomIn, SettingsIn, SupportIn
from ..security import clear_login_attempts, current_admin, make_session, rate_limit_login, request_ip, require_csrf, verify_password
from ..services import audit, create_codes, file_sha256


router = APIRouter(prefix="/tk-api", tags=["admin"])
settings = get_settings()


def row_dict(row, fields: list[str]) -> dict:
    return {field: getattr(row, field, None) for field in fields}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip = request_ip(request)
    rate_limit_login(ip)
    admin = db.scalar(select(Admin).where(Admin.username == payload.username, Admin.active.is_(True)))
    if not admin or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    clear_login_attempts(ip)
    token, csrf = make_session(admin.username)
    response.set_cookie("tk_session", token, httponly=True, samesite="strict", secure=settings.env == "production", max_age=settings.session_hours * 3600)
    audit(db, admin.username, "login", details=ip)
    db.commit()
    return {"ok": True, "csrf": csrf, "username": admin.username}


@router.get("/session")
def session(admin: dict = Depends(current_admin)) -> dict:
    return {"logged_in": True, "username": admin["username"], "csrf": admin["csrf"]}


@router.post("/logout")
def logout(response: Response, admin: dict = Depends(require_csrf)) -> dict:
    response.delete_cookie("tk_session")
    return {"ok": True}


@router.get("/stats")
def stats(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    today = date.today().isoformat()
    report_statuses = dict(db.execute(select(CheckReport.overall_status, func.count()).where(CheckReport.checked_at.startswith(today)).group_by(CheckReport.overall_status)).all())
    top_faults = db.execute(select(CheckItem.title, func.count().label("count")).where(CheckItem.status == "FAIL").group_by(CheckItem.title).order_by(func.count().desc()).limit(8)).all()
    versions = db.execute(select(Device.app_version, func.count().label("count")).group_by(Device.app_version).order_by(func.count().desc())).all()
    regions = db.execute(select(CheckReport.target_region_id, func.count().label("count")).group_by(CheckReport.target_region_id).order_by(func.count().desc()).limit(8)).all()
    repairable = db.scalar(select(func.count()).select_from(CheckItem).where(CheckItem.repairable.is_(True))) or 0
    run_modes = dict(db.execute(select(CheckReport.run_mode, func.count()).group_by(CheckReport.run_mode)).all())
    active = db.scalar(select(Release).where(Release.active.is_(True), Release.channel == "stable"))
    downloads_today = db.scalar(select(func.sum(DownloadStat.count)).where(DownloadStat.day == today)) or 0
    readiness = dict(db.execute(select(CheckReport.readiness_level, func.count()).where(CheckReport.checked_at.startswith(today)).group_by(CheckReport.readiness_level)).all())
    return {
        "customers": db.scalar(select(func.count()).select_from(Customer)) or 0,
        "rooms": db.scalar(select(func.count()).select_from(LiveRoom)) or 0,
        "devices": db.scalar(select(func.count()).select_from(Device)) or 0,
        "reports_today": sum(report_statuses.values()), "report_statuses": report_statuses,
        "support_open": db.scalar(select(func.count()).select_from(SupportCase).where(SupportCase.status == "open")) or 0,
        "codes_available": db.scalar(select(func.count()).select_from(Code).where(Code.status == "available")) or 0,
        "top_faults": [{"title": x.title, "count": x.count} for x in top_faults],
        "versions": [{"app_version": x.app_version, "count": x.count} for x in versions],
        "regions": [{"region": x.target_region_id, "count": x.count} for x in regions],
        "repairable_findings": repairable,
        "run_modes": run_modes,
        "active_release": None if not active else row_dict(active, ["version", "title", "notes"]),
        "downloads_today": downloads_today, "readiness": readiness,
    }


@router.get("/customers")
def customers(q: str = "", _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    stmt = select(Customer).order_by(Customer.id.desc())
    if q:
        stmt = stmt.where(or_(Customer.name.contains(q), Customer.contact.contains(q), Customer.notes.contains(q)))
    rows = db.scalars(stmt.limit(500)).all()
    return {"customers": [row_dict(x, ["id", "name", "contact", "notes", "status", "created_at"]) | {"room_count": len(x.rooms)} for x in rows]}


@router.post("/customer/save")
def save_customer(payload: CustomerIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    row = db.get(Customer, payload.id) if payload.id else Customer(created_at=now_iso())
    if not row:
        raise HTTPException(404, "客户不存在")
    for key, value in payload.model_dump(exclude={"id"}).items():
        setattr(row, key, value)
    db.add(row); db.flush(); audit(db, admin["username"], "save_customer", "customer", str(row.id)); db.commit()
    return {"ok": True, "id": row.id}


@router.get("/rooms")
def rooms(q: str = "", _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    stmt = select(LiveRoom).order_by(LiveRoom.id.desc())
    if q:
        stmt = stmt.where(or_(LiveRoom.name.contains(q), LiveRoom.region.contains(q), LiveRoom.notes.contains(q)))
    rows = db.scalars(stmt.limit(500)).all()
    customers_by_id = {x.id: x.name for x in db.scalars(select(Customer)).all()}
    return {"rooms": [row_dict(x, ["id", "customer_id", "name", "region", "bitrate_kbps", "notes", "status", "created_at"]) | {"customer": customers_by_id.get(x.customer_id, "")} for x in rows]}


@router.post("/room/save")
def save_room(payload: RoomIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    row = db.get(LiveRoom, payload.id) if payload.id else LiveRoom(created_at=now_iso())
    if not row:
        raise HTTPException(404, "直播间不存在")
    for key, value in payload.model_dump(exclude={"id"}).items():
        setattr(row, key, value)
    db.add(row); db.flush(); audit(db, admin["username"], "save_room", "room", str(row.id)); db.commit()
    return {"ok": True, "id": row.id}


@router.get("/devices")
def devices(q: str = "", _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    stmt = select(Device).order_by(Device.last_seen.desc())
    if q:
        stmt = stmt.where(or_(Device.device_id.contains(q), Device.customer_name.contains(q), Device.room_name.contains(q)))
    fields = ["device_id", "customer_id", "room_id", "customer_name", "room_name", "target_region_id", "app_version", "license_code", "free_uses_remaining", "last_seen", "status", "notes"]
    return {"devices": [row_dict(x, fields) for x in db.scalars(stmt.limit(500)).all()]}


@router.post("/device/save")
def save_device(payload: DeviceIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    row = db.get(Device, payload.device_id)
    if not row: raise HTTPException(404, "设备不存在")
    row.customer_id = payload.customer_id; row.room_id = payload.room_id; row.status = payload.status; row.notes = payload.notes
    if payload.unbind_license and row.license_code:
        code = db.get(Code, row.license_code)
        if code: code.bound_device_id = None; code.updated_at = now_iso(); code.status = "available" if code.credits != 0 else "exhausted"
        row.license_code = None
    audit(db, admin["username"], "save_device", "device", row.device_id, "unbind" if payload.unbind_license else payload.status); db.commit()
    return {"ok": True}


@router.get("/reports")
def reports(status: str = "", q: str = "", tag: str = "", user_id: int | None = None, ip: str = "", asn: str = "", provider: str = "", date_from: str = "", date_to: str = "", follow_up_status: str = "", limit: int = Query(200, ge=1, le=1000), _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    stmt = select(CheckReport).order_by(CheckReport.checked_at.desc())
    if status:
        if status in {"READY", "READY_WITH_RISK", "NOT_READY", "INCOMPLETE"}:
            stmt = stmt.where(CheckReport.readiness_level == status)
        else:
            stmt = stmt.where(CheckReport.overall_status == status)
    if q:
        stmt = stmt.where(or_(CheckReport.target_region_id.contains(q), CheckReport.device_id.contains(q), CheckReport.customer_name.contains(q), CheckReport.room_name.contains(q)))
    if date_from: stmt = stmt.where(CheckReport.checked_at >= date_from)
    if date_to: stmt = stmt.where(CheckReport.checked_at <= date_to + "T23:59:59")
    if user_id is not None:
        device_ids = select(Device.device_id).where(Device.user_id == user_id)
        stmt = stmt.where(CheckReport.device_id.in_(device_ids))
    fields = ["report_id", "device_id", "customer_name", "room_name", "run_mode", "target_region_id", "schema_version", "app_version", "checked_at", "overall_status", "conclusion", "readiness_level", "blocking_count", "high_risk_count", "test_mode", "uploaded_at"]
    result = []
    support_reports = {x.report_id for x in db.scalars(select(SupportCase).where(SupportCase.status == follow_up_status)).all()} if follow_up_status else set()
    for row in db.scalars(stmt.limit(1000)).all():
        tags = json.loads(row.issue_tags_json or "[]")
        if tag and tag not in tags:
            continue
        profile = json.loads(row.ip_profile_json or "{}")
        row_ip, row_asn = str(profile.get("ip") or ""), str(profile.get("asn") or "")
        row_provider = str(profile.get("isp") or profile.get("org") or "")
        if ip and ip not in row_ip or asn and asn.lower() not in row_asn.lower() or provider and provider.lower() not in row_provider.lower(): continue
        if follow_up_status and row.report_id not in support_reports: continue
        result.append(row_dict(row, fields) | {"issue_tags": tags, "ip": row_ip, "asn": row_asn, "provider": row_provider,
            "environment_summary": row.environment_summary, "network_summary": row.network_summary, "hardware_summary": row.hardware_summary, "next_action": row.next_action})
    return {"reports": result[:limit]}


@router.get("/report/{report_id}")
def report(report_id: str, admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    row = db.get(CheckReport, report_id)
    if not row:
        raise HTTPException(404, "报告不存在")
    audit(db, admin["username"], "view_report", "report", report_id); db.commit()
    fields = ["report_id", "device_id", "run_mode", "target_region_id", "schema_version", "app_version", "checked_at", "overall_status", "conclusion", "readiness_level", "blocking_count", "high_risk_count", "test_mode"]
    item_fields = ["check_id", "category", "status", "title", "value", "reason", "action", "repairable", "diagnosis", "impact", "data_source", "confidence", "repair_id", "repair_level", "duration_ms", "error_code", "priority", "blocking"]
    items = []
    for item in row.items:
        value = row_dict(item, item_fields)
        value.update({
            "evidence": json.loads(item.evidence_json or "[]"), "metrics": json.loads(item.metrics_json or "{}"),
            "solutions": json.loads(item.solutions_json or "[]"), "verification_check_ids": json.loads(item.verification_json or "[]"),
            "repair_outcome": json.loads(item.repair_outcome_json or "{}"),
        })
        items.append(value)
    return {"report": row_dict(row, fields) | {
        "network_snapshot": json.loads(row.network_snapshot_json or "{}"), "ip_profile": json.loads(row.ip_profile_json or "{}"),
        "streaming_profiles": json.loads(row.streaming_profiles_json or "[]"), "data_sources": json.loads(row.data_sources_json or "[]"),
        "repair_events": json.loads(row.repair_events_json or "[]"),
        "environment_snapshot": json.loads(row.environment_snapshot_json or "{}"),
        "device_snapshot": json.loads(row.device_snapshot_json or "{}"),
        "check_logs": json.loads(row.check_logs_json or "[]"),
        "before_snapshot": json.loads(row.before_snapshot_json or "{}"),
        "after_snapshot": json.loads(row.after_snapshot_json or "{}"),
        "confidence_summary": json.loads(row.confidence_summary_json or "{}"),
        "baseline_delta": json.loads(row.baseline_delta_json or "{}"),
        "source_health": json.loads(row.source_health_json or "{}"),
        "issue_tags": json.loads(row.issue_tags_json or "[]"),
        "environment_summary": row.environment_summary, "network_summary": row.network_summary,
        "hardware_summary": row.hardware_summary, "next_action": row.next_action,
        "ai_analysis": json.loads(row.ai_analysis_json or "{}"),
    }, "items": items}


@router.delete("/report/{report_id}")
def delete_report(report_id: str, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    row = db.get(CheckReport, report_id)
    if not row: raise HTTPException(404, "报告不存在")
    db.delete(row); audit(db, admin["username"], "delete_report", "report", report_id); db.commit()
    return {"ok": True}


@router.get("/providers")
def providers(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    groups: dict[tuple[str, str, str, str], dict] = {}
    for row in db.scalars(select(CheckReport).order_by(CheckReport.checked_at.desc()).limit(5000)).all():
        profile = json.loads(row.ip_profile_json or "{}")
        provider = str(profile.get("isp") or profile.get("org") or "待核实")
        key = (provider, str(profile.get("asn") or ""), str(profile.get("country_code") or profile.get("country") or ""), str(profile.get("network_type") or "unknown"))
        group = groups.setdefault(key, {"provider": key[0], "asn": key[1], "country": key[2], "network_type": key[3], "reports": [], "devices": set()})
        group["reports"].append(row); group["devices"].add(row.device_id)
    result = []
    for group in groups.values():
        uploads=[]; jitters=[]; latencies=[]; losses=[]
        for row in group["reports"]:
            snap=json.loads(row.network_snapshot_json or "{}"); speed=snap.get("network.throughput", {}); route=snap.get("network.target_route", {})
            for target, key in ((uploads,"upload_mbps"),(jitters,"jitter_ms"),(latencies,"latency_ms")):
                value=speed.get(key)
                if isinstance(value,(int,float)): target.append(float(value))
            loss=route.get("packet_loss_percent")
            if isinstance(loss,(int,float)): losses.append(float(loss))
        valid=len(uploads); confidence="high" if valid>=30 else "medium" if valid>=10 else "low"
        samples_7d = samples_30d = 0; periods = {"00-08": 0, "08-18": 0, "18-24": 0}
        for row in group["reports"]:
            try:
                checked = datetime.fromisoformat(row.checked_at.replace("Z", "+00:00")); checked = checked if checked.tzinfo else checked.replace(tzinfo=timezone.utc)
                samples_7d += int(checked >= now - timedelta(days=7)); samples_30d += int(checked >= now - timedelta(days=30))
                periods["00-08" if checked.hour < 8 else "08-18" if checked.hour < 18 else "18-24"] += 1
            except ValueError: pass
        advice="待核实" if valid<10 else "谨慎" if (statistics.median(jitters) if jitters else 0)>30 or (statistics.median(losses) if losses else 0)>1 else "适合"
        result.append({k:v for k,v in group.items() if k not in {"reports","devices"}} | {"sample_count":len(group["reports"]),"valid_samples":valid,"unique_devices":len(group["devices"]),"samples_7d":samples_7d,"samples_30d":samples_30d,"time_periods":periods,"last_checked_at":group["reports"][0].checked_at,"median_upload_mbps":round(statistics.median(uploads),2) if uploads else None,"p95_upload_mbps":sorted(uploads)[max(0,round((len(uploads)-1)*.95))] if uploads else None,"median_jitter_ms":round(statistics.median(jitters),2) if jitters else None,"median_latency_ms":round(statistics.median(latencies),2) if latencies else None,"median_packet_loss":round(statistics.median(losses),2) if losses else None,"confidence":confidence,"advice":advice})
    return {"providers": sorted(result,key=lambda x:x["sample_count"],reverse=True)}


@router.get("/setup-reports")
def setup_reports(limit: int = Query(200, ge=1, le=1000), _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(CheckReport).where(CheckReport.run_mode == "environment_setup").order_by(CheckReport.checked_at.desc()).limit(limit)).all()
    fields = ["report_id", "device_id", "run_mode", "target_region_id", "schema_version", "app_version", "checked_at", "overall_status", "conclusion", "readiness_level", "blocking_count", "high_risk_count", "test_mode", "uploaded_at"]
    return {"reports": [row_dict(row, fields) for row in rows]}


@router.get("/nodes/status")
def node_status(_admin: dict = Depends(current_admin)) -> dict:
    return {"nodes": [
        {"name": "Cloudflare + IPWho + RDAP", "role": "公网 IP、归属与注册信息", "status": "configured", "mode": "primary"},
        {"name": "PingIP", "role": "可选 IP 属性增强", "status": "optional", "mode": "optional"},
        {"name": "Cloudflare Speed", "role": "上传与下载多轮采样", "status": "configured", "mode": "primary"},
        {"name": "Regional TLS probes", "role": "目标地区多节点响应", "status": "configured", "mode": "multi-node"},
    ], "policy": "单个第三方节点不可用时返回 UNKNOWN，不判定客户网络故障"}


@router.get("/codes")
def codes(status: str = "", tier: str = "", q: str = "", _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    stmt = select(Code).order_by(Code.created_at.desc())
    if status: stmt = stmt.where(Code.status == status)
    if tier: stmt = stmt.where(Code.tier == tier)
    if q: stmt = stmt.where(or_(Code.code.contains(q), Code.customer_note.contains(q), Code.batch.contains(q)))
    fields = ["code", "tier", "plan_code", "duration_days", "credits", "status", "created_at", "customer_note", "bound_device_id", "activated_at", "expires_at", "used_count", "updated_at", "batch"]
    return {"codes": [row_dict(x, fields) for x in db.scalars(stmt.limit(2000)).all()]}


@router.get("/support")
def support(status: str = "", q: str = "", _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    stmt = select(SupportCase).order_by(SupportCase.updated_at.desc())
    if status: stmt = stmt.where(SupportCase.status == status)
    if q: stmt = stmt.where(or_(SupportCase.title.contains(q), SupportCase.device_id.contains(q), SupportCase.notes.contains(q)))
    fields = ["id", "report_id", "device_id", "title", "status", "owner", "notes", "created_at", "updated_at"]
    return {"support": [row_dict(x, fields) for x in db.scalars(stmt.limit(500)).all()]}


@router.post("/support/save")
def save_support(payload: SupportIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    row = db.get(SupportCase, payload.id) if payload.id else SupportCase(created_at=now_iso(), updated_at=now_iso())
    if not row: raise HTTPException(404, "故障单不存在")
    for key, value in payload.model_dump(exclude={"id"}).items(): setattr(row, key, value)
    row.updated_at = now_iso(); db.add(row); db.flush(); audit(db, admin["username"], "save_support", "support", str(row.id), row.status); db.commit()
    return {"ok": True, "id": row.id}


@router.post("/codes/generate")
def generate_codes(payload: CodeGenerateRequest, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    values = create_codes(db, payload.tier, payload.count, payload.note, payload.batch)
    audit(db, admin["username"], "generate_codes", "code", payload.tier, json.dumps({"count": payload.count, "batch": payload.batch}, ensure_ascii=False)); db.commit()
    return {"codes": values}


@router.post("/codes/status")
def code_status(payload: CodeStatusRequest, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    row = db.get(Code, payload.code)
    if not row: raise HTTPException(404, "激活码不存在")
    row.status = payload.status; row.updated_at = now_iso(); audit(db, admin["username"], "code_status", "code", row.code, payload.status); db.commit()
    return {"ok": True}


@router.get("/settings")
def get_settings_api(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    return {x.key: x.value for x in db.scalars(select(Setting)).all()}


@router.post("/settings")
def save_settings(payload: SettingsIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    for key, value in payload.values.items():
        row = db.get(Setting, key)
        if row: row.value = value
        else: db.add(Setting(key=key, value=value))
    audit(db, admin["username"], "save_settings", "settings"); db.commit()
    return {"ok": True}


@router.get("/homepage")
def homepage_settings(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    keys = {"product_name", "product_intro", "product_features", "product_faq", "support_text", "latest_changelog", "home_hero_title", "home_hero_subtitle", "home_daily_text", "home_setup_text", "home_steps", "home_system_requirements", "home_extra_notice"}
    return {row.key: row.value for row in db.scalars(select(Setting).where(Setting.key.in_(keys))).all()}


@router.post("/homepage")
def save_homepage(payload: SettingsIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed = {"product_name", "product_intro", "product_features", "product_faq", "support_text", "latest_changelog", "home_hero_title", "home_hero_subtitle", "home_daily_text", "home_setup_text", "home_steps", "home_system_requirements", "home_extra_notice"}
    if not payload.values or not set(payload.values).issubset(allowed):
        raise HTTPException(422, "主页资料字段不正确")
    if not payload.values.get("home_hero_title", "").strip() or not payload.values.get("product_name", "").strip():
        raise HTTPException(422, "产品名称和主页标题不能为空")
    if "product_features" in payload.values and len([line for line in payload.values["product_features"].splitlines() if line.strip()]) != 7:
        raise HTTPException(422, "检测能力必须填写 7 项，每行一项")
    for key, value in payload.values.items():
        row = db.get(Setting, key)
        if row: row.value = value.strip()
        else: db.add(Setting(key=key, value=value.strip()))
    audit(db, admin["username"], "save_homepage", "settings"); db.commit()
    return {"ok": True}


@router.get("/download-stats")
def download_stats(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(DownloadStat).order_by(DownloadStat.day.desc(), DownloadStat.version.desc()).limit(180)).all()
    return {"stats": [row_dict(row, ["day", "version", "count", "updated_at"]) for row in rows]}


@router.get("/profile")
def get_profile(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(CheckProfile).where(CheckProfile.active.is_(True)).order_by(CheckProfile.id.desc()))
    return {"profile": None} if not row else {"profile": {"id": row.id, "name": row.name, "region": row.region, "bitrate_kbps": row.bitrate_kbps, "rules": json.loads(row.rules_json), "updated_at": row.updated_at}}


@router.post("/profile")
def save_profile(payload: ProfileIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    required = {"upload_multiplier", "upload_test_bytes", "packet_loss_warning", "packet_loss_fail", "jitter_warning_ms", "jitter_fail_ms", "latency_warning_ms", "latency_fail_ms", "min_free_disk_gb"}
    if not required.issubset(payload.rules): raise HTTPException(422, "检测规则字段不完整")
    db.execute(CheckProfile.__table__.update().values(active=False))
    row = CheckProfile(name=payload.name, region=payload.region, bitrate_kbps=payload.bitrate_kbps, rules_json=json.dumps(payload.rules, ensure_ascii=False), active=True, created_at=now_iso(), updated_at=now_iso())
    db.add(row); db.flush(); audit(db, admin["username"], "save_profile", "profile", str(row.id)); db.commit()
    return {"ok": True, "id": row.id}


@router.get("/audit")
def audit_logs(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    fields = ["id", "actor", "action", "target_type", "target_id", "details", "created_at"]
    return {"audit": [row_dict(x, fields) for x in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(500)).all()]}


def csv_response(name: str, headers: list[str], rows: list[list[object]]) -> StreamingResponse:
    stream = io.StringIO(); writer = csv.writer(stream); writer.writerow(headers); writer.writerows(rows)
    return StreamingResponse(iter(["\ufeff" + stream.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/codes/export")
def export_codes(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> StreamingResponse:
    rows = db.scalars(select(Code).order_by(Code.created_at.desc())).all()
    return csv_response("activation-codes.csv", ["激活码", "档次", "剩余", "状态", "绑定设备", "备注", "批次", "生成时间"], [[x.code, x.tier, x.credits, x.status, x.bound_device_id or "", x.customer_note, x.batch, x.created_at] for x in rows])


@router.get("/reports/export")
def export_reports(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> StreamingResponse:
    rows = db.scalars(select(CheckReport).order_by(CheckReport.checked_at.desc())).all()
    audit(db, admin["username"], "export_reports", "report", details=f"count={len(rows)}"); db.commit()
    return csv_response("check-reports.csv", ["报告编号", "目标地区", "设备", "状态", "结论", "检查时间"], [[x.report_id, x.target_region_id, x.device_id, x.overall_status, x.conclusion, x.checked_at] for x in rows])


@router.post("/release")
async def publish_release(
    version: str = Form(...), title: str = Form(...), notes: str = Form(""), details: str = Form(...),
    channel: str = Form("stable"), mandatory: bool = Form(False), minimum_version: str = Form(""),
    file: UploadFile = File(...), admin: dict = Depends(require_csrf), db: Session = Depends(get_db),
) -> dict:
    if not version.strip() or not title.strip() or not details.strip():
        raise HTTPException(422, "版本号、标题和详细内容不能为空")
    if channel not in {"stable", "beta"}:
        raise HTTPException(422, "发布通道不正确")
    if not file.filename or Path(file.filename).suffix.lower() != ".exe":
        raise HTTPException(415, "只允许上传 EXE 安装程序")
    safe_name = f"client-{version.strip()}.exe"
    target = settings.downloads_dir / safe_name
    size = 0
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                output.close(); target.unlink(missing_ok=True); raise HTTPException(413, "安装包超过大小限制")
            output.write(chunk)
    digest = file_sha256(target)
    with target.open("rb") as stream:
        valid_exe = stream.read(2) == b"MZ"
    if not valid_exe:
        target.unlink(missing_ok=True); raise HTTPException(415, "文件不是有效的 Windows EXE 安装程序")
    row = db.get(Release, version) or Release(version=version, filename=safe_name, sha256=digest)
    row.filename = row.installer_filename = safe_name; row.sha256 = digest; row.file_size = size
    row.title = title; row.notes = notes; row.details = details; row.channel = channel; row.mandatory = mandatory; row.minimum_version = minimum_version; row.active = False
    db.add(row); audit(db, admin["username"], "publish_release", "release", version, digest); db.commit()
    return {"ok": True, "version": version, "sha256": digest, "file_size": size, "status": "pending"}


@router.get("/releases")
def releases(_admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    fields = ["version", "title", "notes", "details", "filename", "sha256", "file_size", "channel", "mandatory", "minimum_version", "active", "created_at"]
    return {"releases": [row_dict(x, fields) for x in db.scalars(select(Release).order_by(Release.created_at.desc())).all()]}


@router.post("/release/activate")
def activate_release(payload: ReleaseActivateIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    row = db.get(Release, payload.version)
    if not row: raise HTTPException(404, "版本不存在")
    filename = row.installer_filename or row.filename
    target = settings.downloads_dir / Path(filename).name
    if not target.is_file() or target.stat().st_size != row.file_size or file_sha256(target) != row.sha256:
        raise HTTPException(409, "安装包缺失、大小不符或哈希校验失败，禁止发布")
    db.execute(Release.__table__.update().where(Release.channel == row.channel, Release.version != row.version).values(active=False)); row.active = True
    audit(db, admin["username"], "activate_release", "release", row.version, row.channel); db.commit(); return {"ok": True}


USER_FIELDS = ["id", "phone", "phone_country", "email", "company_name", "country", "city", "wechat_id", "platform_account", "profile_completed_at", "trial_granted", "trial_expires_at", "status", "created_at", "last_active_at"]


def _parse_business_types(raw) -> list:
    try:
        val = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        val = []
    return val if isinstance(val, list) else []


def _user_row(u: User) -> dict:
    d = row_dict(u, USER_FIELDS)
    d["business_types"] = _parse_business_types(u.business_types)
    return d


def _user_clauses(phone: str, company_name: str, country: str, business_type: str, status: str) -> list:
    clauses = []
    if phone:
        clauses.append(User.phone.contains(phone))
    if company_name:
        clauses.append(User.company_name.contains(company_name))
    if country:
        clauses.append(User.country.contains(country))
    if business_type:
        clauses.append(User.business_types.contains(business_type))
    if status:
        clauses.append(User.status == status)
    return clauses


@router.get("/users")
def list_users(phone: str = "", company_name: str = "", country: str = "", business_type: str = "", status: str = "", page: int = 1, page_size: int = 50, _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    clauses = _user_clauses(phone, company_name, country, business_type, status)
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if clauses:
        stmt = stmt.where(*clauses)
        count_stmt = count_stmt.where(*clauses)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(User.id.desc()).limit(page_size).offset(max(0, page - 1) * page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "users": [_user_row(x) for x in rows]}


@router.get("/users/export")
def export_users(phone: str = "", company_name: str = "", country: str = "", business_type: str = "", status: str = "", _admin: dict = Depends(current_admin), db: Session = Depends(get_db)):
    clauses = _user_clauses(phone, company_name, country, business_type, status)
    stmt = select(User)
    if clauses:
        stmt = stmt.where(*clauses)
    rows = db.scalars(stmt.order_by(User.id.desc())).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    headers = ["id", "phone", "phone_country", "email", "company_name", "country", "city", "business_types", "wechat_id", "platform_account", "profile_completed_at", "trial_granted", "trial_expires_at", "status", "created_at", "last_active_at"]
    writer.writerow(headers)
    for u in rows:
        d = row_dict(u, USER_FIELDS)
        writer.writerow([d.get(h, "") if h != "business_types" else ";".join(_parse_business_types(u.business_types)) for h in headers])
    buf.seek(0)
    return StreamingResponse(iter(["\ufeff" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=wd-users-export.csv"})


@router.get("/users/{user_id}")
def user_detail(user_id: int, _admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    d = _user_row(u)
    d["device_count"] = db.scalar(select(func.count()).select_from(Device).where(Device.user_id == u.id)) or 0
    d["session_count"] = db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == u.id, UserSession.revoked == 0)) or 0
    return {"user": d}
