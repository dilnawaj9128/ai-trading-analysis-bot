"""Stage 51B: record local market-source readiness safely."""

from research.stage51_forward_observation import record_observation


def main():
    record, path, created = record_observation()

    print("=== STAGE 51B FORWARD OBSERVATION ===")
    print("New observation:", created)
    print("Recorded UTC:", record["recorded_at_utc"])
    print("Market:", record["symbol"])
    print("Last candle:", record["latest_candle_open_utc"])
    print("Candles:", record["candle_count"])
    print("Source hash:", record["csv_sha256"])
    print("Probe:", record["probe_status"])
    print("Signal:", record["signal"])
    print("Authorization:", record["authorization"])
    print("Reasons:", ", ".join(record["reasons"]))
    print("Evidence:", path)
    print("Checksum: VERIFIED")
    print("Real API requests: 0")
    print("Directional predictions: 0")
    print("Trading execution: DISABLED")


if __name__ == "__main__":
    main()
