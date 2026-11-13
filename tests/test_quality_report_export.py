
import hashlib
import json
from datetime import timedelta

import pandas as pd
import pytest

from data.dataset_quality import audit_dataset
from data.quality_report_export import (
    export_quality_report,
)
from tests.test_dataset_quality import (
    START,
    make_dataset,
    update_hash,
)


def test_json_report_export(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    output = tmp_path / "quality_report.json"

    export_quality_report(
        audit,
        csv_path,
        receipt_path,
        output,
    )

    payload = json.loads(
        output.read_text(encoding="utf-8")
    )

    assert payload["audit"]["status"] == "PASS"
    assert (
        payload["audit"]["directional_backtesting_allowed"]
        is False
    )
    assert (
        payload["source"]["csv_sha256"]
        == hashlib.sha256(
            csv_path.read_bytes()
        ).hexdigest()
    )


def test_source_files_remain_unchanged(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    before_csv = csv_path.read_bytes()
    before_receipt = receipt_path.read_bytes()

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    export_quality_report(
        audit,
        csv_path,
        receipt_path,
        tmp_path / "quality_report.json",
    )

    assert csv_path.read_bytes() == before_csv
    assert receipt_path.read_bytes() == before_receipt


def test_cannot_overwrite_csv(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    with pytest.raises(ValueError, match="overwrite"):
        export_quality_report(
            audit,
            csv_path,
            receipt_path,
            csv_path,
        )


def test_incomplete_candle_rejected(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    receipt = json.loads(
        receipt_path.read_text()
    )

    receipt["retrieved_at"] = (
        START + timedelta(
            minutes=119,
            seconds=30,
        )
    ).isoformat()

    receipt_path.write_text(json.dumps(receipt))

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    assert audit["status"] == "FAIL"
    assert any(
        "Incomplete candles" in error
        for error in audit["errors"]
    )


def test_timezone_naive_timestamp_rejected(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    frame = pd.read_csv(csv_path)

    frame.loc[0, "timestamp"] = (
        "2026-11-12T10:00:00"
    )

    frame.to_csv(csv_path, index=False)
    update_hash(csv_path, receipt_path)

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    assert audit["status"] == "FAIL"
    assert any(
        "Timezone-naive" in error
        for error in audit["errors"]
    )


def test_nonfinite_price_rejected(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    frame = pd.read_csv(csv_path)
    frame.loc[0, "High"] = float("inf")

    frame.to_csv(csv_path, index=False)
    update_hash(csv_path, receipt_path)

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    assert audit["status"] == "FAIL"
    assert any(
        "Non-finite" in error
        for error in audit["errors"]
    )


def test_tampered_receipt_hash_rejected(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    receipt = json.loads(
        receipt_path.read_text()
    )

    receipt["csv_sha256"] = "0" * 64

    receipt_path.write_text(json.dumps(receipt))

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    assert audit["status"] == "FAIL"
    assert "CSV SHA-256 mismatch" in audit["errors"]


def test_export_rejects_backtesting_permission(tmp_path):
    csv_path, receipt_path = make_dataset(tmp_path)

    audit = audit_dataset(
        csv_path,
        receipt_path,
    )

    audit["directional_backtesting_allowed"] = True

    with pytest.raises(ValueError, match="blocked"):
        export_quality_report(
            audit,
            csv_path,
            receipt_path,
            tmp_path / "quality_report.json",
        )

