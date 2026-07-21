from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models import Admin, Alert, AuditLog, CheckReport, Customer, Device, DeviceBindingCode, DeviceEvent, LiveRoom, StreamingAccount, WorkOrder, now_iso
from ..schemas import AdminMemberIn, AlertUpdateIn, BindingCodeIn, RoomIn, StreamingAccountIn, TenantAlertSettingsIn, TenantDeviceUpdateIn, TenantProvisionIn, WorkOrderIn
from ..security import current_admin, hasher, permissions_for, require_csrf
from ..services import audit
from ..notifications import enqueue_alert, secret_box


router = APIRouter(prefix="/tk-api/enterprise", tags=["enterprise-admin"])


def tenant_id(admin: dict) -> int:
    value = admin.get("customer_id")
    if not value:
        raise HTTPException(status_code=403, detail="平台账号请先进入具体企业，或使用平台管理功能")
    return int(value)


def allowed(admin: dict, permission: str) -> None:
    permissions = permissions_for(admin.get("role", ""))
    implied = permission.replace(".read", ".manage") if permission.endswith(".read") else ""
    if "*" not in permissions and permission not in permissions and implied not in permissions:
        raise HTTPException(status_code=403, detail="当前账号没有此操作权限")


def device_view(row: Device, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    heartbeat = datetime.fromisoformat(row.last_heartbeat_at) if row.last_heartbeat_at else None
    online = bool(heartbeat and (now - heartbeat).total_seconds() <= 90)
    return {
        "device_id": row.device_id, "display_name": row.display_name or row.device_id,
        "room_id": row.room_id, "streaming_account_id": row.streaming_account_id,
        "store_name": row.store_name, "location": row.location, "owner_name": row.owner_name,
        "tags": json.loads(row.tags_json or "[]"), "app_version": row.app_version,
        "target_region_id": row.target_region_id, "online": online,
        "live_state": row.live_state, "readiness_state": row.readiness_state,
        "studio_state": row.studio_state, "last_heartbeat_at": row.last_heartbeat_at,
        "last_report_id": row.last_report_id, "last_report_at": row.last_report_at,
        "module_summary": json.loads(row.module_summary_json or "{}"), "state_version": row.state_version,
    }


@router.get("/platform/tenants")
def platform_tenants(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    if admin.get("role") != "platform_super": raise HTTPException(status_code=403, detail="仅限平台管理员")
    rows = db.scalars(select(Customer).order_by(Customer.created_at.desc())).all()
    result=[]
    for x in rows:
        used=db.scalar(select(func.count()).select_from(Device).where(Device.customer_id==x.id,Device.status=="active")) or 0
        result.append({"id":x.id,"tenant_code":x.tenant_code,"name":x.name,"short_name":x.short_name,"contact":x.contact,"status":x.status,"plan_code":x.plan_code,"device_limit":x.device_limit,"devices_used":used,"subscription_expires_at":x.subscription_expires_at})
    return {"tenants":result}


@router.post("/platform/tenants")
def provision_tenant(payload: TenantProvisionIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    if admin.get("role") != "platform_super": raise HTTPException(status_code=403, detail="仅限平台管理员")
    if db.scalar(select(Admin).where(Admin.username==payload.owner_username)): raise HTTPException(status_code=409,detail="登录账号已存在")
    now=datetime.now(timezone.utc); expires=now+timedelta(days=payload.subscription_days)
    code=f"ENT-{secrets.token_hex(4).upper()}"
    tenant=Customer(name=payload.name,short_name=payload.short_name,contact=payload.contact,timezone=payload.timezone,plan_code=payload.plan_code,device_limit=payload.device_limit,member_limit=payload.member_limit,tenant_code=code,organization_code=code,subscription_starts_at=now.isoformat(),subscription_expires_at=expires.isoformat(),grace_ends_at=(expires+timedelta(days=7)).isoformat())
    db.add(tenant); db.flush(); owner=Admin(username=payload.owner_username,password_hash=hasher.hash(payload.owner_password),customer_id=tenant.id,role="tenant_owner",display_name=payload.owner_name,password_changed_at=now_iso()); db.add(owner); db.flush(); audit(db,admin["username"],"provision_tenant","customer",str(tenant.id),payload.plan_code); db.commit()
    return {"ok":True,"tenant_id":tenant.id,"tenant_code":tenant.tenant_code,"owner_id":owner.id}


@router.get("/overview")
def overview(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "dashboard.read"); customer_id = tenant_id(admin)
    devices = db.scalars(select(Device).where(Device.customer_id == customer_id, Device.status == "active")).all()
    views = [device_view(row) for row in devices]
    today = datetime.now(timezone.utc).date().isoformat()
    checked = db.scalar(select(func.count(func.distinct(CheckReport.device_id))).join(Device, Device.device_id == CheckReport.device_id).where(Device.customer_id == customer_id, CheckReport.checked_at.startswith(today))) or 0
    open_alerts = db.scalar(select(func.count()).select_from(Alert).where(Alert.customer_id == customer_id, Alert.status.in_(["open", "acknowledged", "processing"]))) or 0
    tenant = db.get(Customer, customer_id)
    return {"metrics": {
        "devices": len(views), "online": sum(x["online"] for x in views),
        "ready": sum(x["readiness_state"] == "ready" for x in views),
        "blocked": sum(x["readiness_state"] == "blocked" for x in views),
        "network_risk": sum((x["module_summary"].get("network") or {}).get("status") == "WARNING" for x in views),
        "studio_running": sum(x["studio_state"] == "running" for x in views),
        "checked_today": checked, "open_alerts": open_alerts,
    }, "subscription": {"plan_code": tenant.plan_code, "device_limit": tenant.device_limit, "expires_at": tenant.subscription_expires_at}, "devices": views}


@router.get("/devices")
def devices(q: str = "", state: str = "", admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "devices.read"); customer_id = tenant_id(admin)
    stmt = select(Device).where(Device.customer_id == customer_id)
    if q:
        stmt = stmt.where(or_(Device.device_id.contains(q), Device.display_name.contains(q), Device.store_name.contains(q), Device.owner_name.contains(q)))
    if state:
        stmt = stmt.where(Device.readiness_state == state)
    return {"devices": [device_view(row) for row in db.scalars(stmt.order_by(Device.last_heartbeat_at.desc())).all()]}


@router.get("/devices/{device_id}")
def device_detail(device_id: str, admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "devices.read"); customer_id = tenant_id(admin)
    row = db.scalar(select(Device).where(Device.device_id == device_id, Device.customer_id == customer_id))
    if not row: raise HTTPException(status_code=404, detail="设备不存在")
    reports = db.scalars(select(CheckReport).where(CheckReport.device_id == device_id).order_by(CheckReport.checked_at.desc()).limit(20)).all()
    events = db.scalars(select(DeviceEvent).where(DeviceEvent.device_id == device_id, DeviceEvent.customer_id == customer_id).order_by(DeviceEvent.created_at.desc()).limit(100)).all()
    alerts = db.scalars(select(Alert).where(Alert.device_id == device_id, Alert.customer_id == customer_id).order_by(Alert.last_seen_at.desc()).limit(50)).all()
    return {"device": device_view(row), "reports": [{"report_id": x.report_id, "checked_at": x.checked_at, "readiness_level": x.readiness_level, "conclusion": x.conclusion} for x in reports], "events": [{"event_id": x.event_id, "event_type": x.event_type, "severity": x.severity, "client_at": x.client_at, "created_at": x.created_at, "payload": json.loads(x.payload_json or "{}")} for x in events], "alerts": [alert_view(x) for x in alerts]}


@router.post("/devices/{device_id}")
def update_device(device_id: str, payload: TenantDeviceUpdateIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "devices.manage"); cid = tenant_id(admin)
    row = db.scalar(select(Device).where(Device.device_id == device_id, Device.customer_id == cid))
    if not row: raise HTTPException(status_code=404, detail="设备不存在")
    if payload.room_id and not db.scalar(select(LiveRoom).where(LiveRoom.id == payload.room_id, LiveRoom.customer_id == cid)): raise HTTPException(status_code=400, detail="直播间不属于当前企业")
    if payload.streaming_account_id and not db.scalar(select(StreamingAccount).where(StreamingAccount.id == payload.streaming_account_id, StreamingAccount.customer_id == cid)): raise HTTPException(status_code=400, detail="开播账号不属于当前企业")
    for key, value in payload.model_dump(exclude={"tags"}).items(): setattr(row, key, value)
    row.tags_json = json.dumps(payload.tags, ensure_ascii=False); audit(db, admin["username"], "update_enterprise_device", "device", device_id); db.commit(); return {"ok": True}


@router.get("/rooms")
def tenant_rooms(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "accounts.read"); cid = tenant_id(admin)
    rows = db.scalars(select(LiveRoom).where(LiveRoom.customer_id == cid).order_by(LiveRoom.created_at.desc())).all()
    return {"rooms": [{"id":x.id,"name":x.name,"region":x.region,"bitrate_kbps":x.bitrate_kbps,"notes":x.notes,"status":x.status} for x in rows]}


@router.post("/rooms")
def save_tenant_room(payload: RoomIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "accounts.manage"); cid = tenant_id(admin)
    row = db.get(LiveRoom, payload.id) if payload.id else LiveRoom(customer_id=cid, name=payload.name)
    if row and row.customer_id != cid: raise HTTPException(status_code=404, detail="直播间不存在")
    row.name=payload.name; row.region=payload.region; row.bitrate_kbps=payload.bitrate_kbps; row.notes=payload.notes; row.status=payload.status
    db.add(row); db.flush(); audit(db,admin["username"],"save_tenant_room","live_room",str(row.id)); db.commit(); return {"ok":True,"id":row.id}


@router.get("/reports")
def reports(q: str = "", admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "reports.read"); cid = tenant_id(admin)
    stmt = select(CheckReport).join(Device, Device.device_id == CheckReport.device_id).where(Device.customer_id == cid)
    if q: stmt = stmt.where(or_(CheckReport.device_id.contains(q), CheckReport.conclusion.contains(q), CheckReport.target_region_id.contains(q)))
    rows = db.scalars(stmt.order_by(CheckReport.checked_at.desc()).limit(500)).all()
    return {"reports": [{"report_id":x.report_id,"device_id":x.device_id,"checked_at":x.checked_at,"readiness_level":x.readiness_level,"overall_status":x.overall_status,"conclusion":x.conclusion,"target_region_id":x.target_region_id,"environment_summary":x.environment_summary,"network_summary":x.network_summary,"hardware_summary":x.hardware_summary} for x in rows]}


@router.get("/reports/{report_id}")
def report_detail(report_id: str, admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "reports.read"); cid = tenant_id(admin)
    row = db.scalar(select(CheckReport).join(Device,Device.device_id==CheckReport.device_id).where(CheckReport.report_id==report_id,Device.customer_id==cid))
    if not row: raise HTTPException(status_code=404,detail="报告不存在")
    return {"report":{"report_id":row.report_id,"device_id":row.device_id,"checked_at":row.checked_at,"readiness_level":row.readiness_level,"conclusion":row.conclusion,"summaries":{"network":row.network_summary,"system":row.environment_summary,"performance":row.hardware_summary},"items":[{"check_id":x.check_id,"category":x.category,"status":x.status,"title":x.title,"value":x.value,"diagnosis":x.diagnosis,"impact":x.impact} for x in row.items]}}


@router.get("/accounts")
def accounts(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "accounts.read"); cid = tenant_id(admin)
    rows = db.scalars(select(StreamingAccount).where(StreamingAccount.customer_id == cid).order_by(StreamingAccount.created_at.desc())).all()
    return {"accounts": [{"id": x.id, "room_id": x.room_id, "name": x.name, "platform": x.platform, "owner_name": x.owner_name, "target_region_id": x.target_region_id, "notes": x.notes, "status": x.status} for x in rows]}


@router.post("/accounts")
def save_account(payload: StreamingAccountIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "accounts.manage"); cid = tenant_id(admin)
    row = db.get(StreamingAccount, payload.id) if payload.id else StreamingAccount(customer_id=cid, name=payload.name)
    if row and row.customer_id != cid: raise HTTPException(status_code=404, detail="开播账号不存在")
    if payload.room_id and not db.scalar(select(LiveRoom).where(LiveRoom.id == payload.room_id, LiveRoom.customer_id == cid)): raise HTTPException(status_code=400, detail="直播间不属于当前企业")
    for key, value in payload.model_dump(exclude={"id"}).items(): setattr(row, key, value)
    db.add(row); db.flush(); audit(db, admin["username"], "save_streaming_account", "streaming_account", str(row.id)); db.commit()
    return {"ok": True, "id": row.id}


@router.get("/members")
def members(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "members.manage"); cid = tenant_id(admin)
    rows = db.scalars(select(Admin).where(Admin.customer_id == cid).order_by(Admin.created_at)).all()
    return {"members": [{"id": x.id, "username": x.username, "display_name": x.display_name, "phone": x.phone, "role": x.role, "active": x.active, "last_login_at": x.last_login_at} for x in rows]}


@router.post("/members")
def save_member(payload: AdminMemberIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "members.manage"); cid = tenant_id(admin); tenant = db.get(Customer, cid)
    row = db.get(Admin, payload.id) if payload.id else None
    if row and row.customer_id != cid: raise HTTPException(status_code=404, detail="成员不存在")
    if not row:
        count = db.scalar(select(func.count()).select_from(Admin).where(Admin.customer_id == cid, Admin.active.is_(True))) or 0
        if count >= tenant.member_limit: raise HTTPException(status_code=409, detail="已达到套餐成员上限")
        if db.scalar(select(Admin).where(Admin.username == payload.username)): raise HTTPException(status_code=409, detail="登录账号已存在")
        if len(payload.password) < 8: raise HTTPException(status_code=400, detail="新成员密码至少8位")
        row = Admin(username=payload.username, password_hash=hasher.hash(payload.password), customer_id=cid)
    row.display_name = payload.display_name; row.phone = payload.phone; row.role = payload.role; row.active = payload.active
    if payload.password: row.password_hash = hasher.hash(payload.password); row.password_changed_at = now_iso()
    db.add(row); db.flush(); audit(db, admin["username"], "save_member", "admin", str(row.id), row.role); db.commit()
    return {"ok": True, "id": row.id}


@router.post("/binding-codes")
def binding_code(payload: BindingCodeIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "devices.manage"); cid = tenant_id(admin); tenant = db.get(Customer, cid)
    active_devices = db.scalar(select(func.count()).select_from(Device).where(Device.customer_id == cid, Device.status == "active")) or 0
    if active_devices >= tenant.device_limit: raise HTTPException(status_code=409, detail="已达到套餐设备上限")
    code = f"{secrets.randbelow(1000000):06d}"; digest = hashlib.sha256(code.encode()).hexdigest()
    row = DeviceBindingCode(code_hash=digest, customer_id=cid, room_id=payload.room_id, streaming_account_id=payload.streaming_account_id, created_by=int(admin.get("admin_id") or 0), expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    db.add(row); audit(db, admin["username"], "create_binding_code", "customer", str(cid)); db.commit()
    return {"code": code, "expires_at": row.expires_at}


def alert_view(row: Alert) -> dict:
    return {"id": row.id, "device_id": row.device_id, "alert_type": row.alert_type, "severity": row.severity, "status": row.status, "title": row.title, "root_cause": row.root_cause, "occurrence_count": row.occurrence_count, "first_seen_at": row.first_seen_at, "last_seen_at": row.last_seen_at, "acknowledged_by": row.acknowledged_by, "resolved_at": row.resolved_at, "details": json.loads(row.details_json or "{}")}


@router.get("/alerts")
def alerts(status: str = "", admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "alerts.read" if admin.get("role") == "tenant_viewer" else "alerts.manage"); cid = tenant_id(admin)
    stmt = select(Alert).where(Alert.customer_id == cid)
    if status: stmt = stmt.where(Alert.status == status)
    return {"alerts": [alert_view(x) for x in db.scalars(stmt.order_by(Alert.last_seen_at.desc()).limit(500)).all()]}


@router.post("/alerts/{alert_id}")
def update_alert(alert_id: int, payload: AlertUpdateIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "alerts.manage"); cid = tenant_id(admin)
    row = db.scalar(select(Alert).where(Alert.id == alert_id, Alert.customer_id == cid))
    if not row: raise HTTPException(status_code=404, detail="告警不存在")
    row.status = payload.status; row.acknowledged_by = admin["username"]
    if payload.status in {"resolved", "closed"}: row.resolved_at = now_iso(); enqueue_alert(db, row, "resolved")
    audit(db, admin["username"], "update_alert", "alert", str(row.id), payload.status); db.commit(); return {"ok": True}


@router.get("/work-orders")
def work_orders(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "workorders.read" if admin.get("role") == "tenant_viewer" else "workorders.manage"); cid = tenant_id(admin)
    rows = db.scalars(select(WorkOrder).where(WorkOrder.customer_id == cid).order_by(WorkOrder.updated_at.desc())).all()
    return {"work_orders": [{"id": x.id, "alert_id": x.alert_id, "device_id": x.device_id, "title": x.title, "priority": x.priority, "status": x.status, "owner": x.owner, "notes": x.notes, "resolution": x.resolution, "created_at": x.created_at, "updated_at": x.updated_at, "resolved_at": x.resolved_at} for x in rows]}


@router.post("/work-orders")
def save_work_order(payload: WorkOrderIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "workorders.manage"); cid = tenant_id(admin)
    if not payload.id and payload.alert_id:
        existing = db.scalar(select(WorkOrder).where(WorkOrder.customer_id == cid, WorkOrder.alert_id == payload.alert_id, WorkOrder.status.in_(["open", "processing"])))
        if existing: raise HTTPException(status_code=409, detail="该告警已经存在处理中工单")
    row = db.get(WorkOrder, payload.id) if payload.id else WorkOrder(customer_id=cid, title=payload.title)
    if row and row.customer_id != cid: raise HTTPException(status_code=404, detail="工单不存在")
    for key, value in payload.model_dump(exclude={"id"}).items(): setattr(row, key, value)
    row.updated_at = now_iso()
    if row.status in {"resolved", "closed"}: row.resolved_at = now_iso()
    db.add(row); db.flush(); audit(db, admin["username"], "save_work_order", "work_order", str(row.id), row.status); db.commit(); return {"ok": True, "id": row.id}


@router.get("/alert-settings")
def alert_settings(admin: dict = Depends(current_admin), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "subscription.read"); tenant = db.get(Customer, tenant_id(admin)); settings = json.loads(tenant.alert_settings_json or "{}")
    return {"settings": settings, "wecom_configured": bool(tenant.wecom_webhook_encrypted)}


@router.post("/alert-settings")
def save_alert_settings(payload: TenantAlertSettingsIn, admin: dict = Depends(require_csrf), db: Session = Depends(get_db)) -> dict:
    allowed(admin, "members.manage"); tenant = db.get(Customer, tenant_id(admin))
    if payload.wecom_webhook:
        if not payload.wecom_webhook.startswith("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="):
            raise HTTPException(status_code=400, detail="企业微信群机器人地址格式不正确")
        tenant.wecom_webhook_encrypted = secret_box().encrypt(payload.wecom_webhook.encode()).decode()
    tenant.alert_settings_json = json.dumps(payload.model_dump(exclude={"wecom_webhook"}), ensure_ascii=False)
    audit(db, admin["username"], "save_alert_settings", "customer", str(tenant.id)); db.commit(); return {"ok": True, "wecom_configured": bool(tenant.wecom_webhook_encrypted)}


@router.get("/stream")
def stream(cursor: int = Query(default=0, ge=0), last_event_id: str | None = Header(default=None, alias="Last-Event-ID"), admin: dict = Depends(current_admin)) -> StreamingResponse:
    allowed(admin, "dashboard.read"); cid = tenant_id(admin)
    def events():
        try: resume = int(last_event_id or cursor)
        except ValueError: resume = cursor
        last = resume; started = time.monotonic()
        while time.monotonic() - started < 25:
            with SessionLocal() as db:
                rows = db.scalars(select(DeviceEvent).where(DeviceEvent.customer_id == cid, DeviceEvent.id > last).order_by(DeviceEvent.id).limit(100)).all()
                for row in rows:
                    last = max(last, row.id)
                    yield f"id: {last}\nevent: device-status\ndata: {json.dumps({'device_id': row.device_id, 'event_type': row.event_type}, ensure_ascii=False)}\n\n"
            yield ": keepalive\n\n"; time.sleep(2)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
