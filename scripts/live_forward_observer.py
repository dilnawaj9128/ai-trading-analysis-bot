import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.providers.multi_market_router import MultiMarketRouter
from data.providers.twelve_data_live import TwelveDataLiveProvider
from analysis.unified_pipeline import UnifiedTradingPipeline
from simulator.drift_retrainer import DriftAutoRetrainer


def _fetch_candles(router: MultiMarketRouter, td: TwelveDataLiveProvider, symbol: str, expiry: int, limit: int):
    m_type = router.get_market_type(symbol)
    if m_type == "INDIAN_INDICES":
        return symbol, router.fetch_indian_candles(symbol=symbol, interval=f"{expiry}m", limit=limit)
    mapped = router.prepare_quotex_symbol(symbol) if m_type == "QUOTEX" else symbol
    return mapped, td.fetch_candles(symbol=mapped, interval=f"{expiry}m", limit=limit)


def run_loop(symbol: str, expiry: int, limit: int, interval_sec: int, max_cycles: int) -> None:
    router = MultiMarketRouter()
    td = TwelveDataLiveProvider()
    pipeline = UnifiedTradingPipeline()
    retrainer = DriftAutoRetrainer(ledger=pipeline.ledger)

    cycles = 0
    while max_cycles <= 0 or cycles < max_cycles:
        cycles += 1
        try:
            resolved_sym, candles = _fetch_candles(router, td, symbol, expiry, limit)
            if candles:
                latest_price = float(candles[-1]["close"])

                # Settle any open trades for this symbol using latest price
                for tr in pipeline.ledger.get_open_trades():
                    if tr["symbol"] == symbol:
                        pipeline.ledger.settle_trade(int(tr["id"]), exit_price=latest_price)

                # Run signal cycle
                tag = f"{resolved_sym.replace('/', '')}_{expiry}m"
                res = pipeline.run_cycle(symbol=symbol, expiry_minutes=expiry, candles=candles, model_tag=tag)
                print(
                    f"[Cycle {cycles}] {symbol} ({expiry}m) -> Signal: {res['signal']} | "
                    f"Conf: {res['confidence']:.1%} | Regime: {res['regime']} | Price: {latest_price}"
                )

                # Check drift and auto-retrain if needed
                retrain_res = retrainer.check_and_retrain(candles=candles, horizon_bars=1)
                if retrain_res["retrained"]:
                    print(f"[Retrain] {retrain_res['reason']}")
            else:
                print(f"[Cycle {cycles}] No candles returned for {symbol}.")
        except Exception as exc:
            print(f"[Cycle {cycles}] Error: {exc}")

        if max_cycles > 0 and cycles >= max_cycles:
            break
        time.sleep(max(1, interval_sec))


def main() -> None:
    parser = argparse.ArgumentParser(description="Live forward observation and settlement loop.")
    parser.add_argument("--symbol", default="BANKNIFTY")
    parser.add_argument("--expiry", type=int, default=5, choices=[1, 5, 15])
    parser.add_argument("--bars", type=int, default=100)
    parser.add_argument("--interval-sec", type=int, default=60)
    parser.add_argument("--max-cycles", type=int, default=1, help="0 for infinite loop, 1+ for bounded cycles")
    args = parser.parse_args()
    run_loop(args.symbol, args.expiry, args.bars, args.interval_sec, args.max_cycles)


if __name__ == "__main__":
    main()
