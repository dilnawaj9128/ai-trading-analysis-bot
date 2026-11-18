
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from simulator.session_research import (
    CSV_NAME,
    analyze_multiple_sessions,
    export_research_report,
)


def _load_accepted_frame(dataset_dir):
    """Read a dataset only after the existing audit accepts it."""

    path = Path(dataset_dir) / CSV_NAME
    frame = pd.read_csv(path)

    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], utc=True
    )

    frame = frame.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    return frame


def _candle_statistics(frame):
    """Descriptive OHLC statistics, never trading signals."""

    count = len(frame)

    if count == 0:
        return {
            "candle_count": 0,
            "bullish": 0,
            "bearish": 0,
            "doji": 0,
            "average_range": None,
            "maximum_range": None,
            "return_std": None,
        }

    opens = frame["Open"].astype(float)
    highs = frame["High"].astype(float)
    lows = frame["Low"].astype(float)
    closes = frame["Close"].astype(float)

    ranges = highs - lows
    returns = closes.pct_change().dropna()

    return {
        "candle_count": count,
        "bullish": int((closes > opens).sum()),
        "bearish": int((closes < opens).sum()),
        "doji": int((closes == opens).sum()),
        "average_range": float(ranges.mean()),
        "maximum_range": float(ranges.max()),
        "return_std": (
            float(returns.std(ddof=0))
            if len(returns) else 0.0
        ),
    }


def _coverage(timestamps):
    """
    Calculate observed UTC minute coverage.

    Missing minutes are measured between the first and last
    accepted candle. This is not an exchange-hours calendar.
    """

    unique = sorted(set(timestamps))

    if not unique:
        return {
            "first_timestamp": None,
            "last_timestamp": None,
            "observed_minutes": 0,
            "expected_minutes": 0,
            "missing_minutes": 0,
            "coverage_percent": None,
            "missing_intervals": [],
        }

    first = unique[0]
    last = unique[-1]

    expected = int(
        (last - first).total_seconds() // 60
    ) + 1

    intervals = []

    for previous, current in zip(
        unique, unique[1:]
    ):
        difference = int(
            (current - previous).total_seconds() // 60
        )

        if difference > 1:
            intervals.append({
                "start": (
                    previous + pd.Timedelta(minutes=1)
                ).isoformat(),
                "end": (
                    current - pd.Timedelta(minutes=1)
                ).isoformat(),
                "missing_minutes": difference - 1,
            })

    missing = expected - len(unique)

    return {
        "first_timestamp": first.isoformat(),
        "last_timestamp": last.isoformat(),
        "observed_minutes": len(unique),
        "expected_minutes": expected,
        "missing_minutes": missing,
        "coverage_percent": (
            len(unique) / expected * 100
        ),
        "missing_intervals": intervals,
    }


def build_advanced_research(dataset_dirs):
    """
    Generate advanced research from accepted datasets only.

    Existing quality, duplicate and overlap rules are reused.
    """

    base = analyze_multiple_sessions(dataset_dirs)

    hourly_frames = defaultdict(list)
    accepted_frames = []
    rankings = []

    for index, session in enumerate(
        base["sessions"], start=1
    ):
        if session["selection_status"] != "ACCEPTED":
            continue

        frame = _load_accepted_frame(
            session["dataset"]
        )

        accepted_frames.append(frame)

        stats = _candle_statistics(frame)

        rankings.append({
            "session": index,
            "dataset": session["dataset"],
            "candle_count": stats["candle_count"],
            "average_range": stats["average_range"],
            "return_std": stats["return_std"],
        })

        # Group by exact UTC hour, including the calendar date.
        frame = frame.copy()

        frame["hour_start"] = frame[
            "timestamp"
        ].dt.floor("h")

        for hour, group in frame.groupby(
            "hour_start"
        ):
            hourly_frames[
                hour.isoformat()
            ].append(
                group.drop(columns=["hour_start"])
            )

    hourly = []

    for hour in sorted(hourly_frames):
        combined_hour = pd.concat(
            hourly_frames[hour],
            ignore_index=True,
        )

        hourly.append({
            "hour_start_utc": hour,
            **_candle_statistics(combined_hour),
        })

    rankings.sort(
        key=lambda item: (
            -item["average_range"],
            item["session"],
        )
    )

    for position, item in enumerate(
        rankings, start=1
    ):
        item["volatility_rank"] = position

    if accepted_frames:
        combined_frame = pd.concat(
            accepted_frames,
            ignore_index=True,
        ).sort_values("timestamp")

        timestamps = combined_frame[
            "timestamp"
        ].tolist()

        combined_stats = _candle_statistics(
            combined_frame
        )

        # Cross-session return_std is intentionally omitted:
        # returns across disconnected sessions are not
        # necessarily consecutive market observations.
        combined_stats["return_std"] = None
    else:
        timestamps = []
        combined_stats = _candle_statistics(
            pd.DataFrame()
        )

    advanced = {
        **base,
        "schema_version": 3,
        "report_type": "advanced_historical_research",
        "analysis_only": True,
        "directional_backtesting_allowed": False,
        "advanced_analytics": {
            "combined_candle_statistics": combined_stats,
            "coverage": _coverage(timestamps),
            "hourly_utc": hourly,
            "volatility_ranking": rankings,
        },
        "dashboard": {
            "cards": {
                "accepted_sessions": base[
                    "datasets_accepted"
                ],
                "unique_candles": base[
                    "total_valid_candles"
                ],
                "duplicate_sessions": base[
                    "datasets_duplicate"
                ],
                "overlapping_sessions": base[
                    "datasets_overlapping"
                ],
            },
            "hourly_chart": [
                {
                    "hour": item["hour_start_utc"],
                    "average_range": item[
                        "average_range"
                    ],
                    "candle_count": item[
                        "candle_count"
                    ],
                }
                for item in hourly
            ],
        },
    }

    advanced["limitations"].extend([
        "Coverage uses the observed first-to-last UTC window",
        "Missing minutes may include market closures",
        "Hourly statistics are grouped by UTC calendar hour",
        "Session rankings are descriptive, not predictive",
        "Cross-session returns are not treated as continuous",
        "Feed authenticity and Quotex prices remain unverified",
    ])

    return advanced


def export_advanced_research(report, output_path):
    """Reuse the existing atomic, research-only JSON exporter."""

    if report.get("schema_version") != 3:
        raise ValueError(
            "Expected advanced research schema version 3"
        )

    return export_research_report(
        report, output_path
    )

