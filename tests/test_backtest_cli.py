
import csv
import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pandas as pd
import pytest

import simulator.backtesting as bt

from simulator.dataset_trust import (
    file_sha256,
    verify_dataset,
)
from simulator.backtest_cli import main


START = datetime(
    2026, 11, 12, 10, 0,
    tzinfo=timezone.utc,
)


def make_fixture(tmp_path, *, approved=True):
    csv_path = tmp_path / "eurusd.csv"
    manifest_path = tmp_path / "manifest.json"
    registry_path = tmp_path / "registry.json"

    candles = pd.DataFrame([
        {
            "timestamp": (
                START + timedelta(minutes=i)
            ).isoformat(),
            "Open": 100 + i * 0.01,
            "High": 100.1 + i * 0.01,
            "Low": 99.9 + i * 0.01,
            "Close": 100.005 + i * 0.01,
        }
        for i in range(90)
    ])

    candles.to_csv(csv_path, index=False)

    manifest = {
        "schema_version": 1,
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "timestamp_semantics": "candle_open_utc",
        "provider": "SYNTHETIC_TEST",
        "feed_mode": "live",
        "retrieved_at": (
            START + timedelta(minutes=100)
        ).isoformat(),
        "csv_sha256": file_sha256(csv_path),
    }

    manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    registry = {
        "schema_version": 1,
        "trusted_manifests": [
            {
                "manifest_sha256": file_sha256(
                    manifest_path
                ),
                "status": (
                    "approved" if approved
                    else "revoked"
                ),
                "verification_reference": (
                    "SYNTHETIC_TEST_FIXTURE_ONLY"
                ),
            }
        ],
    }

    registry_path.write_text(
        json.dumps(registry),
        encoding="utf-8",
    )

    return csv_path, manifest_path, registry_path


def cli_args(paths, output):
    csv_path, manifest, registry = paths

    return [
        "--csv", str(csv_path),
        "--manifest", str(manifest),
        "--trust-registry", str(registry),
        "--output", str(output),
    ]


def test_trusted_fixture_verifies(tmp_path):
    paths = make_fixture(tmp_path)

    result = verify_dataset(*paths)

    assert result.provenance.provider == "SYNTHETIC_TEST"
    assert result.dataset_sha256 == file_sha256(paths[0])


def test_missing_registry_blocks(tmp_path):
    paths = make_fixture(tmp_path)
    paths[2].unlink()

    with pytest.raises(ValueError, match="registry"):
        verify_dataset(*paths)


def test_revoked_manifest_blocks(tmp_path):
    paths = make_fixture(
        tmp_path, approved=False
    )

    with pytest.raises(ValueError, match="approved"):
        verify_dataset(*paths)


def test_modified_csv_blocks(tmp_path):
    paths = make_fixture(tmp_path)

    with paths[0].open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write("\n")

    with pytest.raises(ValueError, match="hash mismatch"):
        verify_dataset(*paths)


def test_modified_manifest_blocks(tmp_path):
    paths = make_fixture(tmp_path)

    manifest = json.loads(
        paths[1].read_text(encoding="utf-8")
    )

    manifest["provider"] = "ALTERED_PROVIDER"

    paths[1].write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="trusted registry"):
        verify_dataset(*paths)


def test_cli_exports_reports(tmp_path, monkeypatch):
    paths = make_fixture(tmp_path)
    output = tmp_path / "reports"

    # Synthetic signal for deterministic testing.
    monkeypatch.setattr(
        bt, "calculate_indicators",
        lambda data: data,
    )
    monkeypatch.setattr(
        bt, "detect_candlestick_patterns",
        lambda data: data,
    )
    monkeypatch.setattr(
        bt, "generate_signal",
        lambda *args, **kwargs: {"signal": "UP"},
    )

    result = main(cli_args(paths, output))

    assert result == 0
    assert (output / "summary.json").is_file()
    assert (output / "comparison.csv").is_file()
    assert (output / "trades.csv").is_file()

    summary = json.loads(
        (output / "summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert summary["research_only"] is True
    assert summary["broker_verified"] is False
    assert len(summary["comparison"]) == 3

    with (output / "trades.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        trades = list(csv.DictReader(stream))

    assert len(trades) == 50


def test_cli_blocks_untrusted_data(tmp_path):
    paths = make_fixture(
        tmp_path, approved=False
    )

    output = tmp_path / "blocked_reports"

    result = main(cli_args(paths, output))

    assert result == 1
    assert not output.exists()


def test_cli_does_not_modify_sqlite(
    tmp_path, monkeypatch
):
    from database.repository import (
        PaperTradingRepository,
    )

    db_path = tmp_path / "paper.db"
    repository = PaperTradingRepository(db_path)
    repository.get_or_create_account(10000.0)

    balance_before = repository.get_balance()
    trades_before = len(
        repository.get_all_trades()
    )

    paths = make_fixture(tmp_path)

    monkeypatch.setattr(
        bt, "calculate_indicators",
        lambda data: data,
    )
    monkeypatch.setattr(
        bt, "detect_candlestick_patterns",
        lambda data: data,
    )
    monkeypatch.setattr(
        bt, "generate_signal",
        lambda *args, **kwargs: {"signal": "NO TRADE"},
    )

    assert main(
        cli_args(paths, tmp_path / "reports")
    ) == 0

    assert repository.get_balance() == balance_before
    assert len(
        repository.get_all_trades()
    ) == trades_before

