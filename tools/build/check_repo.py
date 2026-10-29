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
    # casefold spells out the ligatures; the dotless i some ligature glyphs extract as is i (as in parse.py)
    return re.sub(r'[\W_]+', '', s.casefold().replace('ı', 'i'))


LABEL = re.compile(r'\d{1,3}(?:,\d{3})+|\d{3,6}')
_PAGES: dict[str, list[tuple]] = {}


def turned_box(w, d, wd, h):
    """The word's box in the frame its text is read in: rows top to bottom, words left to right."""
    x0, y0, x1, y1 = w[:4]
    if d == (0, -1):
        return (h - y1, x0, h - y0, x1)
    if d == (0, 1):
        return (y0, wd - x1, y1, wd - x0)
    return (wd - x1, h - y1, wd - x0, h - y0)


def reading_order(boxes: list[tuple]) -> list[tuple]:
    """(box, text) pairs in reading order: rows top to bottom, each left to right, so a table row reads across its
    columns. A word is on the row if its top is within 2.5pt of the row's first word, or the two overlap by half the
    smaller height (sub- and superscripts)."""
    boxes = sorted(boxes, key=lambda b: (b[0][1], b[0][0]))
    rows: list[list] = []
    for b in boxes:
        if rows:
            f = rows[-1][0][0]
            ov = min(f[3], b[0][3]) - max(f[1], b[0][1])
            if abs(f[1] - b[0][1]) <= 2.5 or ov >= 0.5 * min(f[3] - f[1], b[0][3] - b[0][1]):
                rows[-1].append(b)
                continue
        rows.append([b])
    return [b for r in rows for b in sorted(r, key=lambda b: b[0][0])]


def pdf_pages(pdf: str) -> list[tuple]:
    """(label, words, plain text) of every page, read once per PDF with PyMuPDF; the label is the last number in the
    bottom fifth of the page."""
    if pdf not in _PAGES:
        import pymupdf
        if len(_PAGES) > 8:
            _PAGES.clear()
        out = []
        for page in pymupdf.open(pdf):
            h, wd = page.rect.height, page.rect.width
            # Lines written sideways or upside down, by their writing direction: a word inside one is rotated.
            turned = [(ln['bbox'], (round(ln['dir'][0]), round(ln['dir'][1])))
                      for b in page.get_text('dict')['blocks'] for ln in b.get('lines', [])
                      if (round(ln['dir'][0]), round(ln['dir'][1])) in ((0, -1), (0, 1), (-1, 0))]
            words = []
            for w in page.get_text('words', sort=True):
                cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
                d = next((d for bb, d in turned if bb[0] <= cx <= bb[2] and bb[1] <= cy <= bb[3]), None)
                words.append((*w[:5], d, turned_box(w, d, wd, h) if d else None))
            foot = [w[4] for w in words if not w[5] and w[1] > h * 0.8 and LABEL.fullmatch(w[4])]
            out.append((int(foot[-1].replace(',', '')) if foot else None, words, page.get_text(), h))
        _PAGES[pdf] = out
    return _PAGES[pdf]


def text_range(pages: list[tuple], start_from_build: int) -> tuple[int, float]:
    """The instrument's text pages, from the PDF alone: with a Table of Contents, every label it lists; the text runs
    from the build's start label (which must be one of them) to the next listed label. Without one, the text is the
    first block of labels after the Table of Amendments, to the end of the file."""
    toc_labels: list[int] = []
    if 'Table of Contents' in pages[0][2]:
        first = pages[0][0]
        for lab, _, t, _ in pages:
            if lab is None or first is None or lab - first >= 100 or 'TABLE OF PROVISIONS' in t \
                    or 'TABLE OF AMENDMENTS' in t:
                break
            lines = [x.strip() for x in t.splitlines()]
            for k in range(1, len(lines)):
                if LABEL.fullmatch(lines[k]) and lines[k - 1]:
                    toc_labels.append(int(lines[k].replace(',', '')))
        if start_from_build not in toc_labels:
            raise ValueError(f'text label {start_from_build} is not in the Table of Contents {toc_labels}')
        return start_from_build, next((x for x in sorted(toc_labels) if x > start_from_build), float('inf'))
    ta = next(k for k, (lab, _, t, _) in enumerate(pages) if 'TABLE OF AMENDMENTS' in t and lab is not None)
    prev = pages[ta][0]
    for lab, _, _, _ in pages[ta + 1:]:
        if lab is None:
            continue
        if lab != prev + 1:
            return lab, float('inf')
        prev = lab
    raise ValueError('no text after the Table of Amendments')


def raw_words(pdf: str, start_from_build: int) -> str:
    pages = pdf_pages(pdf)
    start, end = text_range(pages, start_from_build)
    out = []
    for label, words, _, h in pages:
        if label is None or not start <= label < end:
            continue
        # The footer band: from the lowest "Service" stamp down (the stamp and the page label sit side by side).
        # Rotated words (sideways forms and tables) are read after the page's horizontal text, in their own frame.
        stamps = [w[1] for w in words if not w[5] and w[1] > h * 0.8 and w[4] == 'Service']
        band = (max(stamps) - 4) if stamps else h
        flat = [(w[:4], w[4]) for w in words if not w[5] and 45 <= w[1] < band]
        turned = [(w[6], w[4]) for w in words if w[5]]
        body = reading_order(flat) + reading_order(turned)
        text = ' '.join(t for _, t in body)
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


_LOG: dict[str, str] = {}


def tree_files(repo: Path, day: str, act_dir: str) -> dict[str, str]:
    if str(repo) not in _LOG:
        _LOG[str(repo)] = subprocess.run(['git', '-C', str(repo), 'log', '--first-parent',
                                          '--format=%H%x1f%(trailers:key=In-force,valueonly,separator=)', 'main'],
                                         capture_output=True, text=True, encoding='utf-8', check=True).stdout
    log = _LOG[str(repo)]
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
    ap.add_argument('--only', help='a regex: check only the laws whose path matches (no --record)')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    import build
    today = subprocess.run(['git', '-C', str(args.repo), 'log', '-1', '--format=%cs', 'main'], capture_output=True,
                           text=True, check=True).stdout.strip()
    versions, _ = build.load_versions(today)
    byte_ok = byte_bad = ws_only = 0
    word_ok = word_bad = 0
    notes = []
    todo = sorted(((v['file'], key, v) for key, vs in versions.items() for v in vs
                   if not args.only or re.search(args.only, build.INSTR[key]['dir'])), key=lambda t: (t[0], t[1]))
    for _, key, v in todo:
            act_dir = build.INSTR[key]['dir']
            got = tree_files(args.repo, v['as_at'], act_dir)
            want = v['files']
            for p in sorted(set(got) | set(want)):
                if got.get(p) == want.get(p):
                    byte_ok += 1
                elif p in got and p in want and build.squash(got[p]) == build.squash(want[p]):
                    ws_only += 1
                else:
                    byte_bad += 1
                    notes.append(f'bytes {act_dir} {v["as_at"]} {p}: {"missing in git" if p not in got else "extra in git" if p not in want else "differs"}')
            g = tool_text(args.repo, v['as_at'], act_dir)
            try:
                r = raw_words(str(build.PDF / v['file']), v['labels'][1])
                why = '' if g == r else first_diff(g, r)
            except ValueError as e:
                r, why = None, f'no text range: {e}'
            if not why:
                word_ok += 1
            else:
                word_bad += 1
                notes.append(f'words {act_dir} {v["as_at"]} {v["file"]}: {why}')
            differing = [o for o in v['same_date'] if o['differs']]
            if why or differing:
                print(f'{act_dir} {v["as_at"]}: files {len(want)}, words {"MISMATCH" if why else "ok"}', flush=True)
                for o in differing:
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
