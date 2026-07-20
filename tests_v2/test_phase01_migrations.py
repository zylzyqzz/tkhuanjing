from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).parents[1]
PHASE_TABLES = {
    "organization_members",
    "organization_member_sessions",
    "live_accounts",
    "anchor_profiles",
    "device_room_bindings",
    "device_heartbeats_v2",
}


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def reset_server_modules() -> None:
    for name in list(sys.modules):
        if name == "server" or name.startswith("server."):
            del sys.modules[name]


def table_names(path: Path) -> set[str]:
    with sqlite3.connect(path) as db:
        return {row[0] for row in db.execute("select name from sqlite_master where type='table'")}


def test_empty_database_upgrade_downgrade_and_reupgrade(tmp_path):
    database = tmp_path / "alembic-empty.sqlite3"
    os.environ["TK_DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    reset_server_modules()
    cfg = alembic_config()

    command.upgrade(cfg, "head")
    assert PHASE_TABLES <= table_names(database)
    assert "customers" in table_names(database)

    command.downgrade(cfg, "20260721_00")
    assert not (PHASE_TABLES & table_names(database))
    assert "customers" in table_names(database)

    command.upgrade(cfg, "head")
    assert PHASE_TABLES <= table_names(database)


def test_phase_models_compile_for_postgresql(tmp_path):
    os.environ["TK_DATABASE_URL"] = f"sqlite:///{(tmp_path / 'compile.sqlite3').as_posix()}"
    reset_server_modules()
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable
    from server import models as _legacy_models  # noqa: F401 - resolves FK targets
    from server.models_enterprise import AnchorProfile, DeviceHeartbeatV2, DeviceRoomBinding, LiveAccount, OrganizationMember, OrganizationMemberSession

    dialect = postgresql.dialect()
    models = (OrganizationMember, OrganizationMemberSession, LiveAccount, AnchorProfile, DeviceRoomBinding, DeviceHeartbeatV2)
    ddl = []
    for model in models:
        ddl.append(str(CreateTable(model.__table__).compile(dialect=dialect)))
        ddl.extend(str(CreateIndex(index).compile(dialect=dialect)) for index in model.__table__.indexes)
    sql = "\n".join(ddl)
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "WHERE status='active' AND binding_type='primary'" in sql
    assert all(f"CREATE TABLE {model.__tablename__}" in sql for model in models)
