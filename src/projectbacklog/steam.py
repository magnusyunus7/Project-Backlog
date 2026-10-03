"""Steam Web API client. Network only: no scoring, no printing."""

import httpx

BASE_URL = "https://api.steampowered.com"


class SteamError(Exception):
    """Raised for any problem talking to Steam, with a human-readable message."""


def get_owned_games(
    api_key: str, steam_id: str, client: httpx.Client | None = None
) -> list[dict]:
    """Return the user's library.

    Each game is a dict with: appid, name, playtime_forever (minutes),
    rtime_last_played (unix timestamp, 0 if never launched), and sometimes
    playtime_2weeks (minutes).
    """
    params = {
        "key": api_key,
        "steamid": steam_id,
        "include_appinfo": 1,  # include game names
        "include_played_free_games": 1,
        "format": "json",
    }
    url = f"{BASE_URL}/IPlayerService/GetOwnedGames/v1/"

    owns_client = client is None
    client = client or httpx.Client(timeout=15)
    try:
        response = client.get(url, params=params)
    except httpx.HTTPError as exc:
        # Report only the exception type: its message can contain the full
        # request URL, which includes your API key.
        raise SteamError(
            f"Could not reach Steam ({type(exc).__name__}). Check your connection."
        ) from None
    finally:
        if owns_client:
            client.close()

    if response.status_code in (401, 403):
        raise SteamError("Steam rejected the request. Check STEAM_API_KEY in .env.")
    if response.status_code != 200:
        raise SteamError(f"Steam returned HTTP {response.status_code}.")

    games = response.json().get("response", {}).get("games")
    if games is None:
        raise SteamError(
            "Steam returned no games. Most likely your profile's Game details are "
            "not Public (Steam > Profile > Edit Profile > Privacy Settings), "
            "or STEAM_ID is wrong."
        )
    return games