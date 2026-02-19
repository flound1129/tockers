#!/usr/bin/env python3
"""
Extract TFT Set 16 data from Community Dragon and build a SQLite database
for Tocker's Trials score optimization.
"""

import json
import sqlite3
import tempfile
import urllib.request
import sys
from pathlib import Path

CDRAGON_URL = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
_TMPDIR = Path(tempfile.gettempdir())
CDRAGON_CACHE = _TMPDIR / "cdragon_tft.json"
MAP22_PATH = _TMPDIR / "map22.bin.json"
DB_PATH = Path(__file__).parent / "tft.db"
SET_NUMBER = "16"
PVE_AUGMENT_LIST_KEY = "{8885b3bc}"  # Set16_PVEMODE_Items_Augments


def fetch_cdragon_data():
    if CDRAGON_CACHE.exists():
        print(f"Using cached Community Dragon data from {CDRAGON_CACHE}")
    else:
        print(f"Downloading Community Dragon data...")
        req = urllib.request.Request(CDRAGON_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(CDRAGON_CACHE, "wb") as f:
            f.write(resp.read())
        print(f"Saved to {CDRAGON_CACHE}")

    with open(CDRAGON_CACHE, "r", encoding="utf-8") as f:
        return json.load(f)


def create_schema(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS scoring_rules;
        DROP TABLE IF EXISTS champions;
        DROP TABLE IF EXISTS champion_abilities;
        DROP TABLE IF EXISTS champion_traits;
        DROP TABLE IF EXISTS traits;
        DROP TABLE IF EXISTS trait_breakpoints;
        DROP TABLE IF EXISTS items;
        DROP TABLE IF EXISTS item_components;
        DROP TABLE IF EXISTS augments;
        DROP TABLE IF EXISTS tocker_rounds;
        DROP TABLE IF EXISTS enemy_boards;
        DROP TABLE IF EXISTS enemy_units;
        DROP TABLE IF EXISTS run_rounds;
        DROP TABLE IF EXISTS runs;

        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            ended_at TEXT,
            rounds_completed INTEGER DEFAULT 0,
            end_reason TEXT
        );

        CREATE TABLE run_rounds (
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

        CREATE TABLE scoring_rules (
            name TEXT PRIMARY KEY,
            points_per_round INTEGER,
            description TEXT
        );

        CREATE TABLE champions (
            api_name TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            cost INTEGER NOT NULL,
            role TEXT,
            hp REAL,
            armor REAL,
            magic_resist REAL,
            attack_damage REAL,
            attack_speed REAL,
            range REAL,
            mana REAL,
            initial_mana REAL,
            crit_chance REAL,
            crit_multiplier REAL
        );

        CREATE TABLE champion_abilities (
            champion_api_name TEXT NOT NULL,
            ability_name TEXT,
            ability_desc TEXT,
            variable_name TEXT NOT NULL,
            star1 REAL,
            star2 REAL,
            star3 REAL,
            FOREIGN KEY (champion_api_name) REFERENCES champions(api_name)
        );

        CREATE TABLE champion_traits (
            champion_api_name TEXT NOT NULL,
            trait_name TEXT NOT NULL,
            PRIMARY KEY (champion_api_name, trait_name),
            FOREIGN KEY (champion_api_name) REFERENCES champions(api_name)
        );

        CREATE TABLE traits (
            api_name TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE trait_breakpoints (
            trait_api_name TEXT NOT NULL,
            min_units INTEGER NOT NULL,
            max_units INTEGER,
            style INTEGER,
            variables TEXT,  -- JSON blob of variable name -> value
            PRIMARY KEY (trait_api_name, min_units),
            FOREIGN KEY (trait_api_name) REFERENCES traits(api_name)
        );

        CREATE TABLE items (
            api_name TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            is_component INTEGER NOT NULL DEFAULT 0,
            is_augment INTEGER NOT NULL DEFAULT 0,
            is_unique INTEGER NOT NULL DEFAULT 0,
            effects TEXT,  -- JSON blob of effect name -> value
            tags TEXT      -- JSON array of tags
        );

        CREATE TABLE item_components (
            item_api_name TEXT NOT NULL,
            component_api_name TEXT NOT NULL,
            FOREIGN KEY (item_api_name) REFERENCES items(api_name),
            FOREIGN KEY (component_api_name) REFERENCES items(api_name)
        );

        CREATE TABLE augments (
            api_name TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            effects TEXT,           -- JSON blob
            associated_traits TEXT, -- JSON array
            in_tockers INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE tocker_rounds (
            round_number INTEGER PRIMARY KEY,  -- 1-30
            stage INTEGER NOT NULL,
            round_in_stage INTEGER NOT NULL,
            round_type TEXT NOT NULL,  -- minion, standard, augment, boss
            augment_tier TEXT,         -- gold, prismatic
            notes TEXT
        );

        CREATE TABLE enemy_boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_name TEXT NOT NULL,
            round_number INTEGER,
            variant TEXT
        );

        CREATE TABLE enemy_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER NOT NULL,
            character TEXT NOT NULL,
            star_level INTEGER NOT NULL DEFAULT 1,
            row INTEGER,
            col INTEGER,
            items TEXT,     -- JSON array of item api names
            mod_health REAL,
            mod_ad REAL,
            mod_ap REAL,
            FOREIGN KEY (board_id) REFERENCES enemy_boards(id)
        );
    """)


def insert_scoring_rules(conn):
    rules = [
        ("unused_component", 2500, "Per component on item bench, per round"),
        ("surviving_champion", 250, "Per surviving champion, per round"),
        ("close_call", 5000, "Win with only 1 unit alive, per round"),
        ("gold_interest", 1000, "Per gold of interest earned, per round"),
        ("star_up", 1000, "Per champion star-up (one-time)"),
        ("time_bonus", 2750, "Average time bonus per round"),
    ]
    conn.executemany(
        "INSERT INTO scoring_rules (name, points_per_round, description) VALUES (?, ?, ?)",
        rules,
    )


def insert_champions(conn, set_data):
    champs = set_data.get("champions", [])
    inserted = 0
    for c in champs:
        api_name = c.get("apiName", "")
        cost = c.get("cost", 0)
        # Skip non-playable units (summons, props, PVE monsters)
        if not api_name.startswith("TFT16_"):
            continue
        if any(x in api_name for x in ["PVE", "Carousel", "Prop", "Minion", "XerathZap"]):
            continue
        if cost < 1 or cost > 7:
            continue

        stats = c.get("stats", {})
        conn.execute(
            """INSERT OR REPLACE INTO champions
               (api_name, name, cost, role, hp, armor, magic_resist,
                attack_damage, attack_speed, range, mana, initial_mana,
                crit_chance, crit_multiplier)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                api_name,
                c.get("name", "").strip(),
                cost,
                c.get("role"),
                stats.get("hp"),
                stats.get("armor"),
                stats.get("magicResist"),
                stats.get("damage"),
                stats.get("attackSpeed"),
                stats.get("range"),
                stats.get("mana"),
                stats.get("initialMana"),
                stats.get("critChance"),
                stats.get("critMultiplier"),
            ),
        )

        # Insert traits
        for trait_name in c.get("traits", []):
            conn.execute(
                "INSERT OR IGNORE INTO champion_traits (champion_api_name, trait_name) VALUES (?, ?)",
                (api_name, trait_name),
            )

        # Insert ability variables
        ability = c.get("ability", {})
        ability_name = ability.get("name", "")
        ability_desc = ability.get("desc", "")
        for var in ability.get("variables", []):
            var_name = var.get("name", "")
            values = var.get("value") or []
            star1 = values[1] if len(values) > 1 else None
            star2 = values[2] if len(values) > 2 else None
            star3 = values[3] if len(values) > 3 else None
            conn.execute(
                """INSERT INTO champion_abilities
                   (champion_api_name, ability_name, ability_desc, variable_name, star1, star2, star3)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (api_name, ability_name, ability_desc, var_name, star1, star2, star3),
            )

        inserted += 1
    return inserted


def insert_traits(conn, set_data):
    traits = set_data.get("traits", [])
    inserted = 0
    for t in traits:
        api_name = t.get("apiName", "")
        if not api_name.startswith("TFT16_"):
            continue

        conn.execute(
            "INSERT OR REPLACE INTO traits (api_name, name, description) VALUES (?, ?, ?)",
            (api_name, t.get("name", "").strip(), t.get("desc", "").strip()),
        )

        for effect in t.get("effects", []):
            variables = effect.get("variables", {})
            conn.execute(
                """INSERT OR REPLACE INTO trait_breakpoints
                   (trait_api_name, min_units, max_units, style, variables)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    api_name,
                    effect.get("minUnits"),
                    effect.get("maxUnits"),
                    effect.get("style"),
                    json.dumps(variables) if variables else None,
                ),
            )

        inserted += 1
    return inserted


def insert_items(conn, items_data):
    components_inserted = 0
    completed_inserted = 0
    augments_inserted = 0

    for item in items_data:
        api_name = item.get("apiName", "")
        tags = item.get("tags", [])
        composition = item.get("composition", [])

        is_component = 1 if "component" in tags else 0
        is_augment = 1 if any("augment" in str(t).lower() for t in tags) else 0
        is_unique = 1 if item.get("unique", False) else 0

        # Skip items that are clearly not relevant
        if not api_name or not item.get("name"):
            continue

        effects = item.get("effects", {})
        conn.execute(
            """INSERT OR REPLACE INTO items
               (api_name, name, description, is_component, is_augment, is_unique, effects, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                api_name,
                item.get("name", "").strip(),
                item.get("desc", "").strip(),
                is_component,
                is_augment,
                is_unique,
                json.dumps(effects) if effects else None,
                json.dumps(tags) if tags else None,
            ),
        )

        # Insert component recipes
        for comp in composition:
            conn.execute(
                "INSERT INTO item_components (item_api_name, component_api_name) VALUES (?, ?)",
                (api_name, comp),
            )

        if is_component:
            components_inserted += 1
        elif is_augment:
            augments_inserted += 1
        elif composition:
            completed_inserted += 1

    return components_inserted, completed_inserted, augments_inserted


def load_map22_data():
    if not MAP22_PATH.exists():
        print(f"WARNING: {MAP22_PATH} not found, skipping map22 data")
        return None
    with open(MAP22_PATH, "r") as f:
        return json.load(f)


def insert_augments(conn, cdragon_items, map22_data):
    """Insert augments from Community Dragon, marking which ones are in Tocker's."""
    # Get the Tocker's augment list from map22
    tockers_api_names = set()
    if map22_data:
        pve_list = map22_data.get(PVE_AUGMENT_LIST_KEY, {})
        for h in pve_list.get("mItems", []):
            entry = map22_data.get(h, {})
            if isinstance(entry, dict):
                name = entry.get("mName", "")
                if name:
                    tockers_api_names.add(name)

    # Insert TFT16 augments from Community Dragon (has display names/descriptions)
    inserted = 0
    for item in cdragon_items:
        api_name = item.get("apiName", "")
        if not api_name.startswith("TFT16_Augment") and not api_name.startswith("TFT16_Teamup"):
            continue

        in_tockers = 1 if api_name in tockers_api_names else 0
        effects = item.get("effects", {})
        traits = item.get("associatedTraits", [])

        conn.execute(
            """INSERT OR REPLACE INTO augments
               (api_name, name, description, effects, associated_traits, in_tockers)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                api_name,
                item.get("name", "").strip(),
                item.get("desc", "").strip(),
                json.dumps(effects) if effects else None,
                json.dumps(traits) if traits else None,
                in_tockers,
            ),
        )
        inserted += 1

    tockers_count = conn.execute(
        "SELECT COUNT(*) FROM augments WHERE in_tockers = 1"
    ).fetchone()[0]
    return inserted, tockers_count


def insert_tocker_rounds(conn):
    """Insert the 30-round Tocker's Trials structure."""
    rounds = []
    for stage in range(1, 4):
        for r in range(1, 11):
            round_num = (stage - 1) * 10 + r
            if stage == 1 and r <= 2:
                round_type = "minion"
            elif r == 5:
                round_type = "augment"
            elif r == 10:
                round_type = "boss"
            else:
                round_type = "standard"

            augment_tier = None
            if round_type == "augment":
                if stage <= 2:
                    augment_tier = "gold"
                else:
                    augment_tier = "prismatic"

            rounds.append((round_num, stage, r, round_type, augment_tier))

    conn.executemany(
        """INSERT INTO tocker_rounds
           (round_number, stage, round_in_stage, round_type, augment_tier)
           VALUES (?, ?, ?, ?, ?)""",
        rounds,
    )
    return len(rounds)


def insert_enemy_boards(conn, map22_data):
    """Insert enemy board compositions from map22.bin.json."""
    if not map22_data:
        return 0, 0

    boards_inserted = 0
    units_inserted = 0

    for key, entry in map22_data.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("__type") != "{d545dcdd}":
            continue

        name = entry.get("name", "")
        if not name.startswith("Round"):
            continue

        champions = entry.get("champions", [])
        # Only include boards that have at least one TFT16 champion
        has_tft16 = any("TFT16" in c.get("Character", "") for c in champions)
        if not has_tft16:
            continue

        # Parse round number and variant from name like "Round22_BrockAnivia"
        parts = name.split("_", 1)
        round_num = None
        variant = None
        if len(parts) >= 2:
            try:
                round_num = int(parts[0].replace("Round", ""))
            except ValueError:
                pass
            variant = parts[1]

        conn.execute(
            "INSERT INTO enemy_boards (round_name, round_number, variant) VALUES (?, ?, ?)",
            (name, round_num, variant),
        )
        board_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        boards_inserted += 1

        for champ in champions:
            character = champ.get("Character", "")
            level = champ.get("level", 1)
            row = champ.get("Row")
            col = champ.get("Col")
            items = champ.get("items", [])

            # Parse stat modifiers from buff vars
            mod_health = None
            mod_ad = None
            mod_ap = None
            for buff in champ.get("{801b0cad}", []):
                bvars = buff.get("NextBuffVars", {})
                if "Health" in bvars:
                    mod_health = bvars["Health"].get("mValue")
                if "AD" in bvars:
                    mod_ad = bvars["AD"].get("mValue")
                if "AP" in bvars:
                    mod_ap = bvars["AP"].get("mValue")

            conn.execute(
                """INSERT INTO enemy_units
                   (board_id, character, star_level, row, col, items,
                    mod_health, mod_ad, mod_ap)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    board_id,
                    character,
                    level,
                    row,
                    col,
                    json.dumps(items) if items else None,
                    mod_health,
                    mod_ad,
                    mod_ap,
                ),
            )
            units_inserted += 1

    return boards_inserted, units_inserted


def print_summary(conn):
    print("\n" + "=" * 60)
    print("DATABASE SUMMARY")
    print("=" * 60)

    # Scoring rules
    print("\n--- Scoring Rules ---")
    for row in conn.execute("SELECT name, points_per_round, description FROM scoring_rules"):
        print(f"  {row[0]:25s} {row[1]:>6,d} pts  {row[2]}")

    # Champions by cost
    print("\n--- Champions by Cost ---")
    for row in conn.execute(
        "SELECT cost, COUNT(*), GROUP_CONCAT(name, ', ') FROM champions GROUP BY cost ORDER BY cost"
    ):
        print(f"  Cost {row[0]}: {row[1]:2d} - {row[2]}")

    # Traits
    print("\n--- Traits ---")
    for row in conn.execute("SELECT name, api_name FROM traits ORDER BY name"):
        breakpoints = conn.execute(
            "SELECT min_units FROM trait_breakpoints WHERE trait_api_name = ? ORDER BY min_units",
            (row[1],),
        ).fetchall()
        bp_str = "/".join(str(b[0]) for b in breakpoints)
        print(f"  {row[0]:25s} ({bp_str})")

    # Items
    print("\n--- Items ---")
    comp_count = conn.execute("SELECT COUNT(*) FROM items WHERE is_component = 1").fetchone()[0]
    completed_count = conn.execute(
        "SELECT COUNT(*) FROM items WHERE is_component = 0 AND is_augment = 0 AND api_name IN (SELECT DISTINCT item_api_name FROM item_components)"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"  Components: {comp_count}")
    print(f"  Completed items: {completed_count}")
    print(f"  Total: {total}")

    # Augments
    print("\n--- Augments ---")
    aug_total = conn.execute("SELECT COUNT(*) FROM augments").fetchone()[0]
    aug_tockers = conn.execute("SELECT COUNT(*) FROM augments WHERE in_tockers = 1").fetchone()[0]
    print(f"  Total TFT16 augments: {aug_total}")
    print(f"  Available in Tocker's: {aug_tockers}")
    print("\n  Tocker's augments:")
    for row in conn.execute("SELECT name, api_name FROM augments WHERE in_tockers = 1 ORDER BY name"):
        print(f"    {row[0]}")

    # Enemy boards
    print("\n--- Enemy Boards ---")
    board_count = conn.execute("SELECT COUNT(*) FROM enemy_boards").fetchone()[0]
    unit_count = conn.execute("SELECT COUNT(*) FROM enemy_units").fetchone()[0]
    print(f"  Boards: {board_count}")
    print(f"  Total enemy units: {unit_count}")
    for row in conn.execute(
        "SELECT round_number, variant, (SELECT COUNT(*) FROM enemy_units WHERE board_id = enemy_boards.id) as cnt FROM enemy_boards ORDER BY round_number"
    ):
        print(f"    Round {row[0]:2d}: {row[1]:30s} ({row[2]} units)")

    # Tocker rounds
    print("\n--- Tocker's Round Structure ---")
    for row in conn.execute(
        "SELECT round_number, stage, round_in_stage, round_type, augment_tier FROM tocker_rounds ORDER BY round_number"
    ):
        aug = f" ({row[4]})" if row[4] else ""
        print(f"    {row[0]:2d}  Stage {row[1]}-{row[2]:2d}  {row[3]}{aug}")

    print(f"\nDatabase saved to: {DB_PATH}")


def main():
    data = fetch_cdragon_data()
    set_data = data["sets"][SET_NUMBER]

    map22_data = load_map22_data()

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    create_schema(conn)

    insert_scoring_rules(conn)
    print("Inserted scoring rules")

    n = insert_champions(conn, set_data)
    print(f"Inserted {n} champions")

    n = insert_traits(conn, set_data)
    print(f"Inserted {n} traits")

    comp, completed, aug = insert_items(conn, data.get("items", []))
    print(f"Inserted items: {comp} components, {completed} completed, {aug} augments")

    total_aug, tockers_aug = insert_augments(conn, data.get("items", []), map22_data)
    print(f"Inserted {total_aug} augments ({tockers_aug} in Tocker's)")

    n = insert_tocker_rounds(conn)
    print(f"Inserted {n} Tocker's rounds")

    boards, units = insert_enemy_boards(conn, map22_data)
    print(f"Inserted {boards} enemy boards with {units} units")

    conn.commit()
    print_summary(conn)
    conn.close()


if __name__ == "__main__":
    main()
