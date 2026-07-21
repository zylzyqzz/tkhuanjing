from __future__ import annotations
import json,secrets
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from sqlalchemy import func,or_,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Admin,AuditLog,Customer,Device,LiveRoom,now_iso
from ..models_enterprise import AnchorProfile,DeviceFeatureOverride,DeviceHeartbeatV2,DeviceRoomBinding,FeatureDefinition,FeatureRollout,LiveAccount,OrganizationFeature,OrganizationMember,OrganizationMemberSession,PlanFeature
from ..schemas_v2 import AccountCreateIn,AnchorCreateIn,BindingDeleteIn,BindingPutIn,FeatureAssignmentIn,FeatureAssignmentsIn,FeatureDefinitionIn,HeartbeatIn,MemberCreateIn,MemberLoginIn,MemberRoleUpdateIn,OnboardingProgressIn,RoomCreateIn
from ..security import current_platform_admin,enforce_rate_limit,hasher,request_ip,require_platform_csrf,verify_password
from ..enterprise.common import ROLE_PERMISSIONS,TenantContext,audit_v2,organization,organization_by_code,page,require_permission,tenant_row,token_hash
from ..enterprise.organization_service import OrganizationService
from ..enterprise.security import current_member,current_v2_device,revoke_member_sessions
from ..enterprise.bindings import get_active_primary_binding
from ..enterprise.features import FeatureService,require_feature,require_feature_permission,seed_feature_definitions
from ..config import get_settings

router=APIRouter(prefix="/api/v2",tags=["enterprise-v2"])

def binding_view(x:DeviceRoomBinding)->dict:
 return {"id":x.id,"organization_id":x.organization_id,"device_id":x.device_id,"room_id":x.room_id,"account_id":x.account_id,"anchor_id":x.anchor_id,"binding_type":x.binding_type,"status":x.status,"bound_by_user_id":x.bound_by_user_id,"bound_at":x.bound_at,"unbound_at":x.unbound_at,"reason":x.reason,"version":x.version}

@router.post("/auth/login")
def member_login(payload:MemberLoginIn,request:Request,db:Session=Depends(get_db))->dict:
 enforce_rate_limit("v2-member-login",f"{request_ip(request)}:{payload.username}",8,600)
 stmt=select(OrganizationMember).where(OrganizationMember.username==payload.username,OrganizationMember.active.is_(True))
 if payload.organization_code:
  org=organization_by_code(db,payload.organization_code)
  if not org: raise HTTPException(401,"账号或密码错误")
  stmt=stmt.where(OrganizationMember.organization_id==org.id)
 member=db.scalar(stmt)
 if not payload.organization_code:
  matches=db.scalars(stmt).all()
  if len(matches)>1: raise HTTPException(400,{"code":"AUTH_ORGANIZATION_REQUIRED","message":"请输入企业代码后重新登录","details":{}})
  member=matches[0] if matches else None
 if not member or not verify_password(payload.password,member.password_hash):raise HTTPException(401,"账号或密码错误")
 organization(db,member.organization_id);token=secrets.token_urlsafe(32);expires=datetime.now(timezone.utc)+timedelta(hours=12)
 db.add(OrganizationMemberSession(token_hash=token_hash(token),organization_id=member.organization_id,member_id=member.id,expires_at=expires));db.commit()
 return {"token":token,"expires_at":expires,"permissions":sorted(ROLE_PERMISSIONS.get(member.role,set())),"member":{"id":member.id,"organization_id":member.organization_id,"username":member.username,"display_name":member.display_name,"role":member.role}}

@router.post("/platform/organizations/{organization_id}/members")
def platform_create_member(organization_id:int,payload:MemberCreateIn,admin:dict=Depends(require_platform_csrf),db:Session=Depends(get_db))->dict:
 if admin.get("role","platform_super")!="platform_super":raise HTTPException(403,"仅平台超级管理员可开通企业成员")
 organization(db,organization_id)
 if db.scalar(select(OrganizationMember).where(OrganizationMember.organization_id==organization_id,OrganizationMember.username==payload.username)):raise HTTPException(409,"该企业成员账号已存在")
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
 if not row.active:
  revoke_member_sessions(db,row.id)
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

@router.post("/organization/rooms")
def create_room(payload:RoomCreateIn,ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db),_feature:dict=Depends(require_feature_permission("device_binding","create")))->dict:
 row=LiveRoom(customer_id=ctx.organization_id,name=payload.name,region=payload.region,status="active");db.add(row);db.flush();audit_v2(db,ctx,"create_live_room","live_room",str(row.id),json.dumps({"name":row.name,"region":row.region},ensure_ascii=False));db.commit();return {"id":row.id,"name":row.name,"region":row.region}

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
 row=get_active_primary_binding(db,device.device_id,device.customer_id)
 return {"binding":binding_view(row) if row else None,"synced_at":datetime.now(timezone.utc)}

@router.put("/device/binding")
def put_binding(payload:BindingPutIn,ctx:TenantContext=Depends(current_member),device:Device=Depends(current_v2_device),db:Session=Depends(get_db),_feature:dict=Depends(require_feature_permission("device_binding","update")))->dict:
 require_permission(ctx,"binding.write");organization(db,ctx.organization_id);tenant_room(db,payload.room_id,ctx.organization_id)
 if device.customer_id not in {None,ctx.organization_id}:raise HTTPException(403,"设备属于其他企业")
 if payload.account_id:tenant_row(db,LiveAccount,payload.account_id,ctx.organization_id)
 if payload.anchor_id:tenant_row(db,AnchorProfile,payload.anchor_id,ctx.organization_id)
 if payload.binding_type=="primary":
  room_conflict=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.room_id==payload.room_id,DeviceRoomBinding.status=="active",DeviceRoomBinding.binding_type=="primary",DeviceRoomBinding.device_id!=device.device_id))
  if room_conflict:raise HTTPException(409,"该直播间已有主设备")
  old=get_active_primary_binding(db,device.device_id,ctx.organization_id,for_update=True)
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
 if not FeatureService(db,device.customer_id).is_feature_enabled("device_heartbeat",device=device,client_version=payload.agent_version):raise HTTPException(403,{"code":"FEATURE_NOT_ENABLED","message":"当前企业尚未开通设备实时状态","details":{"feature_code":"device_heartbeat"}})
 binding=None
 if payload.binding_id:
  binding=db.scalar(select(DeviceRoomBinding).where(DeviceRoomBinding.id==payload.binding_id,DeviceRoomBinding.organization_id==device.customer_id,DeviceRoomBinding.device_id==device.device_id,DeviceRoomBinding.status=="active"))
  if not binding:raise HTTPException(409,"绑定已失效，请重新同步")
 existing=db.scalar(select(DeviceHeartbeatV2).where(DeviceHeartbeatV2.device_id==device.device_id,DeviceHeartbeatV2.sent_at==payload.sent_at))
 if existing:return {"server_time":datetime.now(timezone.utc),"heartbeat_interval_seconds":20,"binding_version":binding.version if binding else 0,"commands":[],"config_version":1,"idempotent":True}
 m=payload.metrics;row=DeviceHeartbeatV2(organization_id=device.customer_id,device_id=device.device_id,binding_id=payload.binding_id,agent_version=payload.agent_version,sent_at=payload.sent_at,uptime_seconds=payload.uptime_seconds,device_status=payload.status,live_software_json=payload.live_software.model_dump_json(),collection_json=payload.collection.model_dump_json(),cpu_percent=m.cpu_percent,memory_percent=m.memory_percent,network_latency_ms=m.network_latency_ms,upload_mbps=m.upload_mbps,stream_bitrate_kbps=m.stream_bitrate_kbps,dropped_frames=m.dropped_frames,last_success_at=payload.collection.last_success_at)
 received=datetime.now(timezone.utc);skew=int((received-payload.sent_at).total_seconds());row.received_at=received
 db.add(row);device.last_seen=now_iso();device.last_heartbeat_at=received.isoformat();device.app_version=payload.agent_version;device.studio_state="running" if payload.live_software.running else "not_running";device.collector_state=payload.collection.status;device.cpu_percent=m.cpu_percent;device.memory_percent=m.memory_percent;device.network_latency_ms=m.network_latency_ms;device.upload_mbps=m.upload_mbps;device.stream_bitrate_kbps=m.stream_bitrate_kbps;device.dropped_frames=m.dropped_frames;device.clock_skew_seconds=skew;device.online_state="online";device.state_version+=1
 try:db.commit()
 except IntegrityError:db.rollback();return {"server_time":datetime.now(timezone.utc),"heartbeat_interval_seconds":20,"binding_version":binding.version if binding else 0,"commands":[],"config_version":1,"idempotent":True}
 return {"server_time":received,"heartbeat_interval_seconds":20,"binding_version":binding.version if binding else 0,"clock_skew_warning":abs(skew)>300,"clock_skew_seconds":skew,"commands":[],"config_version":1,"idempotent":False}

@router.get("/device/config")
def device_config(device:Device=Depends(current_v2_device),db:Session=Depends(get_db))->dict:
 binding=get_active_primary_binding(db,device.device_id,device.customer_id)
 return {"config_version":1,"heartbeat_interval_seconds":20,"binding":binding_view(binding) if binding else None,"allowed_commands":["refresh_config","sync_binding"],"commands":[]}

@router.get("/organization/devices")
def realtime_devices(room_id:int|None=None,status:str="",version:str="",limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"devices.read");page(limit,offset)
 stmt=select(Device).where(Device.customer_id==ctx.organization_id)
 if room_id:stmt=stmt.where(Device.room_id==room_id)
 if version:stmt=stmt.where(Device.app_version==version)
 total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
 rows=db.scalars(stmt.order_by(Device.last_heartbeat_at.desc()).offset(offset).limit(limit)).all();now=datetime.now(timezone.utc)
 result=[]
 for d in rows:
  age=(now-datetime.fromisoformat(d.last_heartbeat_at)).total_seconds() if d.last_heartbeat_at else 10**9
  online_state="online" if age<=60 else ("unstable" if age<=180 else "offline")
  if status and status!=online_state:continue
  binding=get_active_primary_binding(db,d.device_id,ctx.organization_id)
  result.append({"device_id":d.device_id,"display_name":d.display_name or d.device_id,"online":online_state=="online","online_state":online_state,"agent_version":d.app_version,"last_heartbeat_at":d.last_heartbeat_at,"binding":binding_view(binding) if binding else None,"studio_state":d.studio_state,"collector_state":d.collector_state,"live_software":{"name":"TikTok LIVE Studio","running":d.studio_state=="running"},"collection":{"status":d.collector_state},"metrics":{"cpu_percent":d.cpu_percent,"memory_percent":d.memory_percent,"network_latency_ms":d.network_latency_ms,"upload_mbps":d.upload_mbps,"stream_bitrate_kbps":d.stream_bitrate_kbps,"dropped_frames":d.dropped_frames}})
 return {"items":result,"pagination":{"limit":limit,"offset":offset,"total":total}}

@router.get("/platform/devices")
def platform_realtime_devices(organization_id:int=Query(...,ge=1),room_id:int|None=None,status:str="",version:str="",limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),admin:dict=Depends(current_platform_admin),db:Session=Depends(get_db))->dict:
 organization(db,organization_id)
 return realtime_devices(room_id=room_id,status=status,version=version,limit=limit,offset=offset,ctx=TenantContext(organization_id,0,admin["username"],"owner"),db=db)


def _feature_view(row:FeatureDefinition)->dict:
 return {"id":row.id,"feature_code":row.feature_code,"feature_name":row.feature_name,"category":row.category,"description":row.description,"client_type":row.client_type,"default_enabled":row.default_enabled,"status":row.status,"minimum_client_version":row.minimum_client_version,"config_schema":json.loads(row.config_schema_json or "{}"),"updated_at":row.updated_at}

@router.get("/organization/bootstrap")
def organization_bootstrap(ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 org=organization(db,ctx.organization_id);member=tenant_row(db,OrganizationMember,ctx.member_id,ctx.organization_id);features=FeatureService(db,ctx.organization_id).get_effective_features_for_organization(ctx.role)
 limits={"max_devices":org.device_limit,"max_members":org.member_limit,"max_rooms":max(org.device_limit,1)}
 for item in features.values():limits.update(item.get("limits",{}))
 return {"organization":{"id":org.id,"name":org.name,"code":org.organization_code,"status":org.status,"plan_code":org.plan_code,"onboarding":{"step":org.onboarding_step,"completed":org.onboarding_completed,"total_steps":7}},"member":{"id":member.id,"username":member.username,"display_name":member.display_name,"role":member.role},"permissions":sorted(ROLE_PERMISSIONS.get(ctx.role,set())),"features":features,"limits":limits,"config_version":org.feature_config_version}

@router.get("/organization/features")
def organization_features(ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"organization.read");return {"features":FeatureService(db,ctx.organization_id).get_effective_features_for_organization(ctx.role),"config_version":organization(db,ctx.organization_id).feature_config_version}

@router.get("/organization/usage")
def organization_usage(ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 org=organization(db,ctx.organization_id)
 return {"devices":{"used":db.scalar(select(func.count()).select_from(Device).where(Device.customer_id==ctx.organization_id,Device.status=="active")) or 0,"limit":org.device_limit},"rooms":{"used":db.scalar(select(func.count()).select_from(LiveRoom).where(LiveRoom.customer_id==ctx.organization_id,LiveRoom.status=="active")) or 0,"limit":max(org.device_limit,1)},"members":{"used":db.scalar(select(func.count()).select_from(OrganizationMember).where(OrganizationMember.organization_id==ctx.organization_id,OrganizationMember.active.is_(True))) or 0,"limit":org.member_limit}}

@router.put("/organization/onboarding")
def update_onboarding(payload:OnboardingProgressIn,ctx:TenantContext=Depends(current_member),db:Session=Depends(get_db))->dict:
 require_permission(ctx,"organization.read");org=organization(db,ctx.organization_id);before={"step":org.onboarding_step,"completed":org.onboarding_completed};org.onboarding_step=max(org.onboarding_step,payload.step);org.onboarding_completed=payload.completed or org.onboarding_completed;audit_v2(db,ctx,"update_onboarding","customer",str(org.id),json.dumps({"before":before,"after":{"step":org.onboarding_step,"completed":org.onboarding_completed}},ensure_ascii=False));db.commit();return {"step":org.onboarding_step,"completed":org.onboarding_completed,"total_steps":7}

@router.get("/device/bootstrap")
def device_bootstrap(device:Device=Depends(current_v2_device),db:Session=Depends(get_db))->dict:
 if not device.customer_id:raise HTTPException(409,{"code":"DEVICE_NOT_BOUND","message":"这台电脑还没有加入企业","details":{}})
 org=organization(db,device.customer_id);settings=get_settings();binding=get_active_primary_binding(db,device.device_id,device.customer_id);features=FeatureService(db,device.customer_id).get_effective_features_for_device(device,device.app_version)
 return {"device":{"device_id":device.device_id,"display_name":device.display_name or device.device_id,"status":device.status,"version":device.app_version},"organization":{"id":org.id,"name":org.name,"code":org.organization_code},"binding":binding_view(binding) if binding else None,"features":{code:item["enabled"] for code,item in features.items()},"feature_details":features,"config":{"heartbeat_interval_seconds":settings.heartbeat_interval_seconds,"queue_max_items":settings.heartbeat_queue_max_items,"queue_max_age_hours":settings.heartbeat_queue_max_age_hours,"allowed_commands":["refresh_config","sync_binding"]},"minimum_version":settings.minimum_client_version,"config_version":max(org.feature_config_version,device.feature_config_version)}

@router.get("/platform/features")
def platform_features(admin:dict=Depends(current_platform_admin),db:Session=Depends(get_db))->dict:
 seed_feature_definitions(db);db.commit();rows=db.scalars(select(FeatureDefinition).order_by(FeatureDefinition.category,FeatureDefinition.feature_code)).all();return {"items":[_feature_view(x) for x in rows]}

@router.post("/platform/features")
def create_feature(payload:FeatureDefinitionIn,admin:dict=Depends(require_platform_csrf),db:Session=Depends(get_db))->dict:
 if db.scalar(select(FeatureDefinition).where(FeatureDefinition.feature_code==payload.feature_code)):raise HTTPException(409,{"code":"FEATURE_CODE_EXISTS","message":"功能代码已存在","details":{"feature_code":payload.feature_code}})
 row=FeatureDefinition(feature_code=payload.feature_code,feature_name=payload.feature_name,category=payload.category,description=payload.description,client_type=payload.client_type,default_enabled=payload.default_enabled,status=payload.status,minimum_client_version=payload.minimum_client_version,config_schema_json=json.dumps(payload.config_schema,ensure_ascii=False));db.add(row);db.flush();db.add(AuditLog(actor=admin["username"],action="create_feature",target_type="feature_definition",target_id=str(row.id),details=json.dumps(_feature_view(row),ensure_ascii=False,default=str)));db.commit();return _feature_view(row)

@router.put("/platform/features/{feature_id}")
def update_feature(feature_id:int,payload:FeatureDefinitionIn,admin:dict=Depends(require_platform_csrf),db:Session=Depends(get_db))->dict:
 row=db.get(FeatureDefinition,feature_id)
 if not row:raise HTTPException(404,{"code":"TENANT_RESOURCE_NOT_FOUND","message":"功能不存在"})
 before=_feature_view(row)
 for key in ("feature_code","feature_name","category","description","client_type","default_enabled","status","minimum_client_version"):setattr(row,key,getattr(payload,key))
 row.config_schema_json=json.dumps(payload.config_schema,ensure_ascii=False);db.add(AuditLog(actor=admin["username"],action="update_feature",target_type="feature_definition",target_id=str(row.id),details=json.dumps({"before":before,"after":_feature_view(row)},ensure_ascii=False,default=str)));db.commit();return _feature_view(row)

def _feature_by_code(db:Session,code:str)->FeatureDefinition:
 seed_feature_definitions(db)
 row=db.scalar(select(FeatureDefinition).where(FeatureDefinition.feature_code==code))
 if not row:raise HTTPException(404,{"code":"FEATURE_NOT_FOUND","message":"功能不存在","details":{"feature_code":code}})
 return row

@router.get("/platform/plans/{plan_id}/features")
def platform_plan_features(plan_id:str,admin:dict=Depends(current_platform_admin),db:Session=Depends(get_db))->dict:
 seed_feature_definitions(db);rows=db.scalars(select(PlanFeature).where(PlanFeature.plan_id==plan_id)).all();defs={x.id:x for x in db.scalars(select(FeatureDefinition)).all()};return {"items":[{"feature_code":defs[x.feature_id].feature_code,"enabled":x.enabled,"limits":json.loads(x.limits_json or "{}"),"config":json.loads(x.config_json or "{}")} for x in rows if x.feature_id in defs]}

@router.put("/platform/plans/{plan_id}/features")
def update_plan_features(plan_id:str,payload:FeatureAssignmentsIn,admin:dict=Depends(require_platform_csrf),db:Session=Depends(get_db))->dict:
 for item in payload.items:
  feature=_feature_by_code(db,item.feature_code);row=db.scalar(select(PlanFeature).where(PlanFeature.plan_id==plan_id,PlanFeature.feature_id==feature.id)) or PlanFeature(plan_id=plan_id,feature_id=feature.id);row.enabled=item.enabled;row.limits_json=json.dumps(item.limits,ensure_ascii=False);row.config_json=json.dumps(item.config,ensure_ascii=False);db.add(row)
 for org in db.scalars(select(Customer).where(Customer.plan_code==plan_id)).all():org.feature_config_version+=1
 db.add(AuditLog(actor=admin["username"],action="update_plan_features",target_type="subscription_plan",target_id=plan_id,details=json.dumps(payload.model_dump(mode="json"),ensure_ascii=False)));db.commit();return {"ok":True}

@router.get("/platform/organizations/{organization_id}/features")
def platform_organization_features(organization_id:int,admin:dict=Depends(current_platform_admin),db:Session=Depends(get_db))->dict:
 org=organization(db,organization_id);return {"organization":{"id":org.id,"name":org.name},"features":FeatureService(db,organization_id).get_effective_features_for_organization(),"config_version":org.feature_config_version}

@router.put("/platform/organizations/{organization_id}/features")
def update_organization_features(organization_id:int,payload:FeatureAssignmentsIn,admin:dict=Depends(require_platform_csrf),db:Session=Depends(get_db))->dict:
 org=organization(db,organization_id)
 for item in payload.items:
  feature=_feature_by_code(db,item.feature_code);row=db.scalar(select(OrganizationFeature).where(OrganizationFeature.organization_id==organization_id,OrganizationFeature.feature_id==feature.id)) or OrganizationFeature(organization_id=organization_id,feature_id=feature.id,enabled=item.enabled);row.enabled=item.enabled;row.source=item.source;row.config_json=json.dumps(item.config,ensure_ascii=False);row.starts_at=item.starts_at;row.expires_at=item.expires_at;row.updated_by=admin["username"];db.add(row)
 org.feature_config_version+=1;db.add(AuditLog(actor=admin["username"],action="update_organization_features",target_type="customer",target_id=str(org.id),details=json.dumps(payload.model_dump(mode="json"),ensure_ascii=False)));db.commit();return {"ok":True,"config_version":org.feature_config_version}

@router.get("/platform/devices/{device_id}/features")
def platform_device_features(device_id:str,admin:dict=Depends(current_platform_admin),db:Session=Depends(get_db))->dict:
 device=db.get(Device,device_id)
 if not device or not device.customer_id:raise HTTPException(404,{"code":"TENANT_RESOURCE_NOT_FOUND","message":"设备不存在或尚未加入企业"})
 return {"device":{"device_id":device.device_id,"organization_id":device.customer_id},"features":FeatureService(db,device.customer_id).get_effective_features_for_device(device,device.app_version),"config_version":device.feature_config_version}

@router.put("/platform/devices/{device_id}/features")
def update_device_features(device_id:str,payload:FeatureAssignmentsIn,admin:dict=Depends(require_platform_csrf),db:Session=Depends(get_db))->dict:
 device=db.get(Device,device_id)
 if not device or not device.customer_id:raise HTTPException(404,{"code":"TENANT_RESOURCE_NOT_FOUND","message":"设备不存在或尚未加入企业"})
 for item in payload.items:
  feature=_feature_by_code(db,item.feature_code);row=db.scalar(select(DeviceFeatureOverride).where(DeviceFeatureOverride.device_id==device_id,DeviceFeatureOverride.feature_id==feature.id)) or DeviceFeatureOverride(organization_id=device.customer_id,device_id=device_id,feature_id=feature.id,enabled=item.enabled);row.enabled=item.enabled;row.config_json=json.dumps(item.config,ensure_ascii=False);row.reason=item.reason;row.expires_at=item.expires_at;db.add(row)
 device.feature_config_version+=1;db.add(AuditLog(actor=admin["username"],action="update_device_features",target_type="device",target_id=device_id,details=json.dumps(payload.model_dump(mode="json"),ensure_ascii=False)));db.commit();return {"ok":True,"config_version":device.feature_config_version}
