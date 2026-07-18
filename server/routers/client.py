import json
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CheckItem, CheckProfile, CheckReport, Code, Device, LicenseEvent, Release, User, UserSession, VerificationCode, now_iso
from ..schemas import ActivateRequest, AuthorizeRequest, ForgotPasswordRequest, RegisterRequest, ReportIn, ResetPasswordRequest, SendCodeRequest, UserLoginRequest, UserProfileUpdate, UserRegisterRequest
from ..security import current_device, current_user, hash_token, hasher, verify_password
from ..services import DEFAULT_PROFILE, release_manifest
from ..config import get_settings
from ..email_utils import send_verification_code
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
        readiness_level=payload.readiness_level, blocking_count=payload.blocking_count,
        high_risk_count=payload.high_risk_count, test_mode=payload.test_mode,
        baseline_delta_json=json.dumps(payload.baseline_delta, ensure_ascii=False),
        source_health_json=json.dumps(payload.source_health, ensure_ascii=False),
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
        priority=item.priority, blocking=item.blocking,
        repair_outcome_json=json.dumps(item.repair_outcome, ensure_ascii=False),
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


@router.get("/changelog")
def changelog(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Release).order_by(Release.created_at.desc()).limit(20)).all()
    return {"releases": [{"version": row.version, "title": row.title, "notes": row.notes, "details": row.details, "channel": row.channel, "created_at": row.created_at} for row in rows]}


@router.get("/regions")
def regions() -> dict:
    return {"regions": [{
        "id": item.region_id, "label": item.label, "country_code": item.country_code,
        "windows_timezone": item.windows_timezone, "iana_timezone": item.iana_timezone,
        "group": getattr(item, 'group', 'other'),
    } for item in REGIONS]}


@router.get("/network-intelligence/status")
def network_intelligence_status() -> dict:
    return {"providers": [
        {"name": "Cloudflare + IPWho + RDAP", "role": "公网 IP、归属与注册信息", "mode": "primary"},
        {"name": "PingIP", "role": "可选 IP 属性增强", "mode": "optional"},
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


def _make_user_session(db: Session, user: "User", device_id: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=get_settings().user_session_hours)
    db.add(UserSession(token_hash=hash_token(token), user_id=user.id, device_id=device_id, expires_at=expires.isoformat()))
    db.commit()
    return token


def _public_user(u: "User") -> dict:
    return {
        "id": u.id, "phone": u.phone, "phone_country": u.phone_country, "email": u.email,
        "profile_completed_at": u.profile_completed_at, "trial_granted": u.trial_granted,
        "trial_expires_at": u.trial_expires_at, "status": u.status,
    }


def _gen_code(settings) -> str:
    return settings.dev_verify_code if (settings.dev_verify_code and settings.env != "production") else f"{secrets.randbelow(900000) + 100000:06d}"


@router.post("/auth/send-code")
def auth_send_code(payload: SendCodeRequest, db: Session = Depends(get_db)) -> dict:
    if payload.purpose not in ("register", "reset_password"):
        raise HTTPException(status_code=400, detail="无效的验证码用途")
    settings = get_settings()
    now = datetime.now(timezone.utc)
    recent = db.scalar(
        select(VerificationCode)
        .where(VerificationCode.target == payload.target, VerificationCode.purpose == payload.purpose, VerificationCode.used == 0)
        .order_by(VerificationCode.id.desc())
    )
    if recent is not None and (now - datetime.fromisoformat(recent.created_at)).total_seconds() < settings.verify_code_cooldown_seconds:
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")
    code = _gen_code(settings)
    expires_at = (now + timedelta(minutes=settings.verify_code_ttl_minutes)).isoformat()
    verification = VerificationCode(target=payload.target, code=code, purpose=payload.purpose, expires_at=expires_at)
    db.add(verification)
    db.commit()
    if not send_verification_code(payload.target, code, payload.purpose):
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=503, detail="验证码暂时无法发送，请稍后重试")
    result: dict = {"ok": True}
    if settings.env != "production":
        result["dev_code"] = code
    return result


@router.post("/auth/register")
def auth_register(payload: UserRegisterRequest, db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User).where(User.phone == payload.phone)):
        raise HTTPException(status_code=409, detail="手机号已注册")
    now = datetime.now(timezone.utc)
    vc = db.scalar(
        select(VerificationCode)
        .where(VerificationCode.target == payload.email, VerificationCode.purpose == "register", VerificationCode.used == 0)
        .order_by(VerificationCode.id.desc())
    )
    if vc is None or datetime.fromisoformat(vc.expires_at) <= now or vc.code != payload.code:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    user = User(phone=payload.phone, phone_country=payload.phone_country, password_hash=hasher.hash(payload.password), email=payload.email, status="active")
    vc.used = 1
    db.add(user)
    db.commit()
    db.refresh(user)
    token = _make_user_session(db, user)
    return {"token": token, "user": _public_user(user)}


@router.post("/auth/login")
def auth_login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.phone == payload.phone))
    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="手机号或密码错误")
    user.last_active_at = now_iso()
    db.commit()
    token = _make_user_session(db, user)
    return {"token": token, "user": _public_user(user)}


@router.post("/auth/forgot-password")
def auth_forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    user = db.scalar(select(User).where(User.phone == payload.phone))
    if user is not None and user.email:
        code = _gen_code(settings)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=settings.verify_code_ttl_minutes)).isoformat()
        db.add(VerificationCode(target=user.email, code=code, purpose="reset_password", expires_at=expires_at))
        db.commit()
        send_verification_code(user.email, code, "reset_password")
        if settings.env != "production":
            return {"ok": True, "dev_code": code}
    return {"ok": True}


@router.post("/auth/reset-password")
def auth_reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(User.phone == payload.phone))
    if user is None:
        raise HTTPException(status_code=400, detail="账号不存在")
    vc = db.scalar(
        select(VerificationCode)
        .where(VerificationCode.target == user.email, VerificationCode.purpose == "reset_password", VerificationCode.used == 0)
        .order_by(VerificationCode.id.desc())
    )
    valid = vc is not None and datetime.fromisoformat(vc.expires_at) > now and (
        vc.code == payload.code or (settings.dev_verify_code and settings.env != "production" and payload.code == settings.dev_verify_code)
    )
    if not valid:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    user.password_hash = hasher.hash(payload.password)
    vc.used = 1
    db.commit()
    return {"ok": True}


@router.post("/auth/logout")
def auth_logout(me: dict = Depends(current_user), authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(authorization[7:])))
        if session is not None:
            session.revoked = 1
            db.commit()
    return {"ok": True}


def _parse_business_types(raw) -> list:
    try:
        val = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        val = []
    return val if isinstance(val, list) else []


def _profile_is_complete(u: "User") -> bool:
    return bool(u.company_name and u.country and _parse_business_types(u.business_types) and u.wechat_id)


def _user_profile_view(u: "User") -> dict:
    return {
        "id": u.id, "phone": u.phone, "phone_country": u.phone_country, "email": u.email,
        "company_name": u.company_name, "country": u.country, "city": u.city,
        "business_types": _parse_business_types(u.business_types), "wechat_id": u.wechat_id,
        "platform_account": u.platform_account, "profile_completed_at": u.profile_completed_at,
        "trial_granted": u.trial_granted, "trial_expires_at": u.trial_expires_at,
        "status": u.status, "created_at": u.created_at, "last_active_at": u.last_active_at,
    }


@router.get("/user/profile")
def get_user_profile(me: dict = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, me["user_id"])
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return {"profile": _user_profile_view(user)}


@router.put("/user/profile")
def update_user_profile(payload: UserProfileUpdate, me: dict = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, me["user_id"])
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    data = payload.model_dump(exclude_unset=True)
    was_complete = _profile_is_complete(user)
    for key, value in data.items():
        if value is None:
            continue
        if key == "business_types":
            user.business_types = json.dumps(value, ensure_ascii=False)
        else:
            setattr(user, key, value)
    now = datetime.now(timezone.utc)
    if not was_complete and _profile_is_complete(user) and not user.profile_completed_at:
        user.profile_completed_at = now_iso()
        user.trial_granted = 1
        user.trial_expires_at = (now + timedelta(days=3)).isoformat()
    user.last_active_at = now_iso()
    db.commit()
    return {"profile": _user_profile_view(user), "trial_granted": bool(user.trial_granted)}
