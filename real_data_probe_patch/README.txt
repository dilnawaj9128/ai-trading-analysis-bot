CONTROLLED REAL DATA PROBE (not an automatic live monitor)

1. Copy scripts/approved_real_data_probe.py to your project's scripts/ folder.
2. Copy tests/test_approved_real_data_probe.py to your project's tests/ folder.
3. Run: env -u TWELVE_DATA_API_KEY python -m pytest tests/test_approved_real_data_probe.py -q
4. Run full tests: env -u TWELVE_DATA_API_KEY python -m pytest tests/ -q
5. Optional real request (consumes credits, explicit one-time consent):
   set -a; source .env; set +a
   PYTHONPATH="$PWD" python scripts/approved_real_data_probe.py --approve-one-request

The script uses a separate durable audit record and does NOT remove or modify
existing bootstrap claims, manual refresh lifecycle, authorization journals,
or reservation ledgers. No automatic retry. A failed/uncertain operation
requires manual review. At most one approved request per 180 seconds.
The price feed is Twelve Data, NOT verified Quotex prices.
