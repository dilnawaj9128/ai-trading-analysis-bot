"""Pure offline tests; no Twelve Data HTTP calls."""
import pytest

from dashboard.verified_live_control import approved_live_snapshot


def _fake_result():
    return {
        'status': 'VERIFIED_NORMAL_FETCH', 'candles': 120,
        'credits_renewed': True,
        'analysis': {
            'status': 'RESEARCH_ANALYSIS_READY', 'symbol': 'EUR/USD',
            'timeframe': '1min', 'expiry_minutes': 15, 'signal': 'NO TRADE',
            'execution_enabled': False, 'broker_orders': 0,
            'extra_http_requests': 0, 'indicators': {'RSI_14': 55},
        },
    }


def test_requires_approval():
    calls = []
    with pytest.raises(ValueError, match='approval'):
        approved_live_snapshot(approved=False, api_key='testkey', runner=lambda **kw: calls.append(kw))
    assert not calls


def test_requires_api_key():
    calls = []
    with pytest.raises(ValueError, match='not configured'):
        approved_live_snapshot(approved=True, api_key=' ', runner=lambda **kw: calls.append(kw))
    assert not calls


def test_one_shot_delegates_once_to_existing_engine():
    calls = []
    def runner(**kw):
        calls.append(kw)
        return _fake_result()
    result = approved_live_snapshot(approved=True, api_key='secret', runner=runner)
    assert len(calls) == 1
    assert calls[0] == {'approved': True, 'api_key': 'secret', 'include_analysis': True}
    assert result['analysis']['signal'] == 'NO TRADE'
    assert result['maximum_http_requests'] == 2
    assert result['analysis_only'] is True
    assert 'secret' not in str(result)


@pytest.mark.parametrize('field,bad', [
    ('signal', 'UP'), ('execution_enabled', True), ('broker_orders', 1),
    ('extra_http_requests', 1), ('symbol', 'GBP/USD'), ('expiry_minutes', 5),
    ('status', 'ERROR'),
])
def test_rejects_unsafe_analysis(field, bad):
    result = _fake_result()
    result['analysis'][field] = bad
    with pytest.raises(ValueError, match='Unsafe'):
        approved_live_snapshot(approved=True, api_key='test', runner=lambda **kw: result)


def test_rejects_unverified_normal_fetch():
    result = _fake_result()
    result['status'] = 'FAILED'
    with pytest.raises(ValueError, match='not verified'):
        approved_live_snapshot(approved=True, api_key='test', runner=lambda **kw: result)


def test_transport_failure_never_retries():
    calls = []
    def runner(**kw):
        calls.append(kw)
        raise TimeoutError('timeout')
    with pytest.raises(TimeoutError):
        approved_live_snapshot(approved=True, api_key='test', runner=runner)
    assert len(calls) == 1
