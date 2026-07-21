from __future__ import annotations
from datetime import datetime
from typing import Any,Literal
from pydantic import BaseModel,Field

class MemberLoginIn(BaseModel):
    username:str=Field(min_length=3,max_length=80)
    password:str=Field(min_length=8,max_length=256)
    organization_code:str|None=Field(default=None,min_length=2,max_length=40)
class MemberCreateIn(BaseModel):username:str=Field(min_length=3,max_length=80);password:str=Field(min_length=8,max_length=256);display_name:str=Field(default="",max_length=80);role:Literal["owner","manager","operator","viewer"]="viewer"
class MemberRoleUpdateIn(BaseModel):role:Literal["owner","manager","operator","viewer"];active:bool=True
class OrganizationProfileIn(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    short_name:str=Field(default="",max_length=80)
    contact:str=Field(default="",max_length=160)
    timezone:str=Field(default="Asia/Shanghai",max_length=80)
class AccountCreateIn(BaseModel):display_name:str=Field(min_length=1,max_length=120);room_id:int|None=None;platform_account_ref:str=Field(default="",max_length=160);target_region_id:str=Field(default="us-los-angeles",max_length=80)
class AnchorCreateIn(BaseModel):display_name:str=Field(min_length=1,max_length=120);employee_ref:str=Field(default="",max_length=80)
class RoomCreateIn(BaseModel):name:str=Field(min_length=1,max_length=120);region:str=Field(default="",max_length=80)
class BindingPutIn(BaseModel):room_id:int;account_id:int|None=None;anchor_id:int|None=None;binding_type:Literal["primary","backup","temporary"]="primary";reason:str=Field(default="",max_length=1000)
class BindingDeleteIn(BaseModel):reason:str=Field(min_length=1,max_length=1000)
class LiveSoftware(BaseModel):name:str=Field(max_length=80);running:bool;pid:int|None=Field(default=None,ge=1)
class CollectionHealth(BaseModel):status:Literal["healthy","degraded","offline","unknown"]="unknown";provider:str=Field(default="client_agent",max_length=80);last_success_at:datetime|None=None
class HeartbeatMetrics(BaseModel):cpu_percent:float|None=Field(default=None,ge=0,le=100);memory_percent:float|None=Field(default=None,ge=0,le=100);network_latency_ms:float|None=Field(default=None,ge=0);upload_mbps:float|None=Field(default=None,ge=0);stream_bitrate_kbps:float|None=Field(default=None,ge=0);dropped_frames:int|None=Field(default=None,ge=0)
class HeartbeatIn(BaseModel):device_id:str=Field(min_length=8,max_length=80);binding_id:int|None=None;agent_version:str=Field(max_length=40);sent_at:datetime;uptime_seconds:int=Field(ge=0);status:Literal["online","idle","busy","degraded"]="online";live_software:LiveSoftware;collection:CollectionHealth;metrics:HeartbeatMetrics=Field(default_factory=HeartbeatMetrics)

class FeatureDefinitionIn(BaseModel):
    feature_code:str=Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    feature_name:str=Field(min_length=1,max_length=120)
    category:str=Field(min_length=1,max_length=60)
    description:str=Field(default="",max_length=2000)
    client_type:Literal["platform_admin","enterprise_admin","windows_client","api","all"]="all"
    default_enabled:bool=False
    status:Literal["disabled","internal","beta","enabled","deprecated"]="internal"
    minimum_client_version:str=Field(default="",max_length=40)
    config_schema:dict[str,Any]=Field(default_factory=dict)

class FeatureAssignmentIn(BaseModel):
    feature_code:str=Field(min_length=3,max_length=80)
    enabled:bool
    limits:dict[str,Any]=Field(default_factory=dict)
    config:dict[str,Any]=Field(default_factory=dict)
    source:Literal["plan","manual","trial","promotion","system"]="manual"
    starts_at:datetime|None=None
    expires_at:datetime|None=None
    reason:str=Field(default="",max_length=1000)

class FeatureAssignmentsIn(BaseModel):items:list[FeatureAssignmentIn]

class OnboardingProgressIn(BaseModel):
    step:int=Field(ge=1,le=7)
    completed:bool=False

class RoleFeaturePermissionIn(BaseModel):
    feature_code:str=Field(min_length=3,max_length=80)
    can_read:bool=True
    can_create:bool=False
    can_update:bool=False
    can_delete:bool=False
    can_manage:bool=False

class RoleFeaturePermissionsIn(BaseModel):items:list[RoleFeaturePermissionIn]

class FeatureRolloutIn(BaseModel):
    rollout_type:Literal["all","percentage","organizations","devices","internal"]="percentage"
    percentage:int=Field(default=0,ge=0,le=100)
    organization_ids:list[int]=Field(default_factory=list)
    device_ids:list[str]=Field(default_factory=list)
    minimum_version:str=Field(default="",max_length=40)
    starts_at:datetime|None=None
    ends_at:datetime|None=None
    status:Literal["active","paused","ended"]="active"
