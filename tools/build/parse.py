"""Parse one RONLAW consolidated reprint (Laws of the Republic of Nauru, "Service N") into provisions.

    python parse.py <pdf> [chars]

Layout (same template across acts, born-digital Times, one column):
- page 1: "Table of Contents" for the title: the principal act's "Table of Provisions", "Table of Amendments" and
  text start at page labels such as 5201 / 5401 / 5601; subsidiary instruments follow at later labels (9001, ...).
- every page: a running header above y ~ 45 (title, "LAWS OF THE REPUBLIC OF NAURU", the provision on the page) and a
  footer below ~ 82% of the height ("Service N" in 7pt and the page label in 11pt). Both are dropped.
- the Table of Amendments: the original act's certification and commencement, then rows "Amending Legislation |
  Certified | Date of Commencement" (the date may be prefixed by the provisions it covers: "s 5: 12 May 2026").
- the text: 12pt bold provision headings ("Article 19 Election of President" or "10 Composition of Public Service"),
  part / division headings in 9-10pt (centred), 10pt body, schedules headed in 10pt bold ("Third Schedule"), and
  history notes in 8pt brackets after each provision or clause: "[cl (2) insrt Act 18 of 2026 s 5, opn 16 Apr 2026]".
- "[The next page is N]" fillers on blank pages.

Only the principal act is read (pages from its text label up to the next instrument's first label).
Output: {'title', 'number_line', 'amendments': [{'name', 'certified', 'commenced', 'raw'}], 'original': str,
'as_at', 'services', 'preamble': [lines], 'units': [{'id', 'kind', 'heading': [..], 'title', 'lines': [..]}]}.
"""
import re
import sys
import unicodedata

import pymupdf

MONTHS = {m: i for i, m in enumerate(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                                      'September', 'October', 'November', 'December'], 1)}
SHORT = {m[:3]: i for m, i in MONTHS.items()} | {'Sept': 9}
DATE = re.compile(r'\b(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|'
                  r'December) (\d{4})\b')
ENUM = re.compile(r'^\((?:\d{1,3}[A-Z]{0,2}|[a-z]{1,2}|[ivxl]{1,6}|[A-Z]{1,2})\)')
SCHEDULE = re.compile(r'^(?:(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth)\s+'
                      r'Schedule|Schedule(?:\s+\d{1,2}[A-Z]?)?)$', re.I)
LIGATURES = {'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', '­': ''}


def iso(day: str, month: str, year: str) -> str:
    return f'{int(year):04d}-{MONTHS[month]:02d}-{int(day):02d}'


def clean(t: str) -> str:
    for k, v in LIGATURES.items():
        t = t.replace(k, v)
    t = t.replace(' ', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def label_value(s: str) -> int | None:
    s = s.replace(',', '')
    return int(s) if s.isdigit() else None


def page_rows(page) -> tuple[list[dict], str | None, str | None]:
    """Body rows of one page, plus its footer label and service number."""
    h = page.rect.height
    spans = []
    for b in page.get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            for s in ln['spans']:
                if s['text'].strip():
                    spans.append(s)
    label = service = None
    body = []
    for s in spans:
        x0, y0, x1, _ = s['bbox']
        t = s['text'].strip()
        if y0 > h * 0.80:
            # The footer: "Service N" in 7pt and the page label in 11pt. Body text can run this low; keep it.
            if re.fullmatch(r'\d{1,3}(?:,\d{3})+|\d{3,6}', t) and s['size'] >= 10:
                label = t
                continue
            if s['size'] < 7.5 and re.fullmatch(r'Service|\d+|Service \d+', t):
                if t[-1].isdigit():
                    service = t.split()[-1]
                continue
        if y0 < 45:
            continue
        body.append(s)
    # Rows: spans whose tops lie within 2.5pt, read left to right.
    body.sort(key=lambda s: (s['bbox'][1], s['bbox'][0]))
    clusters: list[list[dict]] = []
    for s in body:
        if clusters and abs(clusters[-1][0]['bbox'][1] - s['bbox'][1]) <= 2.5:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    rows: list[dict] = []
    for cl in clusters:
        cl.sort(key=lambda s: s['bbox'][0])
        r = None
        for s in cl:
            x0, y0, x1, _ = s['bbox']
            if r is None:
                r = {'y': y0, 'x': x0, 'x1': x1, 'size': s['size'],
                     'bold': 'Bold' in s['font'] or bool(s['flags'] & 16), 'text': s['text']}
                continue
            gap = x0 - r['x1']
            r['text'] += (' ' if gap > 0.8 and not r['text'].endswith(' ') and not s['text'].startswith(' ') else '') + s['text']
            r['x1'] = max(r['x1'], x1)
            r['size'] = max(r['size'], s['size'])
        rows.append(r)
    for r in rows:
        r['text'] = clean(r['text'])
    return [r for r in rows if r['text']], label, service


def read_toc(doc) -> tuple[int | None, int | None, int | None]:
    """(amendments label, text label, next instrument's first label) from the title's Table of Contents."""
    t = doc[0].get_text()
    labels = [label_value(x) for x in re.findall(r'\.{2,}\s*\n\s*(\d{1,3}(?:,\d{3})+|\d{3,6})\s*\n', t)]
    labels = [x for x in labels if x]
    if len(labels) < 3:
        return None, None, None
    return labels[1], labels[2], (labels[3] if len(labels) > 3 else None)


def parse_amendments(rows: list[dict]) -> tuple[str, list[dict], str]:
    text = ' '.join(r['text'] for r in rows)
    text = re.sub(r'\[The next page is [^\]]*\]', ' ', text)
    m = re.search(r'TABLE OF AMENDMENTS\s*(.*?)\s*Amending Legislation', text)
    original = clean(m.group(1)) if m else ''
    body = text[m.start():] if m else text
    # The table may run over pages, each with its own header row; footnotes ("* The ... Act ...") follow the rows
    # of a page.
    chunks = re.split(r'(?:TABLE OF AMENDMENTS.*?)?Amending Legislation\s+(?:Certified|Notified|Made)\s+'
                      r'Date of Commencement', body)[1:]
    rows_text, notes = [], []
    for ch in chunks:
        parts = re.split(r'(?:^|\s)\*\s', ch, maxsplit=1)
        rows_text.append(parts[0])
        if len(parts) > 1:
            notes.append(clean('* ' + parts[1]))
    out = []
    # A row: <name ...> <certified date or GN ref> <commencement (optionally "s 5: ")date>
    pat = re.compile(r'(.+?)\s+((?:\d{1,2} \w+ \d{4})|(?:\d{4} GN No \d+/\d{4}))\s+((?:[^0-9\s][^:]{0,40}:\s*)?'
                     r'\d{1,2} \w+ \d{4})(?=\s|$)')
    pos = 0
    body = clean(' '.join(rows_text))
    while True:
        mm = pat.match(body, pos)
        if not mm:
            break
        name, cert, com = mm.group(1).strip(), mm.group(2), mm.group(3)
        if 'GN No' in cert:  # "Constitutional Convention of Nauru 1968 GN No 72/1968 17 May 1968"
            name = name + ' ' + cert
            cert = ''
        d = DATE.search(com)
        out.append({'name': clean(name.lstrip('* ')), 'certified': iso(*DATE.search(cert).groups()) if cert else '',
                    'commenced': iso(*d.groups()) if d else '', 'raw': com})
        pos = mm.end()
        while pos < len(body) and body[pos] == ' ':
            pos += 1
    return original, out, (body[pos:].strip() + ' ' + ' '.join(notes)).strip()


def paragraphs(rows: list[dict]) -> list[str]:
    out: list[str] = []
    prev = None
    for r in rows:
        t = r['text']
        new = (prev is None or ENUM.match(t) or t.startswith(('[', '‘')) or prev['text'].startswith('[') and prev['text'].endswith(']')
               or r.get('heading') or prev.get('heading') or r['y'] - prev['y'] > 14.5 or r['page'] != prev['page'] and False)
        if prev is not None and prev['text'].startswith('[') and not prev['text'].endswith(']'):
            new = False  # a note that wraps
        if new or not out:
            out.append(t)
        else:
            out[-1] = out[-1] + t if out[-1].endswith('-') and t[:1].islower() else out[-1] + ' ' + t
        prev = r
    return out


def parse(path: str) -> dict:
    doc = pymupdf.open(path)
    first = clean(doc[0].get_text().split('\n')[0])
    ta_label, text_label, end_label = read_toc(doc)
    pages = []
    services = set()
    for pno, page in enumerate(doc):
        rows, label, service = page_rows(page)
        if service:
            services.add(int(service))
        for r in rows:
            r['page'] = pno
        pages.append((label_value(label) if label else None, rows))
    ta_rows, text_rows = [], []
    for pno, (label, rows) in enumerate(pages):
        if label is None:
            continue
        if ta_label and ta_label <= label < (text_label or 10**9):
            # Block order keeps a wrapped act name ("Constitution (Amendment) Act 2024 / No 6") before its dates.
            pg = doc[pno]
            clip = pymupdf.Rect(0, 45, pg.rect.width, pg.rect.height * 0.80)
            ta_rows.extend({'text': clean(x)} for x in pg.get_text(clip=clip).splitlines() if clean(x))
        elif text_label and label >= text_label and (end_label is None or label < end_label):
            text_rows.extend(rows)
    original, amendments, rest = parse_amendments(ta_rows)
    dates = [a['commenced'] for a in amendments if a['commenced']]
    m = DATE.search(original)
    if m:
        dates.append(iso(*m.groups()))
    as_at = max(dates) if dates else ''

    text_rows = [r for r in text_rows if not re.fullmatch(r'\[The next page is [^\]]*\]', r['text'])]
    units: list[dict] = []
    pre: list[dict] = []
    pending: list[str] = []
    last_heading: dict = {"page": -1, "y": 0}
    cur = None
    for r in text_rows:
        t = r['text']
        if r['size'] >= 11.5 and r['bold']:
            m = re.match(r'^(?:Article\s+)?(\d{1,3}[A-Z]{0,2})\b\s*(.*)$', t)
            if m:
                if cur is not None and cur.get('open_title'):
                    pass
                cur = {'id': m.group(1), 'kind': 'article' if t.startswith('Article') else 'section',
                       'heading': pending, 'title': m.group(2).strip(), 'rows': []}
                pending = []
                units.append(cur)
                continue
            if cur is not None and not cur['rows'] and cur['title'] and r['y'] - cur.get('_y', r['y']) < 20:
                cur['title'] += ' ' + t  # a wrapped heading
                continue
        if r['bold'] and SCHEDULE.match(t) and r['size'] >= 9.5:
            cur = {'id': re.sub(r'\s+', '-', t.lower()), 'kind': 'schedule', 'heading': pending, 'title': t, 'rows': []}
            pending = []
            units.append(cur)
            continue
        is_heading = t in ('THE SCHEDULES', 'SCHEDULES') or (re.match(r'^(PART|DIVISION|Subdivision|SUBDIVISION|Part|Division)\b', t) is not None
                      and len(t) < 160 and r['size'] >= 8.5 and not t.endswith((',', ';', ':'))
                      and (r['bold'] or t.upper() == t or t.startswith('Subdivision')))
        if is_heading and (cur is None or cur['kind'] != 'schedule'):
            pending.append(t)
            last_heading = r
            continue
        if (pending and not pending[-1].startswith('[') and t.upper() == t and r['size'] >= 8.5
                and r['page'] == last_heading['page'] and 0 < r['y'] - last_heading['y'] < 14
                and (cur is None or cur['kind'] != 'schedule')):
            pending[-1] += ' ' + t  # a heading that wraps ("PART 6 — TERMS AND ... OF PUBLIC SERVICE / EMPLOYMENT")
            last_heading = r
            continue
        if pending and t.startswith('['):
            # a note on the heading just read ("[Pt I am Act 21 of 2026 ...]"): keep it with the heading
            pending.append(t)
            continue
        if cur is None:
            pre.append(r)
        else:
            cur['rows'].append(r)
    if pending and units:
        units[-1]['rows'].extend({'text': h, 'y': 0, 'page': -1, 'heading': True} for h in pending)

    seen: dict[str, int] = {}
    out_units = []
    for u in units:
        n = seen.get(u['id'], 0)
        seen[u['id']] = n + 1
        out_units.append({'id': u['id'] if n == 0 else f"{u['id']}~{n + 1}", 'kind': u['kind'], 'heading': u['heading'],
                          'title': clean(u['title']), 'lines': paragraphs(u['rows'])})
    return {'first_line': first, 'amendments': amendments, 'original': original, 'ta_rest': rest, 'as_at': as_at,
            'services': sorted(services), 'labels': [ta_label, text_label, end_label],
            'preamble': paragraphs(pre), 'units': out_units}


if __name__ == '__main__':
    import json
    d = parse(sys.argv[1])
    s = json.dumps(d, ensure_ascii=False, indent=1)
    sys.stdout.reconfigure(encoding='utf-8')
    print(s[:int(sys.argv[2])] if len(sys.argv) > 2 else s)
