from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient


def build_client(tmp_path: Path) -> TestClient:
    os.environ.update({
        "TK_DATABASE_URL": f"sqlite:///{(tmp_path / 'platform.sqlite3').as_posix()}",
        "TK_DATA_DIR": str(tmp_path / "data"), "TK_ADMIN_PASSWORD": "Admin-Test-123!",
        "TK_SESSION_SECRET": "test-session-secret-at-least-32-characters",
        "TK_LICENSE_SECRET": "test-license-secret-at-least-32-characters",
        "TK_DEV_VERIFY_CODE": "123456",
    })
    for name in list(sys.modules):
        if name == "server" or name.startswith("server."):
            del sys.modules[name]
    module = importlib.import_module("server.main")
    return TestClient(module.app)


def register(client: TestClient, device_id: str = "DEVICE-TEST-0001") -> tuple[str, dict]:
    response = client.post("/api/v1/client/register", json={"device_id": device_id, "customer_name": "客户A", "room_name": "直播间A", "app_version": "2.1.0"})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["device_token"], {"Authorization": f"Bearer {payload['device_token']}"}


def test_client_registration_authorization_and_report(tmp_path):
    with build_client(tmp_path) as client:
        _, headers = register(client)
        assert client.get("/api/v1/client/profile", headers=headers).status_code == 200
        regions = client.get("/api/v1/client/regions").json()["regions"]
        assert len(regions) >= 12 and regions[0]["windows_timezone"]
        assert client.get("/api/v1/client/network-intelligence/status").json()["providers"]
        event = str(uuid.uuid4())
        first = client.post("/api/v1/client/authorize", headers=headers, json={"event_id": event})
        second = client.post("/api/v1/client/authorize", headers=headers, json={"event_id": event})
        assert first.json()["credits"] == 0
        assert second.json()["idempotent"] is True
        report = {
            "report_id": str(uuid.uuid4()), "customer_name": "客户A", "room_name": "直播间A",
            "app_version": "2.1.0", "checked_at": "2026-07-14T00:00:00+00:00",
            "overall_status": "PASS", "conclusion": "可以开播",
            "schema_version": 4, "run_mode": "environment_setup", "target_region_id": "us-los-angeles",
            "network_snapshot": {"upload_mbps": 20}, "ip_profile": {"ip": "1.2.3.4"},
            "environment_snapshot": {"system.timezone": {"value": "Pacific Standard Time"}},
            "before_snapshot": {"timezone": "China Standard Time"}, "after_snapshot": {"timezone": "Pacific Standard Time"},
            "check_logs": [{"event": "check_started", "module": "core", "message": "开始", "level": "info"}],
            "confidence_summary": {"high": 1},
            "items": [{"check_id": "network.dns", "category": "网络", "status": "PASS", "title": "DNS", "evidence": ["42 ms"], "metrics": {"latency": 42}, "diagnosis": "正常", "impact": "无", "solutions": [], "data_source": "test", "confidence": "high", "duration_ms": 42}],
        }
        assert client.post("/api/v1/client/reports", headers=headers, json=report).status_code == 200
        detail = client.get(f"/tk-api/report/{report['report_id']}")
        assert detail.status_code == 401
        duplicate = client.post("/api/v1/client/reports", headers=headers, json=report).json()
        assert duplicate["idempotent"] is True
        csrf = admin_login(client)
        detail = client.get(f"/tk-api/report/{report['report_id']}").json()["report"]
        assert detail["run_mode"] == "environment_setup"
        assert detail["before_snapshot"]["timezone"] == "China Standard Time"
        assert client.get("/tk-api/setup-reports").json()["reports"][0]["report_id"] == report["report_id"]
        assert client.get("/tk-api/nodes/status").json()["nodes"]


def test_user_registration_requires_a_valid_email_code(tmp_path):
    with build_client(tmp_path) as client:
        email = "customer@example.com"
        sent = client.post("/api/v1/client/auth/send-code", json={"target": email, "purpose": "register"})
        assert sent.status_code == 200 and sent.json()["dev_code"] == "123456"
        payload = {"phone": "13800138000", "phone_country": "CN", "password": "StrongPass123", "password_confirm": "StrongPass123", "email": email, "code": "000000"}
        assert client.post("/api/v1/client/auth/register", json=payload).status_code == 400
        payload["code"] = "123456"
        registered = client.post("/api/v1/client/auth/register", json=payload)
        assert registered.status_code == 200 and registered.json()["token"]
        assert client.post("/api/v1/client/auth/register", json=payload).status_code == 409


def test_admin_csrf_codes_and_audit(tmp_path):
    with build_client(tmp_path) as client:
        denied = client.post("/tk-api/codes/generate", json={"tier": "TK1", "count": 1})
        assert denied.status_code == 401
        login = client.post("/tk-api/login", json={"username": "admin", "password": "Admin-Test-123!"})
        assert login.status_code == 200, login.text
        csrf = login.json()["csrf"]
        blocked = client.post("/tk-api/codes/generate", json={"tier": "TKX", "count": 2})
        assert blocked.status_code == 403
        generated = client.post("/tk-api/codes/generate", headers={"X-CSRF-Token": csrf}, json={"tier": "TKX", "count": 2, "batch": "测试批次"})
        assert generated.status_code == 200, generated.text
        assert len(generated.json()["codes"]) == 2
        assert client.get("/tk-api/audit").json()["audit"]


def admin_login(client: TestClient) -> str:
    response = client.post("/tk-api/login", json={"username": "admin", "password": "Admin-Test-123!"})
    assert response.status_code == 200
    return response.json()["csrf"]


def test_admin_customer_room_settings_and_exports(tmp_path):
    with build_client(tmp_path) as client:
        csrf = admin_login(client); headers = {"X-CSRF-Token": csrf}
        customer = client.post("/tk-api/customer/save", headers=headers, json={"name": "产品客户", "contact": "13800000000", "notes": "重点", "status": "active"})
        assert customer.status_code == 200
        customer_id = customer.json()["id"]
        room = client.post("/tk-api/room/save", headers=headers, json={"customer_id": customer_id, "name": "直播间一", "region": "US-Los Angeles", "bitrate_kbps": 6000, "status": "active"})
        assert room.status_code == 200
        assert client.get("/tk-api/customers?q=产品").json()["customers"][0]["room_count"] == 1
        assert client.get("/tk-api/rooms?q=直播间").json()["rooms"][0]["customer"] == "产品客户"
        saved = client.post("/tk-api/settings", headers=headers, json={"values": {"product_intro": "新的产品介绍"}})
        assert saved.status_code == 200
        assert client.get("/tk-api/settings").json()["product_intro"] == "新的产品介绍"
        assert client.get("/tk-api/codes/export").status_code == 200
        assert client.get("/tk-api/reports/export").status_code == 200
        _, _headers = register(client, "DEVICE-MANAGE-0001")
        updated = client.post("/tk-api/device/save", headers=headers, json={"device_id": "DEVICE-MANAGE-0001", "customer_id": customer_id, "room_id": room.json()["id"], "status": "inactive", "notes": "测试停用", "unbind_license": False})
        assert updated.status_code == 200
        assert client.get("/tk-api/devices?q=MANAGE").json()["devices"][0]["status"] == "inactive"
        support = client.post("/tk-api/support/save", headers=headers, json={"device_id": "DEVICE-MANAGE-0001", "title": "网络不稳定", "status": "processing", "owner": "技术A", "notes": "已切换线路"})
        assert support.status_code == 200
        assert client.get("/tk-api/support?status=processing").json()["support"][0]["owner"] == "技术A"
        profile = client.get("/tk-api/profile").json()["profile"]
        profile["rules"]["packet_loss_warning"] = 1.5
        saved_profile = client.post("/tk-api/profile", headers=headers, json={"name": "试点规则", "region": "*", "bitrate_kbps": 6000, "rules": profile["rules"]})
        assert saved_profile.status_code == 200
        assert client.get("/tk-api/profile").json()["profile"]["name"] == "试点规则"


def test_paid_activation_release_manifest_and_update_compatibility(tmp_path):
    with build_client(tmp_path) as client:
        csrf = admin_login(client); admin_headers = {"X-CSRF-Token": csrf}
        generated = client.post("/tk-api/codes/generate", headers=admin_headers, json={"tier": "TKX", "count": 1, "note": "付费客户"}).json()["codes"][0]
        _, device_headers = register(client, "DEVICE-PAID-0001")
        activated = client.post("/api/client/activate", headers=device_headers, json={"code": generated})
        assert activated.status_code == 200
        assert activated.json()["license"]["tier"] == "TKX"
        for index in range(3):
            response = client.post("/api/client/authorize-check", headers=device_headers, json={"event_id": f"EVENT-PAID-{index:04d}"})
            assert response.status_code == 200
        installer = b"MZ" + b"candidate-installer" * 100
        published = client.post("/tk-api/release", headers=admin_headers, data={"version": "2.2.0", "title": "候选版", "notes": "摘要", "details": "完整更新说明", "channel": "stable", "minimum_version": "2.1.0"}, files={"file": ("setup.exe", installer, "application/octet-stream")})
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "pending"
        assert client.post("/tk-api/release/activate", headers=admin_headers, json={"version": "2.2.0"}).status_code == 200
        manifest = client.get("/api/v1/client/update").json()
        assert manifest["version"] == "2.2.0"
        assert manifest["file_size"] == len(installer)
        assert len(manifest["sha256"]) == 64
        assert client.get(f"/downloads/{manifest['filename']}").content == installer
        second = client.post("/tk-api/release", headers=admin_headers, data={"version": "2.3.0", "title": "下一版", "notes": "摘要二", "details": "完整更新说明二", "channel": "stable"}, files={"file": ("setup.exe", installer + b"2", "application/octet-stream")})
        assert second.status_code == 200
        rolled_back = client.post("/tk-api/release/activate", headers=admin_headers, json={"version": "2.2.0"})
        assert rolled_back.status_code == 200
        assert client.get("/api/v1/client/update").json()["version"] == "2.2.0"


def test_time_plan_authorization_is_unlimited_with_expiry(tmp_path):
    with build_client(tmp_path) as client:
        csrf = admin_login(client)
        generated = client.post("/tk-api/codes/generate", headers={"X-CSRF-Token": csrf}, json={"tier": "TK-MONTH", "count": 1}).json()["codes"][0]
        _, device_headers = register(client, "DEVICE-TIME-0001")
        activated = client.post("/api/v1/client/activate", headers=device_headers, json={"code": generated})
        assert activated.status_code == 200
        license_data = activated.json()["license"]
        assert license_data["plan_code"] == "TK-MONTH"
        assert license_data["expires_at"]
        for index in range(5):
            response = client.post("/api/v1/client/authorize", headers=device_headers, json={"event_id": f"EVENT-TIME-{index:04d}"})
            assert response.status_code == 200


def test_public_download_page(tmp_path):
    with build_client(tmp_path) as client:
        page = client.get("/download/")
        assert page.status_code == 200
        assert page.history and page.history[0].status_code == 308
        assert "开播前" in page.text
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ok"


def test_admin_password_reset_utility(tmp_path):
    with build_client(tmp_path) as client:
        manage = importlib.import_module("server.manage")
        manage.reset_admin_password("admin", "New-Admin-Password-123")
        response = client.post("/tk-api/login", json={"username": "admin", "password": "New-Admin-Password-123"})
        assert response.status_code == 200
