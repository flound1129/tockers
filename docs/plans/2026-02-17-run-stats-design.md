# Run Stats & Strategy Auto-Update — Design

**Goal:** Automatically record per-round game stats during each run, then after each run have Claude analyze the data and rewrite `docs/strategy.md` with refined findings.

**Architecture:** Two new tables in `tft.db` (`runs`, `run_rounds`). `vision_loop` detects round transitions and run end/start, writing snapshots via a `StatsRecorder`. At run end, `StrategyEngine.update_strategy()` queries recent runs, calls Claude, and overwrites `strategy.md`.

**Tech Stack:** SQLite (existing tft.db), Python threading, Anthropic API (existing client)

---

## Schema

```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,        -- ISO timestamp
    ended_at TEXT,
    rounds_completed INTEGER,
    end_reason TEXT         -- 'eliminated' | 'completed' | 'abandoned'
);

CREATE TABLE run_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES runs(id),
    round_number TEXT,      -- e.g. "1-3"
    gold INTEGER,
    level INTEGER,
    lives INTEGER,
    component_count INTEGER,
    shop TEXT,              -- JSON list of champion names
    items_built INTEGER,    -- inferred: component_count delta from previous round
    life_lost INTEGER       -- inferred: 1 if lives decreased, else 0
);
```

## Detection Logic (vision_loop)

- **Run start**: `round_number` changes to `"1-1"` → insert new `runs` row
- **Round transition**: `round_number` changes → save snapshot of previous round to `run_rounds`
- **Run end (eliminated)**: `lives` drops to 0 → close run as `'eliminated'`, trigger strategy update
- **Run end (completed)**: round 30 snapshot saved → close run as `'completed'`, trigger strategy update
- **Abandoned**: app quit with open run → close as `'abandoned'`, skip strategy update

`items_built` = previous `component_count` − current `component_count` (clamped to 0 if negative)
`life_lost` = 1 if previous `lives` > current `lives`, else 0

## Strategy Update Flow

Triggered in a background thread after each non-abandoned run:

1. Query last 20 completed/eliminated runs with their round snapshots
2. Format as a markdown summary (one table per run: round, gold, components, items_built, life_lost)
3. POST to Claude with current `strategy.md` + data, prompt asks for a rewritten strategy guide
4. Overwrite `docs/strategy.md` with response
5. Reload `_STRATEGY` module-level variable so companion window picks it up

## Components

- `overlay/stats.py` — `StatsRecorder` class: `start_run()`, `record_round()`, `end_run()`, `close()`
- `overlay/strategy.py` — add `update_strategy(runs_data)` method + `reload_strategy()` helper
- `overlay/main.py` — wire `StatsRecorder` into `vision_loop`, detect transitions, trigger update
- `build_db.py` — add schema migration to create new tables if not exist
- `tests/test_stats.py` — unit tests for StatsRecorder using `:memory:` DB
