"""SQLite schema and queries.

Two kinds of data live in separate tables on purpose:
  games       - what Steam tells us. Overwritten on every sync.
  user_state  - what YOU tell us (status, notes...). Sync never touches it.
"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    appid                   INTEGER NOT NULL,
    source                  TEXT    NOT NULL DEFAULT 'owned',  -- 'owned' now, 'family' later
    name                    TEXT    NOT NULL,
    playtime_minutes        INTEGER NOT NULL DEFAULT 0,
    playtime_2weeks_minutes INTEGER NOT NULL DEFAULT 0,
    last_played             INTEGER NOT NULL DEFAULT 0,        -- unix time, 0 = never
    first_seen              INTEGER NOT NULL,
    last_synced             INTEGER NOT NULL,
    in_library              INTEGER NOT NULL DEFAULT 1,        -- 0 = gone from Steam (kept, not deleted)
    PRIMARY KEY (appid, source)
);

CREATE TABLE IF NOT EXISTS user_state (
    appid           INTEGER NOT NULL,
    source          TEXT    NOT NULL DEFAULT 'owned',
    status          TEXT,      -- not_started / playing / finished / dropped / endless
    estimated_hours REAL,
    notes           TEXT,
    updated_at      INTEGER,
    PRIMARY KEY (appid, source)
);
"""

SORTS = {
    "playtime": "playtime_minutes DESC, name COLLATE NOCASE",
    "recent": "last_played DESC, name COLLATE NOCASE",
    "name": "name COLLATE NOCASE",
}


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def list_games(
    conn: sqlite3.Connection,
    sort: str = "playtime",
    limit: int = 20,
    include_removed: bool = False,
) -> list[sqlite3.Row]:
    """limit <= 0 means no limit."""
    order = SORTS[sort]  # KeyError on unknown sort: only whitelisted SQL gets in
    where = "" if include_removed else "WHERE in_library = 1"
    sql = f"SELECT * FROM games {where} ORDER BY {order} LIMIT ?"
    return conn.execute(sql, (limit if limit > 0 else -1,)).fetchall()