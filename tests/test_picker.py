import io
import time

import pytest

from projectbacklog import cli
from projectbacklog.db import connect, list_games
from projectbacklog.labels import set_status
from projectbacklog.picker import confirm_session, find_stale_playing
from projectbacklog.sync import sync_library

NOW = 1_800_000_000
DAY = 86_400


def row(name="G", status="playing", launched_days_ago=800, confirmed_days_ago=None, minutes=600):
    return {
        "name": name,
        "status": status,
        "playtime_minutes": minutes,
        "last_played": NOW - launched_days_ago * DAY if launched_days_ago is not None else 0,
        "status_updated_at": NOW - confirmed_days_ago * DAY if confirmed_days_ago is not None else None,
    }


# --- find_stale_playing -------------------------------------------------------

def test_old_unconfirmed_playing_game_is_stale():
    assert [r["name"] for r in find_stale_playing([row("Old")], NOW)] == ["Old"]


def test_recently_played_is_not_stale():
    assert find_stale_playing([row(launched_days_ago=30)], NOW) == []


def test_recently_labeled_is_not_stale_even_if_long_untouched():
    assert find_stale_playing([row(confirmed_days_ago=10)], NOW) == []


def test_old_confirmation_expires():
    assert len(find_stale_playing([row(confirmed_days_ago=500)], NOW)) == 1


@pytest.mark.parametrize("status", ["not_started", "finished", "dropped", "endless", None])
def test_only_playing_games_can_be_stale(status):
    assert find_stale_playing([row(status=status)], NOW) == []


def test_unknown_last_played_is_not_stale():
    assert find_stale_playing([row(launched_days_ago=None)], NOW) == []


def test_boundary_is_exactly_one_year():
    assert find_stale_playing([row(launched_days_ago=365)], NOW)
    assert not find_stale_playing([row(launched_days_ago=364)], NOW)


def test_custom_threshold():
    assert find_stale_playing([row(launched_days_ago=200)], NOW, stale_days=180)


def test_most_played_first():
    rows = [row("Small", minutes=60), row("Big", minutes=9000), row("Mid", minutes=600)]
    assert [r["name"] for r in find_stale_playing(rows, NOW)] == ["Big", "Mid", "Small"]


# --- confirm_session (with a real in-memory database) -----------------------------

@pytest.fixture
def conn():
    c = connect(":memory:")
    sync_library(c, [
        {"appid": 1, "name": "Old A", "playtime_forever": 9000, "rtime_last_played": NOW - 900 * DAY},
        {"appid": 2, "name": "Old B", "playtime_forever": 3000, "rtime_last_played": NOW - 800 * DAY},
        {"appid": 3, "name": "Old C", "playtime_forever": 600, "rtime_last_played": NOW - 700 * DAY},
    ], now=1)
    for appid in (1, 2, 3):
        set_status(c, appid, "playing", now=NOW - 1000 * DAY)  # labeled long ago
    yield c
    c.close()


def stale(conn):
    return find_stale_playing(list_games(conn, limit=0), NOW)


def state(conn, appid):
    r = conn.execute("SELECT status, updated_at FROM user_state WHERE appid = ?", (appid,)).fetchone()
    return r["status"], r["updated_at"]


def ask(conn, answers):
    it = iter(answers)
    messages = []
    result = confirm_session(conn, stale(conn), NOW, lambda p: next(it), messages.append)
    return result, messages


def test_db_rows_carry_the_label_timestamp(conn):
    assert all(r["status_updated_at"] == NOW - 1000 * DAY for r in list_games(conn, limit=0))


def test_all_three_start_out_stale(conn):
    assert [r["name"] for r in stale(conn)] == ["Old A", "Old B", "Old C"]


def test_yes_keeps_label_and_resets_the_clock(conn):
    result, _ = ask(conn, ["y", "s", "s"])
    assert result.kept == 1 and result.skipped == 2
    assert state(conn, 1) == ("playing", NOW)
    assert [r["name"] for r in stale(conn)] == ["Old B", "Old C"]  # A no longer asked about


def test_no_marks_dropped(conn):
    result, _ = ask(conn, ["n", "", ""])
    assert result.dropped == 1
    assert state(conn, 1)[0] == "dropped"


def test_skip_changes_nothing(conn):
    ask(conn, ["s", "", "skip"])
    assert all(state(conn, a) == ("playing", NOW - 1000 * DAY) for a in (1, 2, 3))
    assert len(stale(conn)) == 3  # asked again next time


def test_quit_stops_and_counts_the_rest_as_skipped(conn):
    result, _ = ask(conn, ["y", "q"])
    assert (result.kept, result.dropped, result.skipped) == (1, 0, 2)
    assert state(conn, 3) == ("playing", NOW - 1000 * DAY)


def test_bad_key_reprompts(conn):
    result, messages = ask(conn, ["zzz", "n", "s", "s"])
    assert result.dropped == 1
    assert any("Not a valid key" in m for m in messages)


def test_eof_stops_cleanly_and_keeps_progress(conn):
    answers = iter(["n"])

    def flaky(prompt):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError

    result = confirm_session(conn, stale(conn), NOW, flaky, lambda m: None)
    assert result.dropped == 1 and result.skipped == 2
    assert state(conn, 1)[0] == "dropped"


# --- the `pick` command, end to end ---------------------------------------------

class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


def seed(path, now=None):
    now = int(time.time()) if now is None else now
    c = connect(path)
    sync_library(c, [
        {"appid": 1, "name": "Active RPG", "playtime_forever": 2500, "playtime_2weeks": 300,
         "rtime_last_played": now - 3 * DAY},
        {"appid": 2, "name": "Fresh Purchase", "playtime_forever": 0},
        {"appid": 3, "name": "Beaten Game", "playtime_forever": 900, "rtime_last_played": now - 30 * DAY},
        {"appid": 4, "name": "Unlabeled Game", "playtime_forever": 600, "rtime_last_played": now - 10 * DAY},
        {"appid": 5, "name": "Ancient Game", "playtime_forever": 1200, "rtime_last_played": now - 900 * DAY},
    ], now=now)
    for appid, status in [(1, "playing"), (2, "not_started"), (3, "finished"), (5, "playing")]:
        set_status(c, appid, status, now=now - 800 * DAY)
    c.close()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "pick.db"
    monkeypatch.setenv("DB_PATH", str(path))
    return path


def run_pick(capsys, *args):
    cli.main(["pick", *args])
    return capsys.readouterr().out


def test_pick_ranks_labeled_games_with_reasons(db_path, capsys):
    seed(db_path)
    out = run_pick(capsys, "--minutes", "90", "--no-prompt", "--top", "5")
    assert "Tonight (90 min)" in out
    ranking = out.split("Tonight (90 min)")[1]  # skip the stale-label warning above it
    assert ranking.index("Active RPG") < ranking.index("Fresh Purchase") < ranking.index("Ancient Game")
    assert "5.0h in the last 2 weeks" in ranking
    assert "Beaten Game" not in ranking and "Unlabeled Game" not in ranking


def test_pick_nudges_about_unlabeled_games(db_path, capsys):
    seed(db_path)
    out = run_pick(capsys, "--no-prompt")
    assert "1 played game(s) are unlabeled" in out


def test_pick_default_shows_top_three(db_path, capsys):
    seed(db_path)
    out = run_pick(capsys, "--no-prompt")
    assert "your top 3" in out


def test_pick_warns_about_stale_labels_when_not_interactive(db_path, capsys):
    seed(db_path)
    out = run_pick(capsys, "--no-prompt")
    assert "Heads up: 1 game(s)" in out and "Ancient Game" in out


def test_pick_asks_in_a_terminal_and_respects_the_answer(db_path, capsys, monkeypatch):
    seed(db_path)
    monkeypatch.setattr("sys.stdin", FakeTerminal("n\n"))
    out = run_pick(capsys, "--top", "5")
    assert "still playing?" in out
    assert "Ancient Game" not in out.split("your top")[1]  # marked dropped, so not recommended
    c = connect(db_path)
    assert state(c, 5)[0] == "dropped"
    c.close()


def test_pick_answer_yes_keeps_the_game_and_stops_asking(db_path, capsys, monkeypatch):
    seed(db_path)
    monkeypatch.setattr("sys.stdin", FakeTerminal("y\n"))
    out = run_pick(capsys, "--top", "5")
    assert "Ancient Game" in out.split("your top")[1]
    out2 = run_pick(capsys, "--no-prompt", "--top", "5")  # clock was reset
    assert "Heads up" not in out2


def test_pick_with_empty_database(db_path, capsys):
    assert "library is empty" in run_pick(capsys)


def test_pick_with_only_unlabeled_games(db_path, capsys):
    c = connect(db_path)
    sync_library(c, [{"appid": 1, "name": "X", "playtime_forever": 100}], now=1)
    c.close()
    out = run_pick(capsys)
    assert "Nothing to recommend yet" in out and "label" in out


def test_pick_when_everything_is_finished(db_path, capsys):
    c = connect(db_path)
    sync_library(c, [{"appid": 1, "name": "X", "playtime_forever": 100}], now=1)
    set_status(c, 1, "finished")
    c.close()
    assert "finished, dropped or endless" in run_pick(capsys)


@pytest.mark.parametrize("bad", ["0", "-5", "abc"])
def test_pick_rejects_bad_minutes(db_path, bad):
    with pytest.raises(SystemExit) as exc:
        cli.main(["pick", "--minutes", bad])
    assert exc.value.code == 2