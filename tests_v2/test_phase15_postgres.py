from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker


POSTGRES_URL = os.getenv("TK_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TK_TEST_POSTGRES_URL is required for PostgreSQL integration")


def _migrate_clean_database(root: Path):
    parsed = make_url(POSTGRES_URL)
    if "test" not in (parsed.database or "").lower():
        pytest.fail("PostgreSQL concurrency tests refuse to reset a database without 'test' in its name")
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    environment = dict(os.environ, TK_DATABASE_URL=POSTGRES_URL)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return engine


def test_postgresql_binding_concurrency_is_transactionally_safe():
    root = Path(__file__).parents[1]
    engine = _migrate_clean_database(root)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    from server.enterprise.bindings import create_binding_transaction
    from server.enterprise.common import token_hash
    from server.models import Customer, Device, LiveRoom
    from server.models_enterprise import DeviceRoomBinding, OrganizationMember

    with Session() as db:
        organization = Customer(name="PostgreSQL 并发验收企业", tenant_code="PG-CONCURRENCY", organization_code="PG-CONCURRENCY")
        db.add(organization)
        db.flush()
        member = OrganizationMember(
            organization_id=organization.id,
            username="pg-owner",
            password_hash="not-used-in-direct-service-test",
            role="owner",
        )
        room_a = LiveRoom(customer_id=organization.id, name="并发直播间 A")
        room_b = LiveRoom(customer_id=organization.id, name="并发直播间 B")
        room_c = LiveRoom(customer_id=organization.id, name="并发直播间 C")
        db.add_all([member, room_a, room_b, room_c])
        db.flush()
        devices = [
            Device(device_id="DEVICE-PG-CONCURRENT-1", token_hash=token_hash("pg-token-1")),
            Device(device_id="DEVICE-PG-CONCURRENT-2", token_hash=token_hash("pg-token-2")),
        ]
        db.add_all(devices)
        db.commit()
        organization_id = organization.id
        member_id = member.id
        room_ids = (room_a.id, room_b.id, room_c.id)

    def compete(device_id: str, room_id: int, barrier: threading.Barrier) -> str:
        with Session() as db:
            try:
                barrier.wait(timeout=5)
                create_binding_transaction(
                    db,
                    device_id=device_id,
                    organization_id=organization_id,
                    member_id=member_id,
                    room_id=room_id,
                    account_id=None,
                    anchor_id=None,
                    binding_type="primary",
                    reason="PostgreSQL 并发测试",
                )
                time.sleep(0.2)
                db.commit()
                return "success"
            except (IntegrityError, OperationalError):
                db.rollback()
                return "conflict"

    same_room_barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda values: compete(*values, same_room_barrier),
                [
                    ("DEVICE-PG-CONCURRENT-1", room_ids[0]),
                    ("DEVICE-PG-CONCURRENT-2", room_ids[0]),
                ],
            )
        )
    assert sorted(outcomes) == ["conflict", "success"]

    with Session() as db:
        winner = db.scalar(
            select(DeviceRoomBinding).where(
                DeviceRoomBinding.room_id == room_ids[0],
                DeviceRoomBinding.status == "active",
                DeviceRoomBinding.binding_type == "primary",
            )
        )
        assert winner is not None
        winning_device_id = winner.device_id

    same_device_barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda values: compete(*values, same_device_barrier),
                [
                    (winning_device_id, room_ids[1]),
                    (winning_device_id, room_ids[2]),
                ],
            )
        )
    assert sorted(outcomes) == ["conflict", "success"]

    with Session() as db:
        active = db.scalars(
            select(DeviceRoomBinding).where(
                DeviceRoomBinding.device_id == winning_device_id,
                DeviceRoomBinding.status == "active",
                DeviceRoomBinding.binding_type == "primary",
            )
        ).all()
        assert len(active) == 1
        assert active[0].room_id in {room_ids[1], room_ids[2]}
    engine.dispose()


def test_postgresql_baseline_upgrade_and_closeout_downgrade_are_reversible():
    root = Path(__file__).parents[1]
    parsed = make_url(POSTGRES_URL)
    if "test" not in (parsed.database or "").lower():
        pytest.fail("PostgreSQL migration tests refuse to reset a database without 'test' in its name")
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    environment = dict(os.environ, TK_DATABASE_URL=POSTGRES_URL)
    for target in ("20260721_02", "head", "20260721_03", "head"):
        command = "downgrade" if target == "20260721_03" else "upgrade"
        subprocess.run(
            [sys.executable, "-m", "alembic", command, target],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        epoch = connection.execute(text("SELECT value FROM settings WHERE key='feature_config_epoch'")).scalar_one()
    assert version == "20260721_04"
    assert int(epoch) >= 1
    engine.dispose()
