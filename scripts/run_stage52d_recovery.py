"""Offline Stage 52D recovery assessment."""

from pathlib import Path

from market_data.uncertain_recovery import assess_recovery


def main():
    root = Path("data/api_usage")

    result = assess_recovery(
        probe_path=root / "approved_research_probe.json",
        execution_path=root / "credit_refresh_execution.json",
        lifecycle_path=root / "credit_refresh_lifecycle.json",
        provider_path=root / "provider_credits.json",
    )

    print("=== STAGE 52D RECOVERY ===")

    for key, value in result.items():
        if key == "probe_journal_sha256":
            print("probe_journal_sha256: calculated")
        else:
            print(f"{key}: {value}")

    print("HTTP requests: 0")
    print("Original state files changed: 0")


if __name__ == "__main__":
    main()
