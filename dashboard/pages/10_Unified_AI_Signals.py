import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from data.providers.multi_market_router import MultiMarketRouter
from data.providers.twelve_data_live import TwelveDataLiveProvider
from analysis.unified_pipeline import UnifiedTradingPipeline

st.set_page_config(page_title="Unified AI Signals", layout="wide")
st.title("Unified AI Multi-Market Signal & Paper Trading")

router = MultiMarketRouter()
td_provider = TwelveDataLiveProvider()
pipeline = UnifiedTradingPipeline()

col1, col2, col3 = st.columns(3)
symbol = col1.selectbox(
    "Market / Symbol",
    ["NIFTY50", "BANKNIFTY", "QX:EURUSD", "QX:GBPUSD", "QX:USDJPY", "EUR/USD", "GBP/USD", "USD/JPY"],
)
expiry = col2.selectbox("Expiry (Minutes)", [1, 5, 15], index=1)
limit = col3.number_input("Lookback Candles", min_value=50, max_value=300, value=100)


def fetch_market_candles(sym: str, exp_min: int, bar_limit: int):
    m_type = router.get_market_type(sym)
    if m_type == "INDIAN_INDICES":
        return sym, router.fetch_indian_candles(symbol=sym, interval=f"{exp_min}m", limit=bar_limit)
    mapped = router.prepare_quotex_symbol(sym) if m_type == "QUOTEX" else sym
    return mapped, td_provider.fetch_candles(symbol=mapped, interval=f"{exp_min}m", limit=bar_limit)


if st.button("Run AI Analysis", type="primary"):
    try:
        resolved_sym, candles = fetch_market_candles(symbol, expiry, int(limit))
        if not candles:
            st.warning("No candles returned (market may be closed or feed unavailable).")
        else:
            st.session_state["latest_prices"] = st.session_state.get("latest_prices", {})
            st.session_state["latest_prices"][symbol] = float(candles[-1]["close"])

            tag = f"{resolved_sym.replace('/', '')}_{expiry}m"
            res = pipeline.run_cycle(symbol=symbol, expiry_minutes=expiry, candles=candles, model_tag=tag)

            st.metric("Signal", res["signal"], f"Confidence: {res['confidence']:.1%}")
            st.write(f"**Feed Symbol:** `{resolved_sym}` | **Latest Price:** `{res['latest_price']}` | **Market Regime:** `{res['regime']}`")
            st.write("**Reasoning:**", res["reasons"])
            st.json(res["ml_breakdown"])
    except Exception as exc:
        st.error(f"Analysis Error: {exc}")

st.divider()
st.subheader("Open Paper Trades & Settlement")
open_trades = pipeline.ledger.get_open_trades()

if open_trades:
    st.dataframe(open_trades, use_container_width=True)
    if st.button("Settle All Open Trades Using Latest Live Price"):
        settled_count = 0
        for tr in open_trades:
            try:
                _, latest_candles = fetch_market_candles(tr["symbol"], int(tr["expiry_minutes"]), 10)
                if latest_candles:
                    exit_p = float(latest_candles[-1]["close"])
                    pipeline.ledger.settle_trade(int(tr["id"]), exit_price=exit_p)
                    settled_count += 1
            except Exception as err:
                st.warning(f"Could not settle Trade #{tr['id']}: {err}")
        if settled_count > 0:
            st.success(f"Settled {settled_count} open trade(s)!")
            st.rerun()
else:
    st.info("No open paper trades right now. Open trades appear automatically when an UP or DOWN signal triggers.")

st.divider()
st.subheader("Paper Trading Performance & Drift Status")
stats = pipeline.ledger.get_performance_and_drift()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Virtual Balance", f"${stats['balance']:,.2f}", f"PnL: ${stats['total_pnl']:+,.2f}")
m2.metric("Win Rate", f"{stats['win_rate']:.1%}", f"{stats['wins']}W / {stats['losses']}L")
m3.metric("Recent Win Rate", f"{stats['recent_win_rate']:.1%}")
m4.metric("Model Drift Alert", "RETRAIN NEEDED" if stats["drift_detected"] else "HEALTHY")

recent_trades = pipeline.ledger.get_recent_trades(10)
if recent_trades:
    st.write("**Recent Trade History**")
    st.dataframe(recent_trades, use_container_width=True)
