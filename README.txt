EUR/USD REAL DATA MODE — STREAMLIT
New standalone page: dashboard/pages/10_Real_Data_Mode.py
Logic: dashboard/real_data_mode.py
Tests: tests/test_real_data_mode.py

Install:
  cd ~/ai-trading-analysis-bot && source venv/bin/activate
  unzip -o ~/Downloads/ai-trading-real-data-mode.zip
  PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
  python -m streamlit run dashboard/app.py

In Streamlit sidebar select "Real Data Mode". Consent and click Fetch once.
This calls your existing authorized-live-fetch + credit-renewal guards; at most TWO accounted HTTP calls for one approval. Do not retry blocked or timed-out requests without accounting review.

The separate page presents completed UTC 1-min OHLC, gap/staleness status, EMA 20/50, RSI/MACD/ATR, candlestick chart, and 20 recent candles. It never invokes the signal engine or places orders. Other existing dashboard pages are unchanged and may still display research signals.

Offline focused tests passed: 9.
No actual API test is possible in the assistant sandbox; full repo regression must run on local Ubuntu.
