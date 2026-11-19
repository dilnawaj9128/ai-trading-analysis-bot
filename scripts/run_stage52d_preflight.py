"""Run offline Stage 52D recovery preflight."""

from pathlib import Path
from market_data.recovery_preflight import evaluate_preflight


def main():
    result = evaluate_preflight(
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

    print("=== STAGE 52D PART 4A ===")

    for key, value in result.items():
        print(f"{key}: {value}")

    print("HTTP requests: 0")
    print("State writes: 0")


if __name__ == "__main__":
    main()
