import sqlite3
import pytest
from overlay.stats import ensure_stats_tables, StatsRecorder


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_stats_tables(c)
    return c


def test_ensure_creates_tables(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "runs" in tables
    assert "run_rounds" in tables


def test_ensure_idempotent(conn):
    # Calling twice should not raise
    ensure_stats_tables(conn)


def test_start_run_inserts_row(conn):
    rec = StatsRecorder(conn)
    rec.start_run()
    assert rec.active_run_id is not None
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (rec.active_run_id,)).fetchone()
    assert row is not None
    assert row["started_at"] is not None
    assert row["end_reason"] is None


def test_record_round_inserts_row(conn):
    rec = StatsRecorder(conn)
    rec.start_run()
    rec.record_round("1-1", gold=10, level=2, lives=3,
                     component_count=5, shop=["Jinx", "Vi"])
    rows = conn.execute("SELECT * FROM run_rounds WHERE run_id = ?",
                        (rec.active_run_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["round_number"] == "1-1"
    assert rows[0]["gold"] == 10
    assert rows[0]["component_count"] == 5


def test_items_built_inferred(conn):
    rec = StatsRecorder(conn)
    rec.start_run()
    rec.record_round("1-1", gold=10, level=2, lives=3,
                     component_count=5, shop=[])
    rec.record_round("1-2", gold=12, level=2, lives=3,
                     component_count=3, shop=[])  # built 2 items
    rows = conn.execute("SELECT * FROM run_rounds ORDER BY id").fetchall()
    assert rows[0]["items_built"] == 0  # no previous — first round
    assert rows[1]["items_built"] == 2


def test_life_lost_inferred(conn):
    rec = StatsRecorder(conn)
    rec.start_run()
    rec.record_round("1-1", gold=10, level=2, lives=3,
                     component_count=5, shop=[])
    rec.record_round("1-2", gold=10, level=2, lives=2,
                     component_count=5, shop=[])  # lost a life
    rows = conn.execute("SELECT * FROM run_rounds ORDER BY id").fetchall()
    assert rows[0]["life_lost"] == 0
    assert rows[1]["life_lost"] == 1


def test_end_run_updates_row(conn):
    rec = StatsRecorder(conn)
    rec.start_run()
    run_id = rec.active_run_id
    rec.record_round("1-1", gold=10, level=2, lives=3,
                     component_count=5, shop=[])
    rec.end_run("eliminated")
    assert rec.active_run_id is None
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row["end_reason"] == "eliminated"
    assert row["ended_at"] is not None
    assert row["rounds_completed"] == 1


def test_record_round_no_active_run_is_noop(conn):
    rec = StatsRecorder(conn)
    rec.record_round("1-1", gold=10, level=2, lives=3,
                     component_count=5, shop=[])
    rows = conn.execute("SELECT * FROM run_rounds").fetchall()
    assert len(rows) == 0


def test_start_run_auto_closes_previous(conn):
    rec = StatsRecorder(conn)
    rec.start_run()
    first_id = rec.active_run_id
    rec.start_run()  # auto-closes first run as abandoned
    row = conn.execute("SELECT end_reason FROM runs WHERE id = ?",
                       (first_id,)).fetchone()
    assert row["end_reason"] == "abandoned"
    assert rec.active_run_id != first_id
