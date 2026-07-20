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

@dataclass(frozen=True)
class TenantContext:
    organization_id:int
    member_id:int
    username:str
    role:str

def require_permission(ctx:TenantContext,permission:str)->None:
    if permission not in ROLE_PERMISSIONS.get(ctx.role,set()): raise HTTPException(403,"当前企业成员没有此操作权限")

def organization(db:Session,organization_id:int)->Customer:
    row=db.scalar(select(Customer).where(Customer.id==organization_id,Customer.status=="active"))
    if not row: raise HTTPException(404,"企业不存在或已停用")
    return row

def tenant_row(db:Session,model,row_id:int,organization_id:int):
    row=db.scalar(select(model).where(model.id==row_id,model.organization_id==organization_id))
    if not row: raise HTTPException(404,"资源不存在")
    return row

def audit_v2(db:Session,ctx:TenantContext,action:str,target_type:str,target_id:str,details:str="")->None:
    db.add(AuditLog(actor=f"org:{ctx.organization_id}:{ctx.username}",action=action,target_type=target_type,target_id=target_id,details=details))

def token_hash(token:str)->str:return hashlib.sha256(token.encode()).hexdigest()

def page(limit:int,offset:int)->tuple[int,int]:
    if limit<1 or limit>200 or offset<0: raise HTTPException(422,"分页参数无效")
    return limit,offset
