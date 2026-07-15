from __future__ import annotations

from pathlib import Path
import threading

from client_v2.checks import CheckContext, DEFAULT_PROFILE, network_checks, ping_metrics, threshold
from client_v2.models import CheckReport, CheckResult, Status
from client_v2.regions import get_region


def test_threshold_boundaries():
    assert threshold(1, 1, 3) == Status.PASS
    assert threshold(1.1, 1, 3) == Status.WARNING
    assert threshold(3.1, 1, 3) == Status.FAIL


def test_ping_metrics_extracts_loss_latency_and_jitter(monkeypatch):
    class Result:
        stdout = "Reply: time=20ms\nReply: time=40ms\nLost = 1 (12% loss)"

    monkeypatch.setattr("client_v2.checks.command", lambda *_args, **_kwargs: Result())
    latency, loss, jitter, samples = ping_metrics("edge.example")
    assert latency == 30
    assert loss == 12
    assert jitter == 20
    assert samples == 2


def test_network_checks_separates_local_gateway_and_target(monkeypatch):
    metrics = iter([(1, 0, 0, 6), (30, 2, 4, 6), (35, 0, 3, 6)])
    monkeypatch.setattr("client_v2.checks.lookup_public_ip", lambda: {"ip":"1.2.3.4","country_code":"US","source":"test","confidence":"high","cleanliness":{"score":90},"network_type":"residential"})
    monkeypatch.setattr("client_v2.checks.tls_probe", lambda host: {"host":host,"ok":True,"connect_ms":40})
    monkeypatch.setattr("client_v2.checks.measure_throughput", lambda: {"download_mbps":100.0,"upload_mbps":20.0,"upload_variation_percent":5.0,"source":"test"})
    monkeypatch.setattr("client_v2.checks.discover_streaming_profiles", lambda: [{"bitrate_kbps":6000}])
    monkeypatch.setattr("client_v2.checks.ping_metrics", lambda *_args, **_kwargs: next(metrics))
    monkeypatch.setattr("client_v2.checks.powershell", lambda *_args, **_kwargs: "192.168.1.1")
    context = CheckContext(dict(DEFAULT_PROFILE), get_region("us-los-angeles"), "target.example", object(), Path("."), "2.3.0", True, threading.Event())
    rows = network_checks(context)
    assert next(x for x in rows if x.check_id == "network.local_gateway").status == Status.PASS
    assert next(x for x in rows if x.check_id == "network.target_route").status == Status.PASS
    assert next(x for x in rows if x.check_id == "network.throughput").metrics["upload_mbps"] == 20.0


def test_report_precedence_and_schema():
    report = CheckReport("device", "2.3.0", [
        CheckResult("network.dns", "网络", Status.PASS, "DNS"),
        CheckResult("devices.camera", "设备", Status.FAIL, "摄像头"),
    ])
    report.finalize()
    assert report.overall_status == Status.FAIL
    payload = report.to_dict()
    assert payload["schema_version"] == 4
    assert payload["run_mode"] == "daily_preflight"
    assert "check_logs" in payload and "environment_snapshot" in payload
    assert report.to_dict()["items"][1]["status"] == "FAIL"


def test_warning_when_unknown_present():
    report = CheckReport("device", "2.3.0", [CheckResult("x", "客户端", Status.UNKNOWN, "测试")])
    report.finalize()
    assert report.overall_status == Status.WARNING
