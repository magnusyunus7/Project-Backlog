"""Throwaway check: run the scorer on your real database.

    python -m projectbacklog.try_scoring --minutes 90

Milestone 5 replaces this with the real `pick` command; delete it then.
"""

import argparse
import sys

from .config import load_config
from .db import connect, list_games
from .scoring import GameFacts, exclusion_reason, rank_games


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=None, help="time you have tonight")
    parser.add_argument("--top", type=int, default=10, help="how many to show")
    args = parser.parse_args()

    config = load_config(require_steam=False)
    conn = connect(config.db_path)
    try:
        rows = list_games(conn, limit=0)
    finally:
        conn.close()

    games = [
        GameFacts(r["name"], r["status"], r["playtime_minutes"],
                  r["playtime_2weeks_minutes"], r["last_played"])
        for r in rows
    ]
    ranked = rank_games(games, args.minutes, limit=0)

    when = f"{args.minutes} min" if args.minutes else "no time limit"
    print(f"Top {min(args.top, len(ranked))} of {len(ranked)} candidates ({when}):\n")
    for i, (game, score) in enumerate(ranked[: args.top], 1):
        print(f"{i:>2}. {score.value:6.1f}  {game.name}")
        for reason in score.reasons:
            print(f"            - {reason}")

    unlabeled = [g for g in games if g.status is None and g.playtime_minutes > 0]
    print(f"\nNot considered: {len(games) - len(ranked)} games "
          f"({len(unlabeled)} played but unlabeled; run `label` to include them).")
    if not ranked:
        print("Nothing to recommend yet: label some games as playing or not_started.")


if __name__ == "__main__":
    main()