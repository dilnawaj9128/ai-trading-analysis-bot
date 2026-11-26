from datetime import datetime, timezone


class CandleBuilder:
    def __init__(self):
        self.current = None

    def add_tick(self, timestamp, price):
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )

        if timestamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")

        timestamp = timestamp.astimezone(timezone.utc)
        price = float(price)

        if not (0 < price < float("inf")):
            raise ValueError("Invalid price")

        minute = timestamp.replace(second=0, microsecond=0)

        if self.current and minute < self.current["timestamp"]:
            raise ValueError("Out-of-order tick")

        if self.current and minute > self.current["timestamp"]:
            completed = dict(self.current)
            self.current = self._new_candle(minute, price)
            return completed

        if self.current is None:
            self.current = self._new_candle(minute, price)
        else:
            self.current["high"] = max(self.current["high"], price)
            self.current["low"] = min(self.current["low"], price)
            self.current["close"] = price

        return None

    @staticmethod
    def _new_candle(minute, price):
        return {
            "timestamp": minute,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
        }
