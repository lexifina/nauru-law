"""Parse every cached PDF once into cache/parsed/<pdf sha256>.<parse.py sha256[:12]>.json (build.py reads these).

    python -W ignore parse_all.py

The cache key includes the parser's own hash, so a changed parse.py never reuses an old answer. One process.
"""
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import parse  # noqa: E402

CACHE = HERE / 'cache'
OUT = CACHE / 'parsed'
PARSER = hashlib.sha256((HERE / 'parse.py').read_bytes()).hexdigest()[:12]


def parsed_path(sha: str) -> Path:
    return OUT / f'{sha}.{PARSER}.json'


def load(sha: str, pdf: Path) -> dict:
    p = parsed_path(sha)
    if p.exists():
        return json.loads(p.read_text('utf-8'))
    try:
        d = parse.parse(str(pdf))
    except Exception:  # noqa: BLE001 - an unreadable PDF is a recorded answer, not a crash
        d = {'first_line': '', 'instruments': [], 'error': traceback.format_exc(limit=3)}
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True), 'utf-8', newline='\n')
    tmp.replace(p)
    return d


def main() -> None:
    manifest = json.loads((CACHE / 'manifest.json').read_text('utf-8'))
    t0 = time.time()
    n = 0
    for src, m in sorted(manifest.items()):
        if 'sha256' not in m:
            continue
        load(m['sha256'], CACHE / 'pdf' / m['file'])
        n += 1
        if n % 100 == 0:
            print(f'{n}/{len(manifest)} {time.time() - t0:.0f}s', flush=True)
    print(f'parsed {n} PDFs with parser {PARSER} in {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
