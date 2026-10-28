"""Check the built Nauru repository against the cached reprints.

    python check_repo.py ../nauru-law [--record]

1. Bytes: for every reprint used, the act's files in git on its consolidation date (the tree of the last commit with
   `In-force:` on or before it) equal the files build.py renders from that PDF, byte for byte; a file that differs
   only in white space (git keeps the earlier typesetting) is counted separately. 0 mismatches expected.
2. Independent words: the act's text on that date as printed by `tools/in_force_on.py` (not the build) is compared,
   as a stream of casefolded letters and digits, with the words of the raw PDF read by PyMuPDF `get_text('words')`
   over the act's text pages only, without the build's parser: page range from the PDF's own Table of Contents and
   footer labels, running head (top 45pt) and footer ("Service N", page label) dropped, "[The next page is N]"
   fillers dropped. 0 mismatches expected.
3. Every reprint that was not used because another has the same date is reported with the files that differ.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))


def letters(s: str) -> str:
    return re.sub(r'[\W_]+', '', s.casefold())


def raw_words(pdf: str) -> str:
    import pymupdf
    doc = pymupdf.open(pdf)
    toc = doc[0].get_text()
    labels = [int(x.replace(',', '')) for x in re.findall(r'\.{2,}\s*\n\s*(\d{1,3}(?:,\d{3})+|\d{3,6})\s*\n', toc)]
    start, end = labels[2], (labels[3] if len(labels) > 3 else 10 ** 9)
    out = []
    for page in doc:
        h = page.rect.height
        words = page.get_text('words', sort=True)
        foot = [w[4] for w in words if w[1] > h * 0.8 and re.fullmatch(r'\d{1,3}(?:,\d{3})+|\d{3,6}', w[4])]
        if not foot:
            continue
        label = int(foot[-1].replace(',', ''))
        if not start <= label < end:
            continue
        # The footer band: from the lowest "Service" stamp down (the stamp and the page label sit side by side).
        stamps = [w[1] for w in words if w[1] > h * 0.8 and w[4] == 'Service']
        band = (max(stamps) - 4) if stamps else h
        body = [w for w in words if 45 <= w[1] < band]
        text = ' '.join(w[4] for w in body)
        text = re.sub(r'\[The next page is [^\]]*\]', ' ', text)
        out.append(text)
    return letters(' '.join(out))


def tool_text(repo: Path, day: str, act: str) -> str:
    r = subprocess.run([sys.executable, '-X', 'utf8', 'tools/in_force_on.py', day, act], cwd=repo, capture_output=True,
                       text=True, encoding='utf-8')
    if r.returncode:
        raise SystemExit(f'tool failed for {day} {act}: {r.stderr}')
    lines = [re.sub(r'^#+ ', '', l) for l in r.stdout.splitlines()]
    return letters(' '.join(lines))


def tree_files(repo: Path, day: str, act_dir: str) -> dict[str, str]:
    log = subprocess.run(['git', '-C', str(repo), 'log', '--first-parent',
                          '--format=%H%x1f%(trailers:key=In-force,valueonly,separator=)', 'main'],
                         capture_output=True, text=True, encoding='utf-8', check=True).stdout
    h = next(l.split('\x1f')[0] for l in log.splitlines() if l.split('\x1f')[1].strip() and l.split('\x1f')[1].strip() <= day)
    names = subprocess.run(['git', '-C', str(repo), 'ls-tree', '-r', '--name-only', h, act_dir + '/'],
                           capture_output=True, text=True, encoding='utf-8', check=True).stdout.split()
    data = subprocess.run(['git', '-C', str(repo), 'cat-file', '--batch'], input=''.join(f'{h}:{n}\n' for n in names).encode(),
                          capture_output=True, check=True).stdout
    out, pos = {}, 0
    for n in names:
        e = data.index(b'\n', pos)
        size = int(data[pos:e].split()[2])
        out[n] = data[e + 1:e + 1 + size].decode('utf-8')
        pos = e + 1 + size + 1
    return out


def first_diff(a: str, b: str) -> str:
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return f'at {i}: git ...{a[max(0, i - 60):i + 60]}... pdf ...{b[max(0, i - 60):i + 60]}...'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', type=Path)
    ap.add_argument('--record', action='store_true')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    import build
    versions, _ = build.load_versions()
    byte_ok = byte_bad = ws_only = 0
    word_ok = word_bad = 0
    notes = []
    for key, vs in versions.items():
        act_dir = build.ACTS[key]['dir']
        for v in vs:
            got = tree_files(args.repo, v['as_at'], act_dir)
            want = v['files']
            for p in sorted(set(got) | set(want)):
                if got.get(p) == want.get(p):
                    byte_ok += 1
                elif p in got and p in want and build.squash(got[p]) == build.squash(want[p]):
                    ws_only += 1
                else:
                    byte_bad += 1
                    notes.append(f'bytes {key} {v["as_at"]} {p}: {"missing in git" if p not in got else "extra in git" if p not in want else "differs"}')
            g = tool_text(args.repo, v['as_at'], act_dir)
            r = raw_words(str(build.PDF / v['file']))
            if g == r:
                word_ok += 1
            else:
                word_bad += 1
                notes.append(f'words {key} {v["as_at"]} {v["file"]}: {first_diff(g, r)}')
            print(f'{key} {v["as_at"]}: files {len(want)}, words {"ok" if g == r else "MISMATCH"} ({len(r)} letters)')
            for o in v['same_date']:
                print(f'  same-date reprint not used: {o["file"]} differs in {len(o["differs"])} file(s) {o["differs"]}')
    for n in notes:
        print(n)
    summary = (f'bytes: {byte_ok} files identical, {ws_only} differ only in white space, {byte_bad} mismatches; '
               f'independent words: {word_ok}/{word_ok + word_bad} versions match the raw PDF letter for letter')
    print(summary)
    if args.record:
        p = HERE / 'verification.json'
        rec = json.loads(p.read_text('utf-8')) if p.exists() else {}
        rec['check'] = {'summary': summary, 'mismatches': notes}
        p.write_text(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    sys.exit(1 if byte_bad or word_bad else 0)


if __name__ == '__main__':
    main()
