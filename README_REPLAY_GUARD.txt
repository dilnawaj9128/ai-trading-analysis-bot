Prediction replay guard (offline safety patch)
- Updates existing research/real_prediction_campaign.py and scripts/run_real_prediction_live_once.py.
- Adds tests/test_prediction_replay_guard.py.
- Prevents the common duplicate API spend when a 15-minute prospective observation window is active.
- Does not alter existing observations or reservations.
- Does NOT guarantee credit availability, candle completeness, or signal accuracy.
- The final observation lock still enforces non-overlap.
- Does not send HTTP during install/tests.

Recommended install (from your project root):
cp research/real_prediction_campaign.py research/real_prediction_campaign.py.before_replay_guard
cp scripts/run_real_prediction_live_once.py scripts/run_real_prediction_live_once.py.before_replay_guard
unzip -o ~/Downloads/ai-trading-replay-guard.zip
PYTHONPATH="$PWD" env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q

Then inspect saved scorecard, no HTTP:
python -m scripts.run_real_prediction_campaign

Avoid reissuing --approve-up-to-two-requests if a request could already be uncertain.
