from __future__ import annotations

from sqlalchemy import select

from test_phase01_enterprise import create_org_fixture, register_device
from test_phase15_features import admin_headers, build_app, organization_fixture


def test_enterprise_device_detail_binding_and_reports_are_tenant_isolated(tmp_path):
    with build_app(tmp_path) as client:
        org_a, room_a, owner_a = create_org_fixture(client, "详情企业 A", "detail-owner-a")
        _org_b, _room_b, owner_b = create_org_fixture(client, "详情企业 B", "detail-owner-b")
        device_headers = register_device(client, "DEVICE-DETAIL-001")

        bound = client.put(
            "/api/v2/organization/devices/DEVICE-DETAIL-001/binding",
            headers=owner_a,
            json={"room_id": room_a, "reason": "企业后台首次绑定"},
        )
        assert bound.status_code == 200, bound.text

        heartbeat = {
            "device_id": "DEVICE-DETAIL-001",
            "binding_id": bound.json()["binding"]["id"],
            "agent_version": "2.1.0",
            "sent_at": "2026-07-21T08:00:00Z",
            "uptime_seconds": 900,
            "status": "online",
            "live_software": {"name": "TikTok LIVE Studio", "running": True, "pid": 2026},
            "collection": {"status": "healthy", "provider": "client_agent", "last_success_at": "2026-07-21T07:59:58Z"},
            "metrics": {"cpu_percent": 35, "memory_percent": 52, "network_latency_ms": 36, "upload_mbps": 25},
        }
        assert client.post("/api/v2/device/heartbeat", headers=device_headers, json=heartbeat).status_code == 200

        from server.database import SessionLocal
        from server.models import CheckReport

        with SessionLocal() as db:
            db.add(
                CheckReport(
                    report_id="REPORT-DETAIL-001",
                    device_id="DEVICE-DETAIL-001",
                    checked_at="2026-07-21T08:01:00+00:00",
                    overall_status="PASS",
                    readiness_level="READY",
                    conclusion="可以开播",
                    target_region_id="us-los-angeles",
                    environment_summary="系统环境正常",
                    network_summary="网络稳定",
                    hardware_summary="性能满足直播要求",
                )
            )
            db.commit()

        detail = client.get("/api/v2/organization/devices/DEVICE-DETAIL-001", headers=owner_a)
        assert detail.status_code == 200
        assert detail.json()["binding"]["room_id"] == room_a
        assert detail.json()["metrics_60m"]
        assert client.get("/api/v2/organization/devices/DEVICE-DETAIL-001", headers=owner_b).status_code == 404

        reports = client.get("/api/v2/organization/reports", headers=owner_a)
        assert reports.status_code == 200 and reports.json()["items"][0]["report_id"] == "REPORT-DETAIL-001"
        report = client.get("/api/v2/organization/reports/REPORT-DETAIL-001", headers=owner_a)
        assert report.status_code == 200 and report.json()["report"]["conclusion"] == "可以开播"
        assert client.get("/api/v2/organization/reports/REPORT-DETAIL-001", headers=owner_b).status_code == 404

        unbound = client.request(
            "DELETE",
            "/api/v2/organization/devices/DEVICE-DETAIL-001/binding",
            headers=owner_a,
            json={"reason": "企业后台确认解绑"},
        )
        assert unbound.status_code == 200 and unbound.json()["binding"]["status"] == "ended"


def test_enterprise_member_settings_and_audit_workflow(tmp_path):
    with build_app(tmp_path) as client:
        organization_id, owner_headers = organization_fixture(client)
        created = client.post(
            "/api/v2/organization/members",
            headers=owner_headers,
            json={"username": "operations-user", "password": "Member-Test-123!", "display_name": "值班运维", "role": "operator"},
        )
        assert created.status_code == 200, created.text
        member_id = created.json()["id"]
        duplicate = client.post(
            "/api/v2/organization/members",
            headers=owner_headers,
            json={"username": "operations-user", "password": "Member-Test-123!", "role": "viewer"},
        )
        assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "MEMBER_EXISTS"

        updated = client.put(
            "/api/v2/organization/settings",
            headers=owner_headers,
            json={"name": "Phase 1.5 企业升级版", "short_name": "VD 企业", "contact": "support@example.test", "timezone": "Asia/Shanghai"},
        )
        assert updated.status_code == 200 and updated.json()["config_version"] > 0
        settings = client.get("/api/v2/organization/settings", headers=owner_headers).json()
        assert settings["organization"]["id"] == organization_id
        assert settings["organization"]["short_name"] == "VD 企业"

        audit = client.get("/api/v2/organization/audit", headers=owner_headers).json()["items"]
        assert any(item["action"] == "create_organization_member" and item["target_id"] == str(member_id) for item in audit)
        assert any(item["action"] == "update_organization_settings" for item in audit)


def test_platform_override_clear_and_role_reset_refresh_config_versions(tmp_path):
    with build_app(tmp_path) as client:
        organization_id, _owner_headers = organization_fixture(client)
        headers = admin_headers(client)
        registered = client.post("/api/v1/client/register", json={"device_id": "DEVICE-CLEAR-001", "app_version": "2.1.0"}).json()

        from server.database import SessionLocal
        from server.models import Device

        with SessionLocal() as db:
            device = db.get(Device, "DEVICE-CLEAR-001")
            device.customer_id = organization_id
            db.commit()

        assert client.put(
            "/api/v2/platform/plans/trial/features",
            headers=headers,
            json={"items": [{"feature_code": "live_dashboard", "enabled": True, "source": "plan"}]},
        ).status_code == 200
        assert client.request("DELETE", "/api/v2/platform/plans/trial/features/live_dashboard", headers=headers).status_code == 200

        assert client.put(
            f"/api/v2/platform/organizations/{organization_id}/features",
            headers=headers,
            json={"items": [{"feature_code": "live_dashboard", "enabled": True, "source": "trial"}]},
        ).status_code == 200
        assert client.request("DELETE", f"/api/v2/platform/organizations/{organization_id}/features/live_dashboard", headers=headers).status_code == 200

        assert client.put(
            "/api/v2/platform/devices/DEVICE-CLEAR-001/features",
            headers=headers,
            json={"items": [{"feature_code": "device_center", "enabled": False, "reason": "回退测试"}]},
        ).status_code == 200
        assert client.request("DELETE", "/api/v2/platform/devices/DEVICE-CLEAR-001/features/device_center", headers=headers).status_code == 200

        assert client.put(
            f"/api/v2/platform/organizations/{organization_id}/roles/viewer/features",
            headers=headers,
            json={"items": [{"feature_code": "device_center", "can_read": False}]},
        ).status_code == 200
        reset = client.request("DELETE", f"/api/v2/platform/organizations/{organization_id}/roles/viewer/features", headers=headers)
        assert reset.status_code == 200

        from server.models_enterprise import DeviceFeatureOverride, OrganizationFeature, PlanFeature, RoleFeaturePermission

        with SessionLocal() as db:
            assert db.scalars(select(PlanFeature).where(PlanFeature.plan_id == "trial")).all() == []
            assert db.scalars(select(OrganizationFeature).where(OrganizationFeature.organization_id == organization_id)).all() == []
            assert db.scalars(select(DeviceFeatureOverride).where(DeviceFeatureOverride.device_id == "DEVICE-CLEAR-001")).all() == []
            assert db.scalars(select(RoleFeaturePermission).where(RoleFeaturePermission.organization_id == organization_id, RoleFeaturePermission.role == "viewer")).all() == []

        bootstrap = client.get("/api/v2/device/bootstrap", headers={"X-Device-Token": registered["device_token"]})
        assert bootstrap.status_code == 200 and bootstrap.json()["config_version"] > 0
