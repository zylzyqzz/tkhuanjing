from __future__ import annotations
import json,secrets
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from sqlalchemy import or_,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Admin,AuditLog,Customer,Device,LiveRoom,now_iso
from ..models_enterprise import AnchorProfile,DeviceHeartbeatV2,DeviceRoomBinding,LiveAccount,OrganizationMember,OrganizationMemberSession
from ..schemas_v2 import AccountCreateIn,AnchorCreateIn,BindingDeleteIn,BindingPutIn,HeartbeatIn,MemberCreateIn,MemberLoginIn,MemberRoleUpdateIn
from ..security import current_platform_admin,enforce_rate_limit,hasher,request_ip,require_platform_csrf,verify_password
from ..enterprise.common import ROLE_PERMISSIONS,TenantContext,audit_v2,organization,page,require_permission,tenant_row,token_hash
from ..enterprise.organization_service import OrganizationService
from ..enterprise.security import current_member,current_v2_device

router=APIRouter(prefix="/api/v2",tags=["enterprise-v2"])

def binding_view(x:DeviceRoomBinding)->dict:
 return {"id":x.id,"organization_id":x.organization_id,"device_id":x.device_id,"room_id":x.room_id,"account_id":x.account_id,"anchor_id":x.anchor_id,"binding_type":x.binding_type,"status":x.status,"bound_by_user_id":x.bound_by_user_id,"bound_at":x.bound_at,"unbound_at":x.unbound_at,"reason":x.reason,"version":x.version}

@router.post("/auth/login")
def member_login(payload:MemberLoginIn,request:Request,db:Session=Depends(get_db))->dict:
 enforce_rate_limit("v2-member-login",f"{request_ip(request)}:{payload.username}",8,600)
 member=db.scalar(select(OrganizationMember).where(OrganizationMember.username==payload.username,OrganizationMember.active.is_(True)))
 if not member or not verify_password(payload.password,member.password_hash):raise HTTPException(401,"账号或密码错误")
 organization(db,member.organization_id);token=secrets.token_urlsafe(32);expires=datetime.now(timezone.utc)+timedelta(hours=12)
 db.add(OrganizationMemberSession(token_hash=token_hash(token),organization_id=member.organization_id,member_id=member.id,expires_at=expires));db.commit()
 return {"token":token,"expires_at":expires,"permissions":sorted(ROLE_PERMISSIONS.get(member.role,set())),"member":{"id":member.id,"organization_id":member.organization_id,"username":member.username,"display_name":member.display_name,"role":member.role}}

@router.post("/platform/organizations/{organization_id}/members")
def platform_create_member(organization_id:int,payload:MemberCreateIn,admin:dict=Depends(require_platform_csrf),db:Session=Depends(get_db))->dict:
 if admin.get("role","platform_super")!="platform_super":raise HTTPException(403,"仅平台超级管理员可开通企业成员")
 organization(db,organization_id)
 if db.scalar(select(OrganizationMember).where(OrganizationMember.username==payload.username)):raise HTTPException(409,"成员账号已存在")
 row=OrganizationMember(organization_id=organization_id,username=payload.username,password_hash=hasher.hash(payload.password),display_name=payload.display_name,role=payload.role)
 db.add(row);db.flush();db.add(AuditLog(actor=admin["username"],action="v2_create_organization_member",target_type="organization_member",target_id=str(row.id),details=f"organization={organization_id},role={row.role}"));db.commit()
 return {"id":row.id,"organization_id":organization_id,"username":row.username,"role":row.role}

@router.get("/organization/members")
def organization_members(ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"members.manage")
 rows=db.scalars(select(OrganizationMember).where(OrganizationMember.organization_id==ctx.organization_id).order_by(OrganizationMember.id)).all()
 return {"items":[{"id":x.id,"username":x.username,"display_name":x.display_name,"role":x.role,"active":x.active,"created_at":x.created_at} for x in rows]}

@router.put("/organization/members/{member_id}")
def update_organization_member(member_id:int,payload:MemberRoleUpdateIn,ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"members.manage")
 row=tenant_row(db,OrganizationMember,member_id,ctx.organization_id)
 if row.id==ctx.member_id and (payload.role!="owner" or not payload.active):raise HTTPException(409,"不能停用或降级当前登录的企业主管账号")
 before={"role":row.role,"active":row.active};row.role=payload.role;row.active=payload.active
 audit_v2(db,ctx,"update_organization_member","organization_member",str(row.id),json.dumps({"before":before,"after":{"role":row.role,"active":row.active}},ensure_ascii=False));db.commit()
 return {"id":row.id,"organization_id":row.organization_id,"role":row.role,"active":row.active}

@router.get("/organization/options")
def organization_options(ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"organization.read");svc=OrganizationService(db,ctx.organization_id)
 return {"organization":{"id":svc.get().id,"name":svc.get().name},"rooms":[{"id":x.id,"name":x.name,"region":x.region} for x in svc.rooms()],"accounts":[{"id":x.id,"display_name":x.display_name,"room_id":x.room_id} for x in svc.accounts()],"anchors":[{"id":x.id,"display_name":x.display_name} for x in svc.anchors()]}

@router.post("/organization/accounts")
def create_account(payload:AccountCreateIn,ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"binding.write")
 if payload.room_id: tenant_room(db,payload.room_id,ctx.organization_id)
 row=LiveAccount(organization_id=ctx.organization_id,room_id=payload.room_id,display_name=payload.display_name,platform_account_ref=payload.platform_account_ref,target_region_id=payload.target_region_id)
 db.add(row);db.flush();audit_v2(db,ctx,"create_live_account","live_account",str(row.id));db.commit();return {"id":row.id}

@router.post("/organization/anchors")
def create_anchor(payload:AnchorCreateIn,ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"binding.write");row=AnchorProfile(organization_id=ctx.organization_id,display_name=payload.display_name,employee_ref=payload.employee_ref)
 db.add(row);db.flush();audit_v2(db,ctx,"create_anchor_profile","anchor_profile",str(row.id));db.commit();return {"id":row.id}

def tenant_room(db:Session,room_id:int,organization_id:int)->LiveRoom:
 row=db.scalar(select(LiveRoom).where(LiveRoom.id==room_id,LiveRoom.customer_id==organization_id,LiveRoom.status=="active"))
 if not row:raise HTTPException(404,"直播间不存在")
 return row

@router.get("/device/binding")
def get_binding(device:Device=Depends(current_v2_device),db:Session=Depends(get_db))->dict:
 row=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.device_id==device.device_id,DeviceRoomBinding.status=="active").order_by(DeviceRoomBinding.binding_type=="primary",DeviceRoomBinding.bound_at.desc()))
 return {"binding":binding_view(row) if row else None,"synced_at":datetime.now(timezone.utc)}

@router.put("/device/binding")
def put_binding(payload:BindingPutIn,ctx:TenantContext=Depends(current_member),device:Device=Depends(current_v2_device),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"binding.write");organization(db,ctx.organization_id);tenant_room(db,payload.room_id,ctx.organization_id)
 if device.customer_id not in {None,ctx.organization_id}:raise HTTPException(403,"设备属于其他企业")
 if payload.account_id:tenant_row(db,LiveAccount,payload.account_id,ctx.organization_id)
 if payload.anchor_id:tenant_row(db,AnchorProfile,payload.anchor_id,ctx.organization_id)
 if payload.binding_type=="primary":
  room_conflict=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.room_id==payload.room_id,DeviceRoomBinding.status=="active",DeviceRoomBinding.binding_type=="primary",DeviceRoomBinding.device_id!=device.device_id))
  if room_conflict:raise HTTPException(409,"该直播间已有主设备")
  old=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.device_id==device.device_id,DeviceRoomBinding.status=="active",DeviceRoomBinding.binding_type=="primary"))
  if old:
   if old.room_id==payload.room_id and old.account_id==payload.account_id and old.anchor_id==payload.anchor_id:return {"binding":binding_view(old),"idempotent":True}
   old.status="ended";old.unbound_at=datetime.now(timezone.utc);old.reason=payload.reason or "换绑"
 version=(db.scalar(select(DeviceRoomBinding.version).where(DeviceRoomBinding.device_id==device.device_id).order_by(DeviceRoomBinding.version.desc())) or 0)+1
 row=DeviceRoomBinding(organization_id=ctx.organization_id,device_id=device.device_id,room_id=payload.room_id,account_id=payload.account_id,anchor_id=payload.anchor_id,binding_type=payload.binding_type,bound_by_user_id=ctx.member_id,reason=payload.reason,version=version)
 db.add(row);device.customer_id=ctx.organization_id;device.room_id=payload.room_id;device.customer_name=organization(db,ctx.organization_id).name;device.room_name=tenant_room(db,payload.room_id,ctx.organization_id).name
 try:db.flush()
 except IntegrityError:db.rollback();raise HTTPException(409,"设备或直播间存在冲突的主绑定") from None
 audit_v2(db,ctx,"bind_device_room","device_room_binding",str(row.id),json.dumps({"device_id":device.device_id,"room_id":payload.room_id,"type":payload.binding_type},ensure_ascii=False));db.commit()
 return {"binding":binding_view(row),"idempotent":False}

@router.delete("/device/binding")
def delete_binding(payload:BindingDeleteIn,ctx:TenantContext=Depends(current_member),device:Device=Depends(current_v2_device),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"binding.write")
 row=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.device_id==device.device_id,DeviceRoomBinding.organization_id==ctx.organization_id,DeviceRoomBinding.status=="active",DeviceRoomBinding.binding_type=="primary"))
 if not row:raise HTTPException(404,"当前没有有效主绑定")
 row.status="ended";row.unbound_at=datetime.now(timezone.utc);row.reason=payload.reason;device.room_id=None;device.room_name=""
 audit_v2(db,ctx,"unbind_device_room","device_room_binding",str(row.id),payload.reason);db.commit();return {"ok":True,"binding":binding_view(row)}

@router.post("/device/heartbeat")
def heartbeat(payload:HeartbeatIn,device:Device=Depends(current_v2_device),db:Session=Depends(get_db))->dict:
 if payload.device_id!=device.device_id:raise HTTPException(403,"心跳设备标识不匹配")
 if not device.customer_id:raise HTTPException(409,"设备尚未绑定企业")
 binding=None
 if payload.binding_id:
  binding=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.id==payload.binding_id,DeviceRoomBinding.organization_id==device.customer_id,DeviceRoomBinding.device_id==device.device_id,DeviceRoomBinding.status=="active"))
  if not binding:raise HTTPException(409,"绑定已失效，请重新同步")
 existing=db.scalar(select(DeviceHeartbeatV2).where(DeviceHeartbeatV2.device_id==device.device_id,DeviceHeartbeatV2.sent_at==payload.sent_at))
 if existing:return {"server_time":datetime.now(timezone.utc),"heartbeat_interval_seconds":20,"binding_version":binding.version if binding else 0,"commands":[],"config_version":1,"idempotent":True}
 m=payload.metrics;row=DeviceHeartbeatV2(organization_id=device.customer_id,device_id=device.device_id,binding_id=payload.binding_id,agent_version=payload.agent_version,sent_at=payload.sent_at,uptime_seconds=payload.uptime_seconds,device_status=payload.status,live_software_json=payload.live_software.model_dump_json(),collection_json=payload.collection.model_dump_json(),cpu_percent=m.cpu_percent,memory_percent=m.memory_percent,network_latency_ms=m.network_latency_ms,upload_mbps=m.upload_mbps,stream_bitrate_kbps=m.stream_bitrate_kbps,dropped_frames=m.dropped_frames,last_success_at=payload.collection.last_success_at)
 db.add(row);device.last_seen=now_iso();device.last_heartbeat_at=now_iso();device.app_version=payload.agent_version;device.studio_state="running" if payload.live_software.running else "not_running";device.state_version+=1
 try:db.commit()
 except IntegrityError:db.rollback();return {"server_time":datetime.now(timezone.utc),"heartbeat_interval_seconds":20,"binding_version":binding.version if binding else 0,"commands":[],"config_version":1,"idempotent":True}
 return {"server_time":datetime.now(timezone.utc),"heartbeat_interval_seconds":20,"binding_version":binding.version if binding else 0,"commands":[],"config_version":1,"idempotent":False}

@router.get("/device/config")
def device_config(device:Device=Depends(current_v2_device),db:Session=Depends(get_db))->dict:
 binding=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.device_id==device.device_id,DeviceRoomBinding.status=="active",DeviceRoomBinding.binding_type=="primary"))
 return {"config_version":1,"heartbeat_interval_seconds":20,"binding":binding_view(binding) if binding else None,"allowed_commands":["refresh_config","sync_binding"],"commands":[]}

@router.get("/organization/devices")
def realtime_devices(room_id:int|None=None,status:str="",version:str="",limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"devices.read");page(limit,offset)
 stmt=select(Device).where(Device.customer_id==ctx.organization_id)
 if room_id:stmt=stmt.where(Device.room_id==room_id)
 if version:stmt=stmt.where(Device.app_version==version)
 rows=db.scalars(stmt.order_by(Device.last_heartbeat_at.desc()).offset(offset).limit(limit)).all();now=datetime.now(timezone.utc)
 result=[]
 for d in rows:
  binding=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.device_id==d.device_id,DeviceRoomBinding.organization_id==ctx.organization_id,DeviceRoomBinding.status=="active",DeviceRoomBinding.binding_type=="primary"))
  latest=db.scalar(select(DeviceHeartbeatV2).where(DeviceHeartbeatV2.device_id==d.device_id,DeviceHeartbeatV2.organization_id==ctx.organization_id).order_by(DeviceHeartbeatV2.received_at.desc()))
  online=bool(latest and (now-(latest.received_at.replace(tzinfo=timezone.utc) if latest.received_at.tzinfo is None else latest.received_at)).total_seconds()<=90)
  if status and status!=("online" if online else "offline"):continue
  result.append({"device_id":d.device_id,"display_name":d.display_name or d.device_id,"online":online,"agent_version":d.app_version,"last_heartbeat_at":latest.received_at if latest else None,"binding":binding_view(binding) if binding else None,"live_software":json.loads(latest.live_software_json) if latest else {},"collection":json.loads(latest.collection_json) if latest else {},"metrics":{"cpu_percent":latest.cpu_percent,"memory_percent":latest.memory_percent,"network_latency_ms":latest.network_latency_ms,"upload_mbps":latest.upload_mbps} if latest else {}})
 return {"items":result,"limit":limit,"offset":offset}

@router.get("/platform/devices")
def platform_realtime_devices(organization_id:int=Query(...,ge=1),room_id:int|None=None,status:str="",version:str="",limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),admin:dict=Depends(current_platform_admin),db:Session=Depends(get_db))->dict:
 organization(db,organization_id)
 return realtime_devices(room_id=room_id,status=status,version=version,limit=limit,offset=offset,ctx=TenantContext(organization_id,0,admin["username"],"owner"),db=db)
