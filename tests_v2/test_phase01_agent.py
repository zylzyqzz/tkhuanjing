from __future__ import annotations

from client_v2.agent import heartbeat, ingest_queue
from client_v2.api import ApiError


PAYLOAD = {
    "device_id": "DEVICE-AGENT-0001",
    "binding_id": 9,
    "agent_version": "2.1.0",
    "sent_at": "2026-07-21T09:00:00+00:00",
    "uptime_seconds": 60,
    "status": "online",
    "live_software": {"name": "TikTok LIVE Studio", "running": False},
    "collection": {"status": "healthy", "provider": "client_agent"},
    "metrics": {"cpu_percent": 10, "memory_percent": 20},
}


def prepare(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest_queue, "QUEUE", tmp_path / "heartbeats.jsonl")
    monkeypatch.setattr(heartbeat, "load_config", lambda: {"api_base": "https://example.test", "device_id": PAYLOAD["device_id"]})
    monkeypatch.setattr(heartbeat, "load_credentials", lambda: {"device_token": "device-secret", "v2_binding_id": "9"})
    monkeypatch.setattr(heartbeat, "payload", lambda: PAYLOAD.copy())


def test_heartbeat_offline_queue_recovers_once(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)

    class OfflineApi:
        def __init__(self, *_): return None
        def v2_heartbeat(self, payload): raise OSError("offline")

    monkeypatch.setattr(heartbeat, "ClientApi", OfflineApi)
    assert heartbeat.flush_once() == {"sent": 0, "queued": 1, "response": {}}
    assert heartbeat.flush_once()["queued"] == 1

    calls = []
    class OnlineApi:
        def __init__(self, *_): return None
        def v2_heartbeat(self, payload):
            calls.append(payload["sent_at"])
            return {"commands": [], "idempotent": False}

    monkeypatch.setattr(heartbeat, "ClientApi", OnlineApi)
    result = heartbeat.flush_once()
    assert result["sent"] == 1 and result["queued"] == 0
    assert calls == [PAYLOAD["sent_at"]]


def test_heartbeat_rejects_non_whitelisted_command(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)

    class MaliciousApi:
        def __init__(self, *_): return None
        def v2_heartbeat(self, payload): return {"commands": [{"type": "powershell", "args": "whoami"}]}

    monkeypatch.setattr(heartbeat, "ClientApi", MaliciousApi)
    result = heartbeat.flush_once()
    assert result["sent"] == 0 and result["queued"] == 1


def test_heartbeat_without_device_token_is_not_queued(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest_queue, "QUEUE", tmp_path / "heartbeats.jsonl")
    monkeypatch.setattr(heartbeat, "load_config", lambda: {"api_base": "https://example.test", "device_id": PAYLOAD["device_id"]})
    monkeypatch.setattr(heartbeat, "load_credentials", lambda: {})
    assert heartbeat.flush_once() == {"sent": 0, "queued": 0}
    assert ingest_queue.pending() == []


def test_heartbeat_clears_invalid_device_credentials(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)
    cleared = []

    class InvalidApi:
        def __init__(self, *_): return None
        def v2_device_bootstrap(self): raise ApiError("令牌失效", code="AUTH_EXPIRED", status_code=401)

    monkeypatch.setattr(heartbeat, "ClientApi", InvalidApi)
    monkeypatch.setattr(heartbeat, "clear_credentials", lambda *keys: cleared.extend(keys))
    result = heartbeat.flush_once()
    assert result["auth_error"] == "AUTH_EXPIRED"
    assert cleared == ["device_token", "v2_binding_id"]
    assert ingest_queue.pending() == []


def test_feature_disabled_stops_heartbeat_without_losing_bootstrap(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)

    class DisabledApi:
        def __init__(self, *_): return None
        def v2_device_bootstrap(self):
            return {"features":{"device_heartbeat":False},"config":{"queue_max_items":10,"queue_max_age_hours":1},"config_version":9}
        def v2_heartbeat(self, _payload): raise AssertionError("disabled heartbeat must not be sent")

    monkeypatch.setattr(heartbeat, "ClientApi", DisabledApi)
    result = heartbeat.flush_once()
    assert result["sent"] == 0 and result["bootstrap"]["config_version"] == 9
    assert ingest_queue.pending() == []
