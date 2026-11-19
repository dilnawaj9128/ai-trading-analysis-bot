"""Read-only audit of active source files: alerts on independent HTTP call paths."""
from pathlib import Path
import ast

ROOTS = [Path('dashboard/pages'), Path('market_data'), Path('scripts')]

def inspect(root=Path('.')):
    findings=[]
    for rel in ROOTS:
        folder=root/rel
        if not folder.exists():
            continue
        for file in sorted(folder.glob('*.py')):
            try:
                source=file.read_text(encoding='utf-8')
                tree=ast.parse(source)
            except (OSError, UnicodeDecodeError, SyntaxError):
                findings.append((str(file.relative_to(root)), 'UNREADABLE_OR_INVALID'))
                continue
            direct=[]
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in ('get','post','request') and isinstance(node.func.value, ast.Name) and node.func.value.id in ('requests','httpx'):
                        direct.append(node.lineno)
            if direct:
                findings.append((str(file.relative_to(root)), f'DIRECT_HTTP lines {direct}'))
            if 'fetch_authorized_live_candles(' in source and rel == Path('dashboard/pages'):
                findings.append((str(file.relative_to(root)), 'LEGACY_AUTHORIZED_FETCH_ENTRYPOINT'))
            if 'approved_refresh_once(' in source and rel == Path('dashboard/pages'):
                findings.append((str(file.relative_to(root)), 'APPROVED_PROBE_ENTRYPOINT'))
    return findings

if __name__ == '__main__':
    print('=== STAGE 28B READ-ONLY FETCH-PATH INVENTORY ===')
    for path, finding in inspect():
        print(f'{path}: {finding}')
    print('Review entrypoints before consolidating guards. No network, no writes.')
