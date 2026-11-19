"""Stage 33 read-only provenance audit: no API credits, no orders."""
import argparse
from research.stage33_provider_attestation import evaluate_attested_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/real_market/latest_eurusd_completed.csv")
    parser.add_argument("--journal", default="data/api_usage/approved_research_probe.json")
    args = parser.parse_args()
    result = evaluate_attested_snapshot(args.csv, args.journal)
    print("STAGE 33 PROVIDER ATTESTATION AUDIT")
    for field in ("status", "signal", "reason", "provider_attested", "analysis_only", "execution_enabled"):
        print(f"{field}: {result[field]}")
    print("No network/API usage; no broker parity or feed mode inferred")


if __name__ == "__main__":
    main()
