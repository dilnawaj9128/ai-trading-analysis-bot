from scripts.run_parity_forward_once import compare_broker_csv

def test_no_broker_file_is_unverified(tmp_path):
    r = compare_broker_csv(journal=tmp_path)
    assert r['status'] == 'NO_BROKER_CSV'
    assert not r['quotex_parity_verified']

def test_no_provider_capture_cannot_verify(tmp_path):
    csv = tmp_path / 'broker.csv'
    csv.write_text('timestamp,Open,High,Low,Close\n2026-11-20T15:00:00+00:00,1.1,1.2,1.0,1.1\n')
    r = compare_broker_csv(csv, journal=tmp_path)
    assert r['status'] == 'NO_PROVIDER_CAPTURE'
    assert not r['quotex_parity_verified']
