"""Helpers for `pick`: spotting stale labels and asking about them.

A game marked Playing that you haven't launched in over a year is probably
one you quietly dropped. Rather than let the scorer guess, we ask you.
"""

import sqlite3
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .fmt import hours, last_played
from .labels import set_status
from .scoring import SECONDS_PER_DAY

STALE_DAYS = 365


def find_stale_playing(
    rows: Sequence[Mapping],
    now: int,
    stale_days: int = STALE_DAYS,
) -> list[Mapping]:
    """Games labeled Playing that look abandoned: not launched for `stale_days`
    AND the label itself hasn't been set or confirmed within `stale_days`.

    Most-played first, so the games you invested in get asked about first.
    `rows` need the keys: status, last_played, status_updated_at,
    playtime_minutes, name.
    """
    cutoff = now - stale_days * SECONDS_PER_DAY
    stale = []
    for r in rows:
        if r["status"] != "playing":
            continue
        launched = r["last_played"] or 0
        if launched <= 0 or launched > cutoff:
            continue  # unknown date, or played recently enough
        confirmed = r["status_updated_at"] or 0
        if confirmed > cutoff:
            continue  # you labeled or confirmed it recently
        stale.append(r)
    stale.sort(key=lambda r: (-r["playtime_minutes"], r["name"].lower()))
    return stale


@dataclass
class ConfirmResult:
    kept: int = 0
    dropped: int = 0
    skipped: int = 0


def confirm_session(
    conn: sqlite3.Connection,
    stale: Sequence[Mapping],
    now: int | None = None,
    input_fn: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> ConfirmResult:
    """Ask about each stale game. Answers are saved immediately.

      y -> still playing: re-saves the label, which resets the one-year clock
      n -> marks it dropped
      s / Enter -> decide later (you'll be asked again next time)
      q -> stop asking
    """
    now = int(time.time()) if now is None else now
    result = ConfirmResult()
    out("These games are marked Playing but haven't been launched in over a year.")
    out("  y = still playing   n = I dropped it   s or Enter = decide later   q = stop asking\n")

    for i, row in enumerate(stale, 1):
        prompt = (
            f"[{i}/{len(stale)}] {row['name']}  "
            f"({hours(row['playtime_minutes'])}, last played {last_played(row['last_played'])})"
            "  still playing? > "
        )
        stop = False
        while True:
            try:
                answer = input_fn(prompt).strip().lower()
            except (EOFError, KeyboardInterrupt):
                out("")
                stop = True
                break
            if answer in ("q", "quit"):
                stop = True
                break
            if answer in ("", "s", "skip"):
                break
            if answer in ("y", "yes"):
                set_status(conn, row["appid"], "playing", row["source"], now=now)
                result.kept += 1
                break
            if answer in ("n", "no"):
                set_status(conn, row["appid"], "dropped", row["source"], now=now)
                result.dropped += 1
                break
            out("  Not a valid key. Use y, n, s, or q.")
        if stop:
            break

    result.skipped = len(stale) - result.kept - result.dropped
    return result