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


MIGRATION_VERSION = 7


REQUIRED_COLUMNS = {
    "users": [
        "phone_country text default '+86'", "email text default ''", "company_name text default ''",
        "country text default ''", "city text default ''", "business_types text default '[]'",
        "wechat_id text default ''", "platform_account text default ''",
        "profile_completed_at text default null", "trial_granted integer default 0",
        "trial_expires_at text default null", "status text default 'active'",
        "created_at text default null", "last_active_at text default null",
    ],
    "user_sessions": [
        "user_id integer default 0", "device_id text default null", "expires_at text default null",
        "revoked integer default 0", "created_at text default null",
    ],
    "verification_codes": [
        "target text default ''", "code text default ''", "purpose text default 'register'",
        "expires_at text default null", "used integer default 0", "created_at text default null",
    ],
    "codes": ["batch text default ''", "plan_code text default ''", "duration_days integer default 0", "expires_at text default null"],
    "releases": [
        "file_size integer default 0", "channel text default 'stable'", "mandatory integer default 0",
        "minimum_version text default ''", "signature text default ''",
    ],
    "live_rooms": ["status text default 'active'"],
    "customers": [
        "tenant_code text default ''", "short_name text default ''", "logo_url text default ''",
        "timezone text default 'Asia/Shanghai'", "plan_code text default 'trial'",
        "device_limit integer default 3", "member_limit integer default 3",
        "subscription_starts_at text default null", "subscription_expires_at text default null",
        "grace_ends_at text default null", "wecom_webhook_encrypted text default ''",
        "alert_settings_json text default '{}'",
    ],
    "admins": [
        "customer_id integer default null", "role text default 'platform_super'",
        "display_name text default ''", "phone text default ''", "last_login_at text default null",
        "last_login_ip text default ''", "password_changed_at text default null",
        "two_factor_enabled integer default 0",
    ],
    "devices": [
        "status text default 'active'", "notes text default ''",
        "free_trial_started_at text default null", "free_trial_expires_at text default null",
        "target_region_id text default 'us-los-angeles'",
        "user_id integer default null",
        "streaming_account_id integer default null", "display_name text default ''",
        "store_name text default ''", "location text default ''", "owner_name text default ''",
        "tags_json text default '[]'", "live_state text default 'idle'",
        "readiness_state text default 'unknown'", "studio_state text default 'unknown'",
        "last_heartbeat_at text default null", "last_report_id text default null",
        "last_report_at text default null", "module_summary_json text default '{}'",
        "state_version integer default 0",
    ],
    "check_reports": [
        "schema_version integer default 3", "target_region_id text default 'us-los-angeles'",
        "network_snapshot_json text default '{}'", "ip_profile_json text default '{}'",
        "streaming_profiles_json text default '[]'", "data_sources_json text default '[]'", "repair_events_json text default '[]'",
        "run_mode text default 'daily_preflight'", "environment_snapshot_json text default '{}'",
        "device_snapshot_json text default '{}'", "check_logs_json text default '[]'",
        "before_snapshot_json text default '{}'", "after_snapshot_json text default '{}'",
        "confidence_summary_json text default '{}'",
        "readiness_level text default 'INCOMPLETE'", "blocking_count integer default 0",
        "high_risk_count integer default 0", "test_mode text default 'standard'",
        "baseline_delta_json text default '{}'", "source_health_json text default '{}'", "issue_tags_json text default '[]'",
        "environment_summary text default '检测未完成'", "network_summary text default '检测未完成'",
        "hardware_summary text default '仅供参考'", "next_action text default ''", "ai_analysis_json text default '{}'",
    ],
    "check_items": [
        "evidence_json text default '[]'", "metrics_json text default '{}'", "diagnosis text default ''",
        "impact text default ''", "solutions_json text default '[]'", "data_source text default 'local'",
        "confidence text default 'high'", "repair_id text default ''", "repair_level text default 'manual'",
        "verification_json text default '[]'",
        "duration_ms integer default 0", "error_code text default ''",
        "priority text default 'INFORMATIONAL'", "blocking integer default 0",
        "repair_outcome_json text default '{}'",
        "sampled_at text default ''", "recheck_of text default ''", "retryable integer default 0",
        "technical_error text default ''", "restart_required integer default 0",
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
            with sqlite3.connect(target) as conn:
                conn.execute("create table if not exists schema_migrations (version integer primary key, applied_at text not null)")
                current = conn.execute("select coalesce(max(version),0) from schema_migrations").fetchone()[0]
            if current < MIGRATION_VERSION:
                snapshot = backup(target)
                try:
                    add_compatible_columns(target)
                    with sqlite3.connect(target) as conn:
                        conn.execute("insert or replace into schema_migrations(version,applied_at) values(?,?)", (MIGRATION_VERSION, datetime.now().isoformat()))
                        conn.commit()
                except Exception:
                    shutil.copy2(snapshot, target)
                    raise
    # Phase 0+ enterprise tables are owned by Alembic revisions. Keep this
    # compatibility helper limited to the V1 schema for old SQLite installs.
    enterprise_tables = {"organization_members", "organization_member_sessions", "live_accounts", "anchor_profiles", "device_room_bindings", "device_heartbeats_v2"}
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in enterprise_tables])
    with SessionLocal() as db:
        seed_admin(db)
        seed_defaults(db)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="迁移 TK 平台数据库到 V2")
    parser.add_argument("--legacy", type=Path)
    args = parser.parse_args()
    print(run(args.legacy))
