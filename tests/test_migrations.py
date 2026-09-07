"""Forward-only schema migrations via `PRAGMA user_version` (docs/roadmap.md
"Scope revision", migrations workstream)."""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from cohort.migrations import MIGRATIONS, Migration, MigrationError, apply_migrations


def test_baseline_creates_the_expected_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "graph.sqlite")
    apply_migrations(conn)
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"nodes", "node_authorship", "edges", "edge_authorship", "agents"} <= tables
    assert "payload_hash" in {r[1] for r in conn.execute("PRAGMA table_info(nodes)").fetchall()}
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    conn.close()


def test_reopening_an_already_migrated_db_is_a_no_op(tmp_path):
    conn = sqlite3.connect(tmp_path / "graph.sqlite")
    apply_migrations(conn)
    version_after_first = conn.execute("PRAGMA user_version").fetchone()[0]
    apply_migrations(conn)  # must not re-run any migration or raise
    assert conn.execute("PRAGMA user_version").fetchone()[0] == version_after_first
    conn.close()


def test_out_of_order_migration_raises(tmp_path):
    conn = sqlite3.connect(tmp_path / "graph.sqlite")
    migrations = [
        Migration(1, "baseline", "CREATE TABLE a (id TEXT);"),
        Migration(3, "skips-two", "CREATE TABLE c (id TEXT);"),
    ]
    with pytest.raises(MigrationError, match="not the next version"):
        apply_migrations(conn, migrations)
    conn.close()


def test_a_later_migration_adds_a_column_with_no_data_loss(tmp_path):
    conn = sqlite3.connect(tmp_path / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    v1 = [Migration(1, "baseline", "CREATE TABLE widgets (id TEXT PRIMARY KEY);")]
    apply_migrations(conn, v1)
    conn.execute("INSERT INTO widgets (id) VALUES ('a')")
    conn.commit()

    v2 = [*v1, Migration(2, "add-color", "ALTER TABLE widgets ADD COLUMN color TEXT;")]
    apply_migrations(conn, v2)

    row = conn.execute("SELECT * FROM widgets WHERE id='a'").fetchone()
    assert row["id"] == "a"
    assert row["color"] is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


def test_migration_2_backfills_payload_hash_for_pre_existing_rows(tmp_path):
    conn = sqlite3.connect(tmp_path / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    apply_migrations(conn, MIGRATIONS[:1])  # baseline only
    conn.execute(
        "INSERT INTO nodes (id, type, status, payload, created_seq, updated_seq) "
        "VALUES ('claim:x', 'claim', 'proposed', '{\"text\": \"hi\"}', 0, 0)"
    )
    conn.commit()

    apply_migrations(conn, MIGRATIONS)  # upgrade to migration 2

    row = conn.execute("SELECT payload_hash FROM nodes WHERE id='claim:x'").fetchone()
    expected = hashlib.sha256(b'{"text": "hi"}').hexdigest()
    assert row["payload_hash"] == expected
    conn.close()


def test_backfill_runs_once_per_migration(tmp_path):
    conn = sqlite3.connect(tmp_path / "graph.sqlite")
    calls = []
    migrations = [
        Migration(1, "baseline", "CREATE TABLE widgets (id TEXT);",
                   backfill=lambda c: calls.append("backfilled")),
    ]
    apply_migrations(conn, migrations)
    apply_migrations(conn, migrations)  # second call: already applied, no re-run
    assert calls == ["backfilled"]
    conn.close()
