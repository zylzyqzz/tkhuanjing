from __future__ import annotations

import base64
import hashlib
import json
import secrets
import string
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuditLog, CheckProfile, Code, Release, Setting, now_iso


TIERS = {"TK1": 1, "TKX": 10, "TKV": -1}
TIME_PLANS = {"TK-MONTH": 30, "TK-QUARTER": 90, "TK-HALF-YEAR": 180, "TK-YEAR": 365}
DEFAULT_PROFILE = {
    "profile_name": "WD 默认直播检测规则",
    "upload_multiplier": 2.0,
    "upload_test_bytes": 2_000_000,
    "packet_loss_warning": 1.0,
    "packet_loss_fail": 3.0,
    "jitter_warning_ms": 30.0,
    "jitter_fail_ms": 60.0,
    "latency_warning_ms": 150.0,
    "latency_fail_ms": 250.0,
    "min_free_disk_gb": 10.0,
}
DEFAULT_SETTINGS = {
    "product_name": "VD开播助手",
    "product_intro": "面向 TikTok 电脑直播公司和工作室的网络、系统环境和电脑性能检测工具。",
    "product_features": "网络环境报告与建议\n影响开播的系统环境\n电脑性能说明与建议",
    "product_faq": "检测通过仅代表网络、系统环境和电脑性能已完成技术检查。",
    "support_text": "遇到问题请通过软件内客服二维码联系技术支持。",
    "latest_changelog": "V2 产品级客户端与管理平台升级。",
    "home_hero_title": "开播前，先检查",
    "home_hero_subtitle": "让每一次 TikTok 电脑直播，从准备充分开始。",
    "home_daily_text": "选择目标地区后，一次检测网络环境、系统环境和电脑性能。",
    "home_setup_text": "系统环境异常时一键修复，执行完成后自动复检。",
    "home_steps": "发现真实问题\n判断问题来源\n安全处理或给出方案\n自动复检\n判断能否开播",
    "home_system_requirements": "Windows 10 / Windows 11 · 1366×768 及以上 · 建议使用有线网络",
    "home_extra_notice": "检测结果用于判断技术准备度，请结合实际直播要求使用。",
}


def audit(db: Session, actor: str, action: str, target_type: str = "", target_id: str = "", details: str = "") -> None:
    db.add(AuditLog(actor=actor, action=action, target_type=target_type, target_id=target_id, details=details))


def seed_defaults(db: Session) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        if not db.get(Setting, key):
            db.add(Setting(key=key, value=value))
    feature_setting = db.get(Setting, "product_features")
    if feature_setting and len([line for line in feature_setting.value.splitlines() if line.strip()]) != 7:
        feature_setting.value = DEFAULT_SETTINGS["product_features"]
    if not db.scalar(select(CheckProfile).where(CheckProfile.active.is_(True))):
        db.add(CheckProfile(name=DEFAULT_PROFILE["profile_name"], region="*", bitrate_kbps=6000, rules_json=json.dumps(DEFAULT_PROFILE, ensure_ascii=False), active=True, created_at=now_iso(), updated_at=now_iso()))
    db.commit()


def generate_code(tier: str) -> str:
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(16))
    signature = hashlib.sha256((random_part + get_settings().license_secret).encode()).hexdigest()[:6].upper()
    return f"{tier}-{random_part[:4]}-{random_part[4:8]}-{random_part[8:12]}-{random_part[12:]}-{signature}"


def create_codes(db: Session, tier: str, count: int, note: str = "", batch: str = "") -> list[str]:
    result: list[str] = []
    for _ in range(count):
        code = generate_code(tier)
        while db.get(Code, code):
            code = generate_code(tier)
        is_time_plan = tier in TIME_PLANS
        db.add(Code(code=code, tier=tier, credits=-1 if is_time_plan else TIERS[tier], plan_code=tier if is_time_plan else "", duration_days=TIME_PLANS.get(tier, 0), customer_note=note, batch=batch))
        result.append(code)
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sign_manifest(manifest: dict) -> str:
    key_text = get_settings().update_private_key.strip()
    if not key_text:
        return ""
    key = serialization.load_pem_private_key(key_text.encode(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("更新签名密钥不是 Ed25519 私钥")
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return base64.b64encode(key.sign(payload)).decode()


def active_release(db: Session, channel: str = "stable") -> Release | None:
    return db.scalar(select(Release).where(Release.active.is_(True), Release.channel == channel).limit(1))


def release_manifest(db: Session, channel: str = "stable") -> dict:
    release = active_release(db, channel)
    if not release:
        return {"available": False, "channel": channel}
    settings = get_settings()
    filename = release.installer_filename or release.filename
    core = {
        "available": True,
        "version": release.version,
        "channel": release.channel,
        "mandatory": release.mandatory,
        "minimum_version": release.minimum_version,
        "title": release.title,
        "notes": release.notes,
        "details": release.details,
        "filename": filename,
        "file_size": release.file_size,
        "sha256": release.sha256,
        "url": f"{settings.public_base.rstrip('/')}/downloads/{filename}",
    }
    core["signature"] = release.signature or sign_manifest(core)
    core["public_key"] = settings.update_public_key
    return core
