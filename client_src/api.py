from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class ApiError(RuntimeError):
    pass


class ClientApi:
    def __init__(self, base_url: str, device_id: str, token: str = "", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.device_id = device_id
        self.token = token
        self.timeout = timeout

    def _request(self, path: str, method: str = "GET", payload: dict | None = None, raw: bytes | None = None) -> dict:
        headers = {"Accept": "application/json", "User-Agent": "WeiDuTKLiveCheck/2.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = raw
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif raw is not None:
            headers["Content-Type"] = "application/octet-stream"
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
            except Exception:
                message = str(exc)
            raise ApiError(message) from exc
        except (OSError, ValueError) as exc:
            raise ApiError(f"无法连接服务：{exc}") from exc

    def register(self, app_version: str, room_name: str, customer_name: str) -> dict:
        response = self._request(
            "/api/client/register",
            "POST",
            {
                "device_id": self.device_id,
                "app_version": app_version,
                "room_name": room_name,
                "customer_name": customer_name,
            },
        )
        self.token = response.get("device_token", self.token)
        return response

    def check_profile(self) -> dict:
        return self._request("/api/client/check-profile")

    def update_info(self) -> dict:
        return self._request("/api/client/update")

    def upload_test(self, size: int) -> float:
        payload = b"0" * max(64 * 1024, min(size, 5 * 1024 * 1024))
        started = time.perf_counter()
        response = self._request("/api/client/upload-test", "POST", raw=payload)
        elapsed = max(time.perf_counter() - started, 0.001)
        received = int(response.get("received", len(payload)))
        return received * 8 / elapsed / 1_000_000

    def upload_report(self, report: dict) -> dict:
        return self._request("/api/client/reports", "POST", report)

    def latest_report(self) -> dict:
        return self._request("/api/client/reports/latest")

    def activate(self, code: str, app_version: str) -> dict:
        return self._request(
            "/api/client/activate",
            "POST",
            {"device_id": self.device_id, "code": code.strip().upper(), "app_version": app_version},
        )

    def authorize_check(self, event_id: str) -> dict:
        return self._request(
            "/api/client/authorize-check",
            "POST",
            {"device_id": self.device_id, "event_id": event_id},
        )
