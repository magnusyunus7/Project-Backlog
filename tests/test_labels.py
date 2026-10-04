import pytest

from projectbacklog.db import connect, list_games
from projectbacklog.labels import (
    clear_status,
    find_games,
    label_session,
    set_status,
    unlabeled_games,
)
from projectbacklog.sync import sync_library


def game(appid, name, minutes=0, last=0):
    return {"appid": appid, "name": name, "playtime_forever": minutes, "rtime_last_played": last}


LIBRARY = [
    game(1, "Elden Ring", 6000, 300),
    game(2, "Dark Souls III", 4000, 200),
    game(3, "Dark Souls Remastered", 900, 100),
    game(4, "Never Launched", 0, 0),
    game(5, "100% Orange Juice", 50, 50),
]


@pytest.fixture
def conn():
    c = connect(":memory:")
    sync_library(c, LIBRARY, now=1)
    yield c
    c.close()


def status_of(conn, appid):
    row = conn.execute("SELECT status FROM user_state WHERE appid = ?", (appid,)).fetchone()
    return row["status"] if row else None


# --- setting labels -------------------------------------------------------

def test_set_and_change_status(conn):
    set_status(conn, 1, "playing")
    assert status_of(conn, 1) == "playing"
    set_status(conn, 1, "finished")
    assert status_of(conn, 1) == "finished"


def test_invalid_status_rejected(conn):
    with pytest.raises(ValueError):
        set_status(conn, 1, "beaten")
    assert status_of(conn, 1) is None


def test_label_survives_resync(conn):
    set_status(conn, 1, "finished")
    sync_library(conn, LIBRARY, now=2)
    assert status_of(conn, 1) == "finished"


def test_changing_status_keeps_notes(conn):
    conn.execute("INSERT INTO user_state (appid, status, notes) VALUES (1, 'playing', 'at Radahn')")
    conn.commit()
    set_status(conn, 1, "finished")
    row = conn.execute("SELECT * FROM user_state WHERE appid = 1").fetchone()
    assert (row["status"], row["notes"]) == ("finished", "at Radahn")


def test_clear_status_keeps_notes(conn):
    conn.execute("INSERT INTO user_state (appid, status, notes) VALUES (1, 'playing', 'keep me')")
    conn.commit()
    clear_status(conn, 1)
    row = conn.execute("SELECT * FROM user_state WHERE appid = 1").fetchone()
    assert row["status"] is None
    assert row["notes"] == "keep me"


# --- finding games --------------------------------------------------------

def test_find_by_appid(conn):
    assert [r["name"] for r in find_games(conn, "2")] == ["Dark Souls III"]


def test_find_exact_name_beats_partial(conn):
    sync_library(conn, LIBRARY + [game(6, "Dark Souls", 10)], now=2)
    assert [r["name"] for r in find_games(conn, "dark souls")] == ["Dark Souls"]


def test_find_partial_is_case_insensitive_and_ranked_by_playtime(conn):
    assert [r["name"] for r in find_games(conn, "SOULS")] == ["Dark Souls III", "Dark Souls Remastered"]


def test_find_no_match(conn):
    assert find_games(conn, "zelda") == []
    assert find_games(conn, "   ") == []


def test_find_digits_that_are_not_an_appid_fall_back_to_name(conn):
    assert [r["name"] for r in find_games(conn, "100")] == ["100% Orange Juice"]


def test_find_percent_is_not_a_wildcard(conn):
    assert [r["name"] for r in find_games(conn, "%")] == ["100% Orange Juice"]


def test_find_ignores_removed_games(conn):
    sync_library(conn, LIBRARY[1:], now=2)  # Elden Ring disappears
    assert find_games(conn, "elden") == []


# --- unlabeled / listing --------------------------------------------------

def test_unlabeled_excludes_labeled_and_unplayed_ordered_by_playtime(conn):
    set_status(conn, 2, "finished")
    names = [r["name"] for r in unlabeled_games(conn)]
    assert names == ["Elden Ring", "Dark Souls Remastered", "100% Orange Juice"]


def test_unlabeled_can_include_unplayed_and_respects_limit(conn):
    assert "Never Launched" in [r["name"] for r in unlabeled_games(conn, include_unplayed=True)]
    assert len(unlabeled_games(conn, limit=2)) == 2
    assert len(unlabeled_games(conn, limit=0, include_unplayed=True)) == 5


def test_list_shows_and_filters_by_status(conn):
    set_status(conn, 1, "finished")
    set_status(conn, 2, "dropped")
    by_name = {r["name"]: r["status"] for r in list_games(conn, limit=0)}
    assert by_name["Elden Ring"] == "finished"
    assert by_name["Dark Souls Remastered"] is None
    assert [r["name"] for r in list_games(conn, status="finished")] == ["Elden Ring"]
    assert len(list_games(conn, status="unlabeled", limit=0)) == 3


# --- interactive session --------------------------------------------------

def scripted(answers):
    it = iter(answers)
    return lambda prompt: next(it)


def run(conn, answers, limit=30):
    rows = unlabeled_games(conn, limit)
    messages = []
    done = label_session(conn, rows, input_fn=scripted(answers), out=messages.append)
    return done, messages


def test_session_labels_skips_and_quits(conn):
    # order: Elden Ring, Dark Souls III, Dark Souls Remastered, 100% Orange Juice
    done, _ = run(conn, ["f", "s", "D", "q"])
    assert done == 2
    assert status_of(conn, 1) == "finished"
    assert status_of(conn, 2) is None  # skipped
    assert status_of(conn, 3) == "dropped"  # uppercase accepted
    assert status_of(conn, 5) is None  # never reached


def test_session_reprompts_on_bad_key(conn):
    done, messages = run(conn, ["zzz", "e", "q"])
    assert done == 1
    assert status_of(conn, 1) == "endless"
    assert any("Not a valid key" in m for m in messages)


def test_session_stops_cleanly_on_eof_and_keeps_progress(conn):
    def flaky(prompt, _answers=iter(["p"])):
        try:
            return next(_answers)
        except StopIteration:
            raise EOFError

    done = label_session(conn, unlabeled_games(conn), input_fn=flaky, out=lambda m: None)
    assert done == 1
    assert status_of(conn, 1) == "playing"