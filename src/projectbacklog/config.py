"""Loads settings from a .env file (never committed to git)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


@dataclass(frozen=True)
class Config:
    api_key: str
    steam_id: str
    db_path: Path


def load_config(require_steam: bool = True) -> Config:
    """Load settings. Commands that never talk to Steam (like `list`) pass
    require_steam=False so they work without an API key."""
    # Walks up from the current directory, so it finds .env in the repo root
    # even if you run the program from inside src/.
    env_file = find_dotenv(usecwd=True)
    if env_file:
        load_dotenv(env_file)

    # The database lives next to .env (repo root) by default, not in src/.
    base = Path(env_file).parent if env_file else Path.cwd()
    db_path = base / os.getenv("DB_PATH", "data/projectbacklog.db")

    api_key = os.getenv("STEAM_API_KEY", "").strip()
    steam_id = os.getenv("STEAM_ID", "").strip()

    if require_steam:
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

    return Config(api_key=api_key, steam_id=steam_id, db_path=db_path)