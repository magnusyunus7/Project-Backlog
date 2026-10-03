"""Steam -> database. Safe to run any number of times."""

import sqlite3
import time
from dataclasses import dataclass, field


class SyncError(Exception):
    pass


@dataclass
class SyncResult:
    total: int
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)


UPSERT = """
INSERT INTO games (appid, source, name, playtime_minutes, playtime_2weeks_minutes,
                   last_played, first_seen, last_synced, in_library)
VALUES (:appid, :source, :name, :playtime, :playtime_2weeks,
        :last_played, :now, :now, 1)
ON CONFLICT(appid, source) DO UPDATE SET
    name                    = excluded.name,
    playtime_minutes        = excluded.playtime_minutes,
    playtime_2weeks_minutes = excluded.playtime_2weeks_minutes,
    last_played             = excluded.last_played,
    last_synced             = excluded.last_synced,
    in_library              = 1
"""


def sync_library(
    conn: sqlite3.Connection,
    games: list[dict],
    source: str = "owned",
    now: int | None = None,
) -> SyncResult:
    if not games:
        # An empty answer is far more likely to be a Steam hiccup than a truly
        # empty library; don't mark everything as removed because of it.
        raise SyncError("Steam returned an empty library; nothing was changed.")

    now = int(time.time()) if now is None else now
    incoming = {g["appid"]: g for g in games}
    result = SyncResult(total=len(incoming))

    with conn:  # one transaction: all or nothing
        existing = {
            row["appid"]: row
            for row in conn.execute(
                "SELECT appid, name, in_library FROM games WHERE source = ?", (source,)
            )
        }

        rows = []
        for appid, g in incoming.items():
            name = g.get("name") or f"App {appid}"
            if appid not in existing:
                result.added.append(name)
            elif not existing[appid]["in_library"]:
                result.restored.append(name)
            rows.append(
                {
                    "appid": appid,
                    "source": source,
                    "name": name,
                    "playtime": g.get("playtime_forever", 0),
                    "playtime_2weeks": g.get("playtime_2weeks", 0),
                    "last_played": g.get("rtime_last_played", 0),
                    "now": now,
                }
            )
        conn.executemany(UPSERT, rows)

        gone = [
            appid
            for appid, row in existing.items()
            if row["in_library"] and appid not in incoming
        ]
        if gone:
            result.removed = [existing[a]["name"] for a in gone]
            marks = ",".join("?" * len(gone))
            conn.execute(
                f"UPDATE games SET in_library = 0 WHERE source = ? AND appid IN ({marks})",
                (source, *gone),
            )

    return result