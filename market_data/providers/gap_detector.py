from datetime import datetime, timezone, timedelta


class CandleGapDetector:
    def __init__(self):
        self.last_timestamp = None

    def check(self, timestamp):
        if not isinstance(timestamp, datetime):
            raise ValueError("Expected datetime")

        if timestamp.tzinfo is None:
            raise ValueError("Timezone-aware timestamp required")

        timestamp = timestamp.astimezone(timezone.utc)

        if timestamp.second or timestamp.microsecond:
            raise ValueError("Timestamp must be minute-aligned")

        if self.last_timestamp is None:
            self.last_timestamp = timestamp
            return 0

        if timestamp <= self.last_timestamp:
            raise ValueError("Duplicate or out-of-order candle")

        delta = timestamp - self.last_timestamp
        missing = int(delta / timedelta(minutes=1)) - 1

        self.last_timestamp = timestamp
        return missing
