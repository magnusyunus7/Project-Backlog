"""Command line interface.

  python -m projectbacklog sync
  python -m projectbacklog label
  python -m projectbacklog pick --minutes 90
  python -m projectbacklog list [--sort playtime|recent|name] [--limit N] [--status S]
  python -m projectbacklog status "Elden Ring" finished
"""

import argparse
import sys
import time

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
from .picker import confirm_session, find_stale_playing
from .scoring import GameFacts, rank_games
from .steam import SteamError, get_owned_games
from .sync import SyncError, sync_library


def preview(names: list[str], limit: int = 10) -> str:
    shown = ", ".join(names[:limit])
    extra = len(names) - limit
    return shown + (f" ... and {extra} more" if extra > 0 else "")


def status_arg(value: str) -> str:
    """Accept 'Not-Started', 'not started', 'not_started' alike."""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number")
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


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


def cmd_pick(args: argparse.Namespace) -> None:
    config = load_config(require_steam=False)
    now = int(time.time())

    conn = connect(config.db_path)
    try:
        rows = list_games(conn, limit=0)

        # Labels can go stale. Ask about them if we can; otherwise just warn.
        stale = find_stale_playing(rows, now)
        if stale:
            if not args.no_prompt and sys.stdin.isatty():
                confirm_session(conn, stale, now)
                rows = list_games(conn, limit=0)  # labels may have changed
                print()
            else:
                print(
                    f"Heads up: {len(stale)} game(s) marked Playing haven't been launched in "
                    f"over a year: {preview([r['name'] for r in stale], 5)}.\n"
                    "Run `pick` in a terminal to review them, or fix one with: "
                    'python -m projectbacklog status "NAME" dropped\n'
                )
    finally:
        conn.close()

    games = [
        GameFacts(r["name"], r["status"], r["playtime_minutes"],
                  r["playtime_2weeks_minutes"], r["last_played"])
        for r in rows
    ]
    ranked = rank_games(games, args.minutes, now, limit=args.top)
    unlabeled = sum(1 for g in games if g.status is None and g.playtime_minutes > 0)

    if not ranked:
        if not games:
            print("Your library is empty. Run:  python -m projectbacklog sync")
        elif unlabeled:
            print("Nothing to recommend yet: only games you've labeled are considered.")
            print(f"{unlabeled} played game(s) are unlabeled. Run:  python -m projectbacklog label")
        else:
            print("Nothing to recommend: everything you've labeled is finished, dropped or "
                  "endless.\nMark something as playing or not_started with:  "
                  'python -m projectbacklog status "NAME" playing')
        return

    when = f"{args.minutes} min" if args.minutes else "no time limit"
    print(f"Tonight ({when}): your top {len(ranked)}\n")
    for i, (game, score) in enumerate(ranked, 1):
        print(f"{i}. {game.name}   (score {score.value:.1f})")
        for reason in score.reasons:
            print(f"     - {reason}")
        print()
    if unlabeled:
        print(f"{unlabeled} played game(s) are unlabeled and weren't considered. "
              "Run:  python -m projectbacklog label")


def main(argv: list[str] | None = None) -> None:
    # Game names contain symbols (tm, R, CJK) that a Windows console may not
    # be able to print; replace them instead of crashing.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(prog="projectbacklog")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("sync", help="fetch your Steam library into the local database")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("pick", help="what should I play tonight?")
    p.add_argument("--minutes", type=positive_int, default=None,
                   help="how much time you have (default: no limit)")
    p.add_argument("--top", type=positive_int, default=3, help="how many to show (default 3)")
    p.add_argument("--no-prompt", action="store_true",
                   help="don't ask about stale labels, just warn")
    p.set_defaults(func=cmd_pick)

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