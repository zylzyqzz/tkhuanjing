from __future__ import annotations
from datetime import datetime,timezone
from fastapi import Depends,Header
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Device
from ..models_enterprise import OrganizationMember,OrganizationMemberSession
from .common import TenantContext,api_error,token_hash

def revoke_member_sessions(db: Session, member_id: int) -> int:
    rows = db.scalars(select(OrganizationMemberSession).where(OrganizationMemberSession.member_id == member_id, OrganizationMemberSession.revoked.is_(False))).all()
    for row in rows:
        row.revoked = True
    return len(rows)

def revoke_organization_sessions(db: Session, organization_id: int) -> int:
    rows = db.scalars(select(OrganizationMemberSession).where(OrganizationMemberSession.organization_id == organization_id, OrganizationMemberSession.revoked.is_(False))).all()
    for row in rows:
        row.revoked = True
    return len(rows)

def aware(value:datetime)->datetime:return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def current_member(authorization:str|None=Header(default=None),db:Session=Depends(get_db))->TenantContext:
    token=authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    session=db.get(OrganizationMemberSession,token_hash(token)) if token else None
    if not session or session.revoked:
        raise api_error("AUTH_INVALID", "企业会话无效，请重新登录")
    if aware(session.expires_at)<=datetime.now(timezone.utc):
        raise api_error("AUTH_EXPIRED", "企业会话已过期，请重新登录")
    member=db.scalar(select(OrganizationMember).where(OrganizationMember.id==session.member_id,OrganizationMember.organization_id==session.organization_id,OrganizationMember.active.is_(True)))
    if not member:raise api_error("AUTH_INVALID", "企业成员已停用")
    return TenantContext(member.organization_id,member.id,member.username,member.role)

def current_v2_device(x_device_token:str|None=Header(default=None,alias="X-Device-Token"),db:Session=Depends(get_db))->Device:
    device=db.scalar(select(Device).where(Device.token_hash==token_hash(x_device_token or "")))
    if not device or device.status!="active":raise api_error("AUTH_INVALID", "设备令牌无效")
    return device
