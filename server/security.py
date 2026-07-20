from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Admin, Device, UserSession


settings = get_settings()
hasher = PasswordHasher()
serializer = URLSafeTimedSerializer(settings.session_secret, salt="tk-admin-session-v2")
login_attempts: dict[str, deque[float]] = defaultdict(deque)
rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, ValueError):
        return False


def seed_admin(db: Session) -> None:
    existing = db.scalar(select(Admin).where(Admin.username == settings.admin_user))
    if existing:
        return
    encoded = settings.admin_password_hash or hasher.hash(settings.admin_password)
    db.add(Admin(username=settings.admin_user, password_hash=encoded))
    db.commit()


def rate_limit_login(ip: str) -> None:
    now = time.monotonic()
    attempts = login_attempts[ip]
    while attempts and now - attempts[0] > 600:
        attempts.popleft()
    if len(attempts) >= 8:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")
    attempts.append(now)


def clear_login_attempts(ip: str) -> None:
    login_attempts.pop(ip, None)


def enforce_rate_limit(scope: str, key: str, limit: int, window_seconds: int) -> None:
    bucket_key = hashlib.sha256(f"{scope}:{key}".encode()).hexdigest()
    now = time.monotonic(); bucket = rate_buckets[bucket_key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    bucket.append(now)


def make_session(username: str) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    token = serializer.dumps({"username": username, "csrf": csrf, "expires": expires.isoformat()})
    return token, csrf


def current_admin(tk_session: str | None = Cookie(default=None)) -> dict:
    if not tk_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = serializer.loads(tk_session, max_age=settings.session_hours * 3600)
        if datetime.fromisoformat(payload["expires"]) < datetime.now(timezone.utc):
            raise BadSignature("expired")
        return payload
    except (BadSignature, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期") from None


def require_csrf(
    admin: dict = Depends(current_admin),
    csrf: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    if not csrf or not secrets.compare_digest(csrf, admin["csrf"]):
        raise HTTPException(status_code=403, detail="安全校验失败，请刷新页面")
    return admin


def current_device(
    authorization: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    db: Session = Depends(get_db),
) -> Device:
    token = x_device_token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else "")
    if not token:
        raise HTTPException(status_code=401, detail="缺少设备令牌")
    device = db.scalar(select(Device).where(Device.token_hash == hash_token(token)))
    if not device or device.status != "active":
        raise HTTPException(status_code=401, detail="设备令牌无效")
    return device


def request_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    from .models import UserSession
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    session_row = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked == 0,
            UserSession.expires_at > now,
        )
    )
    if not session_row:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return {"user_id": session_row.user_id, "phone": session_row.user.phone}


def user_from_token(token: str | None, db: Session):
    """Resolve an optional user token without taking over device authentication."""
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat()
    session_row = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked == 0,
            UserSession.expires_at > now,
        )
    )
    return session_row.user if session_row else None
