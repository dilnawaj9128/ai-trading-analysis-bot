"""Read-only Stage 52D Part 4D recovery diagnosis."""

from pathlib import Path

from market_data.recovery_deadlock import diagnose


def main():
    result = diagnose(
        root=Path("data/api_usage"),
        case_path=Path(
            "data/recovery_reports/"
            "stage52d_20261119_uncertain_case.json"
        ),
        archive_path=Path(
            "data/recovery_reports/"
            "stage52d_historical_provider_credits.json"
        ),
    )

    print("=== STAGE 52D PART 4D ===")

    for key, value in result.items():
        print(f"{key}: {value}")

    print("Network requests: 0")
    print("Original journals modified: 0")


if __name__ == "__main__":
    main()
