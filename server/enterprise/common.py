from __future__ import annotations
import hashlib
from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import AuditLog, Customer
from ..models_enterprise import OrganizationMember

ROLE_PERMISSIONS={
 "owner":{"organization.read","members.manage","binding.read","binding.write","devices.read","devices.write"},
 "manager":{"organization.read","binding.read","binding.write","devices.read","devices.write"},
 "operator":{"organization.read","binding.read","binding.write","devices.read","devices.write"},
 "viewer":{"organization.read","binding.read","devices.read"},
}

ERROR_STATUS = {
    "AUTH_INVALID": 401,
    "AUTH_EXPIRED": 401,
    "AUTH_ORGANIZATION_REQUIRED": 409,
    "PERMISSION_DENIED": 403,
    "FEATURE_NOT_ENABLED": 403,
    "TENANT_RESOURCE_NOT_FOUND": 404,
    "BINDING_CONFLICT": 409,
    "ACCOUNT_ROOM_MISMATCH": 409,
    "ACCOUNT_INACTIVE": 409,
    "ANCHOR_INACTIVE": 409,
    "FEATURE_CODE_EXISTS": 409,
    "FEATURE_NOT_FOUND": 404,
    "MEMBER_EXISTS": 409,
    "MEMBER_SELF_PROTECTION": 409,
    "DEVICE_NOT_BOUND": 409,
    "BINDING_STALE": 409,
    "VALIDATION_ERROR": 422,
    "INTERNAL_ERROR": 500,
}


def api_error(code: str, message: str, details: dict | None = None, status_code: int | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code or ERROR_STATUS.get(code, 400),
        detail={"code": code, "message": message, "details": details or {}},
    )

@dataclass(frozen=True)
class TenantContext:
    organization_id:int
    member_id:int
    username:str
    role:str

def require_permission(ctx:TenantContext,permission:str)->None:
    if permission not in ROLE_PERMISSIONS.get(ctx.role,set()):
        raise api_error("PERMISSION_DENIED", "当前企业成员没有此操作权限", {"permission": permission})

def organization(db:Session,organization_id:int)->Customer:
    row=db.scalar(select(Customer).where(Customer.id==organization_id,Customer.status=="active"))
    if not row: raise api_error("TENANT_RESOURCE_NOT_FOUND", "企业不存在或已停用")
    return row

def organization_by_code(db: Session, code: str) -> Customer | None:
    return db.scalar(select(Customer).where(Customer.organization_code == code, Customer.status == "active"))

def tenant_row(db:Session,model,row_id:int,organization_id:int):
    row=db.scalar(select(model).where(model.id==row_id,model.organization_id==organization_id))
    if not row: raise api_error("TENANT_RESOURCE_NOT_FOUND", "资源不存在")
    return row

def audit_v2(db:Session,ctx:TenantContext,action:str,target_type:str,target_id:str,details:str="")->None:
    db.add(AuditLog(actor=f"org:{ctx.organization_id}:{ctx.username}",action=action,target_type=target_type,target_id=target_id,details=details))

def token_hash(token:str)->str:return hashlib.sha256(token.encode()).hexdigest()

def page(limit:int,offset:int)->tuple[int,int]:
    if limit<1 or limit>200 or offset<0: raise api_error("VALIDATION_ERROR", "分页参数无效")
    return limit,offset
