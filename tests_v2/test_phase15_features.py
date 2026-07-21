from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


def build_app(tmp_path: Path) -> TestClient:
    os.environ.update({
        "TK_DATABASE_URL": f"sqlite:///{(tmp_path / 'phase15.sqlite3').as_posix()}",
        "TK_DATA_DIR": str(tmp_path / "data"),
        "TK_ADMIN_PASSWORD": "Admin-Test-123!",
        "TK_SESSION_SECRET": "phase15-session-secret-at-least-32-chars",
        "TK_LICENSE_SECRET": "phase15-license-secret-at-least-32-chars",
    })
    for name in list(sys.modules):
        if name == "server" or name.startswith("server."):
            del sys.modules[name]
    main = importlib.import_module("server.main")
    main.migrate()
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    command.upgrade(cfg, "head")
    return TestClient(main.app)


def admin_headers(client: TestClient) -> dict:
    response = client.post("/tk-api/login", json={"username":"admin","password":"Admin-Test-123!"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf"]}


def organization_fixture(client: TestClient) -> tuple[int, dict]:
    headers = admin_headers(client)
    org = client.post("/tk-api/customer/save", headers=headers, json={"name":"Phase 1.5 企业","tenant_code":"PHASE15","plan_code":"trial","status":"active"}).json()["id"]
    member = client.post(f"/api/v2/platform/organizations/{org}/members", headers=headers, json={"username":"phase15-owner","password":"Member-Test-123!","role":"owner"})
    assert member.status_code == 200
    login = client.post("/api/v2/auth/login", json={"organization_code":"PHASE15","username":"phase15-owner","password":"Member-Test-123!"})
    assert login.status_code == 200
    return org, {"Authorization": f"Bearer {login.json()['token']}"}


def test_bootstrap_default_features_and_tenant_isolation(tmp_path):
    with build_app(tmp_path) as client:
        org, member = organization_fixture(client)
        bootstrap = client.get("/api/v2/organization/bootstrap", headers=member)
        assert bootstrap.status_code == 200
        body = bootstrap.json()
        assert body["organization"]["id"] == org
        assert body["features"]["device_binding"]["enabled"] is True
        assert body["features"]["live_data_collection"]["enabled"] is False
        assert body["organization"]["onboarding"]["total_steps"] == 7


def test_plan_organization_and_device_override_priority(tmp_path):
    with build_app(tmp_path) as client:
        org, member = organization_fixture(client)
        admin = admin_headers(client)
        plan = client.put("/api/v2/platform/plans/trial/features", headers=admin, json={"items":[{"feature_code":"live_dashboard","enabled":True,"limits":{"max_rooms":4}}]})
        assert plan.status_code == 200
        assert client.get("/api/v2/organization/bootstrap", headers=member).json()["features"]["live_dashboard"]["enabled"] is True
        disabled = client.put(f"/api/v2/platform/organizations/{org}/features", headers=admin, json={"items":[{"feature_code":"live_dashboard","enabled":False,"source":"manual"}]})
        assert disabled.status_code == 200
        assert client.get("/api/v2/organization/bootstrap", headers=member).json()["features"]["live_dashboard"]["enabled"] is False


def test_expired_organization_override_falls_back_to_plan(tmp_path):
    with build_app(tmp_path) as client:
        org, member = organization_fixture(client); admin = admin_headers(client)
        client.put("/api/v2/platform/plans/trial/features", headers=admin, json={"items":[{"feature_code":"live_dashboard","enabled":True}]})
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        response = client.put(f"/api/v2/platform/organizations/{org}/features", headers=admin, json={"items":[{"feature_code":"live_dashboard","enabled":False,"source":"trial","expires_at":expired}]})
        assert response.status_code == 200
        item = client.get("/api/v2/organization/bootstrap", headers=member).json()["features"]["live_dashboard"]
        assert item["enabled"] is True and item["reason"] == "expired"


def test_device_bootstrap_and_feature_config_version(tmp_path):
    with build_app(tmp_path) as client:
        org, _member = organization_fixture(client); admin = admin_headers(client)
        registered = client.post("/api/v1/client/register", json={"device_id":"DEVICE-PHASE15-001","app_version":"2.1.0"})
        token = registered.json()["device_token"]
        from server.database import SessionLocal
        from server.models import Device
        with SessionLocal() as db:
            device = db.get(Device, "DEVICE-PHASE15-001"); device.customer_id = org; db.commit()
        first = client.get("/api/v2/device/bootstrap", headers={"X-Device-Token":token})
        assert first.status_code == 200 and first.json()["features"]["environment_check"] is True
        version = first.json()["config_version"]
        changed = client.put("/api/v2/platform/devices/DEVICE-PHASE15-001/features", headers=admin, json={"items":[{"feature_code":"environment_repair","enabled":False,"reason":"灰度验证"}]})
        assert changed.status_code == 200 and changed.json()["config_version"] > version
        second = client.get("/api/v2/device/bootstrap", headers={"X-Device-Token":token}).json()
        assert second["features"]["environment_repair"] is False


def test_onboarding_progress_is_audited(tmp_path):
    with build_app(tmp_path) as client:
        _org, member = organization_fixture(client)
        progress = client.put("/api/v2/organization/onboarding", headers=member, json={"step":4,"completed":False})
        assert progress.status_code == 200 and progress.json()["step"] == 4
        assert client.get("/api/v2/organization/bootstrap", headers=member).json()["organization"]["onboarding"]["step"] == 4


def test_disabled_feature_cannot_be_bypassed_by_direct_api(tmp_path):
    with build_app(tmp_path) as client:
        org, member = organization_fixture(client); admin = admin_headers(client)
        room = client.post("/api/v2/organization/rooms", headers=member, json={"name":"安全校验直播间"}).json()["id"]
        registered = client.post("/api/v1/client/register", json={"device_id":"DEVICE-PHASE15-DENY","app_version":"2.1.0"}).json()
        disabled = client.put(f"/api/v2/platform/organizations/{org}/features", headers=admin, json={"items":[{"feature_code":"device_binding","enabled":False,"source":"manual"}]})
        assert disabled.status_code == 200
        response = client.put("/api/v2/device/binding", headers={**member,"X-Device-Token":registered["device_token"]}, json={"room_id":room})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


def test_minimum_version_and_zero_percent_rollout(tmp_path):
    with build_app(tmp_path) as client:
        org, member = organization_fixture(client)
        assert client.get("/api/v2/organization/bootstrap",headers=member).status_code==200
        registered = client.post("/api/v1/client/register", json={"device_id":"DEVICE-PHASE15-ROLLOUT","app_version":"2.1.0"}).json()
        from server.database import SessionLocal
        from server.models import Device
        from server.models_enterprise import FeatureDefinition, FeatureRollout
        from sqlalchemy import select
        with SessionLocal() as db:
            device = db.get(Device,"DEVICE-PHASE15-ROLLOUT");device.customer_id=org
            client_feature=db.scalar(select(FeatureDefinition).where(FeatureDefinition.feature_code=="environment_repair"));client_feature.minimum_client_version="9.0.0"
            heartbeat=db.scalar(select(FeatureDefinition).where(FeatureDefinition.feature_code=="device_heartbeat"));db.add(FeatureRollout(feature_id=heartbeat.id,rollout_type="percentage",percentage=0,status="active"));db.commit()
        bootstrap=client.get("/api/v2/device/bootstrap",headers={"X-Device-Token":registered["device_token"]}).json()
        assert bootstrap["features"]["environment_repair"] is False
        assert bootstrap["feature_details"]["environment_repair"]["reason"]=="minimum_version"
        assert bootstrap["features"]["device_heartbeat"] is False
        assert bootstrap["feature_details"]["device_heartbeat"]["reason"]=="rollout_not_selected"


def test_phase15_information_architecture_and_client_entry_contracts():
    root=Path(__file__).parents[1]
    app=(root/"admin/src/App.vue").read_text(encoding="utf-8")
    router=(root/"admin/src/router.ts").read_text(encoding="utf-8")
    sidebar=(root/"client_v2/ui/sidebar.py").read_text(encoding="utf-8")
    binding=(root/"client_v2/ui/enterprise_binding_dialog.py").read_text(encoding="utf-8")
    for label in ("工作台","直播中心","设备中心","运营分析","告警中心","组织管理","系统设置"):assert label in app
    assert "platform-overview" in router and "enterprise-dashboard" in router and "access-state" in router
    for label in ("开播准备","当前直播间","设备状态","帮助与诊断"):assert label in sidebar
    assert sidebar.count('("home"')==1 and "历史数据不会修改" in binding and "QMessageBox.question" in binding


def test_rollout_and_role_permission_update_config_version(tmp_path):
    with build_app(tmp_path) as client:
        org, member = organization_fixture(client);admin=admin_headers(client)
        bootstrap=client.get("/api/v2/organization/bootstrap",headers=member).json();version=bootstrap["config_version"]
        definitions=client.get("/api/v2/platform/features",headers=admin).json()["items"]
        feature=next(x for x in definitions if x["feature_code"]=="live_dashboard")
        rollout=client.post(f"/api/v2/platform/features/{feature['id']}/rollouts",headers=admin,json={"rollout_type":"percentage","percentage":25,"minimum_version":"2.1.0","status":"active"})
        assert rollout.status_code==200 and rollout.json()["percentage"]==25
        role=client.put(f"/api/v2/platform/organizations/{org}/roles/viewer/features",headers=admin,json={"items":[{"feature_code":"device_center","can_read":False}]})
        assert role.status_code==200 and role.json()["config_version"]>version
        items=client.get(f"/api/v2/platform/organizations/{org}/roles/viewer/features",headers=admin).json()["items"]
        assert next(x for x in items if x["feature_code"]=="device_center")["read"] is False
