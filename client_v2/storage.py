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
    "schema_version": 7, "target_region_id": "us-los-angeles", "target_host": "tk.aimj.xin",
    "api_base": "https://tk.aimj.xin", "device_id": "", "device_token": "",
    "privacy_confirm_upload": True, "reduced_effects": False, "theme_id": "obsidian",
    "effects_level": "full", "font_scale": "standard", "test_mode": "standard",
    "result_sound": True, "auto_open_report": True, "update_check_on_start": True,
    "report_retention_days": 90, "upload_confirm": True,
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
    if int(config.get("schema_version", 1)) < 6:
        if config.get("api_base") in {"http://127.0.0.1:8000", "https://v.wdai.cc", "https://tk.wdai.cc"}:
            config["api_base"] = "https://tk.aimj.xin"
        if config.get("target_host") in {"v.wdai.cc", "tk.wdai.cc"}:
            config["target_host"] = "tk.aimj.xin"
        config["schema_version"] = 6
    if int(config.get("schema_version", 1)) < 7:
        config["theme_id"] = "obsidian"
        config["effects_level"] = "light" if config.get("reduced_effects") else "full"
        config["font_scale"] = "standard"; config["test_mode"] = "standard"
        config["result_sound"] = True; config["auto_open_report"] = True
        config["update_check_on_start"] = True; config["report_retention_days"] = 90
        config["upload_confirm"] = bool(config.get("privacy_confirm_upload", True))
        config["schema_version"] = 7
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)
    if not config["device_id"]:
        config["device_id"] = fingerprint()
        save_config(config)
    return config


def save_config(config: dict) -> None:
    config["schema_version"] = 7
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


def cleanup_reports(retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    import time
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for path in REPORT_DIR.glob("*.json"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True); removed += 1
    return removed


def baseline_delta(current: dict, previous: dict | None) -> dict:
    if not previous:
        return {"available": False}
    def metric(report: dict, check_id: str, key: str):
        snapshot = report.get("network_snapshot", {}) if check_id.startswith("network.") else report.get("device_snapshot", {})
        return (snapshot.get(check_id) or {}).get(key)
    changes = {}
    for label, check_id, key in (("upload_mbps", "network.throughput", "upload_mbps"), ("download_mbps", "network.throughput", "download_mbps"), ("cpu_percent", "performance.cpu", "percent"), ("memory_percent", "performance.memory", "percent")):
        now, before = metric(current, check_id, key), metric(previous, check_id, key)
        if isinstance(now, (int, float)) and isinstance(before, (int, float)):
            changes[label] = {"before": before, "current": now, "change": round(now - before, 2)}
    old = {item.get("check_id"): item.get("status") for item in previous.get("items", [])}
    new = {item.get("check_id"): item.get("status") for item in current.get("items", [])}
    changes["new_issues"] = [key for key, value in new.items() if value in {"FAIL", "WARNING"} and old.get(key) not in {"FAIL", "WARNING"}]
    changes["resolved"] = [key for key, value in old.items() if value in {"FAIL", "WARNING"} and new.get(key) == "PASS"]
    changes["available"] = True
    return changes


def queue_report(report_id: str) -> None:
    queue = load_json(QUEUE_FILE, [])
    if report_id not in queue:
        queue.append(report_id)
        atomic_json(QUEUE_FILE, queue)
