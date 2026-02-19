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
            life_lost INTEGER,
            board_champions TEXT,
            bench_champions TEXT,
            projected_score INTEGER,
            star_ups INTEGER DEFAULT 0
        );
    """)
    # Add columns if upgrading from older schema
    for col, coltype in [
        ("board_champions", "TEXT"),
        ("bench_champions", "TEXT"),
        ("projected_score", "INTEGER"),
        ("star_ups", "INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE run_rounds ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


class StatsRecorder:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._run_id: int | None = None
        self._rounds_completed = 0
        self._prev_components: int | None = None
        self._prev_lives: int | None = None
        self._prev_champion_stars: dict[str, int] = {}

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
        self._prev_champion_stars = {}

    def record_round(self, round_number: str, gold: int | None,
                     level: int | None, lives: int | None,
                     component_count: int, shop: list[str],
                     board_champions: list | None = None,
                     bench_champions: list | None = None,
                     projected_score: int | None = None) -> None:
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
        # Track star-ups: count champions with stars > what we saw last round
        star_ups = self._count_star_ups(board_champions, bench_champions)
        board_json = json.dumps(
            [{"name": m.name, "stars": m.stars} for m in (board_champions or [])]
        )
        bench_json = json.dumps(
            [{"name": m.name, "stars": m.stars} for m in (bench_champions or [])]
        )
        self.conn.execute(
            """INSERT INTO run_rounds
               (run_id, round_number, gold, level, lives, component_count,
                shop, items_built, life_lost, board_champions, bench_champions,
                projected_score, star_ups)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self._run_id, round_number, gold, level, lives, component_count,
             json.dumps(shop), items_built, life_lost, board_json, bench_json,
             projected_score, star_ups),
        )
        self._prev_champion_stars = self._build_star_map(
            board_champions, bench_champions
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

    @staticmethod
    def _build_star_map(board: list | None, bench: list | None) -> dict[str, int]:
        """Build {champion_name: max_stars} from board + bench."""
        stars: dict[str, int] = {}
        for m in (board or []) + (bench or []):
            stars[m.name] = max(stars.get(m.name, 0), m.stars)
        return stars

    def _count_star_ups(self, board: list | None, bench: list | None) -> int:
        """Count how many champions gained a star since last round."""
        current = self._build_star_map(board, bench)
        count = 0
        for name, stars in current.items():
            prev = self._prev_champion_stars.get(name, 0)
            if stars > prev and prev > 0:
                count += stars - prev
        return count

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
