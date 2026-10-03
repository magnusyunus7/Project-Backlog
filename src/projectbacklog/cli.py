"""Command line interface.

  python -m projectbacklog sync
  python -m projectbacklog list [--sort playtime|recent|name] [--limit N]
"""

import argparse
import sys
from datetime import datetime

from .config import load_config
from .db import connect, list_games
from .steam import SteamError, get_owned_games
from .sync import SyncError, sync_library


def hours(minutes: int) -> str:
    return f"{minutes / 60:.1f}h"


def last_played(timestamp: int) -> str:
    if not timestamp:
        return "never"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def preview(names: list[str], limit: int = 10) -> str:
    shown = ", ".join(names[:limit])
    extra = len(names) - limit
    return shown + (f" ... and {extra} more" if extra > 0 else "")


def cmd_sync(args: argparse.Namespace) -> None:
    config = load_config()
    try:
        games = get_owned_games(config.api_key, config.steam_id)
    except SteamError as exc:
        raise SystemExit(f"Error: {exc}")

    conn = connect(config.db_path)
    try:
        had_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] > 0
        result = sync_library(conn, games)
    except SyncError as exc:
        raise SystemExit(f"Error: {exc}")
    finally:
        conn.close()

    print(f"Synced {result.total} games into {config.db_path}")
    if not had_games:
        print("First sync: everything was saved.")
        return
    if result.added:
        print(f"  New ({len(result.added)}): {preview(result.added)}")
    if result.restored:
        print(f"  Back in library ({len(result.restored)}): {preview(result.restored)}")
    if result.removed:
        print(f"  No longer in library ({len(result.removed)}): {preview(result.removed)}")
    if not (result.added or result.restored or result.removed):
        print("  Library unchanged (playtime was refreshed).")


def cmd_list(args: argparse.Namespace) -> None:
    config = load_config(require_steam=False)  # no Steam key needed to read the DB
    conn = connect(config.db_path)
    try:
        rows = list_games(conn, args.sort, args.limit, args.include_removed)
    finally:
        conn.close()

    if not rows:
        print("No games stored yet. Run:  python -m projectbacklog sync")
        return
    print(f"{'last played':<12}  {'playtime':>8}  name")
    for r in rows:
        flag = "" if r["in_library"] else "  (removed)"
        print(
            f"{last_played(r['last_played']):<12}  "
            f"{hours(r['playtime_minutes']):>8}  {r['name']}{flag}"
        )


def main(argv: list[str] | None = None) -> None:
    # Game names contain symbols (tm, R, CJK) that a Windows console may not
    # be able to print; replace them instead of crashing.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(prog="projectbacklog")
    sub = parser.add_subparsers(dest="command")

    sync_p = sub.add_parser("sync", help="fetch your Steam library into the local database")
    sync_p.set_defaults(func=cmd_sync)

    list_p = sub.add_parser("list", help="show games from the local database")
    list_p.add_argument("--sort", choices=["playtime", "recent", "name"], default="playtime")
    list_p.add_argument("--limit", type=int, default=20, help="0 = show all")
    list_p.add_argument("--include-removed", action="store_true")
    list_p.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()