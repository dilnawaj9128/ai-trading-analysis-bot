"""Static control-flow checks; no API requests and no Streamlit launch."""
import ast
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / 'dashboard/pages/9_Real_Data_Research.py'


def test_page_compiles():
    compile(PAGE.read_text(), str(PAGE), 'exec')


def test_network_only_in_approved_function():
    tree = ast.parse(PAGE.read_text())
    calls = [(n.lineno, ast.unparse(n.func)) for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert any(s == 'module.probe_once' for _, s in calls)
    assert any(s == 'approved_refresh_once' for _, s in calls)
    assert not any(s.endswith('.get') and s.startswith('requests.') for _, s in calls)


def test_no_automatic_streamlit_refresh():
    source = PAGE.read_text()
    assert 'st_autorefresh' not in source
    assert 'while True' not in source
    assert 'st.session_state["stage25_approval_nonce"] = nonce + 1' in source
