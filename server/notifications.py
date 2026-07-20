from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Alert, Customer, Device, NotificationDelivery, now_iso


def secret_box() -> Fernet:
    digest = hashlib.sha256(get_settings().session_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def enqueue_alert(db: Session, alert: Alert, event_type: str = "opened") -> None:
    tenant = db.get(Customer, alert.customer_id)
    if not tenant or not tenant.wecom_webhook_encrypted:
        return
    settings = json.loads(tenant.alert_settings_json or "{}")
    if alert.alert_type not in settings.get("enabled_types", ["system_blocked", "device_offline", "studio_crashed"]):
        return
    if settings.get("minimum_severity", "critical") == "critical" and alert.severity != "critical":
        return
    existing = db.scalar(select(NotificationDelivery).where(NotificationDelivery.alert_id == alert.id, NotificationDelivery.event_type == event_type, NotificationDelivery.status.in_(["pending", "sent"])))
    if existing:
        return
    device = db.get(Device, alert.device_id)
    payload = {"title": alert.title, "device": device.display_name if device and device.display_name else alert.device_id, "severity": alert.severity, "event_type": event_type, "root_cause": alert.root_cause, "occurred_at": alert.last_seen_at}
    db.add(NotificationDelivery(customer_id=alert.customer_id, alert_id=alert.id, event_type=event_type, payload_json=json.dumps(payload, ensure_ascii=False)))


def _message(payload: dict) -> str:
    action = "恢复通知" if payload.get("event_type") == "resolved" else "开播风险告警"
    return f"## VD Nexus {action}\n> **{payload.get('title', '设备异常')}**\n> 设备：{payload.get('device', '-')}\n> 根因：{payload.get('root_cause', '待分析')}\n> 时间：{str(payload.get('occurred_at', ''))[:19]}\n\n请登录企业管理后台查看检测证据和处理记录。"


def deliver_pending(db: Session, limit: int = 30) -> int:
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(NotificationDelivery).where(NotificationDelivery.status == "pending", NotificationDelivery.next_attempt_at <= now.isoformat()).order_by(NotificationDelivery.created_at).limit(limit)).all()
    sent = 0
    for row in rows:
        tenant = db.get(Customer, row.customer_id)
        if not tenant or not tenant.wecom_webhook_encrypted:
            row.status = "failed"; row.last_error = "企业微信未配置"; continue
        try:
            webhook = secret_box().decrypt(tenant.wecom_webhook_encrypted.encode()).decode()
            response = httpx.post(webhook, json={"msgtype": "markdown", "markdown": {"content": _message(json.loads(row.payload_json or "{}"))}}, timeout=8)
            response.raise_for_status(); result = response.json()
            if int(result.get("errcode", -1)) != 0: raise RuntimeError(str(result.get("errmsg", "发送失败")))
            row.status = "sent"; row.sent_at = now_iso(); row.last_error = ""; sent += 1
        except (httpx.HTTPError, ValueError, RuntimeError, InvalidToken) as exc:
            row.attempts += 1; row.last_error = str(exc)[:500]
            if row.attempts >= 6: row.status = "failed"
            else: row.next_attempt_at = (now + timedelta(seconds=min(1800, 30 * (2 ** row.attempts)))).isoformat()
    db.commit(); return sent
