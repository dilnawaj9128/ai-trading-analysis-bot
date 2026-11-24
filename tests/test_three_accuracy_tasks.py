from scripts.run_three_accuracy_tasks import verify_captures

def test_empty(tmp_path):
    data = verify_captures(tmp_path)
    assert data['market_data_quality'] == 'NO_CAPTURES'
    assert data['quotex_price_parity_verified'] is False

def test_bad_capture(tmp_path, monkeypatch):
    import research.real_prediction_campaign as campaign
    def invalid(_):
        raise ValueError("Invalid saved evidence")
    monkeypatch.setattr(campaign, "_candles", invalid)
    (tmp_path/'captures').mkdir()
    (tmp_path/'captures'/'bad.csv').write_text('invalid\n')
    data = verify_captures(tmp_path)
    assert data['market_data_quality'] == 'FAIL'
    assert len(data['invalid_captures']) == 1
