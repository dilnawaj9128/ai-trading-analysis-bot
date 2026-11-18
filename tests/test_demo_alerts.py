from notifications.demo_alerts import create_demo_alert
from notifications.result_notifications import get_notification_history


def test_demo_alert_saved(tmp_path):
    db = tmp_path / "demo.db"

    result = create_demo_alert(enabled=True, db_path=db)

    assert result["created"] is True
    assert result["source"] == "DEMO"

    history = get_notification_history(db_path=db)
    assert len(history) == 1
    assert history[0]["source"] == "DEMO"
    assert history[0]["signal"] == "NO TRADE"


def test_disabled_demo_creates_nothing(tmp_path):
    db = tmp_path / "demo.db"

    result = create_demo_alert(enabled=False, db_path=db)

    assert result["created"] is False
    assert not db.exists()


def test_invalid_setting_rejected(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        create_demo_alert(
            enabled="yes",
            db_path=tmp_path / "demo.db",
        )
