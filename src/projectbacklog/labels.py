"""Your own labels (status per game).

Everything here writes to user_state, which `sync` never touches.
"""

import sqlite3
import time
from collections.abc import Callable

from .fmt import hours, last_played

STATUSES = ("not_started", "playing", "finished", "dropped", "endless")

SESSION_KEYS = {
    "f": "finished",
    "p": "playing",
    "d": "dropped",
    "e": "endless",
    "n": "not_started",
}


def _check(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unknown status {status!r}; expected one of {STATUSES}")


def find_games(conn: sqlite3.Connection, query: str, source: str = "owned") -> list[sqlite3.Row]:
    """Find games by app id, exact name, or part of a name (in that order).

    Returns every match at the first level that finds anything, so the caller
    can tell "exactly one" from "ambiguous" from "none".
    """
    query = query.strip()
    if not query:
        return []

    base = "SELECT * FROM games WHERE source = ? AND in_library = 1"

    if query.isdigit():
        rows = conn.execute(f"{base} AND appid = ?", (source, int(query))).fetchall()
        if rows:
            return rows

    exact = conn.execute(f"{base} AND lower(name) = lower(?)", (source, query)).fetchall()
    if exact:
        return exact

    # instr() instead of LIKE so "%" and "_" in a search aren't treated as wildcards.
    return conn.execute(
        f"{base} AND instr(lower(name), lower(?)) > 0 "
        "ORDER BY playtime_minutes DESC, name COLLATE NOCASE",
        (source, query),
    ).fetchall()


def set_status(
    conn: sqlite3.Connection,
    appid: int,
    status: str,
    source: str = "owned",
    now: int | None = None,
) -> None:
    _check(status)
    now = int(time.time()) if now is None else now
    with conn:
        conn.execute(
            """
            INSERT INTO user_state (appid, source, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(appid, source) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (appid, source, status, now),
        )


def clear_status(
    conn: sqlite3.Connection, appid: int, source: str = "owned", now: int | None = None
) -> None:
    """Remove the label but keep the row, so notes and other fields survive."""
    now = int(time.time()) if now is None else now
    with conn:
        conn.execute(
            "UPDATE user_state SET status = NULL, updated_at = ? WHERE appid = ? AND source = ?",
            (now, appid, source),
        )


def unlabeled_games(
    conn: sqlite3.Connection,
    limit: int = 30,
    include_unplayed: bool = False,
    source: str = "owned",
) -> list[sqlite3.Row]:
    """Games with no status yet, most-played first. limit <= 0 means no limit."""
    played = "" if include_unplayed else "AND g.playtime_minutes > 0"
    sql = f"""
        SELECT g.* FROM games g
        LEFT JOIN user_state u ON u.appid = g.appid AND u.source = g.source
        WHERE g.source = ? AND g.in_library = 1 AND u.status IS NULL {played}
        ORDER BY g.playtime_minutes DESC, g.name COLLATE NOCASE
        LIMIT ?
    """
    return conn.execute(sql, (source, limit if limit > 0 else -1)).fetchall()


def label_session(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    input_fn: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> int:
    """Ask about each game in turn. Every answer is saved immediately, so
    quitting at any point loses nothing. Returns how many games were labeled."""
    out("Keys: f=finished  p=playing  d=dropped  e=endless  n=not started  "
        "s or Enter=skip  q=quit\n")
    done = 0
    for i, row in enumerate(rows, 1):
        prompt = (
            f"[{i}/{len(rows)}] {row['name']}  "
            f"({hours(row['playtime_minutes'])}, last played {last_played(row['last_played'])})  > "
        )
        while True:
            try:
                answer = input_fn(prompt).strip().lower()
            except (EOFError, KeyboardInterrupt):
                out("")
                return done
            if answer in ("q", "quit"):
                return done
            if answer in ("", "s", "skip"):
                break
            status = SESSION_KEYS.get(answer)
            if status:
                set_status(conn, row["appid"], status, row["source"])
                done += 1
                break
            out("  Not a valid key. Use f, p, d, e, n, s, or q.")
    return done