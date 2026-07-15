from __future__ import annotations

import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
from pathlib import Path
import uuid


DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WeiDuTKLiveCheck"
REPORT_DIR = DATA_DIR / "reports"
CONFIG_FILE = DATA_DIR / "config-v2.json"
LICENSE_FILE = DATA_DIR / "license-v2.json"
QUEUE_FILE = DATA_DIR / "pending-sync.json"

DEFAULT_CONFIG = {
    "schema_version": 5, "target_region_id": "us-los-angeles", "target_host": "tk.wdai.cc",
    "api_base": "https://tk.wdai.cc", "device_id": "", "device_token": "",
    "privacy_confirm_upload": True, "reduced_effects": False,
}


def ensure_dirs() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> logging.Logger:
    ensure_dirs()
    logger = logging.getLogger("tk-client")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(DATA_DIR / "client.log", maxBytes=2_000_000, backupCount=7, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def atomic_json(path: Path, value: object) -> None:
    ensure_dirs()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def load_json(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, ValueError, TypeError):
        return default.copy() if isinstance(default, dict) else list(default)


def fingerprint() -> str:
    seed = "|".join([platform.node(), platform.machine(), platform.processor(), str(uuid.getnode())])
    return hashlib.sha256(seed.encode(errors="ignore")).hexdigest()[:24].upper()


def load_config() -> dict:
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    legacy_regions = {
        "US-Los Angeles": "us-los-angeles", "US-New York": "us-new-york",
        "UK-London": "uk-london", "DE-Frankfurt": "de-frankfurt",
        "JP-Tokyo": "jp-tokyo", "SG-Singapore": "sg-singapore",
    }
    if int(config.get("schema_version", 1)) < 3:
        config["target_region_id"] = legacy_regions.get(config.get("region", ""), "us-los-angeles")
        for obsolete in ("customer_name", "room_name", "bitrate_kbps", "region"):
            config.pop(obsolete, None)
        config["schema_version"] = 3
    if int(config.get("schema_version", 1)) < 4:
        config["reduced_effects"] = False
        config["schema_version"] = 4
    if int(config.get("schema_version", 1)) < 5:
        if config.get("api_base") == "http://127.0.0.1:8000":
            config["api_base"] = "https://tk.wdai.cc"
        if config.get("target_host") == "v.wdai.cc":
            config["target_host"] = "tk.wdai.cc"
        config["schema_version"] = 5
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)
    if not config["device_id"]:
        config["device_id"] = fingerprint()
        save_config(config)
    return config


def save_config(config: dict) -> None:
    config["schema_version"] = 5
    atomic_json(CONFIG_FILE, config)


def load_license() -> dict:
    return load_json(LICENSE_FILE, {"schema_version": 4, "tier": "FREE", "credits": -1, "status": "active", "expires_at": "", "lease_until": "", "pending_events": []})


def save_license(value: dict) -> None:
    value["schema_version"] = 4
    atomic_json(LICENSE_FILE, value)


def save_report(report: dict) -> Path:
    path = REPORT_DIR / f"{report['report_id']}.json"
    atomic_json(path, report)
    return path


def load_reports(limit: int = 100) -> list[dict]:
    ensure_dirs()
    result = []
    for path in sorted(REPORT_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        value = load_json(path, {})
        if value:
            result.append(value)
    return result


def queue_report(report_id: str) -> None:
    queue = load_json(QUEUE_FILE, [])
    if report_id not in queue:
        queue.append(report_id)
        atomic_json(QUEUE_FILE, queue)
