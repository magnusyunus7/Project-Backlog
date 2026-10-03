import pytest

from projectbacklog.db import connect, list_games
from projectbacklog.sync import SyncError, sync_library


def game(appid, name="Game", minutes=0, last=0):
    return {"appid": appid, "name": name, "playtime_forever": minutes, "rtime_last_played": last}


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def count(conn, table="games"):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_first_sync_adds_everything(conn):
    result = sync_library(conn, [game(1, "A"), game(2, "B")], now=100)
    assert sorted(result.added) == ["A", "B"]
    assert count(conn) == 2


def test_resync_is_idempotent(conn):
    games = [game(1, "A", 60), game(2, "B")]
    sync_library(conn, games, now=100)
    result = sync_library(conn, games, now=200)
    assert count(conn) == 2
    assert result.added == result.removed == result.restored == []


def test_resync_updates_steam_data_but_keeps_first_seen(conn):
    sync_library(conn, [game(1, "A", 60, 1000)], now=100)
    sync_library(conn, [game(1, "A", 600, 2000)], now=200)
    row = conn.execute("SELECT * FROM games WHERE appid = 1").fetchone()
    assert row["playtime_minutes"] == 600
    assert row["last_played"] == 2000
    assert row["first_seen"] == 100
    assert row["last_synced"] == 200


def test_user_state_survives_resync(conn):
    sync_library(conn, [game(1, "A")], now=100)
    conn.execute("INSERT INTO user_state (appid, status, notes) VALUES (1, 'finished', 'great')")
    conn.commit()
    sync_library(conn, [game(1, "A", 999)], now=200)
    row = conn.execute("SELECT * FROM user_state WHERE appid = 1").fetchone()
    assert (row["status"], row["notes"]) == ("finished", "great")


def test_missing_game_is_marked_removed_not_deleted(conn):
    sync_library(conn, [game(1, "A"), game(2, "B")], now=100)
    conn.execute("INSERT INTO user_state (appid, status) VALUES (2, 'dropped')")
    conn.commit()

    result = sync_library(conn, [game(1, "A")], now=200)

    assert result.removed == ["B"]
    assert count(conn) == 2  # still stored
    assert count(conn, "user_state") == 1  # label kept
    assert [r["name"] for r in list_games(conn)] == ["A"]
    assert len(list_games(conn, include_removed=True)) == 2


def test_returning_game_is_restored(conn):
    sync_library(conn, [game(1, "A"), game(2, "B")], now=100)
    sync_library(conn, [game(1, "A")], now=200)
    result = sync_library(conn, [game(1, "A"), game(2, "B")], now=300)
    assert result.restored == ["B"]
    assert len(list_games(conn)) == 2


def test_empty_library_is_refused_and_changes_nothing(conn):
    sync_library(conn, [game(1, "A")], now=100)
    with pytest.raises(SyncError):
        sync_library(conn, [], now=200)
    assert [r["name"] for r in list_games(conn)] == ["A"]


def test_sources_are_independent(conn):
    sync_library(conn, [game(1, "A")], source="owned", now=100)
    sync_library(conn, [game(1, "A")], source="family", now=100)
    sync_library(conn, [game(2, "B")], source="owned", now=200)  # drops owned A only
    rows = conn.execute("SELECT source, in_library FROM games WHERE appid = 1").fetchall()
    assert {(r["source"], r["in_library"]) for r in rows} == {("owned", 0), ("family", 1)}


def test_list_sorting(conn):
    sync_library(conn, [game(1, "Zed", 10, 300), game(2, "Alpha", 500, 100), game(3, "Mid", 50, 200)], now=1)
    assert [r["name"] for r in list_games(conn, "playtime")] == ["Alpha", "Mid", "Zed"]
    assert [r["name"] for r in list_games(conn, "recent")] == ["Zed", "Mid", "Alpha"]
    assert [r["name"] for r in list_games(conn, "name")] == ["Alpha", "Mid", "Zed"]
    assert len(list_games(conn, limit=0)) == 3
    assert len(list_games(conn, limit=2)) == 2