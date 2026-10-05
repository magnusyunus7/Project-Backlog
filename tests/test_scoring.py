import math

import pytest

from projectbacklog.labels import STATUSES
from projectbacklog.scoring import (
    DEFAULT_WEIGHTS as W,
    GameFacts,
    exclusion_reason,
    rank_games,
    score_game,
)

NOW = 1_800_000_000
DAY = 86_400


def facts(name="G", status="playing", hours=20, recent_hours=0, days_ago=0):
    return GameFacts(
        name=name,
        status=status,
        playtime_minutes=int(hours * 60),
        playtime_2weeks_minutes=int(recent_hours * 60),
        last_played=NOW - int(days_ago * DAY) if days_ago is not None else 0,
    )


def value(game, minutes=None):
    return score_game(game, minutes, NOW).value


# --- who can be recommended ---------------------------------------------------

def test_unlabeled_is_never_recommended():
    g = facts(status=None)
    assert score_game(g, None, NOW) is None
    assert "label" in exclusion_reason(g).lower()


@pytest.mark.parametrize("status", ["finished", "dropped", "endless"])
def test_closed_statuses_are_never_recommended(status):
    g = facts(status=status)
    assert score_game(g, None, NOW) is None
    assert exclusion_reason(g)


def test_every_known_status_is_handled():
    for status in STATUSES:
        g = facts(status=status)
        assert (score_game(g, None, NOW) is None) == bool(exclusion_reason(g))


def test_unknown_status_is_excluded_not_crashing():
    assert score_game(facts(status="mystery"), None, NOW) is None


def test_non_positive_minutes_rejected():
    with pytest.raises(ValueError):
        score_game(facts(), 0, NOW)
    with pytest.raises(ValueError):
        score_game(facts(), -30, NOW)


# --- the playing score --------------------------------------------------------

def test_recently_played_beats_long_cold():
    assert value(facts(days_ago=3)) > value(facts(days_ago=300))


def test_cold_penalty_is_half_at_the_half_life():
    g = facts(hours=100, days_ago=W.cold_half_life_days)
    expected = W.playing_bonus + W.investment_scale * math.log10(101) - 0.5 * W.cold_max_penalty
    assert value(g, minutes=int(W.reference_session_minutes)) == pytest.approx(expected)


def test_more_hours_scores_higher_but_with_diminishing_returns():
    gain_early = value(facts(hours=20)) - value(facts(hours=10))
    gain_late = value(facts(hours=210)) - value(facts(hours=200))
    assert gain_early > gain_late > 0


def test_momentum_helps_and_is_capped():
    base = value(facts(recent_hours=0))
    some = value(facts(recent_hours=2))
    assert some > base
    assert value(facts(recent_hours=50)) == pytest.approx(value(facts(recent_hours=100)))
    assert value(facts(recent_hours=100)) == pytest.approx(base + W.momentum_cap)


def test_short_evening_hurts_cold_games_more():
    cold = facts(days_ago=200)
    assert value(cold, minutes=45) < value(cold, minutes=120) < value(cold, minutes=300)


def test_warm_game_is_unaffected_by_session_length():
    warm = facts(days_ago=0)
    assert value(warm, minutes=30) == pytest.approx(value(warm, minutes=400))


def test_time_factor_is_bounded():
    cold = facts(days_ago=200)
    assert value(cold, minutes=1) == pytest.approx(value(cold, minutes=5))  # both hit the max factor
    assert value(cold, minutes=2000) == pytest.approx(value(cold, minutes=9000))  # both hit the min


def test_missing_last_played_means_no_cold_penalty():
    g = facts(days_ago=None)
    s = score_game(g, 60, NOW)
    assert s.value == pytest.approx(W.playing_bonus + W.investment_scale * math.log10(21))
    assert any("unknown" in r for r in s.reasons)


def test_future_last_played_is_treated_as_today():
    g = GameFacts("G", "playing", 1200, 0, NOW + 10 * DAY)
    assert value(g) == pytest.approx(value(facts(days_ago=0)))


# --- playing vs not started ---------------------------------------------------

def test_not_started_ignores_time_and_age():
    a = facts(status="not_started", hours=0, days_ago=0)
    b = facts(status="not_started", hours=50, days_ago=900)
    assert value(a, 30) == value(b, 500) == W.not_started_base


def test_active_game_beats_a_fresh_start():
    assert value(facts(days_ago=5, recent_hours=3)) > value(facts(status="not_started"))


def test_long_abandoned_game_loses_to_a_fresh_start():
    assert value(facts(hours=20, days_ago=3 * 365)) < value(facts(status="not_started"))


# --- explanations -------------------------------------------------------------

def test_reasons_are_present_and_mention_what_drove_the_score():
    s = score_game(facts(hours=42, recent_hours=3, days_ago=12), 90, NOW)
    text = " | ".join(s.reasons)
    assert "Playing" in text
    assert "12 days ago" in text
    assert "last 2 weeks" in text
    assert "42h" in text


def test_short_session_note_only_appears_when_it_matters():
    cold = score_game(facts(days_ago=200), 45, NOW)
    warm = score_game(facts(days_ago=1), 45, NOW)
    assert any("Short session" in r for r in cold.reasons)
    assert not any("Short session" in r for r in warm.reasons)


# --- ranking ------------------------------------------------------------------

def test_rank_orders_best_first_and_drops_ineligible():
    games = [
        facts("Cold", days_ago=400),
        facts("Warm", days_ago=2, recent_hours=4),
        facts("Done", status="finished"),
        facts("Mystery", status=None),
        facts("Fresh", status="not_started"),
    ]
    ranked = rank_games(games, 90, NOW, limit=0)
    assert [g.name for g, _ in ranked] == ["Warm", "Fresh", "Cold"]
    assert all(s.reasons for _, s in ranked)


def test_rank_limit_and_stable_tie_break():
    games = [facts("beta", status="not_started"), facts("Alpha", status="not_started"),
             facts("gamma", status="not_started")]
    assert [g.name for g, _ in rank_games(games, None, NOW, limit=2)] == ["Alpha", "beta"]


def test_rank_with_nothing_eligible_is_empty():
    assert rank_games([facts(status=None), facts(status="finished")], 60, NOW) == []