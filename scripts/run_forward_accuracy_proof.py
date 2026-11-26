import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.providers.multi_market_router import MultiMarketRouter
from simulator.forward_accuracy_proof import ForwardAccuracyProver


def main() -> None:
    parser = argparse.ArgumentParser(description="Run forward testing & accuracy proof.")
    parser.add_argument("--symbol", default="NIFTY50", help="NIFTY50 or BANKNIFTY")
    parser.add_argument("--expiry", type=int, default=5, choices=[1, 5, 15])
    parser.add_argument("--bars", type=int, default=180, help="Total candles to fetch")
    parser.add_argument("--horizon", type=int, default=1, help="Settlement horizon in candles")
    parser.add_argument("--min-conf", type=float, default=0.58)
    args = parser.parse_args()

    router = MultiMarketRouter()
    candles = router.fetch_indian_candles(symbol=args.symbol, interval=f"{args.expiry}m", limit=args.bars)
    if not candles:
        print("No live candles returned; check market hours or network.")
        sys.exit(1)

    prover = ForwardAccuracyProver(min_confidence=args.min_conf, warmup_bars=45)
    report = prover.run_forward_proof(
        symbol=args.symbol,
        expiry_minutes=args.expiry,
        candles=candles,
        horizon_bars=args.horizon,
    )
    summary = {k: v for k, v in report.items() if k != "trades"}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
