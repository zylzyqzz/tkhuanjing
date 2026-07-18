from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from .config import get_settings

logger = logging.getLogger("tk-platform")


def send_verification_code(to_email: str, code: str, purpose: str) -> bool:
    """Send a verification code email.

    Args:
        to_email: Recipient email address.
        code: The verification code string.
        purpose: One of "register" or "reset_password".

    Returns:
        True if the email was sent (or simulated in dev), False on SMTP failure.
    """
    settings = get_settings()
    if settings.env != "production":
        logger.info("DEV: verification code for %s = %s (purpose=%s)", to_email, code, purpose)
        return True
    if not settings.smtp_host:
        logger.error("smtp_not_configured to=%s purpose=%s", to_email, purpose)
        return False

    purpose_labels = {"register": "注册账号", "reset_password": "重置密码"}
    label = purpose_labels.get(purpose, purpose)

    msg = MIMEText(
        f"您好！\n\n您的 VD开播助手 {label} 验证码为：{code}\n"
        f"有效期为 {settings.verify_code_ttl_minutes} 分钟，请勿泄露给他人。\n\n"
        f"如果这不是您本人的操作，请忽略此邮件。\n\n—— VD开播助手团队",
        "plain", "utf-8"
    )
    msg["Subject"] = f"VD开播助手 - {label}验证码"
    msg["From"] = settings.smtp_from
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("smtp_send_failed to=%s", to_email)
        return False
