"""Small display helpers shared by the CLI and the labeling session."""

from datetime import datetime


def hours(minutes: int) -> str:
    return f"{minutes / 60:.1f}h"


def last_played(timestamp: int) -> str:
    if not timestamp:
        return "never"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def status_text(status: str | None) -> str:
    return "-" if not status else status.replace("_", " ")