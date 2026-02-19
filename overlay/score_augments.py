"""One-shot script to score all Tocker's augments via Claude API.

Usage: python -m overlay.score_augments
"""
import sys
from pathlib import Path

from overlay.config import DB_PATH
from overlay.strategy import StrategyEngine


def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    engine = StrategyEngine(DB_PATH)
    augments = engine.get_tocker_augments()
    print(f"Found {len(augments)} Tocker's augments to score")

    print("Calling Claude API to score augments...")
    scores = engine.score_all_augments()

    if not scores:
        print("No scores returned", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'Augment':<35} {'Score':>5}  Rank")
    print("-" * 50)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    for i, (name, score) in enumerate(ranked, 1):
        print(f"{name:<35} {score:>5.0f}  #{i}")

    print(f"\nScored {len(scores)}/{len(augments)} augments")
    print(f"Scores saved to {DB_PATH}")


if __name__ == "__main__":
    main()
