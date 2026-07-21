from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import event, select

from test_phase01_enterprise import create_org_fixture, register_device
from test_phase15_features import admin_headers, build_app, organization_fixture


def test_v2_errors_always_include_request_id_and_details(tmp_path):
    with build_app(tmp_path) as client:
        response = client.post(
            "/api/v2/auth/login",
            headers={"X-Request-ID": "req_contract_test"},
            json={"username": "missing-user", "password": "Wrong-Pass-123!"},
        )
        assert response.status_code == 401
        assert response.headers["X-Request-ID"] == "req_contract_test"
        assert response.json() == {
            "error": {
                "code": "AUTH_INVALID",
                "message": "账号或密码错误",
                "details": {},
                "request_id": "req_contract_test",
            }
        }
        _organization_id, member_headers = organization_fixture(client)
        invalid = client.get("/api/v2/organization/devices?limit=0", headers=member_headers)
        assert invalid.status_code == 422
        error = invalid.json()["error"]
        assert error["code"] == "VALIDATION_ERROR" and error["request_id"].startswith("req_")


def test_realtime_devices_has_fixed_query_count_and_complete_filters(tmp_path):
    with build_app(tmp_path) as client:
        organization_id, member_headers = organization_fixture(client)
        from server.database import SessionLocal, engine
        from server.enterprise.common import token_hash
        from server.models import Device

        now = datetime.now(timezone.utc).isoformat()
        with SessionLocal() as db:
            for index in range(200):
                db.add(
                    Device(
                        device_id=f"DEVICE-QUERY-{index:04d}",
                        token_hash=token_hash(f"query-token-{index}"),
                        customer_id=organization_id,
                        display_name=f"直播电脑 {index:03d}",
                        app_version="2.1.0" if index % 2 == 0 else "2.0.9",
                        last_heartbeat_at=now if index < 150 else None,
                        collector_state="healthy" if index % 3 else "degraded",
                        studio_state="running" if index % 4 else "not_running",
                        cpu_percent=float(index % 100),
                    )
                )
            db.commit()

        statements: list[str] = []

        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            response = client.get(
                "/api/v2/organization/devices",
                headers=member_headers,
                params={
                    "agent_version": "2.1.0",
                    "collector_state": "healthy",
                    "studio_state": "running",
                    "keyword": "直播电脑",
                    "sort": "cpu_percent",
                    "order": "desc",
                    "limit": 25,
                },
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["items"]) <= 25
        assert body["pagination"]["total"] >= len(body["items"])
        assert len(statements) <= 4, "查询数不应随设备数量增长"
        assert all(item["agent_version"] == "2.1.0" for item in body["items"])
        assert all(item["collector_state"] == "healthy" for item in body["items"])
        assert all(item["studio_state"] == "running" for item in body["items"])
        assert all("abnormal_reasons" in item and "room" in item and "account" in item and "anchor" in item for item in body["items"])


def test_failed_rebind_preserves_active_history_and_legacy_room(tmp_path):
    with build_app(tmp_path) as client:
        organization_id, first_room_id, member_headers = create_org_fixture(client, "换绑事务企业", "rebind-owner")
        second_room_id = client.post("/api/v2/organization/rooms", headers=member_headers, json={"name": "第二直播间"}).json()["id"]
        device_headers = register_device(client, "DEVICE-REBIND-001")
        account_id = client.post(
            "/api/v2/organization/accounts",
            headers=member_headers,
            json={"display_name": "仅限第一直播间的账号", "room_id": first_room_id},
        ).json()["id"]
        first = client.put(
            "/api/v2/device/binding",
            headers={**member_headers, **device_headers},
            json={"room_id": first_room_id, "account_id": account_id, "reason": "首次绑定"},
        )
        assert first.status_code == 200

        failed = client.put(
            "/api/v2/device/binding",
            headers={**member_headers, **device_headers},
            json={"room_id": second_room_id, "account_id": account_id, "reason": "不合法换绑"},
        )
        assert failed.status_code == 409
        assert failed.json()["error"]["code"] == "ACCOUNT_ROOM_MISMATCH"

        from server.database import SessionLocal
        from server.models import AuditLog, Device
        from server.models_enterprise import DeviceRoomBinding

        with SessionLocal() as db:
            active = db.scalars(
                select(DeviceRoomBinding).where(
                    DeviceRoomBinding.device_id == "DEVICE-REBIND-001",
                    DeviceRoomBinding.status == "active",
                    DeviceRoomBinding.binding_type == "primary",
                )
            ).all()
            device = db.get(Device, "DEVICE-REBIND-001")
            failed_success_audit = db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "bind_device_room",
                    AuditLog.details.contains("不合法换绑"),
                )
            ).all()
            assert len(active) == 1 and active[0].room_id == first_room_id
            assert device.room_id == first_room_id
            assert failed_success_audit == []


def test_feature_action_role_matrix(tmp_path):
    with build_app(tmp_path) as client:
        organization_id, owner_headers = organization_fixture(client)
        platform_headers = admin_headers(client)
        expected = {
            "owner": (200, 200),
            "manager": (200, 200),
            "operator": (403, 200),
            "viewer": (403, 200),
        }
        for role, (create_status, read_status) in expected.items():
            username = f"matrix-{role}"
            if role != "owner":
                created = client.post(
                    f"/api/v2/platform/organizations/{organization_id}/members",
                    headers=platform_headers,
                    json={"username": username, "password": "Member-Test-123!", "role": role},
                )
                assert created.status_code == 200
                login = client.post(
                    "/api/v2/auth/login",
                    json={"organization_code": "PHASE15", "username": username, "password": "Member-Test-123!"},
                )
                headers = {"Authorization": f"Bearer {login.json()['token']}"}
            else:
                headers = owner_headers
            assert client.post("/api/v2/organization/rooms", headers=headers, json={"name": f"{role} 新建直播间"}).status_code == create_status
            assert client.get("/api/v2/organization/devices", headers=headers).status_code == read_status


def test_feature_priority_matrix_has_one_deterministic_result(tmp_path):
    with build_app(tmp_path) as client:
        organization_id, member_headers = organization_fixture(client)
        assert client.get("/api/v2/organization/bootstrap", headers=member_headers).status_code == 200
        client.post("/api/v1/client/register", json={"device_id": "DEVICE-PRIORITY-MATRIX", "app_version": "2.1.0"})

        from server.database import SessionLocal
        from server.enterprise.features import FeatureService
        from server.models import Device
        from server.models_enterprise import (
            DeviceFeatureOverride,
            FeatureDefinition,
            FeatureRollout,
            OrganizationFeature,
            PlanFeature,
            RoleFeaturePermission,
        )

        with SessionLocal() as db:
            device = db.get(Device, "DEVICE-PRIORITY-MATRIX")
            device.customer_id = organization_id
            feature = db.scalar(select(FeatureDefinition).where(FeatureDefinition.feature_code == "live_dashboard"))
            feature.status = "enabled"
            feature.default_enabled = False
            feature.minimum_client_version = ""
            rollout = FeatureRollout(feature_id=feature.id, rollout_type="percentage", percentage=0, status="active")
            db.add(rollout)
            db.commit()
            service = FeatureService(db, organization_id)
            item = service.get_effective_features_for_device(device, "2.1.0")["live_dashboard"]
            assert item["enabled"] is False and item["source"] == "rollout" and item["reason"] == "rollout_not_selected"

            plan = PlanFeature(plan_id="trial", feature_id=feature.id, enabled=True)
            db.add(plan); db.commit()
            item = service.get_effective_features_for_device(device, "2.1.0")["live_dashboard"]
            assert item["enabled"] is True and item["source"] == "plan"

            organization_override = OrganizationFeature(organization_id=organization_id, feature_id=feature.id, enabled=False, source="manual")
            db.add(organization_override); db.commit()
            item = service.get_effective_features_for_device(device, "2.1.0")["live_dashboard"]
            assert item["enabled"] is False and item["source"] == "manual"

            device_override = DeviceFeatureOverride(organization_id=organization_id, device_id=device.device_id, feature_id=feature.id, enabled=True, reason="priority test")
            db.add(device_override); db.commit()
            item = service.get_effective_features_for_device(device, "2.1.0")["live_dashboard"]
            assert item["enabled"] is True and item["source"] == "device"

            feature.status = "disabled"; db.commit()
            item = service.get_effective_features_for_device(device, "2.1.0")["live_dashboard"]
            assert item["enabled"] is False and item["reason"] == "feature_disabled"

            feature.status = "enabled"; feature.minimum_client_version = "9.0.0"; db.commit()
            item = service.get_effective_features_for_device(device, "2.1.0")["live_dashboard"]
            assert item["enabled"] is False and item["reason"] == "minimum_version"

            feature.minimum_client_version = ""
            device_override.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            organization_override.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
            item = service.get_effective_features_for_device(device, "2.1.0")["live_dashboard"]
            assert item["enabled"] is True and item["source"] == "plan" and item["reason"] == "expired"

            role_rule = RoleFeaturePermission(organization_id=organization_id, role="viewer", feature_id=feature.id, can_read=False)
            db.add(role_rule); db.commit()
            item = service.get_effective_features_for_organization("viewer", "2.1.0")["live_dashboard"]
            assert item["enabled"] is False and item["reason"] == "role_forbidden"


def test_client_runtime_settings_change_bootstrap_version(tmp_path):
    with build_app(tmp_path) as client:
        organization_id, _member_headers = organization_fixture(client)
        platform_headers = admin_headers(client)
        registered = client.post("/api/v1/client/register", json={"device_id": "DEVICE-CONFIG-VERSION", "app_version": "2.1.0"}).json()
        from server.database import SessionLocal
        from server.models import Device

        with SessionLocal() as db:
            device = db.get(Device, "DEVICE-CONFIG-VERSION")
            device.customer_id = organization_id
            db.commit()
        headers = {"X-Device-Token": registered["device_token"]}
        before = client.get("/api/v2/device/bootstrap", headers=headers).json()
        changed = client.post(
            "/tk-api/settings",
            headers=platform_headers,
            json={"values": {"heartbeat_interval_seconds": "33", "minimum_client_version": "2.2.0"}},
        )
        assert changed.status_code == 200
        after = client.get("/api/v2/device/bootstrap", headers=headers).json()
        assert after["config_version"] > before["config_version"]
        assert after["config"]["heartbeat_interval_seconds"] == 33
        assert after["minimum_version"] == "2.2.0"
