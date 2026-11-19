import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1]/'scripts'/'apply_stage28b.py'
spec=importlib.util.spec_from_file_location('stage28b_apply',MODULE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

OLD = '''st.subheader("Market condition and research signal")
st.info(market['condition'])
st.metric("Signal", signal["signal"])
if not stale:
    st.info("bias")
with st.expander("Latest 20 completed candles"):
    pass
'''

def test_patch_has_fragment_and_rereads_csv():
    new=module.patch_page(OLD)
    assert 'st.fragment(run_every="30s")' in new
    assert 'load_saved_candles(CSV_PATH)' in new
    assert 'current_stale or current_gaps' in new

def test_patch_is_idempotent():
    once=module.patch_page(OLD)
    assert module.patch_page(once)==once

def test_patch_rejects_unexpected_page():
    with pytest.raises(RuntimeError): module.patch_page('some other page')

def test_invalid_saved_csv_is_no_trade():
    new=module.patch_page(OLD)
    assert 'st.metric("Signal engine output (15-minute expiry)", "NO TRADE")' in new

def test_never_uses_network_for_signal_fragment():
    fragment=module.REPLACE
    assert 'requests.get' not in fragment
    assert 'approved_refresh_once(' not in fragment


def test_inventory_is_read_only(tmp_path):
    path=tmp_path/'market_data'
    path.mkdir()
    (path/'a.py').write_text('import requests\nrequests.get("example")\n')
    inv=Path(__file__).resolve().parents[1]/'scripts'/'audit_live_fetch_paths.py'
    spec=importlib.util.spec_from_file_location('stage28b_inventory',inv)
    tool=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert ('market_data/a.py','DIRECT_HTTP lines [2]') in tool.inspect(tmp_path)
