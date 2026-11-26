from __future__ import annotations

from datetime import datetime, time, timezone, timedelta
from typing import Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))


class MarketSessionFilter:
    """Filters out noisy market-open/close spikes and low-liquidity off-session hours."""

    INDIAN_PRIME_START = time(9, 45)
    INDIAN_PRIME_END = time(15, 10)

    FX_SESSIONS_IST = (
        (time(13, 30), time(17, 30)),  # London session
        (time(18, 30), time(22, 30)),  # London-NY overlap
    )

    @classmethod
    def parse_timestamp_ist(cls, ts: Optional[str]) -> datetime:
        if not ts:
            return datetime.now(IST)
        clean = ts.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST)

    @classmethod
    def check_session(cls, symbol: str, timestamp_str: Optional[str] = None) -> Tuple[bool, str]:
        dt_ist = cls.parse_timestamp_ist(timestamp_str)
        if dt_ist.weekday() >= 5:
            return False, f"Weekend ({dt_ist.strftime('%A')}): markets closed."

        t_ist = dt_ist.time()
        clean_sym = symbol.strip().upper().replace(" ", "").replace("_", "")

        if clean_sym in ("NIFTY50", "BANKNIFTY"):
            if cls.INDIAN_PRIME_START <= t_ist <= cls.INDIAN_PRIME_END:
                return True, f"Valid Indian prime session ({t_ist.strftime('%H:%M')} IST)."
            return (
                False,
                f"Blocked outside Indian prime window 09:45-15:10 IST (current: {t_ist.strftime('%H:%M')} IST).",
            )

        for start_t, end_t in cls.FX_SESSIONS_IST:
            if start_t <= t_ist <= end_t:
                return True, f"Valid FX high-liquidity session ({t_ist.strftime('%H:%M')} IST)."

        return (
            False,
            f"Blocked low-liquidity FX hour ({t_ist.strftime('%H:%M')} IST; allowed: 13:30-17:30 & 18:30-22:30 IST).",
        )
