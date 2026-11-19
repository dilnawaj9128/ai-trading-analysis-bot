"""Offline Stage 28 patch tests: no network, no journal mutation."""
import ast
from pathlib import Path
import importlib.util
import pytest

PATCH = Path(__file__).resolve().parents[1] / 'scripts' / 'apply_stage28_patch.py'
spec = importlib.util.spec_from_file_location('stage28_patch_module', PATCH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SAMPLE = '''import uuid\ndef example(td, budget_path, now, history, state_path):\n''' + module.OLD + '''                client = None\n            except BaseException:\n                raise\n'''

def test_patch_moves_budget_reservation_before_attempt():
    result = module.patch_source(SAMPLE)
    assert result.index('td.reserve_request(') < result.index("history['attempts'].append")
    assert result.index("history['attempts'].append") < result.index("attempt['status'] = 'REQUEST_ATTEMPTED'")
    ast.parse(result)

def test_patch_idempotent():
    first = module.patch_source(SAMPLE)
    assert module.patch_source(first) == first

def test_patch_refuses_unexpected_source():
    with pytest.raises(ValueError):
        module.patch_source('print("unsupported")')

def test_patch_does_not_modify_input_file(tmp_path):
    path = tmp_path / 'probe.py'
    path.write_text(SAMPLE)
    original = path.read_bytes()
    module.patch_source(path.read_text())
    assert path.read_bytes() == original

def test_budget_rejected_pre_http_no_attempt():
    patched = module.patch_source(SAMPLE)
    namespace = {'uuid': __import__('uuid')}
    exec(patched, namespace)
    class Budget:
        def reserve_request(self, **kwargs):
            raise RuntimeError('budget denied')
    history = {'attempts': []}
    with pytest.raises(RuntimeError, match='budget denied'):
        namespace['example'](Budget(), Path('/nonexistent'), None, history, Path('/nonexistent'))
    assert history == {'attempts': []}
