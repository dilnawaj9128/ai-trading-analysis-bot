import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

ROOT = Path("data/research/nifty50/live")
DB = ROOT / "predictions.db"

st.set_page_config(
    page_title="AI Market Intelligence",
    page_icon="📈",
    layout="wide"
)

st.title("AI Market Intelligence")
st.caption("NIFTY 50 | UPSTOX | ML RESEARCH ENGINE")

@st.fragment(run_every="10s")
def dashboard():

    now = pd.Timestamp.now(tz="Asia/Kolkata")
    minute = now.hour * 60 + now.minute

    session = (
        now.weekday() < 5
        and 555 <= minute < 930
    )

    st.caption(f"Dashboard time: {now:%d %b %Y %H:%M:%S IST}")

    if not (ROOT / "latest.csv").exists():
        st.warning("Waiting for market data")
        return

    try:
        candles = pd.read_csv(ROOT / "latest.csv")
        candles.timestamp = pd.to_datetime(
            candles.timestamp, utc=True
        )
        candles = candles.sort_values("timestamp")

        if candles.empty:
            st.warning("No market candles")
            return

    except Exception:
        st.warning("Waiting for next data refresh")
        return

    last = candles.iloc[-1]
    close_time = last.timestamp + pd.Timedelta(minutes=1)
    age = (now - close_time).total_seconds()
    fresh = session and 0 <= age <= 120

    if fresh:
        status = "LIVE DATA"
    elif session:
        status = "WAITING / STALE"
    else:
        status = "MARKET CLOSED"

    a,b,c,d = st.columns(4)

    a.metric("NIFTY 50", f"{last.Close:,.2f}")
    b.metric("Market status", status)
    c.metric("Candles", len(candles))
    d.metric("Data provider", "Upstox")

    st.caption(
        "Last completed candle: "
        + str(close_time.tz_convert("Asia/Kolkata"))
    )

    st.subheader("Market chart")

    chart = go.Figure(
        data=[go.Candlestick(
            x=candles.timestamp.dt.tz_convert("Asia/Kolkata"),
            open=candles.Open,
            high=candles.High,
            low=candles.Low,
            close=candles.Close
        )]
    )

    chart.update_layout(
        height=430,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=10,r=10,t=10,b=10)
    )

    st.plotly_chart(chart, use_container_width=True)

    st.subheader("AI Directional Predictions")

    columns = st.columns(3)

    if DB.exists():
        try:
            with sqlite3.connect(DB, timeout=5) as conn:
                history = pd.read_sql_query(
                    "SELECT * FROM predictions ORDER BY timestamp DESC",
                    conn
                )
        except Exception:
            history = pd.DataFrame()
    else:
        history = pd.DataFrame()

    for col,h in zip(columns,[5,10,15]):

        with col:
            st.markdown(f"### {h} Minute")

            if history.empty:
                st.info("Waiting for prediction")
                continue

            rows = history[history.horizon == h]

            if rows.empty:
                st.info("Waiting for prediction")
                continue

            r = rows.iloc[0]

            entry_time = pd.Timestamp(r.timestamp)
            expiry = pd.Timestamp(r.expiry) + pd.Timedelta(minutes=1)

            active = (
                fresh
                and r.result == "PENDING"
                and now < expiry
                and entry_time.tz_convert("Asia/Kolkata").date()
                    == now.date()
            )

            st.metric(
                "Research direction",
                r.direction if active else "NO TRADE"
            )

            st.write(f"Last model direction: {r.direction}")
            st.write(f"UP score: {r.up_score*100:.2f}%")
            st.progress(float(r.up_score))
            st.write(f"DOWN score: {(1-r.up_score)*100:.2f}%")
            st.progress(float(1-r.up_score))
            st.caption(f"Entry reference: {r.entry:,.2f}")
            st.caption(f"Expiry: {expiry.tz_convert('Asia/Kolkata')}")
            st.caption("Trade approved: FALSE")

    st.divider()
    st.subheader("Forward Performance")

    if history.empty:
        st.info("No recorded predictions yet")
        return

    wins = int((history.result == "WIN").sum())
    losses = int((history.result == "LOSS").sum())
    pushes = int((history.result == "PUSH").sum())
    pending = int((history.result == "PENDING").sum())

    a,b,c,d,e = st.columns(5)

    a.metric("Wins", wins)
    b.metric("Losses", losses)
    c.metric("Pushes", pushes)
    d.metric("Pending", pending)
    e.metric(
        "Recorded accuracy",
        f"{100*wins/(wins+losses):.2f}%"
        if wins+losses else "Unverified"
    )

    stats = []

    for h in [5,10,15]:
        r = history[history.horizon == h]
        w = int((r.result == "WIN").sum())
        l = int((r.result == "LOSS").sum())

        stats.append({
            "Timeframe": f"{h}m",
            "Predictions": len(r),
            "Wins": w,
            "Losses": l,
            "Accuracy": (
                f"{100*w/(w+l):.2f}%"
                if w+l else "Unverified"
            )
        })

    st.dataframe(
        pd.DataFrame(stats),
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Prediction History")
    st.dataframe(history, use_container_width=True)

    st.download_button(
        "Download Prediction History",
        history.to_csv(index=False),
        file_name="nifty_prediction_history.csv",
        mime="text/csv"
    )

st.warning(
    "Research only. Model scores are not verified probabilities. "
    "Automatic trading is disabled."
)

dashboard()
