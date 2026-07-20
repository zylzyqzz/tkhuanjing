from client_v2.checks import PLUGINS
from client_v2.live_studio import candidate_paths, find_live_studio
from client_v2.models import CheckReport, CheckResult, Status
from client_v2.regions import REGIONS
from client_v2.system_repair import run_system_repair


def test_detection_scope_is_network_system_performance_only():
    assert [plugin.plugin_id for plugin in PLUGINS] == ["network", "system", "performance"]


def test_every_region_has_explicit_dns_pair():
    assert all(region.preferred_dns and region.alternate_dns for region in REGIONS)


def test_network_and_performance_are_advisory_but_system_failures_block():
    report = CheckReport("device", "2.9.1", [
        CheckResult("network.throughput", "网络环境", Status.FAIL, "上传"),
        CheckResult("performance.cpu", "电脑性能", Status.WARNING, "CPU"),
    ])
    report.finalize()
    assert report.blocking_count == 0 and report.readiness_level == "READY_WITH_RISK"
    report.items.append(CheckResult("system.timezone", "系统环境", Status.FAIL, "时区"))
    report.finalize()
    assert report.blocking_count == 1 and report.readiness_level == "NOT_READY"


def test_repair_runner_records_failures_and_continues(monkeypatch):
    def fake_action(ok=True):
        def run(*_args):
            if not ok:
                raise RuntimeError("命令失败")
            return "完成", {}, False
        return run
    monkeypatch.setattr("client_v2.system_repair._close_tiktok", fake_action())
    monkeypatch.setattr("client_v2.system_repair._set_timezone", fake_action(False))
    monkeypatch.setattr("client_v2.system_repair._set_region", fake_action())
    monkeypatch.setattr("client_v2.system_repair._configure_dns", fake_action())
    monkeypatch.setattr("client_v2.system_repair._flush_network", fake_action())
    monkeypatch.setattr("client_v2.system_repair._sync_time", fake_action())
    monkeypatch.setattr("client_v2.system_repair._power", fake_action())
    monkeypatch.setattr("client_v2.system_repair._sleep", fake_action())
    monkeypatch.setattr("client_v2.system_repair._clean_cache", fake_action())
    results = run_system_repair(REGIONS[0])
    assert len(results) == 9 and not results[1].ok and results[-1].ok


def test_custom_live_studio_path_has_priority(tmp_path):
    executable = tmp_path / "TikTok LIVE Studio.exe"
    executable.write_bytes(b"MZ")
    assert candidate_paths(str(executable))[0] == executable
    assert find_live_studio(str(executable)) == executable
