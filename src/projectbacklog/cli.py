"""Command line interface.

  python -m projectbacklog sync
  python -m projectbacklog list [--sort playtime|recent|name] [--limit N] [--status S]
  python -m projectbacklog status "Elden Ring" finished
  python -m projectbacklog label
"""

import argparse
import sys

from .config import load_config
from .db import connect, list_games
from .fmt import hours, last_played, status_text
from .labels import (
    STATUSES,
    clear_status,
    find_games,
    label_session,
    set_status,
    unlabeled_games,
)
from .steam import SteamError, get_owned_games
from .sync import SyncError, sync_library


def preview(names: list[str], limit: int = 10) -> str:
    shown = ", ".join(names[:limit])
    extra = len(names) - limit
    return shown + (f" ... and {extra} more" if extra > 0 else "")


def status_arg(value: str) -> str:
    """Accept 'Not-Started', 'not started', 'not_started' alike."""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


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
        rows = list_games(conn, args.sort, args.limit, args.include_removed, args.status)
    finally:
        conn.close()

    if not rows:
        if args.status:
            print(f"No games with status '{args.status}'.")
        else:
            print("No games stored yet. Run:  python -m projectbacklog sync")
        return
    print(f"{'last played':<12}  {'playtime':>8}  {'status':<11}  name")
    for r in rows:
        flag = "" if r["in_library"] else "  (removed)"
        print(
            f"{last_played(r['last_played']):<12}  "
            f"{hours(r['playtime_minutes']):>8}  "
            f"{status_text(r['status']):<11}  {r['name']}{flag}"
        )


def cmd_status(args: argparse.Namespace) -> None:
    config = load_config(require_steam=False)
    conn = connect(config.db_path)
    try:
        matches = find_games(conn, args.game)
        if not matches:
            raise SystemExit(
                f'No game matching "{args.game}". '
                "Try: python -m projectbacklog list --limit 0"
            )
        if len(matches) > 1:
            lines = [f"  {m['appid']:>8}  {m['name']}" for m in matches[:10]]
            more = f"\n  ... and {len(matches) - 10} more" if len(matches) > 10 else ""
            raise SystemExit(
                f'{len(matches)} games match "{args.game}". Be more specific, '
                "or use the app id:\n" + "\n".join(lines) + more
            )
        game = matches[0]
        if args.value == "clear":
            clear_status(conn, game["appid"], game["source"])
            print(f"{game['name']}: label cleared")
        else:
            set_status(conn, game["appid"], args.value, game["source"])
            print(f"{game['name']}: {status_text(args.value)}")
    finally:
        conn.close()


def cmd_label(args: argparse.Namespace) -> None:
    config = load_config(require_steam=False)
    conn = connect(config.db_path)
    try:
        rows = unlabeled_games(conn, args.limit, args.include_unplayed)
        if not rows:
            print("Nothing left to label. (Never-launched games are skipped; "
                  "use --include-unplayed to include them.)")
            return
        done = label_session(conn, rows)
        print(f"\nLabeled {done} game(s).")
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    # Game names contain symbols (tm, R, CJK) that a Windows console may not
    # be able to print; replace them instead of crashing.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(prog="projectbacklog")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("sync", help="fetch your Steam library into the local database")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("list", help="show games from the local database")
    p.add_argument("--sort", choices=["playtime", "recent", "name"], default="playtime")
    p.add_argument("--limit", type=int, default=20, help="0 = show all")
    p.add_argument("--status", type=status_arg, choices=[*STATUSES, "unlabeled"],
                   help="only show games with this label")
    p.add_argument("--include-removed", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="set (or clear) the label of one game")
    p.add_argument("game", help="app id, or all/part of the game's name")
    p.add_argument("value", type=status_arg, choices=[*STATUSES, "clear"])
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("label", help="label your unlabeled games one by one")
    p.add_argument("--limit", type=int, default=30, help="0 = all (default 30)")
    p.add_argument("--include-unplayed", action="store_true")
    p.set_defaults(func=cmd_label)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()