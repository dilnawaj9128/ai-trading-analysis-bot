"""Read-only historical outcome plot, separated from indicator calculations."""

import pandas as pd
import plotly.graph_objects as go


def build_historical_outcome_chart(frame, observation, *, context_candles=10):
    """Display up to 10 prior candles and the evaluated 15-minute window.

    Requires an observation produced by evaluate_historical_window().
    Never computes or labels a prediction or modifies the input DataFrame.
    """
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Expected historical candle DataFrame")
    if not isinstance(observation, dict):
        raise ValueError("Expected validated observation")
    index = observation.get("selected_index")
    if type(index) is not int or index < 0 or index + 15 >= len(frame):
        raise ValueError("Observation index outside complete evaluation window")
    if type(context_candles) is not int or context_candles < 0:
        raise ValueError("Invalid context candle count")
    required = {"timestamp", "Open", "High", "Low", "Close"}
    if not required.issubset(frame.columns):
        raise ValueError("Missing historical OHLC columns")

    segment = frame.iloc[max(0, index - context_candles):index + 16].copy()
    times = pd.to_datetime(segment["timestamp"], utc=True, errors="raise")
    entry_time = pd.Timestamp(observation["observation_close_utc"])
    exit_time = pd.Timestamp(observation["evaluation_close_utc"])
    if entry_time.tzinfo is None or exit_time.tzinfo is None:
        raise ValueError("Evaluation timestamps must be timezone-aware")
    if exit_time - entry_time != pd.Timedelta(minutes=15):
        raise ValueError("Evaluation must span exactly 15 minutes")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=times, open=segment["Open"], high=segment["High"],
        low=segment["Low"], close=segment["Close"],
        name="Historical candles",
    ))
    fig.add_vrect(
        x0=entry_time.isoformat(), x1=exit_time.isoformat(),
        fillcolor="rgba(100,149,237,0.16)", opacity=0.35,
        line_width=0, layer="below",
    )
    fig.add_trace(go.Scatter(
        x=[entry_time], y=[observation["entry_close"]],
        mode="markers", name="Observation close", marker={"size": 12, "symbol": "circle"},
    ))
    fig.add_trace(go.Scatter(
        x=[exit_time], y=[observation["exit_close"]],
        mode="markers", name="15-minute outcome close", marker={"size": 12, "symbol": "diamond"},
    ))
    fig.update_layout(
        title="Historical 15-minute evaluation (not a prediction)",
        height=460, xaxis_title="UTC", yaxis_title="EUR/USD price",
        xaxis_rangeslider_visible=False,
    )
    return fig
