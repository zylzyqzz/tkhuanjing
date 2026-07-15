from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import get_settings
from .database import Base, engine
from . import models  # noqa: F401
from .database import SessionLocal
from .security import seed_admin
from .services import seed_defaults


REQUIRED_COLUMNS = {
    "codes": ["batch text default ''", "plan_code text default ''", "duration_days integer default 0", "expires_at text default null"],
    "releases": [
        "file_size integer default 0", "channel text default 'stable'", "mandatory integer default 0",
        "minimum_version text default ''", "signature text default ''",
    ],
    "live_rooms": ["status text default 'active'"],
    "devices": ["status text default 'active'", "notes text default ''", "free_trial_started_at text default null", "free_trial_expires_at text default null", "target_region_id text default 'us-los-angeles'"],
    "check_reports": [
        "schema_version integer default 3", "target_region_id text default 'us-los-angeles'",
        "network_snapshot_json text default '{}'", "ip_profile_json text default '{}'",
        "streaming_profiles_json text default '[]'", "data_sources_json text default '[]'", "repair_events_json text default '[]'",
        "run_mode text default 'daily_preflight'", "environment_snapshot_json text default '{}'",
        "device_snapshot_json text default '{}'", "check_logs_json text default '[]'",
        "before_snapshot_json text default '{}'", "after_snapshot_json text default '{}'",
        "confidence_summary_json text default '{}'",
    ],
    "check_items": [
        "evidence_json text default '[]'", "metrics_json text default '{}'", "diagnosis text default ''",
        "impact text default ''", "solutions_json text default '[]'", "data_source text default 'local'",
        "confidence text default 'high'", "repair_id text default ''", "repair_level text default 'manual'",
        "verification_json text default '[]'",
        "duration_ms integer default 0", "error_code text default ''",
    ],
}


def sqlite_target() -> Path | None:
    url = get_settings().database_url
    return Path(url.removeprefix("sqlite:///")) if url.startswith("sqlite:///") else None


def backup(path: Path) -> Path:
    target = get_settings().backups_dir / f"pre-v2-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


def add_compatible_columns(path: Path) -> None:
    if not path.exists():
        return
    with sqlite3.connect(path) as conn:
        for table, definitions in REQUIRED_COLUMNS.items():
            exists = conn.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
            if not exists:
                continue
            names = {row[1] for row in conn.execute(f"pragma table_info({table})")}
            for definition in definitions:
                if definition.split()[0] not in names:
                    conn.execute(f"alter table {table} add column {definition}")
        conn.commit()


def run(legacy: Path | None = None) -> Path | None:
    target = sqlite_target()
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        if legacy and legacy.exists() and not target.exists():
            shutil.copy2(legacy, target)
        if target.exists():
            backup(target)
            add_compatible_columns(target)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_admin(db)
        seed_defaults(db)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="迁移 TK 平台数据库到 V2")
    parser.add_argument("--legacy", type=Path)
    args = parser.parse_args()
    print(run(args.legacy))
