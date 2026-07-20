from pathlib import Path

import pytest

from client_v2.credentials import CredentialStore
from client_v2.errors import AppError, normalize_error
from client_v2.models import CheckReport, CheckResult, Status
from client_v2.product import APP_VERSION, REPORT_SCHEMA_VERSION
from client_v2.regions import REGIONS
from client_v2.state import ClientState, StateMachine
from server.schemas import ReportIn


def test_single_version_and_schema_source():
    assert APP_VERSION == "2.10.0"
    assert REPORT_SCHEMA_VERSION == 6
    assert CheckReport("d", APP_VERSION, []).to_dict()["schema_version"] == REPORT_SCHEMA_VERSION


def test_state_machine_rejects_parallel_or_invalid_paths():
    machine = StateMachine()
    machine.transition(ClientState.CHECKING)
    assert machine.busy
    with pytest.raises(ValueError):
        machine.transition(ClientState.REPAIRING)
    machine.transition(ClientState.NEEDS_REPAIR)
    machine.transition(ClientState.REPAIRING)
    machine.transition(ClientState.RECHECKING)
    machine.transition(ClientState.READY)


def test_error_model_hides_technical_detail():
    error = normalize_error(RuntimeError("PowerShell secret internal detail"))
    assert error.code == "CLIENT_OPERATION_FAILED"
    assert "PowerShell" not in error.display()
    assert error.technical_detail


def test_credential_store_does_not_write_raw_token(tmp_path):
    path = tmp_path / "credentials.json"
    CredentialStore(path).save({"user_token": "TOP-SECRET-TOKEN"})
    assert "TOP-SECRET-TOKEN" not in path.read_text()
    assert CredentialStore(path).load()["user_token"] == "TOP-SECRET-TOKEN"


def test_region_dns_has_metadata_and_multiple_pairs():
    assert all(r.dns_source and r.dns_maintained_at for r in REGIONS)
    assert len({(r.preferred_dns, r.alternate_dns) for r in REGIONS}) >= 3


def test_report_round_trip_and_recheck_timestamps():
    original = CheckReport("device", APP_VERSION, [CheckResult("system.timezone", "系统环境", Status.FAIL, "时区", recheck_of="old")])
    restored = CheckReport.from_dict(original.to_dict())
    assert restored.items[0].sampled_at and restored.items[0].recheck_of == "old"


def test_schema_6_rejects_old_categories_but_schema_5_reads_them():
    base = CheckReport("device-123", APP_VERSION, [CheckResult("devices.camera", "直播设备", Status.PASS, "摄像头")]).to_dict()
    base.update({"checked_at": "2026-07-20T00:00:00+00:00", "overall_status": "PASS"})
    with pytest.raises(ValueError):
        ReportIn.model_validate(base)
    base["schema_version"] = 5
    assert ReportIn.model_validate(base).schema_version == 5


def test_cache_roots_are_specific_live_studio_temp_directories():
    from client_v2.system_repair import TIKTOK_CACHE_ROOTS
    assert {path.name for path in TIKTOK_CACHE_ROOTS} == {"Cache", "Code Cache", "GPUCache"}
    assert all("TikTok LIVE Studio" in str(path) for path in TIKTOK_CACHE_ROOTS)
