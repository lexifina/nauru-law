"""Print a Nauru act, or one provision of it, as it stood on a date.

    python tools/in_force_on.py 2026-04-01 constitution                 # the whole Constitution on that day
    python tools/in_force_on.py 2026-04-01 constitution article/19      # Article 19
    python tools/in_force_on.py 2025-09-01 public-service-act-2016 section/94A

`main` is one line of commits in in-force order, so the text on a day is the tree of the last commit whose
`In-force:` trailer is on or before it. Reads the trailer, not the commit date. Standard library only; the files are
read through one `git cat-file --batch`.
"""
import re
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', check=True).stdout


def commit_on(day: str) -> str | None:
    best = None
    for line in git('log', '--first-parent', '--format=%H%x1f%(trailers:key=In-force,valueonly,separator=)',
                    'main').splitlines():
        h, d = (line.split('\x1f') + [''])[:2]
        d = d.strip()
        if d and d <= day:
            best = h
            break
    return best


def order(path: str):
    kind, _, stem = path.rpartition('/')
    stem = stem[:-3]
    m = re.match(r'(\d+)([A-Z]*)', stem)
    rank = {'': 0, 'article': 1, 'section': 1, 'schedule': 2}.get(kind.split('/')[-1] if '/' in kind else '', 1)
    if path.endswith('/preamble.md'):
        rank = 0
    words = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth']
    n = int(m.group(1)) if m else (words.index(stem) + 1 if stem in words else 99)
    return rank, n, m.group(2) if m else stem


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    day, act = sys.argv[1], sys.argv[2].strip('/')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        sys.exit('date must be YYYY-MM-DD')
    h = commit_on(day)
    if not h:
        sys.exit(f'no text on or before {day}: the record starts at the earliest reprint (see corpus.json history_from)')
    if len(sys.argv) > 3:
        names = [f"{act}/{sys.argv[3].strip('/').removesuffix('.md')}.md"]
    else:
        names = [n for n in git('ls-tree', '-r', '--name-only', h, f'{act}/').split('\n') if n.endswith('.md')]
        if not names:
            sys.exit(f'{act}: not in force on {day}')
        names.sort(key=order)
    proc = subprocess.run(['git', 'cat-file', '--batch'], input=''.join(f'{h}:{n}\n' for n in names).encode('utf-8'),
                          capture_output=True, check=True)
    out, data, pos = [], proc.stdout, 0
    for n in names:
        head_end = data.index(b'\n', pos)
        head = data[pos:head_end].decode()
        if head.endswith('missing'):
            sys.exit(f'{n}: not in force on {day}')
        size = int(head.split()[2])
        out.append(data[head_end + 1:head_end + 1 + size].decode('utf-8'))
        pos = head_end + 1 + size + 1
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdout.write('\n'.join(out))


if __name__ == '__main__':
    main()
