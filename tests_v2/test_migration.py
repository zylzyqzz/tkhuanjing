from __future__ import annotations

import sqlite3

from server.migrate import add_compatible_columns


def test_legacy_database_columns_are_added_without_data_loss(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("create table codes(code text primary key, tier text, credits integer, status text, created_at text)")
        conn.execute("insert into codes values('TK1-OLD', 'TK1', 1, 'available', '2026-01-01')")
        conn.commit()
    add_compatible_columns(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("select count(*) from codes").fetchone()[0] == 1
        columns = {row[1] for row in conn.execute("pragma table_info(codes)")}
        assert "batch" in columns

