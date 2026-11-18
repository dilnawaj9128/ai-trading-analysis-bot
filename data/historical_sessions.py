
"""Split historical candles into contiguous 1m sessions.

Does not fill missing candles or alter original prices.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from simulator.historical_integrity import normalize_candles


@dataclass(frozen=True)
class SessionSummary:
    session_id: int
    start_time: object
    end_time: object
    candle_count: int
    eligible_for_comparison: bool


def split_sessions(candles, min_candles=66):
    if min_candles < 1:
        raise ValueError("min_candles must be positive.")

    frame = normalize_candles(candles)
    frame = frame.reset_index(drop=True)

    if frame.empty:
        raise ValueError("No candles available.")

    timestamps = frame["timestamp"]

    if timestamps.duplicated().any():
        raise ValueError("Duplicate timestamps.")

    differences = timestamps.diff()

    if (differences.iloc[1:] <= pd.Timedelta(0)).any():
        raise ValueError(
            "Candles must be in ascending order."
        )

    boundaries = (
        differences.ne(pd.Timedelta(minutes=1))
    ).cumsum()

    sessions = []
    summaries = []

    for number, (_, group) in enumerate(
        frame.groupby(boundaries, sort=True),
        start=1,
    ):
        session = group.reset_index(drop=True)
        sessions.append(session)

        summaries.append(
            SessionSummary(
                session_id=number,
                start_time=session.iloc[0]["timestamp"],
                end_time=session.iloc[-1]["timestamp"],
                candle_count=len(session),
                eligible_for_comparison=(
                    len(session) >= min_candles
                ),
            )
        )

    return sessions, summaries


def export_sessions(
    candles,
    output_dir,
    min_candles=66,
):
    sessions, summaries = split_sessions(
        candles, min_candles=min_candles
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True, exist_ok=True
    )

    paths = []

    for summary, session in zip(summaries, sessions):
        filename = (
            f"session_{summary.session_id:03d}.csv"
        )
        path = output_dir / filename

        if path.exists():
            raise FileExistsError(
                f"Session output already exists: {path}"
            )

        session.to_csv(path, index=False)
        paths.append(path)

    return paths, summaries

