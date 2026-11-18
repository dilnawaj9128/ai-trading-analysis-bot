
"""Local dataset trust gate for research backtesting.

A trusted registry is an operator-maintained allowlist.
Hash matching proves integrity, not provider authenticity.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from simulator.historical_integrity import HistoricalProvenance


@dataclass(frozen=True)
class VerifiedDataset:
    provenance: HistoricalProvenance
    dataset_sha256: str
    manifest_sha256: str
    trust_reference: str


def file_sha256(path):
    digest = sha256()

    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024), b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _read_json(path):
    with Path(path).open(
        "r", encoding="utf-8"
    ) as stream:
        return json.load(stream)


def _parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("retrieved_at must be a string.")

    try:
        result = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            "Invalid retrieved_at timestamp."
        ) from exc

    if result.tzinfo is None:
        raise ValueError(
            "retrieved_at must include a timezone."
        )

    return result.astimezone(timezone.utc)


def verify_dataset(
    csv_path,
    manifest_path,
    registry_path,
):
    csv_path = Path(csv_path)
    manifest_path = Path(manifest_path)
    registry_path = Path(registry_path)

    if not registry_path.is_file():
        raise ValueError(
            "Trusted registry is missing. "
            "Directional backtesting blocked."
        )

    manifest_hash = file_sha256(manifest_path)
    manifest = _read_json(manifest_path)
    registry = _read_json(registry_path)

    if not isinstance(manifest, dict):
        raise ValueError("Invalid manifest format.")

    if not isinstance(registry, dict):
        raise ValueError("Invalid registry format.")

    if registry.get("schema_version") != 1:
        raise ValueError(
            "Unsupported trusted registry version."
        )

    entries = registry.get("trusted_manifests")

    if not isinstance(entries, list):
        raise ValueError(
            "trusted_manifests must be a list."
        )

    trusted = None

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(
                "Invalid trusted registry entry."
            )

        if entry.get("manifest_sha256") == manifest_hash:
            trusted = entry
            break

    if trusted is None:
        raise ValueError(
            "Manifest is not in the trusted registry."
        )

    if trusted.get("status") != "approved":
        raise ValueError(
            "Manifest is not approved."
        )

    reference = trusted.get("verification_reference")

    if not isinstance(reference, str) or not reference.strip():
        raise ValueError(
            "Independent verification reference required."
        )

    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported manifest version.")

    if manifest.get("symbol") != "EUR/USD":
        raise ValueError(
            "Only EUR/USD is supported."
        )

    if manifest.get("timeframe") != "1min":
        raise ValueError(
            "Only 1-minute candles are supported."
        )

    if manifest.get("timestamp_semantics") != "candle_open_utc":
        raise ValueError(
            "Unsupported timestamp semantics."
        )

    actual_csv_hash = file_sha256(csv_path)
    expected_csv_hash = manifest.get("csv_sha256")

    if expected_csv_hash != actual_csv_hash:
        raise ValueError(
            "CSV hash mismatch. Dataset may have changed."
        )

    provider = manifest.get("provider")
    mode = manifest.get("feed_mode")

    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("Provider is required.")

    if not isinstance(mode, str):
        raise ValueError("Feed mode is required.")

    mode = mode.strip().lower()

    if mode not in {"live", "delayed"}:
        raise ValueError(
            "Unknown or unsupported feed mode."
        )

    retrieved_at = _parse_utc(
        manifest.get("retrieved_at")
    )

    return VerifiedDataset(
        provenance=HistoricalProvenance(
            provider=provider,
            feed_mode=mode,
            retrieved_at=retrieved_at,
        ),
        dataset_sha256=actual_csv_hash,
        manifest_sha256=manifest_hash,
        trust_reference=reference,
    )

