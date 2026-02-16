import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnemyUnit:
    character: str
    star_level: int
    row: int | None
    col: int | None
    items: list[str]
    mod_health: float | None
    mod_ad: float | None
    mod_ap: float | None


class StrategyEngine:
    def __init__(self, db_path: str | Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def component_score(self, num_components: int, rounds_remaining: int) -> int:
        return num_components * 2500 * rounds_remaining

    def interest(self, gold: int) -> int:
        return min(gold // 10, 5)

    def get_enemy_board(self, round_number: int) -> list[EnemyUnit]:
        rows = self.conn.execute("""
            SELECT eu.character, eu.star_level, eu.row, eu.col,
                   eu.items, eu.mod_health, eu.mod_ad, eu.mod_ap
            FROM enemy_units eu
            JOIN enemy_boards eb ON eu.board_id = eb.id
            WHERE eb.round_number = ?
        """, (round_number,)).fetchall()
        return [
            EnemyUnit(
                character=r["character"],
                star_level=r["star_level"],
                row=r["row"],
                col=r["col"],
                items=json.loads(r["items"]) if r["items"] else [],
                mod_health=r["mod_health"],
                mod_ad=r["mod_ad"],
                mod_ap=r["mod_ap"],
            )
            for r in rows
        ]

    def get_round_info(self, round_number: int) -> dict | None:
        row = self.conn.execute("""
            SELECT stage, round_in_stage, round_type, augment_tier
            FROM tocker_rounds WHERE round_number = ?
        """, (round_number,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_tocker_augments(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT api_name, name, description, effects, associated_traits
            FROM augments WHERE in_tockers = 1
            ORDER BY name
        """).fetchall()
        return [dict(r) for r in rows]

    def projected_score(self, current_round: int, num_components: int,
                        gold: int, surviving_units: int) -> dict:
        rounds_remaining = 30 - current_round
        component_pts = self.component_score(num_components, rounds_remaining)
        interest_pts = self.interest(gold) * 1000 * rounds_remaining
        surviving_pts = surviving_units * 250 * rounds_remaining
        time_pts = 2750 * rounds_remaining
        return {
            "component_pts": component_pts,
            "interest_pts": interest_pts,
            "surviving_pts": surviving_pts,
            "time_pts": time_pts,
            "total": component_pts + interest_pts + surviving_pts + time_pts,
        }
