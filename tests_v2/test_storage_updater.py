from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from client_v2 import storage
from client_v2.checks import CheckContext, CheckPlugin, client_checks, run_checks, run_repair
from client_v2.models import CheckResult, Status
from client_v2.updater import UpdateError, manifest_payload, verify_manifest
from client_v2.api import ApiError, ClientApi
from client_v2.regions import get_region


def test_atomic_storage_config_reports_and_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(storage, "LICENSE_FILE", tmp_path / "license.json")
    monkeypatch.setattr(storage, "QUEUE_FILE", tmp_path / "queue.json")
    config = storage.load_config()
    assert config["schema_version"] == 8 and config["device_id"]
    assert config["api_base"] == "https://tk.aimj.xin"
    assert config["reduced_effects"] is False
    config["target_region_id"] = "jp-tokyo"; storage.save_config(config)
    assert storage.load_config()["target_region_id"] == "jp-tokyo"
    license_data = storage.load_license(); storage.save_license(license_data)
    report = {"report_id": "REPORT-0001", "room_name": "直播间", "checked_at": "2026"}
    storage.save_report(report); assert storage.load_reports()[0]["report_id"] == "REPORT-0001"
    storage.queue_report("REPORT-0001"); storage.queue_report("REPORT-0001")
    assert storage.load_json(storage.QUEUE_FILE, []) == ["REPORT-0001"]


def test_signed_manifest_validation():
    key = Ed25519PrivateKey.generate(); public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    manifest = {"available": True, "version": "2.2.0", "file_size": 10, "sha256": "a" * 64, "url": "https://example.test/x.exe"}
    manifest["signature"] = base64.b64encode(key.sign(manifest_payload(manifest))).decode(); manifest["public_key"] = public
    verify_manifest(manifest)
    manifest["version"] = "9.9.9"
    with pytest.raises(UpdateError): verify_manifest(manifest)


def test_client_resource_check_and_plugin_isolation(tmp_path, monkeypatch):
    for name in ("收款码.jpg", "客服二维码.png", "app_icon.ico"):
        (tmp_path / name).write_bytes(b"asset")
    class Api: base_url = "http://localhost"
    context = CheckContext({}, get_region("us-los-angeles"), "localhost", Api(), tmp_path, "2.3.0", False, __import__('threading').Event())
    assert all(x.status != Status.FAIL for x in client_checks(context))
    def broken(_): raise RuntimeError("boom")
    monkeypatch.setattr("client_v2.checks.PLUGINS", [CheckPlugin("broken", "异常插件", 1, broken)])
    values = run_checks(context, lambda _value, _text: None)
    assert values[0].status == Status.UNKNOWN and values[0].check_id == "broken.error"
    ok, message, details = run_repair("not-supported")
    assert not ok and not details and "不支持" in message


def test_client_api_contract(monkeypatch):
    class Response:
        is_error = False
        status_code = 200
        def __init__(self, value): self.value = value
        def json(self): return self.value
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, **kwargs):
            if path.endswith('/register'): return Response({'device_token':'TOKEN','license':{'tier':'FREE'}})
            if path.endswith('/profile'): return Response({'packet_loss_warning':1})
            if path.endswith('/activate'): return Response({'license':{'tier':'TKX'}})
            if path.endswith('/authorize'): return Response({'authorized':True,'credits':9})
            if path.endswith('/reports'): return Response({'ok':True})
            if path.endswith('/update'): return Response({'available':False})
            return Response({})
    monkeypatch.setattr('client_v2.api.httpx.Client', FakeClient)
    api = ClientApi('http://localhost')
    config = {'device_id':'DEVICE-TEST','target_region_id':'us-los-angeles'}
    assert api.register(config, '2.1.0')['device_token'] == 'TOKEN' and api.token == 'TOKEN'
    assert api.profile()['packet_loss_warning'] == 1
    assert api.activate('TKX-CODE')['license']['tier'] == 'TKX'
    assert api.authorize('EVENT-0001')['credits'] == 9
    assert api.upload_report({'report_id':'REPORT'})['ok']
    assert api.update_info()['available'] is False


def test_client_api_error_envelope(monkeypatch):
    class BadResponse:
        is_error=True; status_code=403
        def json(self): return {'error':{'message':'授权失败'}}
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def request(self,*args,**kwargs): return BadResponse()
    monkeypatch.setattr('client_v2.api.httpx.Client', FakeClient)
    with pytest.raises(ApiError, match='授权失败'):
        ClientApi('http://localhost').update_info()
