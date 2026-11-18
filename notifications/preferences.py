"""Local notification preferences. No network requests."""

import json
import os
import tempfile
from pathlib import Path

DEFAULT_PATH = Path("data/notifications/preferences.json")


def load_notification_enabled(path=DEFAULT_PATH):
    path = Path(path)

    if not path.exists():
        return False

    data = json.loads(path.read_text(encoding="utf-8"))

    if (
        type(data) is not dict
        or data.get("version") != 1
        or type(data.get("enabled")) is not bool
    ):
        raise ValueError("Invalid notification preferences")

    return data["enabled"]


def save_notification_enabled(enabled, path=DEFAULT_PATH):
    if type(enabled) is not bool:
        raise ValueError("Notification setting must be boolean")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".notification_preferences_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)

            json.dump(
                {"version": 1, "enabled": enabled},
                handle,
            )

            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return enabled
