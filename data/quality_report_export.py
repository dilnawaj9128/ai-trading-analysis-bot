
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_quality_report(
    report: dict,
    csv_path: str | Path,
    receipt_path: str | Path,
    output_path: str | Path,
) -> Path:
    """
    Export a quality audit report without modifying
    the original CSV or acquisition receipt.
    """

    csv_path = Path(csv_path)
    receipt_path = Path(receipt_path)
    output_path = Path(output_path)

    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)

    if not receipt_path.is_file():
        raise FileNotFoundError(receipt_path)

    if output_path.resolve() in {
        csv_path.resolve(),
        receipt_path.resolve(),
    }:
        raise ValueError(
            "Report cannot overwrite source files"
        )

    if not isinstance(report, dict):
        raise TypeError("Audit report must be a dictionary")

    if report.get("status") not in {"PASS", "FAIL"}:
        raise ValueError("Invalid audit report status")

    if report.get("directional_backtesting_allowed") is not False:
        raise ValueError(
            "Directional backtesting must remain blocked"
        )

    # Audit result must be tied to the exact input bytes.
    payload = {
        "schema_version": 1,
        "report_type": "historical_dataset_quality",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": {
            "csv_path": str(csv_path),
            "receipt_path": str(receipt_path),
            "csv_sha256": sha256_file(csv_path),
            "receipt_sha256": sha256_file(receipt_path),
        },
        "audit": report,
        "limitations": [
            "SHA-256 verifies byte consistency, not provider authenticity",
            "Provider feed mode is not independently verified",
            "Broker execution prices are not verified",
            "Directional backtesting is not authorized",
            "This report is not a prediction accuracy measurement",
        ],
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Atomic replacement prevents partially written JSON.
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=".quality_report_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)

            json.dump(
                payload,
                handle,
                indent=2,
                allow_nan=False,
            )

            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            output_path,
        )

    finally:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

    return output_path

