"""Stage 51 offline safety decision. No provider fetch."""
from research.stage51_forward_recorder import (
    build_record,
    save_record,
    verify_record,
)


def main():
    record = build_record()
    path = save_record(record)

    if not verify_record(path):
        raise SystemExit("BLOCKED: Saved evidence checksum mismatch")

    print("=== STAGE 51 FORWARD RESEARCH GATE ===")
    print("Recorded UTC:", record["recorded_at_utc"])
    print("Market:", record["symbol"])
    print("Expiry:", record["expiry_minutes"])
    print("Probe:", record["probe_status"])
    print("Signal:", record["signal"])
    print("Authorization:", record["authorization"])
    print("Reasons:")

    for reason in record["reasons"]:
        print(" -", reason)

    print("Evidence file:", path)
    print("Checksum: VERIFIED")
    print("Real provider requests: 0")
    print("Directional predictions: 0")
    print("Trading execution: DISABLED")


if __name__ == "__main__":
    main()
