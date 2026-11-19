"""Stage 28C additive source patch for production HTTP fetch entrypoints.

Source only. Dry run unless --apply. No history, credentials, or credits read.
"""
import argparse
import ast
import os
from pathlib import Path

TARGETS = {
    Path("market_data/authorized_live_fetch.py"): "fetch_authorized_live_candles",
    Path("market_data/twelve_data_client.py"): "fetch_recent_candles",
    Path("market_data/manual_credit_refresh.py"): "refresh_production_provider_credits",
}
IMPORT = "from market_data.probe_cross_path_gate import guard_production_fetch\n"
DECORATOR = "@guard_production_fetch\n"


def patched(source, function_name):
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function_name]
    if len(matches) != 1:
        raise ValueError(f"Expected one function: {function_name}")
    node = matches[0]
    if any(isinstance(d, ast.Name) and d.id == "guard_production_fetch" for d in node.decorator_list):
        if IMPORT not in source:
            raise ValueError("Decorator installed but import missing")
        return source
    if IMPORT in source:
        raise ValueError("Gate import present without decorator: manual review")
    lines = source.splitlines(keepends=True)
    if not lines[node.lineno - 1].startswith("def " if isinstance(node, ast.FunctionDef) else "async def "):
        raise ValueError("Unexpected function layout")
    lines.insert(node.lineno - 1, DECORATOR)
    # Insert import after module docstring and __future__ imports to avoid SyntaxError.
    next_tree = ast.parse("".join(lines))
    insert_after = 0
    for item in next_tree.body:
        if (isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)) or (isinstance(item, ast.ImportFrom) and item.module == "__future__"):
            insert_after = item.end_lineno
        else:
            break
    lines.insert(insert_after, IMPORT)
    result = "".join(lines)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    updates = []
    for path, name in TARGETS.items():
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"BLOCKED missing/symlink target: {path}")
        source = path.read_text(encoding="utf-8")
        try:
            updated = patched(source, name)
        except (SyntaxError, ValueError) as exc:
            raise SystemExit(f"BLOCKED incompatible source {path}: {exc}") from exc
        updates.append((path, source, updated))
    if not args.apply:
        print("DRY RUN: all three entrypoints compatible. No changes.")
        return
    gate = Path("market_data/probe_cross_path_gate.py")
    if not gate.is_file():
        raise SystemExit("BLOCKED: install gate module first")
    for path, source, updated in updates:
        if updated == source:
            print(f"ALREADY PATCHED: {path}")
            continue
        backup = path.with_suffix(path.suffix + ".stage28c.bak")
        if backup.exists():
            raise SystemExit(f"BLOCKED: backup exists {backup}")
    for path, source, updated in updates:
        if updated == source:
            continue
        backup = path.with_suffix(path.suffix + ".stage28c.bak")
        with backup.open("x", encoding="utf-8") as f:
            f.write(source)
            f.flush()
            os.fsync(f.fileno())
        path.write_text(updated, encoding="utf-8")
        print(f"PATCHED: {path} (backup: {backup})")
    print("No HTTP requests or runtime API-state changes.")


if __name__ == "__main__":
    main()
