
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


@dataclass
class DataQuality:
    status: str
    total_candles: int
    missing_candles: int
    duplicate_candles: int
    invalid_candles: int
    last_candle_age_seconds: float | None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        return self.status == "VALID"


class DataValidator:

    REQUIRED_COLUMNS = [
        "timestamp",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    def validate(
        self,
        df: pd.DataFrame,
        interval_seconds: int,
        max_staleness_seconds: int | None = None,
        min_candles: int = 1,
        now: datetime | None = None
    ) -> DataQuality:

        warnings = []

        if df.empty:
            return DataQuality(
                "INVALID", 0, 0, 0, 0, None,
                ["No market data available"]
            )

        missing_columns = (
            set(self.REQUIRED_COLUMNS) - set(df.columns)
        )

        if missing_columns:
            return DataQuality(
                "INVALID", len(df), 0, 0, 0, None,
                [f"Missing columns: {missing_columns}"]
            )

        data = df.copy()

        data["timestamp"] = pd.to_datetime(
            data["timestamp"],
            utc=True,
            errors="coerce"
        )

        numeric_columns = [
            "Open", "High", "Low", "Close"
        ]

        for col in numeric_columns:
            data[col] = pd.to_numeric(
                data[col],
                errors="coerce"
            )

        duplicate_count = int(
            data["timestamp"].duplicated().sum()
        )

        data = data.drop_duplicates(
            subset="timestamp",
            keep="last"
        )

        invalid_mask = (
            data["timestamp"].isna()
            | data[numeric_columns].isna().any(axis=1)
            | (data[numeric_columns] <= 0).any(axis=1)
            | (data["High"] < data["Low"])
            | (
                data["High"]
                < data[["Open", "Close"]].max(axis=1)
            )
            | (
                data["Low"]
                > data[["Open", "Close"]].min(axis=1)
            )
        )

        invalid_count = int(invalid_mask.sum())

        data = data.loc[~invalid_mask].copy()

        data = data.sort_values("timestamp")

        missing_count = 0
        age_seconds = None

        if len(data) >= 2:

            differences = (
                data["timestamp"].diff().dt.total_seconds()
            )

            missing_count = int(
                sum(
                    max(
                        0,
                        round(
                            difference / interval_seconds
                        ) - 1
                    )
                    for difference in differences.dropna()
                )
            )

            if missing_count:
                warnings.append(
                    f"{missing_count} missing candle(s) detected"
                )

        if not data.empty:

            current_time = now or datetime.now(timezone.utc)

            if current_time.tzinfo is None:
                raise ValueError(
                    "now must be timezone-aware"
                )

            last_timestamp = data["timestamp"].iloc[-1]

            age_seconds = max(
                0.0,
                (
                    pd.Timestamp(current_time)
                    - last_timestamp
                ).total_seconds() - interval_seconds
            )

        if max_staleness_seconds is None:
            max_staleness_seconds = interval_seconds * 3

        if len(data) < min_candles:
            warnings.append(
                "Insufficient valid historical candles"
            )

        stale = (
            age_seconds is None
            or age_seconds > max_staleness_seconds
        )

        if stale:
            warnings.append(
                "Market data is stale or unavailable"
            )

        if duplicate_count:
            warnings.append(
                f"{duplicate_count} duplicate candle(s) removed"
            )

        if invalid_count:
            warnings.append(
                f"{invalid_count} invalid candle(s) removed"
            )

        if len(data) < min_candles:
            status = "INVALID"
        elif stale:
            status = "STALE"
        elif invalid_count:
            status = "INVALID"
        else:
            status = "VALID"

        return DataQuality(
            status=status,
            total_candles=len(data),
            missing_candles=missing_count,
            duplicate_candles=duplicate_count,
            invalid_candles=invalid_count,
            last_candle_age_seconds=age_seconds,
            warnings=warnings
        )

