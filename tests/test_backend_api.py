from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


def password_hash(password: str) -> str:
    salt = b"0123456789abcdef"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000).hex()
    return salt.hex() + "$" + digest


class BackendApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ["TK_PLATFORM_ROOT"] = cls.temp.name
        os.environ["TK_ADMIN_PASSWORD_HASH"] = password_hash("test-password")
        os.environ["TK_PUBLIC_BASE"] = "http://127.0.0.1"
        path = Path(__file__).resolve().parents[1] / "backend.py"
        spec = importlib.util.spec_from_file_location("tk_test_backend", path)
        cls.backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.backend)
        cls.backend.init_db()
        cls.server = cls.backend.ThreadingHTTPServer(("127.0.0.1", 0), cls.backend.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.temp.cleanup()

    def request(self, path, method="GET", data=None, token=""):
        headers = {}
        body = None
        if data is not None:
            body = json.dumps(data).encode(); headers["Content-Type"] = "application/json"
        if token: headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read())

    def test_registration_profile_free_use_and_report(self):
        registered = self.request("/api/client/register", "POST", {
            "device_id": "TESTDEVICE01", "app_version": "2.0.0", "customer_name": "测试客户", "room_name": "直播间A"
        })
        token = registered["device_token"]
        self.assertEqual(registered["license"]["credits"], 1)
        profile = self.request("/api/client/check-profile", token=token)
        self.assertEqual(profile["profile"]["packet_loss_fail"], 3.0)
        event = "11111111-1111-4111-8111-111111111111"
        allowed = self.request("/api/client/authorize-check", "POST", {"device_id": "TESTDEVICE01", "event_id": event}, token)
        self.assertTrue(allowed["allowed"])
        self.assertEqual(allowed["license"]["credits"], 0)
        report_id = "22222222-2222-4222-8222-222222222222"
        uploaded = self.request("/api/client/reports", "POST", {
            "report_id": report_id, "customer_name": "测试客户", "room_name": "直播间A",
            "device_id": "TESTDEVICE01", "app_version": "2.0.0", "checked_at": "2026-07-13T00:00:00+00:00",
            "overall_status": "FAIL", "conclusion": "不建议开播",
            "items": [{"check_id": "network.packet_loss", "category": "网络", "status": "FAIL", "title": "网络丢包", "value": "4%", "reason": "丢包", "action": "更换线路"}],
        }, token)
        self.assertEqual(uploaded["report_id"], report_id)
        latest = self.request("/api/client/reports/latest", token=token)
        self.assertEqual(latest["report"]["overall_status"], "FAIL")

    def test_code_activation_and_idempotent_consumption(self):
        with self.backend.connect() as conn:
            conn.execute("insert into codes(code,tier,credits,status,created_at,updated_at) values(?,?,?,?,?,?)", ("TKX-ABCDE-ABCDE", "TKX", 10, "available", self.backend.utc_now(), self.backend.utc_now()))
        registered = self.request("/api/client/register", "POST", {"device_id": "TESTDEVICE02", "app_version": "2.0.0"})
        token = registered["device_token"]
        activated = self.request("/api/client/activate", "POST", {"device_id": "TESTDEVICE02", "code": "TKX-ABCDE-ABCDE", "app_version": "2.0.0"}, token)
        self.assertEqual(activated["license"]["credits"], 10)
        event = "33333333-3333-4333-8333-333333333333"
        first = self.request("/api/client/authorize-check", "POST", {"device_id": "TESTDEVICE02", "event_id": event}, token)
        second = self.request("/api/client/authorize-check", "POST", {"device_id": "TESTDEVICE02", "event_id": event}, token)
        self.assertEqual(first["license"]["credits"], 9)
        self.assertEqual(second["license"]["credits"], 9)


if __name__ == "__main__":
    unittest.main()
