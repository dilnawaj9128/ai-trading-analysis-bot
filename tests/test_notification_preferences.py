import json

import pytest

from notifications.preferences import (
    load_notification_enabled,
    save_notification_enabled,
)


def test_default_disabled(tmp_path):
    path = tmp_path / "preferences.json"
    assert load_notification_enabled(path) is False


def test_enable_persists(tmp_path):
    path = tmp_path / "preferences.json"
    save_notification_enabled(True, path)
    assert load_notification_enabled(path) is True


def test_disable_persists(tmp_path):
    path = tmp_path / "preferences.json"
    save_notification_enabled(True, path)
    save_notification_enabled(False, path)
    assert load_notification_enabled(path) is False


def test_invalid_setting_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_notification_enabled("yes", tmp_path / "prefs.json")


def test_corrupt_preferences_rejected(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(
        json.dumps({"version": 1, "enabled": "true"})
    )

    with pytest.raises(ValueError):
        load_notification_enabled(path)
