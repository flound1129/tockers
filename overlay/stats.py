import json
import sqlite3
from datetime import datetime, timezone


def ensure_stats_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            ended_at TEXT,
            rounds_completed INTEGER DEFAULT 0,
            end_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS run_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES runs(id),
            round_number TEXT,
            gold INTEGER,
            level INTEGER,
            lives INTEGER,
            component_count INTEGER,
            shop TEXT,
            items_built INTEGER,
            life_lost INTEGER
        );
    """)
    conn.commit()


class StatsRecorder:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._run_id: int | None = None
        self._rounds_completed = 0
        self._prev_components: int | None = None
        self._prev_lives: int | None = None

    @property
    def active_run_id(self) -> int | None:
        return self._run_id

    def start_run(self) -> None:
        if self._run_id is not None:
            self.end_run("abandoned")
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, rounds_completed) VALUES (?, 0)",
            (now,),
        )
        self.conn.commit()
        self._run_id = cur.lastrowid
        self._rounds_completed = 0
        self._prev_components = None
        self._prev_lives = None

    def record_round(self, round_number: str, gold: int | None,
                     level: int | None, lives: int | None,
                     component_count: int, shop: list[str]) -> None:
        if self._run_id is None:
            return
        items_built = max(
            0,
            (self._prev_components if self._prev_components is not None
             else component_count) - component_count,
        )
        life_lost = (
            max(0, self._prev_lives - lives)
            if self._prev_lives is not None and lives is not None
            else 0
        )
        self.conn.execute(
            """INSERT INTO run_rounds
               (run_id, round_number, gold, level, lives, component_count,
                shop, items_built, life_lost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self._run_id, round_number, gold, level, lives, component_count,
             json.dumps(shop), items_built, life_lost),
        )
        self._rounds_completed += 1
        self.conn.execute(
            "UPDATE runs SET rounds_completed = ? WHERE id = ?",
            (self._rounds_completed, self._run_id),
        )
        self.conn.commit()
        self._prev_components = component_count
        if lives is not None:
            self._prev_lives = lives

    def end_run(self, reason: str) -> None:
        if self._run_id is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE runs SET ended_at = ?, end_reason = ? WHERE id = ?",
            (now, reason, self._run_id),
        )
        self.conn.commit()
        self._run_id = None
