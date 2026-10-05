"""Scoring: which game fits tonight?

Pure functions. No database, no network, no printing. Plain facts go in; a
score and plain-English reasons come out. That keeps it easy to test and easy
to tune: every number lives in `Weights` below.

Only games YOU labeled can be recommended:
  playing      -> scored (momentum, investment, how cold it has gone)
  not_started  -> scored (a flat "fresh start" value)
  finished / dropped / endless / unlabeled -> never recommended
"""

import math
import time
from dataclasses import dataclass

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class Weights:
    """Every tunable number in one place. These are educated first guesses;
    expect to adjust them after living with `pick` for a week."""

    playing_bonus: float = 35.0  # base value of a game you marked Playing
    not_started_base: float = 20.0  # value of a game you marked Not started

    momentum_per_hour: float = 4.0  # points per hour played in the last 2 weeks
    momentum_cap: float = 20.0  # ...but never more than this

    investment_scale: float = 6.0  # points = scale * log10(1 + hours played)

    cold_half_life_days: float = 90.0  # after this long, half of the cold penalty applies
    cold_max_penalty: float = 25.0  # penalty for a game left untouched forever

    reference_session_minutes: float = 120.0  # a "normal" evening
    time_factor_min: float = 0.5  # long evenings halve the cold penalty at most
    time_factor_max: float = 2.0  # short evenings double it at most


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True)
class GameFacts:
    name: str
    status: str | None  # one of labels.STATUSES, or None if unlabeled
    playtime_minutes: int = 0
    playtime_2weeks_minutes: int = 0
    last_played: int = 0  # unix time, 0 = never launched


@dataclass(frozen=True)
class Score:
    value: float
    reasons: tuple[str, ...]


def exclusion_reason(game: GameFacts) -> str | None:
    """Why this game can't be recommended, or None if it can."""
    if game.status is None:
        return "Not labeled yet, so it isn't considered. Label it to include it."
    if game.status in ("playing", "not_started"):
        return None
    if game.status == "finished":
        return "Marked finished"
    if game.status == "dropped":
        return "Marked dropped"
    if game.status == "endless":
        return "Marked endless (nothing to finish)"
    return f"Unknown status {game.status!r}"


def score_game(
    game: GameFacts,
    minutes_available: int | None = None,
    now: int | None = None,
    weights: Weights = DEFAULT_WEIGHTS,
) -> Score | None:
    """Score one game, or return None if it can't be recommended.

    minutes_available=None means "no time limit stated".
    """
    if minutes_available is not None and minutes_available <= 0:
        raise ValueError("minutes_available must be positive")
    if exclusion_reason(game) is not None:
        return None
    now = int(time.time()) if now is None else now
    w = weights

    if game.status == "not_started":
        return Score(
            w.not_started_base,
            ("Marked Not started: a fresh start, nothing to re-learn",),
        )

    # --- status == "playing" ------------------------------------------------
    value = w.playing_bonus
    reasons = ["You marked it Playing"]

    # How cold has it gone? Re-learning controls, build and plot gets harder
    # the longer you've been away, so the score decays with time.
    days = _days_since(game.last_played, now)
    coldness = 0.0
    if days is None:
        reasons.append("No last-played date, so the break length is unknown")
    else:
        coldness = 1 - 0.5 ** (days / w.cold_half_life_days)
        factor = _time_factor(minutes_available, w)
        value -= w.cold_max_penalty * coldness * factor
        if coldness >= 0.5:
            reasons.append(f"Cold: last played {_ago(int(days))}, expect some re-learning")
        else:
            reasons.append(f"Last played {_ago(int(days))}")

    # Recent play means you're warmed up and re-entry is cheap.
    hours_2w = game.playtime_2weeks_minutes / 60
    momentum = min(w.momentum_cap, w.momentum_per_hour * hours_2w)
    if momentum > 0:
        value += momentum
        reasons.append(f"{hours_2w:.1f}h in the last 2 weeks, so you're warmed up")

    # Total hours: a weak proxy for how far in you are. The log curve means
    # 200h isn't ten times more meaningful than 20h.
    total_hours = game.playtime_minutes / 60
    value += w.investment_scale * math.log10(1 + total_hours)
    reasons.append(f"{_fmt_hours(total_hours)} invested")

    # Mention the session length only when it actually changed something.
    if minutes_available is not None and coldness > 0.2:
        factor = _time_factor(minutes_available, w)
        if factor > 1:
            reasons.append(
                f"Short session ({minutes_available} min): getting back into a "
                "game you left a while ago costs more"
            )
        elif factor < 1:
            reasons.append(
                f"Long session ({minutes_available} min): plenty of time to get back into it"
            )

    return Score(value, tuple(reasons))


def rank_games(
    games: list[GameFacts],
    minutes_available: int | None = None,
    now: int | None = None,
    weights: Weights = DEFAULT_WEIGHTS,
    limit: int = 3,
) -> list[tuple[GameFacts, Score]]:
    """Best candidates first. Games that can't be recommended are left out.
    Ties break alphabetically so the order is stable."""
    now = int(time.time()) if now is None else now
    ranked = []
    for game in games:
        score = score_game(game, minutes_available, now, weights)
        if score is not None:
            ranked.append((game, score))
    ranked.sort(key=lambda pair: (-pair[1].value, pair[0].name.lower()))
    return ranked[:limit] if limit > 0 else ranked


# --- helpers -----------------------------------------------------------------

def _days_since(last_played: int, now: int) -> float | None:
    """Days since last launch; None if unknown. Never negative (clock skew)."""
    if last_played <= 0:
        return None
    return max(0.0, (now - last_played) / SECONDS_PER_DAY)


def _time_factor(minutes_available: int | None, w: Weights) -> float:
    """Short evenings make a long break hurt more; long evenings hurt less."""
    if minutes_available is None:
        return 1.0
    raw = w.reference_session_minutes / minutes_available
    return min(w.time_factor_max, max(w.time_factor_min, raw))


def _fmt_hours(hours: float) -> str:
    return f"{hours:.0f}h" if hours >= 10 else f"{hours:.1f}h"


def _ago(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    if days < 730:
        return f"{days // 30} months ago"
    return f"{days // 365} years ago"