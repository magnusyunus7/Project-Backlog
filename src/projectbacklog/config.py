"""Loads settings from a .env file (never committed to git)."""

import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv


@dataclass(frozen=True)
class Config:
    api_key: str
    steam_id: str


def load_config() -> Config:
    # Walks up from the current directory, so it finds .env in the repo root
    # even if you run the program from inside src/.
    load_dotenv(find_dotenv(usecwd=True))

    api_key = os.getenv("STEAM_API_KEY", "").strip()
    steam_id = os.getenv("STEAM_ID", "").strip()

    missing = [
        name
        for name, value in (("STEAM_API_KEY", api_key), ("STEAM_ID", steam_id))
        if not value
    ]
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)}. Copy .env.example to .env and fill it in."
        )

    if not (steam_id.isdigit() and len(steam_id) == 17):
        raise SystemExit(
            "STEAM_ID must be your 17-digit SteamID64 (looks like 7656119XXXXXXXXXX), "
            "not your profile name."
        )

    return Config(api_key=api_key, steam_id=steam_id)