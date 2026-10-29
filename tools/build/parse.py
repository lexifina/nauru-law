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
MONTH = (r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|'
         r'Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)')
DATE = re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)? (' + MONTH + r')\.?,? (\d{4})\b')
ENUM = re.compile(r'^\((?:\d{1,3}[A-Z]{0,2}|[a-z]{1,2}|[ivxl]{1,6}|[A-Z]{1,2})\)')
SCHEDULE = re.compile(r'^(?:(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth)\s+'
                      r'Schedule|Schedule(?:\s+\d{1,2}[A-Z]?)?)$', re.I)
LIGATURES = {'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ı': 'i', '­': ''}


def iso(day: str, month: str, year: str) -> str:
    return f'{int(year):04d}-{(MONTHS.get(month) or SHORT[month[:3]]):02d}-{int(day):02d}'


def clean(t: str) -> str:
    for k, v in LIGATURES.items():
        t = t.replace(k, v)
    t = t.replace(' ', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def label_value(s: str) -> int | None:
    s = s.replace(',', '')
    return int(s) if s.isdigit() else None


ROTATED = ((0, -1), (0, 1), (-1, 0))


def rotate(b, d, w, h):
    """A bbox in the reading frame of text whose writing direction is d (PyMuPDF line 'dir')."""
    x0, y0, x1, y1 = b
    if d == (0, -1):  # reads upwards: rows run left to right
        return (h - y1, x0, h - y0, x1)
    if d == (0, 1):  # reads downwards: rows run right to left
        return (y0, w - x1, y1, w - x0)
    return (w - x1, h - y1, w - x0, h - y0)  # upside down


def page_rows(page) -> tuple[list[dict], str | None, str | None]:
    """Body rows of one page, plus its footer label and service number."""
    h, w = page.rect.height, page.rect.width
    spans = []
    for b in page.get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            d = (round(ln['dir'][0]), round(ln['dir'][1]))
            for s in ln['spans']:
                if s['text'].strip():
                    s['rot'] = d if d in ROTATED else None
                    spans.append(s)
    label = service = None
    body = []
    # The footer: the page label (the lowest number of 10pt or more in the bottom fifth) and, beside it, the
    # "Service N" stamp in 7pt. Body text, notes and footnote markers can run this low; they are kept.
    low = [s for s in spans if not s['rot'] and s['bbox'][1] > h * 0.80 and s['size'] >= 10
           and re.fullmatch(r'\d{1,3}(?:,\d{3})+|\d{3,6}', s['text'].strip())]
    lab_span = max(low, key=lambda s: (s['bbox'][1], s['bbox'][0])) if low else None
    stamp_y = [s['bbox'][1] for s in spans if s['bbox'][1] > h * 0.80 and s['size'] < 7.5
               and re.fullmatch(r'Service(?: \d+)?', s['text'].strip())]
    for s in spans:
        x0, y0, x1, y1 = s['bbox']
        t = s['text'].strip()
        if s is lab_span:
            label = t
            continue
        if y0 > h * 0.80 and s['size'] < 7.5 and re.fullmatch(r'Service|\d+|Service \d+', t)                 and any(abs(y0 - sy) <= 3 for sy in stamp_y):
            if t[-1].isdigit():
                service = t.split()[-1]
            continue
        if s['rot']:
            # Rotated text (forms and tables printed sideways) is read in its own frame, after the page's
            # horizontal text; the head and footer bands do not apply to it.
            s['bbox'] = rotate(s['bbox'], s['rot'], w, h)
            body.append(s)
            continue
        if y0 < 45 or stamp_y and y0 >= max(stamp_y) - 4:
            continue  # running head; the footer band, from the lowest service stamp down
        body.append(s)
    # Rows: spans whose tops lie within 2.5pt, or that overlap the row's first span by half the smaller height
    # (sub- and superscripts), read left to right.
    clusters: list[list[dict]] = []
    for group in ([s for s in body if not s['rot']], [s for s in body if s['rot']]):
        group.sort(key=lambda s: (s['bbox'][1], s['bbox'][0]))
        start = len(clusters)
        for s in group:
            if len(clusters) > start:
                f = clusters[-1][0]['bbox']
                b = s['bbox']
                ov = min(f[3], b[3]) - max(f[1], b[1])
                if abs(f[1] - b[1]) <= 2.5 or ov >= 0.5 * min(f[3] - f[1], b[3] - b[1]):
                    clusters[-1].append(s)
                    continue
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


def read_toc(doc) -> list[dict]:
    """The instruments of a reprint from its Table of Contents (the first pages, labels below 5201):
    [{'title', 'part' (principal|subsidiary), 'provisions', 'amendments', 'text', 'end'}] with page labels."""
    lines: list[str] = []
    first = None
    for page in doc:
        t = page.get_text()
        if 'Table of Contents' not in t and not lines:
            return []
        foot = re.findall(r'(?m)^\s*(\d{1,3}(?:,\d{3})+|\d{3,6})\s*$', t)
        lab = label_value(foot[-1]) if foot else None
        if lines and (lab is None or first is None or lab - first >= 100
                      or 'TABLE OF PROVISIONS' in t or 'TABLE OF AMENDMENTS' in t):
            break
        if first is None:
            first = lab
        lines.extend(clean(x) for x in t.splitlines())
        if len(lines) > 4000:
            break
    entries = []
    part = 'principal'
    name: list[str] = []
    footer = re.compile(r'Service \d+|\d{1,3}(?:,\d{3})+|\d{3,6}')
    i = 0
    while i < len(lines):
        ln = lines[i]
        j = i + 1
        while j < len(lines) and not lines[j]:
            j += 1
        nxt = label_value(lines[j]) if j < len(lines) and re.fullmatch(r'\d{1,3}(?:,\d{3})+|\d{3,6}', lines[j]) else None
        if ln in ('Principal', 'Subsidiary'):
            part = ln.lower()
            name = []
        elif ln and nxt and not footer.fullmatch(ln) and not re.fullmatch(r'Service', ln):
            # An entry: a line (dotted leaders, or a single '.') followed by its page label.
            text = clean(re.sub(r'[ .]*\.[ .]*$', '', ln))
            entries.append({'what': text, 'name': clean(' '.join(name + [text])), 'part': part, 'label': nxt,
                            'head': clean(' '.join(name))})
            name = []
            i = j
        elif ln and ln not in ('Table of Contents', 'Page', 'LAWS OF THE REPUBLIC OF NAURU',
                               'LAWS OF THE REPUBLIC OF NAOERO') and not footer.fullmatch(ln)                 and not re.fullmatch(r'\[The next page is [^\]]*\]', ln):
            if i > 0 and ln == lines[0]:
                pass
            else:
                name.append(ln)
        i += 1
    insts = []
    cur = None
    for e in entries:
        if e['what'] == 'Table of Provisions':
            cur = {'title': e['head'], 'part': e['part'], 'provisions': e['label'], 'amendments': None, 'text': None}
            insts.append(cur)
        elif e['what'] == 'Table of Amendments':
            if cur is None or cur['amendments'] is not None:
                cur = {'title': e['head'], 'part': e['part'], 'provisions': None, 'amendments': None, 'text': None}
                insts.append(cur)
            cur['amendments'] = e['label']
        elif cur is not None and cur['text'] is None:
            cur['text'] = e['label']
            cur['text_title'] = e['name']
            if not cur['title']:
                cur['title'] = e['name']
    # Every label the Table of Contents lists ends the text before it, including entries that are not instruments
    # (a code of practice or practice direction printed after an instrument).
    labels = sorted({e['label'] for e in entries})
    out = []
    for x in insts:
        if not x['text'] or not x['amendments']:
            continue
        x['end'] = next((l for l in labels if l > x['text']), None)
        out.append(x)
    # The first page names the title group ("PUBLIC SERVICE"); the title of the principal is its text entry.
    return out


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
    day = r'\d{1,2}(?:st|nd|rd|th)? ' + MONTH + r'\.?,? \d{4}'
    pat = re.compile(r'(.+?)\s+((?:' + day + r')|(?:\d{4} GN No \d+/\d{4}))\s+((?:[^0-9\s][^:]{0,40}:\s*)?'
                     + day + r')(?=\s|$)')
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


def standalone(doc, pages) -> list[dict]:
    """A reprint of one instrument without a Table of Contents (most subsidiary legislation): its own Table of
    Provisions (optional) and Table of Amendments, then the text, all with footer labels and service stamps."""
    ta = [(pno, lab) for pno, (lab, rows, _) in enumerate(pages)
          if lab is not None and any(r['text'] == 'TABLE OF AMENDMENTS' for r in rows)]
    if not ta:
        return []
    # The text starts at the first jump in the page labels after the table (the table's pages run on: 398,201,
    # 398,202; the text starts a new block: 398,401).
    text, prev = None, ta[0][1]
    for pno, (lab, rows, _) in enumerate(pages):
        if pno <= ta[0][0] or lab is None:
            continue
        if lab != prev + 1:
            text = (pno, lab)
            break
        prev = lab
    if text is None:
        return []
    provisions = next((lab for lab, rows, _ in pages[:ta[0][0]] if lab is not None
                       and any(r['text'] == 'TABLE OF PROVISIONS' for r in rows)), None)
    # The title: the lines above TABLE OF PROVISIONS (or TABLE OF AMENDMENTS) on its first page.
    head_page = next(pno for pno, (lab, rows, _) in enumerate(pages)
                     if any(r['text'] in ('TABLE OF PROVISIONS', 'TABLE OF AMENDMENTS') for r in rows))
    title = []
    for r in pages[head_page][1]:
        if r['text'] in ('TABLE OF PROVISIONS', 'TABLE OF AMENDMENTS'):
            break
        title.append(r['text'])
    return [{'title': clean(' '.join(title)), 'part': 'standalone', 'provisions': provisions,
             'amendments': ta[0][1], 'text': text[1], 'text_title': clean(' '.join(title)), 'end': None}]


def unit_word(pages, label) -> str:
    """The provision word of an instrument: the column head under its TABLE OF PROVISIONS ("Section", "Regulation")."""
    if label is None:
        return ''
    for lab, rows, _ in pages:
        if lab == label:
            for k, r in enumerate(rows):
                if r['text'] == 'TABLE OF PROVISIONS' and k + 1 < len(rows):
                    w = rows[k + 1]['text'].split()[0] if rows[k + 1]['text'] else ''
                    return w.lower() if w.isalpha() and len(w) < 15 else ''
            # Some heads print "Regulation Title" on one row
            for r in rows[:8]:
                m = re.match(r'^(Section|Regulation|Rule|Clause|Article|Paragraph|Order|By-law|Bylaw)\b', r['text'])
                if m:
                    return m.group(1).lower()
    return ''


def parse(path: str) -> dict:
    """Every instrument of one reprint: {'first_line', 'instruments': [...]}; [] when the PDF is not a reprint."""
    doc = pymupdf.open(path)
    first = clean(doc[0].get_text().splitlines()[0]) if len(doc) and doc[0].get_text().strip() else ''
    insts = read_toc(doc)
    pages = []
    for pno, page in enumerate(doc):
        rows, label, service = page_rows(page)
        for r in rows:
            r['page'] = pno
        pages.append((label_value(label) if label else None, rows, service))
    if not insts:
        insts = standalone(doc, pages)
    if not insts:
        return {'first_line': first, 'instruments': []}
    out = []
    for inst in insts:
        d = parse_instrument(doc, pages, inst)
        d.update({'title': inst['title'], 'text_title': inst.get('text_title', ''), 'part': inst['part'],
                  'unit': unit_word(pages, inst['provisions']),
                  'labels': [inst['amendments'], inst['text'], inst['end']]})
        out.append(d)
    return {'first_line': first, 'instruments': out}


def parse_instrument(doc, pages, inst) -> dict:
    ta_label, text_label, end_label = inst['amendments'], inst['text'], inst['end']
    services = set()
    ta_rows, text_rows = [], []
    for pno, (label, rows, service) in enumerate(pages):
        if label is None:
            continue
        if ta_label <= label < text_label:
            # Block order keeps a wrapped act name ("Constitution (Amendment) Act 2024 / No 6") before its dates.
            pg = doc[pno]
            clip = pymupdf.Rect(0, 45, pg.rect.width, pg.rect.height * 0.80)
            ta_rows.extend({'text': clean(x)} for x in pg.get_text(clip=clip).splitlines() if clean(x))
        elif label >= text_label and (end_label is None or label < end_label):
            text_rows.extend(rows)
            if service:
                services.add(int(service))
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
            if m and cur is not None and cur['kind'] == 'schedule':
                # A numbered heading inside a schedule (rules or a model set out in it) stays in the schedule.
                cur['rows'].append(dict(r, text='### ' + t, heading=True))
                continue
            if (cur is not None and cur['kind'] != 'schedule' and not cur['rows'] and cur['title']
                    and r['page'] == cur['_page'] and 0 < r['y'] - cur['_y'] < 16):
                # a wrapped heading ("4 No immunity or privilege in respect of acts done under section / 3")
                cur['title'] += ' ' + t
                cur['_y'] = r['y']
                continue
            if m:
                cur = {'id': m.group(1), 'kind': 'article' if t.startswith('Article') else 'section',
                       'heading': pending, 'title': m.group(2).strip(), 'rows': [], '_y': r['y'], '_page': r['page']}
                pending = []
                units.append(cur)
                continue
            if cur is not None and not cur['rows'] and cur['title']:
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
        if (pending and not pending[-1].startswith('[') and r['size'] >= 8.5 and r['size'] < 11.5
                and r['page'] == last_heading['page'] and 0 < r['y'] - last_heading['y'] < 14
                and (t.upper() == t or not t.startswith(('(', '[')) and r['x'] > 60)
                and (cur is None or cur['kind'] != 'schedule')):
            # a heading that wraps ("PART 6 — TERMS AND ... OF PUBLIC SERVICE / EMPLOYMENT", "Subdivision 4 — ...
            # correspondent banking relationships and / shell banks")
            pending[-1] += ' ' + t
            last_heading = r
            continue
        if (pending and not pending[-1].startswith('[') and t.upper() == t and r['size'] >= 8.5
                and r['size'] < 11.5 and re.search('[A-Z]{3}', t)
                and r['page'] == last_heading['page'] and 0 < r['y'] - last_heading['y'] < 30
                and (cur is None or cur['kind'] != 'schedule')):
            pending.append(t)  # a sub-heading under a Part ("GENERAL PROVISIONS AFFECTING ADMINISTRATION ...")
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
    return {'amendments': amendments, 'original': original, 'ta_rest': rest, 'as_at': as_at,
            'services': sorted(services), 'preamble': paragraphs(pre), 'units': out_units}


if __name__ == '__main__':
    import json
    d = parse(sys.argv[1])
    s = json.dumps(d, ensure_ascii=False, indent=1)
    sys.stdout.reconfigure(encoding='utf-8')
    print(s[:int(sys.argv[2])] if len(sys.argv) > 2 else s)
