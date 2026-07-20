from __future__ import annotations
import importlib,os,sys
from pathlib import Path
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

def build_v2(tmp_path:Path)->TestClient:
 os.environ.update({"TK_DATABASE_URL":f"sqlite:///{(tmp_path/'v2.sqlite3').as_posix()}","TK_DATA_DIR":str(tmp_path/'data'),"TK_ADMIN_PASSWORD":"Admin-Test-123!","TK_SESSION_SECRET":"phase01-session-secret-at-least-32-chars","TK_LICENSE_SECRET":"phase01-license-secret-at-least-32-chars"})
 for name in list(sys.modules):
  if name=="server" or name.startswith("server."):del sys.modules[name]
 main=importlib.import_module("server.main");main.migrate()
 cfg=Config(str(Path(__file__).parents[1]/"alembic.ini"));cfg.set_main_option("script_location",str(Path(__file__).parents[1]/"migrations"));command.upgrade(cfg,"head")
 return TestClient(main.app)

def admin_headers(client:TestClient)->dict:
 x=client.post("/tk-api/login",json={"username":"admin","password":"Admin-Test-123!"});assert x.status_code==200
 return {"X-CSRF-Token":x.json()["csrf"]}

def create_org_fixture(client:TestClient,name:str,member:str):
 h=admin_headers(client);org=client.post("/tk-api/customer/save",headers=h,json={"name":name,"status":"active"}).json()["id"]
 room=client.post("/tk-api/room/save",headers=h,json={"customer_id":org,"name":f"{name}-直播间","status":"active"}).json()["id"]
 member_row=client.post(f"/api/v2/platform/organizations/{org}/members",headers=h,json={"username":member,"password":"Member-Test-123!","display_name":member,"role":"owner"})
 assert member_row.status_code==200,member_row.text
 login=client.post("/api/v2/auth/login",json={"username":member,"password":"Member-Test-123!"});assert login.status_code==200
 return org,room,{"Authorization":f"Bearer {login.json()['token']}"}

def register_device(client:TestClient,device_id:str):
 x=client.post("/api/v1/client/register",json={"device_id":device_id,"app_version":"2.1.0"});assert x.status_code==200
 return {"X-Device-Token":x.json()["device_token"]}

def test_phase01_tenant_isolation_binding_history_conflicts_and_heartbeat(tmp_path):
 with build_v2(tmp_path) as client:
  org_a,room_a,member_a=create_org_fixture(client,"企业A","owner-a")
  org_b,room_b,member_b=create_org_fixture(client,"企业B","owner-b")
  device_a=register_device(client,"DEVICE-PHASE1-A001");device_a2=register_device(client,"DEVICE-PHASE1-A002")
  account=client.post("/api/v2/organization/accounts",headers=member_a,json={"display_name":"A账号","room_id":room_a}).json()["id"]
  anchor=client.post("/api/v2/organization/anchors",headers=member_a,json={"display_name":"A主播"}).json()["id"]
  bound=client.put("/api/v2/device/binding",headers={**member_a,**device_a},json={"room_id":room_a,"account_id":account,"anchor_id":anchor,"binding_type":"primary","reason":"首次绑定"})
  assert bound.status_code==200 and bound.json()["binding"]["organization_id"]==org_a
  assert client.put("/api/v2/device/binding",headers={**member_a,**device_a},json={"room_id":room_a,"account_id":account,"anchor_id":anchor}).json()["idempotent"] is True
  conflict=client.put("/api/v2/device/binding",headers={**member_a,**device_a2},json={"room_id":room_a,"binding_type":"primary"})
  assert conflict.status_code==409
  cross=client.put("/api/v2/device/binding",headers={**member_b,**device_a},json={"room_id":room_b,"binding_type":"primary"})
  assert cross.status_code==403
  options_a=client.get("/api/v2/organization/options",headers=member_a).json();assert all(x["id"]!=room_b for x in options_a["rooms"])
  binding_id=bound.json()["binding"]["id"]
  heartbeat={"device_id":"DEVICE-PHASE1-A001","binding_id":binding_id,"agent_version":"2.1.0","sent_at":"2026-07-21T08:00:00Z","uptime_seconds":7200,"status":"online","live_software":{"name":"TikTok LIVE Studio","running":True,"pid":1234},"collection":{"status":"healthy","provider":"client_agent","last_success_at":"2026-07-21T07:59:55Z"},"metrics":{"cpu_percent":42.1,"memory_percent":61.3,"network_latency_ms":48,"upload_mbps":38.2}}
  first=client.post("/api/v2/device/heartbeat",headers=device_a,json=heartbeat);second=client.post("/api/v2/device/heartbeat",headers=device_a,json=heartbeat)
  assert first.status_code==200 and first.json()["idempotent"] is False
  assert second.status_code==200 and second.json()["idempotent"] is True
  realtime=client.get("/api/v2/organization/devices",headers=member_a).json()["items"][0]
  assert realtime["online"] is True and realtime["binding"]["account_id"]==account and realtime["collection"]["status"]=="healthy"
  assert client.get("/api/v2/organization/devices",headers=member_b).json()["items"]==[]
  platform_devices=client.get(f"/api/v2/platform/devices?organization_id={org_a}",headers=admin_headers(client))
  assert platform_devices.status_code==200 and platform_devices.json()["items"][0]["device_id"]=="DEVICE-PHASE1-A001"
  unbound=client.request("DELETE","/api/v2/device/binding",headers={**member_a,**device_a},json={"reason":"更换直播间"})
  assert unbound.status_code==200 and unbound.json()["binding"]["status"]=="ended" and unbound.json()["binding"]["unbound_at"]
  assert client.get("/api/v2/device/binding",headers=device_a).json()["binding"] is None
  assert client.post("/api/v2/device/heartbeat",headers={"X-Device-Token":"invalid"},json=heartbeat).status_code==401

def test_phase01_viewer_cannot_bind(tmp_path):
 with build_v2(tmp_path) as client:
  org,room,owner=create_org_fixture(client,"只读企业","owner-view-test");h=admin_headers(client)
  created=client.post(f"/api/v2/platform/organizations/{org}/members",headers=h,json={"username":"viewer-a","password":"Member-Test-123!","role":"viewer"});assert created.status_code==200
  token=client.post("/api/v2/auth/login",json={"username":"viewer-a","password":"Member-Test-123!"}).json()["token"]
  device=register_device(client,"DEVICE-PHASE1-VIEW")
  denied=client.put("/api/v2/device/binding",headers={"Authorization":f"Bearer {token}",**device},json={"room_id":room})
  assert denied.status_code==403
  assert client.get("/api/v2/organization/members",headers={"Authorization":f"Bearer {token}"}).status_code==403

def test_phase01_member_role_audit_and_cross_tenant_update_denied(tmp_path):
 with build_v2(tmp_path) as client:
  org_a,_,owner_a=create_org_fixture(client,"成员企业A","owner-members-a")
  org_b,_,owner_b=create_org_fixture(client,"成员企业B","owner-members-b")
  h=admin_headers(client)
  created=client.post(f"/api/v2/platform/organizations/{org_a}/members",headers=h,json={"username":"operator-a","password":"Member-Test-123!","role":"operator"})
  member_id=created.json()["id"]
  updated=client.put(f"/api/v2/organization/members/{member_id}",headers=owner_a,json={"role":"viewer","active":True})
  assert updated.status_code==200 and updated.json()["role"]=="viewer"
  assert client.put(f"/api/v2/organization/members/{member_id}",headers=owner_b,json={"role":"manager","active":True}).status_code==404
  from server.database import SessionLocal
  from server.models import AuditLog
  with SessionLocal() as db:
   log=db.query(AuditLog).filter(AuditLog.action=="update_organization_member",AuditLog.target_id==str(member_id)).one()
   assert f"org:{org_a}:" in log.actor and '"role": "operator"' in log.details
