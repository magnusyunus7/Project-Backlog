"""Prove the Steam connection by printing your library."""

from datetime import datetime

from .config import load_config
from .steam import SteamError, get_owned_games


def hours(minutes: int) -> str:
    return f"{minutes / 60:.1f}h"


def last_played(timestamp: int) -> str:
    if not timestamp:
        return "never"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def main() -> None:
    config = load_config()
    try:
        games = get_owned_games(config.api_key, config.steam_id)
    except SteamError as exc:
        raise SystemExit(f"Error: {exc}")

    played = [g for g in games if g.get("playtime_forever", 0) > 0]
    print(f"Library: {len(games)} games, {len(played)} played, "
          f"{len(games) - len(played)} never touched.\n")

    print("Top 15 by total playtime")
    top = sorted(games, key=lambda g: g.get("playtime_forever", 0), reverse=True)[:15]
    for g in top:
        print(f"  {hours(g.get('playtime_forever', 0)):>8}  {g.get('name', g['appid'])}")

    print("\n10 most recently played")
    recent = sorted(games, key=lambda g: g.get("rtime_last_played", 0), reverse=True)[:10]
    for g in recent:
        print(f"  {last_played(g.get('rtime_last_played', 0))}  "
              f"{hours(g.get('playtime_forever', 0)):>8}  {g.get('name', g['appid'])}")


if __name__ == "__main__":
    main()