from __future__ import annotations

import httpx


class ApiError(RuntimeError):
    pass


class ClientApi:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(12, connect=5), headers={"User-Agent": "VDLiveCheck/2.9.1", **headers}) as client:
                response = client.request(method, path, **kwargs)
            if response.is_error:
                body = response.json()
                message = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("detail")
                raise ApiError(message or f"服务返回 {response.status_code}")
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(f"无法连接服务：{exc}") from exc

    def register(self, config: dict, version: str) -> dict:
        data = self.request("POST", "/api/v1/client/register", json={
            "device_id": config["device_id"], "app_version": version,
            "target_region_id": config.get("target_region_id", "us-los-angeles"),
        })
        self.token = data["device_token"]
        return data

    def profile(self) -> dict:
        return self.request("GET", "/api/v1/client/profile")

    def activate(self, code: str) -> dict:
        return self.request("POST", "/api/v1/client/activate", json={"code": code})

    def authorize(self, event_id: str, user_token: str = "") -> dict:
        headers = {"X-User-Token": user_token} if user_token else {}
        return self.request("POST", "/api/v1/client/authorize", json={"event_id": event_id}, headers=headers)

    def upload_report(self, report: dict) -> dict:
        return self.request("POST", "/api/v1/client/reports", json=report)

    def update_info(self) -> dict:
        return self.request("GET", "/api/v1/client/update")

    def changelog(self) -> dict:
        return self.request("GET", "/api/v1/client/changelog")

    # ── User auth ──────────────────────────────────────────────

    def auth_register(self, phone: str, phone_country: str, password: str, email: str, code: str) -> dict:
        return self.request("POST", "/api/v1/client/auth/register", json={
            "phone": phone, "phone_country": phone_country, "password": password,
            "password_confirm": password, "email": email, "code": code,
        })

    def auth_login(self, phone: str, password: str) -> dict:
        response = self.request("POST", "/api/v1/client/auth/login", json={"phone": phone, "password": password})
        self.token = response["token"]
        return response

    def auth_send_code(self, target: str, purpose: str = "register") -> dict:
        return self.request("POST", "/api/v1/client/auth/send-code", json={"target": target, "purpose": purpose})

    def auth_forgot_password(self, phone: str) -> dict:
        return self.request("POST", "/api/v1/client/auth/forgot-password", json={"phone": phone})

    def auth_reset_password(self, phone: str, code: str, password: str) -> dict:
        return self.request("POST", "/api/v1/client/auth/reset-password", json={
            "phone": phone, "code": code, "password": password, "password_confirm": password,
        })

    def auth_logout(self) -> dict:
        return self.request("POST", "/api/v1/client/auth/logout")

    def get_user_profile(self) -> dict:
        return self.request("GET", "/api/v1/client/user/profile")

    def update_user_profile(self, **fields) -> dict:
        payload = {key: value for key, value in fields.items() if value is not None}
        return self.request("PUT", "/api/v1/client/user/profile", json=payload)
