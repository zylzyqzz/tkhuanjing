from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import uuid


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WeiDuTKLiveCheck"
REPORT_DIR = APP_DIR / "reports"
CONFIG_FILE = APP_DIR / "config.json"
LICENSE_FILE = APP_DIR / "license.json"
LOG_FILE = APP_DIR / "client.log"


DEFAULT_CONFIG = {
    "customer_name": "",
    "room_name": "直播间 1",
    "bitrate_kbps": 6000,
    "target_host": "v.wdai.cc",
    "api_base": "https://v.wdai.cc",
    "device_token": "",
    "device_id": "",
    "free_uses": 1,
}


def ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def atomic_json(path: Path, data: dict) -> None:
    ensure_dirs()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def load_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else dict(default)
    except (OSError, ValueError):
        return dict(default)


def device_fingerprint() -> str:
    seed = "|".join(
        [
            platform.node(),
            platform.machine(),
            platform.processor(),
            str(uuid.getnode()),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:24].upper()


def load_config() -> dict:
    ensure_dirs()
    data = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    for key, value in DEFAULT_CONFIG.items():
        data.setdefault(key, value)
    if not data.get("device_id"):
        data["device_id"] = device_fingerprint()
        save_config(data)
    return data


def save_config(data: dict) -> None:
    atomic_json(CONFIG_FILE, data)


def load_license() -> dict:
    return load_json(
        LICENSE_FILE,
        {"code": "", "tier": "FREE", "credits": 1, "lease_until": "", "pending_events": []},
    )


def save_license(data: dict) -> None:
    atomic_json(LICENSE_FILE, data)


def save_report(report: dict) -> Path:
    path = REPORT_DIR / f"{report['report_id']}.json"
    atomic_json(path, report)
    return path


def load_reports(limit: int = 30) -> list[dict]:
    ensure_dirs()
    rows: list[dict] = []
    files = sorted(REPORT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:limit]:
        value = load_json(path, {})
        if value:
            rows.append(value)
    return rows


def append_log(message: str) -> None:
    ensure_dirs()
    from datetime import datetime

    with LOG_FILE.open("a", encoding="utf-8") as stream:
        stream.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")

