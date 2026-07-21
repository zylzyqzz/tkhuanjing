from __future__ import annotations

import httpx

from .product import APP_VERSION


class ApiError(RuntimeError):
    pass


class ClientApi:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        use_token = kwargs.pop("use_token", True)
        if self.token and use_token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(12, connect=5), headers={"User-Agent": f"VDLiveCheck/{APP_VERSION}", **headers}) as client:
                response = client.request(method, path, **kwargs)
            if response.is_error:
                body = response.json()
                error = body.get("error", {}) if isinstance(body, dict) else {}
                message = error.get("message") if isinstance(error, dict) else body.get("detail")
                request_id = error.get("request_id", "") if isinstance(error, dict) else ""
                raise ApiError((message or f"服务返回 {response.status_code}") + (f" [{request_id[:8]}]" if request_id else ""))
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

    def bind_enterprise(self, code: str) -> dict:
        return self.request("POST", "/api/v1/client/bind-enterprise", json={"code": code})

    def heartbeat(self, payload: dict) -> dict:
        return self.request("POST", "/api/v1/client/heartbeat", json=payload)

    def upload_events(self, events: list[dict]) -> dict:
        return self.request("POST", "/api/v1/client/events", json={"events": events})

    def enterprise_login(self, organization_code: str, username: str, password: str) -> dict:
        return self.request("POST", "/api/v2/auth/login", json={"organization_code": organization_code, "username": username, "password": password}, use_token=False)

    def enterprise_options(self, member_token: str) -> dict:
        return self.request("GET", "/api/v2/organization/options", headers={"Authorization": f"Bearer {member_token}"}, use_token=False)

    def v2_binding(self, member_token: str = "") -> dict:
        headers = {"X-Device-Token": self.token}
        if member_token: headers["Authorization"] = f"Bearer {member_token}"
        return self.request("GET", "/api/v2/device/binding", headers=headers, use_token=False)

    def v2_bind(self, member_token: str, payload: dict) -> dict:
        return self.request("PUT", "/api/v2/device/binding", json=payload, headers={"Authorization": f"Bearer {member_token}", "X-Device-Token": self.token}, use_token=False)

    def v2_unbind(self, member_token: str, reason: str) -> dict:
        return self.request("DELETE", "/api/v2/device/binding", json={"reason": reason}, headers={"Authorization": f"Bearer {member_token}", "X-Device-Token": self.token}, use_token=False)

    def v2_heartbeat(self, payload: dict) -> dict:
        return self.request("POST", "/api/v2/device/heartbeat", json=payload, headers={"X-Device-Token": self.token}, use_token=False)

    def v2_device_config(self) -> dict:
        return self.request("GET", "/api/v2/device/config", headers={"X-Device-Token": self.token}, use_token=False)

    def v2_device_bootstrap(self) -> dict:
        return self.request("GET", "/api/v2/device/bootstrap", headers={"X-Device-Token": self.token}, use_token=False)

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

    def validate_user_session(self) -> dict:
        return self.get_user_profile()

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
