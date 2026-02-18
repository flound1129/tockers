import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic

from overlay.config import CLAUDE_MODEL
from overlay.stats import ensure_stats_tables

_STRATEGY_FILE = Path(__file__).parent.parent / "docs" / "strategy.md"


def _load_strategy() -> str:
    try:
        return _STRATEGY_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


_STRATEGY = _load_strategy()


def reload_strategy() -> None:
    global _STRATEGY
    _STRATEGY = _load_strategy()


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
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        ensure_stats_tables(self.conn)

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

    def ask_claude(self, game_state_summary: str, question: str,
               history: list[dict] | None = None) -> str:
        """Ask Claude for complex strategy advice. Returns advice text."""
        client = Anthropic()

        system = _STRATEGY or (
            "You are a TFT Tocker's Trials score optimizer. Be concise."
        )

        new_message = {
            "role": "user",
            "content": f"Game state:\n{game_state_summary}\n\nQuestion: {question}",
        }
        messages = list(history or []) + [new_message]

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=system,
            messages=messages,
        )
        text = response.content[0].text
        if response.stop_reason == "max_tokens":
            text += " [response truncated]"
        return text

    def update_strategy(self) -> None:
        """Query recent runs, ask Claude to refine docs/strategy.md, reload in memory."""
        runs = self.conn.execute("""
            SELECT id, started_at, rounds_completed, end_reason
            FROM runs
            WHERE end_reason IS NOT NULL
              AND end_reason != 'abandoned'
            ORDER BY id DESC LIMIT 20
        """).fetchall()

        if not runs:
            return

        lines = ["# Run History Summary\n"]
        for run in runs:
            lines.append(
                f"## Run {run['id']} ({run['end_reason']}, "
                f"{run['rounds_completed']} rounds)"
            )
            lines.append(
                "| Round | Gold | Level | Lives | Components | "
                "Items Built | Life Lost |"
            )
            lines.append(
                "|-------|------|-------|-------|------------|"
                "-------------|-----------|"
            )
            rounds = self.conn.execute("""
                SELECT round_number, gold, level, lives,
                       component_count, items_built, life_lost
                FROM run_rounds WHERE run_id = ? ORDER BY id
            """, (run["id"],)).fetchall()
            for r in rounds:
                lines.append(
                    f"| {r['round_number']} | {r['gold']} | {r['level']} "
                    f"| {r['lives']} | {r['component_count']} "
                    f"| {r['items_built']} | {r['life_lost']} |"
                )
            lines.append("")

        run_summary = "\n".join(lines)
        current_strategy = (
            _STRATEGY_FILE.read_text(encoding="utf-8")
            if _STRATEGY_FILE.exists() else ""
        )

        client = Anthropic()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=(
                "You are a TFT Tocker's Trials strategy optimizer. "
                "Analyze the run history and rewrite the strategy guide to "
                "reflect findings. Keep the same markdown format. "
                "Be concise and fact-driven. Only update sections where the "
                "data shows clear patterns."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Current strategy guide:\n\n{current_strategy}\n\n"
                    f"Run history:\n\n{run_summary}\n\n"
                    "Rewrite the strategy guide incorporating findings from "
                    "the run history."
                ),
            }],
        )
        if response.stop_reason == "max_tokens":
            import logging
            logging.warning("update_strategy: Claude response truncated at max_tokens; strategy.md not updated")
            return
        new_strategy = response.content[0].text
        _STRATEGY_FILE.write_text(new_strategy, encoding="utf-8")
        reload_strategy()
