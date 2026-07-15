from __future__ import annotations

from pathlib import Path
import threading

from client_v2.checks import CheckContext, CheckPlugin, DEFAULT_PROFILE, run_checks
from client_v2.environment_setup import SetupAction, capture_environment_snapshot, execute_setup_action, new_setup_record, planned_actions
from client_v2.events import CheckEvent, emit
from client_v2.models import CheckReport, CheckResult, Status
from client_v2.regions import get_region


def test_setup_plan_separates_safe_and_confirm_actions():
    snapshot = {
        "timezone": "China Standard Time", "culture": "zh-CN", "system_locale": "zh-CN",
        "dns_servers": "1.1.1.1", "tiktok_processes": ["obs64"],
        "cache_inventory": [{"path": "C:/Temp/Cache", "files": 4, "bytes": 100}],
    }
    actions = planned_actions(snapshot, get_region("us-los-angeles"))
    by_id = {item.action_id: item for item in actions}
    assert by_id["reset_network_cache"].level == "safe"
    assert by_id["set_target_timezone"].level == "confirm"
    assert by_id["close_tiktok_processes"].level == "confirm"
    assert all(item.action_id not in {"disable_defender", "delete_registry"} for item in actions)


def test_v4_environment_report_contract():
    event = CheckEvent("module_started", "network", "正在测试", "info", 10)
    report = CheckReport(
        "device", "2.4.0", [CheckResult("network.public_ip", "网络环境", Status.WARNING, "IP 地区")],
        run_mode="environment_setup", before_snapshot={"timezone": "A"}, after_snapshot={"timezone": "B"},
        check_logs=[event.to_dict()],
    )
    report.finalize()
    payload = report.to_dict()
    assert payload["schema_version"] == 5
    assert payload["run_mode"] == "environment_setup"
    assert payload["before_snapshot"]["timezone"] == "A"
    assert payload["check_logs"][0]["module"] == "network"


def test_all_regions_have_three_probes():
    from client_v2.regions import REGIONS
    assert len(REGIONS) == 12
    assert all(len(region.probes) >= 3 for region in REGIONS)


def test_event_sink_and_plugin_runner(monkeypatch):
    events = []
    emit(events.append, "check_started", "core", "开始", progress=1)
    assert events[0].message == "开始"
    plugin = CheckPlugin("demo", "演示模块", 2, lambda _ctx: [CheckResult("demo.ok", "演示", Status.PASS, "完成", "42")])
    monkeypatch.setattr("client_v2.checks.PLUGINS", [plugin])
    context = CheckContext(dict(DEFAULT_PROFILE), get_region("us-los-angeles"), "example.com", object(), Path("."), "2.4.0", True, threading.Event(), events.append)
    rows = run_checks(context, lambda *_args: None)
    assert rows[0].duration_ms >= 0
    assert any(event.event == "module_finished" for event in events)
    assert events[-1].event == "check_finished"


def test_capture_snapshot_and_setup_record(tmp_path, monkeypatch):
    monkeypatch.setattr("client_v2.environment_setup._safe_ps", lambda script: "value")
    monkeypatch.setattr("client_v2.environment_setup._process_names", lambda: ["obs64"])
    monkeypatch.setattr("client_v2.environment_setup._cache_inventory", lambda: [{"path": "cache", "files": 1, "bytes": 10}])
    monkeypatch.setattr("client_v2.environment_setup.discover_streaming_profiles", lambda: [{"software": "OBS"}])
    (tmp_path / "app_icon.ico").write_bytes(b"ico")
    snapshot = capture_environment_snapshot(get_region("us-los-angeles"), tmp_path)
    assert snapshot["tiktok_processes"] == ["obs64"]
    assert snapshot["streaming_profiles"][0]["software"] == "OBS"
    record = new_setup_record("device", get_region("us-los-angeles"), snapshot)
    assert record["status"] == "running" and record["before_snapshot"] == snapshot


def test_execute_setup_actions_and_failures(tmp_path, monkeypatch):
    region = get_region("us-los-angeles")
    monkeypatch.setattr("client_v2.environment_setup.run_repair", lambda *_args, **_kwargs: (True, "已处理", {"before": "old"}))
    safe = execute_setup_action(SetupAction("sync_time", "同步时间", "safe"), region)
    assert safe.status == "success" and safe.recovery["before"] == "old"
    calls = []
    monkeypatch.setattr("client_v2.environment_setup.powershell", lambda script, *args: calls.append(script) or "ok")
    monkeypatch.setattr("client_v2.environment_setup._safe_ps", lambda _script: "old")
    monkeypatch.setattr("client_v2.environment_setup._process_names", lambda: ["obs64"])
    for action_id in ("set_culture", "set_system_locale", "close_tiktok_processes"):
        result = execute_setup_action(SetupAction(action_id, action_id, "confirm"), region)
        assert result.status == "success"
    cache = tmp_path / "Cache"
    cache.mkdir()
    (cache / "temporary.bin").write_bytes(b"123")
    monkeypatch.setattr("client_v2.environment_setup._cache_inventory", lambda: [{"path": str(cache), "files": 1, "bytes": 3}])
    cleaned = execute_setup_action(SetupAction("clean_safe_cache", "缓存", "confirm"), region)
    assert cleaned.status == "success" and not (cache / "temporary.bin").exists()
    unsupported = execute_setup_action(SetupAction("unsupported", "未知", "manual"), region)
    assert unsupported.status == "failed"
