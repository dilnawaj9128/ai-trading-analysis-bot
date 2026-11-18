
"""Stage 6.6.2 - Historical CSV dataset loader.

No network calls, trading actions, or database writes.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from simulator.historical_integrity import normalize_candles


REQUIRED_COLUMNS = (
    "timestamp", "Open", "High", "Low", "Close"
)


@dataclass(frozen=True)
class HistoricalDataset:
    candles: pd.DataFrame
    file_path: Path
    candle_count: int
    start_time: object
    end_time: object


def load_historical_csv(file_path, min_candles=66):
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Historical CSV not found: {path}"
        )

    if path.suffix.lower() != ".csv":
        raise ValueError("Historical dataset must be CSV.")

    if min_candles < 1:
        raise ValueError("min_candles must be positive.")

    # Keep strings initially so malformed timestamps
    # are rejected by the existing integrity validator.
    raw = pd.read_csv(path, dtype=str)

    if raw.empty:
        raise ValueError("Historical CSV is empty.")

    raw.columns = [
        str(column).strip()
        for column in raw.columns
    ]

    if raw.columns.duplicated().any():
        raise ValueError("Duplicate CSV column names.")

    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in raw.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required CSV columns: {missing}"
        )

    # Preserve only the fields needed by the
    # historical integrity and backtesting engines.
    selected = raw.loc[
        :, list(REQUIRED_COLUMNS)
    ].copy()

    # Reject empty fields before numeric conversion.
    if selected.isna().any().any():
        raise ValueError(
            "Historical CSV contains missing values."
        )

    # Reuse the strict Stage 6.5 validator.
    normalized = normalize_candles(selected)
    normalized = normalized.reset_index(drop=True)

    if len(normalized) < min_candles:
        raise ValueError(
            f"At least {min_candles} candles required; "
            f"received {len(normalized)}."
        )

    # Every consecutive candle must be one minute apart.
    intervals = normalized["timestamp"].diff().iloc[1:]

    if not intervals.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError(
            "Historical CSV contains missing minute "
            "candles or non-contiguous sessions."
        )

    return HistoricalDataset(
        candles=normalized,
        file_path=path.resolve(),
        candle_count=len(normalized),
        start_time=normalized.iloc[0]["timestamp"],
        end_time=normalized.iloc[-1]["timestamp"],
    )

