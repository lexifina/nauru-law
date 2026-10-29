"""Build the Nauru law repository from the RONLAW cache.

    python -W ignore parse_all.py                                   # parse every cached PDF once (cache/parsed/)
    python -W ignore build.py ~/Documents/nauru-law --today 2026-10-29 [--plan]

Every law in a consolidated reprint of the Laws of the Republic of Nauru on ronlaw.gov.nr (fetch.py): the
Constitution, every Act with a reprint, and every subsidiary instrument printed in a reprint (with its Act, or on its
own).

Steps:
1. Parse every cached PDF (parse.py, through parse_all.py's cache). A reprint holds one or more instruments, each
   with its own Table of Amendments and text; the table gives the date the instrument is consolidated to (`as_at`:
   the latest commencement it lists). An instrument is keyed by its title (case, punctuation and Naoero/Nauru
   folded), so the copy printed with its Act and the copy printed on its own are versions of one law. Copies with
   the same as_at are one version: the one in the PDF with the latest modification date is used, the others listed.
2. The earliest version of each instrument is a baseline commit by RONLAW, `Kind: consolidated`. Each later version
   is compared with the one before, file by file (article/section/regulation, schedule, preamble).
3. A changed file is credited by the history notes the reprint prints after each provision ("[Art 21 subst Act 18
   of 2026 s 6, opn 16 Apr 2026]"): the (law, operative date) citations new in that file since the previous version,
   with an operative date after the previous version's as_at (`Evidence: note`). One such law: it is the author and
   its operative date is the commit date. Several: the file's final text is committed on the latest of their dates
   by RONLAW, `Kind: several-acts`, with one `Candidate:` per law and no credit. None: if exactly one law was added
   to the Table of Amendments between the two versions, it is credited (`Evidence: table`); otherwise the change is
   RONLAW's, `Kind: unexplained`, dated by the new version's as_at.
4. One commit per amending law per in-force day, across all instruments; noon Nauru time (UTC+12, no summer time).
   Versions consolidated to a day after --today are left out of main. Written with one git fast-import, so the same
   cache gives the same hashes.
"""
import argparse
import json
import re
import shutil
import os
import stat
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import parse_all  # noqa: E402

CACHE = HERE / 'cache'
PDF = CACHE / 'pdf'
COMMITTER = 'Lexifina <nauru-law@lexifina.com>'
PUBLISHER = ('RONLAW (Department of Justice and Border Control)', 'ronlaw@ronlaw-gov-nr.invalid')

# Not a reprint of the Laws of the Republic of Nauru: a Word copy of the Constitution with no notes ("Repulbic" in its
# name). Files without a Table of Amendments (Acts and instruments as made) are left out by the parser.
SKIP = re.compile(r'Repulbic')
INSTR: dict[str, dict] = {}  # key -> {'dir', 'label', 'unit', 'part'}; filled by load_versions()
sys.modules.setdefault('build', sys.modules[__name__])  # docs.py imports INSTR from this module, run as a script
CONSTITUTION_KEYS = ('constitution', 'constitution of nauru', 'constitution of nauru 1968')

MON = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'June': 6, 'Jul': 7, 'July': 7, 'Aug': 8,
       'Sep': 9, 'Sept': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12, 'January': 1, 'February': 2, 'March': 3, 'April': 4,
       'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}
# "Act 18 of 2026 s 5, opn 16 Apr 2026"; "GN No 72/1968, opn 17 May 1968"; "Act 6 of 2020 ss 18, 30, opn 4 June 2020"
CITE = re.compile(r'(?:(Act|No|SL|Ord) (\d+) of (\d{4})|GN No (\d+)/(\d{4}))(?:[^;]*?)opn (\d{1,2}) ([A-Z][a-z]+) (\d{4})')


def cite_keys(text: str) -> set[tuple]:
    out = set()
    for line in text.splitlines():
        if not line.startswith('['):
            continue
        for m in CITE.finditer(line):
            kind = {'SL': 'sl', 'Ord': 'ord'}.get(m.group(1), 'act') if m.group(2) else 'gn'
            num, year = (m.group(2), m.group(3)) if m.group(2) else (m.group(4), m.group(5))
            mon = MON.get(m.group(7))
            if not mon:
                continue
            out.add((kind, int(year), int(num), f'{int(m.group(8)):04d}-{mon:02d}-{int(m.group(6)):02d}'))
    return out


def norm_title(name: str) -> str:
    return re.sub(r'\s+', ' ', name.replace('*', '')).strip()


def law_author(key: tuple, names: dict) -> tuple[str, str]:
    kind, year, num = key[:3]
    if kind == 'gn':
        return f'GN No {num}/{year}', f'gn-{year}-{num}@ronlaw-gov-nr.invalid'
    title = names.get((kind, year, num))
    if kind in ('sl', 'ord'):
        return (title or f"{'SL' if kind == 'sl' else 'Ordinance'} {num} of {year}"),             f'{kind}-{year}-{num}@ronlaw-gov-nr.invalid'
    return (title or f'Act {num} of {year}'), f'act-{year}-{num}@ronlaw-gov-nr.invalid'


def cited_as(key: tuple) -> str:
    kind, year, num = key[:3]
    return {'act': f'Act {num} of {year}', 'sl': f'SL {num} of {year}', 'ord': f'Ord {num} of {year}',
            'gn': f'GN No {num}/{year}'}[kind]


def law_list(labels: list[str]) -> str:
    return ', '.join(labels) if len(labels) <= 3 else f'{len(labels)} laws'


def table_keys(amendments: list[dict]) -> dict[tuple, dict]:
    """Table rows keyed like note citations: ('act', certified year, number), ('sl', year, number) or ('gn', year,
    number)."""
    out = {}
    for a in amendments:
        n = norm_title(a['name'])
        m = re.search(r'GN No (\d+)/(\d{4})', n)
        if m:
            out[('gn', int(m.group(2)), int(m.group(1)))] = a
            continue
        m = re.search(r'\bSL (?:No )?(\d+)$', n)
        if m:
            ys = re.findall(r'\b(1[89]\d\d|20\d\d)\b', n[:m.start()])
            year = int(a['certified'][:4]) if a['certified'] else (int(ys[-1]) if ys else 0)
            if year:
                out[('sl', year, int(m.group(1)))] = a
            continue
        m = re.search(r'No (\d+)$', n)
        if m and a['certified']:
            out[('act', int(a['certified'][:4]), int(m.group(1)))] = a
    return out


# ------------------------------------------------------------------------------------------------ files

def unit_path(inst: dict, u: dict) -> str:
    if u['kind'] == 'schedule':
        sid = re.sub(r'^schedule-?', '', u['id']).replace('-schedule', '') or 'only'
        return f"{inst['dir']}/schedule/{sid}.md"
    return f"{inst['dir']}/{inst['unit']}/{u['id']}.md"


def unit_text(u: dict) -> str:
    lines = [f'## {h}' for h in u['heading']]
    if u['kind'] == 'schedule':
        lines.append(f"# {u['title']}")
    else:
        lines.append(f"# {'Article ' if u['kind'] == 'article' else ''}{u['id'].split('~')[0]} {u['title']}".rstrip())
    lines.extend(u['lines'])
    return '\n'.join(lines) + '\n'


def version_files(inst: dict, d: dict) -> dict[str, str]:
    files = {}
    if d['preamble']:
        files[f"{inst['dir']}/preamble.md"] = '\n'.join(d['preamble']) + '\n'
    for u in d['units']:
        files[unit_path(inst, u)] = unit_text(u)
    return files


def squash(s: str) -> str:
    return re.sub(r'\s+', '', s)


# ------------------------------------------------------------------------------------------------ versions

def pdf_moddate(path: Path) -> str:
    import pymupdf
    return (pymupdf.open(str(path)).metadata or {}).get('modDate') or ''


def title_key(title: str) -> str:
    t = re.sub(r'naoero', 'nauru', title.replace('*', '').casefold())
    t = t.replace('&', ' and ')
    return re.sub(r'[^0-9a-z]+', ' ', t).strip()


def slugify(key: str) -> str:
    return '-'.join(key.split())[:90].rstrip('-')


def is_act(title: str) -> bool:
    return re.search(r'\bAct\b(?: \d{4})?(?: \(No \d+\))?$', title.replace('*', '').strip()) is not None


def load_versions(today: str = '9999-12-31') -> tuple[dict[str, list[dict]], list[dict]]:
    """Every instrument's versions, oldest first, and the files (or instruments) not used, with the reason."""
    manifest = json.loads((CACHE / 'manifest.json').read_text('utf-8'))
    by_key: dict[str, list[dict]] = {}
    skipped = []
    for src, m in sorted(manifest.items()):
        f = PDF / m['file']
        if not f.exists() or 'sha256' not in m:
            continue
        if SKIP.search(m['file']):
            skipped.append({'act': '', 'source': src, 'file': m['file'], 'reason': 'not a reprint of the Laws of '
                            'the Republic of Nauru (a Word copy with no Table of Amendments or history notes)'})
            continue
        d = parse_all.load(m['sha256'], f)
        if not d['instruments']:
            skipped.append({'act': '', 'source': src, 'file': m['file'],
                            'reason': 'unreadable PDF' if 'error' in d else
                            'not a reprint (no Table of Amendments): a law as made'})
            continue
        moddate = pdf_moddate(f)
        for k, inst in enumerate(d['instruments']):
            key = title_key(inst['title'] or inst['text_title'])
            same = sum(1 for x in d['instruments'][:k] if title_key(x['title'] or x['text_title']) == key)
            if key and same:  # two instruments of one name in one reprint (two appointments)
                key = f'{key} {same + 1}'
            reason = ('no title' if not key else 'Table of Contents not readable (page labels of two digits)'
                      if re.search(r'table of (provisions|amendments)', key)
                      else 'no dates in its Table of Amendments' if not inst['as_at']
                      else 'no text' if not (inst['units'] or inst['preamble'])
                      else f"consolidated to {inst['as_at']}, after the build day" if inst['as_at'] > today else '')
            if reason:
                skipped.append({'act': key, 'source': src, 'file': m['file'],
                                'reason': f"instrument {k + 1} ({inst['title'] or '?'}): {reason}"})
                continue
            v = dict(inst)
            v.update({'source': src, 'file': m['file'], 'sha256': m['sha256'], 'moddate': moddate, 'index': k})
            by_key.setdefault(key, []).append(v)
    # Directory, label and provision word per instrument (from the key and every version, so stable).
    INSTR.clear()
    used_dirs: set[str] = set()
    for key in sorted(by_key):
        ds = by_key[key]
        latest = max(ds, key=lambda d: (d['as_at'], d['moddate'], d['source'], d['index']))
        label = norm_title(latest['title'] or latest['text_title'])
        if key in CONSTITUTION_KEYS:
            info = {'dir': 'constitution', 'unit': 'article', 'part': 'constitution'}
        else:
            act = any(d['part'] == 'principal' for d in ds) or all(is_act(d['title']) for d in ds)
            base = 'acts' if act else 'subsidiary'
            slug = slugify(key)
            d0, n = f'{base}/{slug}', 2
            while d0 in used_dirs:
                d0, n = f'{base}/{slug}-{n}', n + 1
            units = Counter(d['unit'] for d in ds if d.get('unit'))
            unit = sorted(units.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if units else ('section' if act else 'clause')
            if any(u['kind'] == 'article' for d in ds for u in d['units']):
                unit = 'article'
            info = {'dir': d0, 'unit': unit, 'part': 'act' if act else 'subsidiary'}
        used_dirs.add(info['dir'])
        info['label'] = label
        INSTR[key] = info
    versions: dict[str, list[dict]] = {}
    for key, ds in sorted(by_key.items()):
        for d in ds:
            d['files'] = version_files(INSTR[key], d)
        groups: dict[str, list[dict]] = {}
        for d in ds:
            groups.setdefault(d['as_at'], []).append(d)
        out = []
        for as_at, g in sorted(groups.items()):
            g.sort(key=lambda d: (d['moddate'], d['source'], d['index']))
            chosen = g[-1]
            chosen['same_date'] = []
            for other in g[:-1]:
                diff = sorted(p for p in set(chosen['files']) | set(other['files'])
                              if squash(chosen['files'].get(p, '')) != squash(other['files'].get(p, '')))
                chosen['same_date'].append({'source': other['source'], 'file': other['file'], 'differs': diff})
            out.append(chosen)
        versions[key] = out
    return versions, skipped


# ------------------------------------------------------------------------------------------------ history

def plan(versions: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    events: list[dict] = []
    names: dict[tuple, str] = {}
    for vs in versions.values():
        for v in vs:
            for k, a in table_keys(v['amendments']).items():
                names.setdefault(k, norm_title(a['name']))
    for key, vs in versions.items():
        prev = None
        for v in vs:
            files = dict(v['files'])
            if prev is None:
                events.append({'date': v['as_at'], 'kind': 'consolidated', 'author': None, 'act': key, 'version': v,
                               'changes': files})
                prev = {'v': v, 'files': files}
                continue
            pv, pfiles = prev['v'], prev['files']
            for p in files:  # typesetting alone is not a change
                if p in pfiles and squash(files[p]) == squash(pfiles[p]):
                    files[p] = pfiles[p]
            changed = sorted(p for p in files if files[p] != pfiles.get(p))
            removed = sorted(p for p in pfiles if p not in files)
            lo, hi = pv['as_at'], v['as_at']
            new_rows = sorted(k for k in table_keys(v['amendments']) if k not in table_keys(pv['amendments']))
            buckets: dict[tuple, dict] = {}
            for p in changed + removed:
                new = cite_keys(files.get(p, '')) - cite_keys(pfiles.get(p, ''))
                cands = sorted({k for k in new if lo < k[3] <= hi})
                acts = sorted({k[:3] for k in cands})
                if len(acts) == 1:
                    date = max(k[3] for k in cands)
                    b = (date, 'amendment', acts[0], '')
                    ev = 'note'
                elif len(acts) > 1:
                    date = max(k[3] for k in cands)
                    b = (date, 'several-acts', None, key + '|' + '|'.join(f'{a[0]}-{a[1]}-{a[2]}' for a in acts))
                    ev = 'note'
                elif len(new_rows) == 1:
                    row = table_keys(v['amendments'])[new_rows[0]]
                    date = row['commenced'] or hi
                    b = (date, 'amendment', new_rows[0], '')
                    ev = 'table'
                else:
                    b = (hi, 'unexplained', None, key)
                    ev = 'none'
                    acts = new_rows
                e = buckets.setdefault(b, {'date': b[0], 'kind': b[1], 'author': b[2], 'act': key, 'version': v,
                                           'prev': pv, 'changes': {}, 'evidence': {}, 'candidates': set()})
                e['changes'][p] = files.get(p)
                e['evidence'][p] = ev
                if b[1] != 'amendment':
                    e['candidates'] |= set(acts)
            for b in sorted(buckets, key=lambda b: (b[0], b[1], b[2] or ('', 0, 0), b[3])):
                events.append(buckets[b])
            prev = {'v': v, 'files': files}
    return events, names


def group(events: list[dict]) -> list[dict]:
    commits: dict[tuple, dict] = {}
    for e in events:
        if e['kind'] == 'amendment':
            k = (e['date'], 1, e['author'], '')
        else:
            k = (e['date'], 0 if e['kind'] == 'consolidated' else 2, None,
                 e['act'] + '|' + e['kind'] + '|' + '|'.join(f'{a[0]}-{a[1]}-{a[2]}' for a in sorted(e.get('candidates', ()))))
        c = commits.setdefault(k, {'date': e['date'], 'kind': e['kind'], 'author': e['author'], 'parts': []})
        c['parts'].append(e)
    return [commits[k] for k in sorted(commits, key=lambda k: (k[0], k[1], k[2] or ('', 0, 0), k[3]))]


def git_date(day: str, seq: int = 0) -> str:
    """Noon Nauru time (UTC+12 all year; Nauru has no summer time). Git rejects dates before 1970: those commits are
    dated 1970-01-01 00:00:01 UTC onwards, one second apart (`seq`), and keep their day in `In-force:`."""
    d = datetime.strptime(day, '%Y-%m-%d').replace(hour=12, tzinfo=timezone(timedelta(hours=12)))
    ts = int(d.timestamp())
    return f'{ts if ts > 10 ** 6 else seq + 1} +1200'


def message(c: dict, names: dict) -> tuple[str, str]:
    acts = sorted({INSTR[p['act']]['label'] for p in c['parts']})
    n = sum(len(p['changes']) for p in c['parts'])
    if c['kind'] == 'consolidated':
        p = c['parts'][0]
        v = p['version']
        name, email = PUBLISHER
        subject = f"{acts[0]}: the reprint consolidated to {c['date']}"
        serv = f" (service {max(v['services'])})" if v['services'] else ''
        body = [f"The text of the {INSTR[p['act']]['label']} as the Laws of the Republic of Nauru reprint{serv} "
                f"prints it, consolidated to {c['date']}: the earliest reprint on RONLAW.",
                'Who wrote each line before this date is not shown as commits; each provision keeps the history',
                'notes the reprint prints after it.']
        trailers = ['Kind: consolidated', f"Consolidated: {c['date']}", f"In-force: {c['date']}",
                    f"Law: {INSTR[p['act']]['label']}", f"Source: https://ronlaw.gov.nr/assets{_q(v['source'])}"]
    elif c['kind'] in ('unexplained', 'several-acts'):
        p = c['parts'][0]
        name, email = PUBLISHER
        cands = sorted(c['parts'][0]['candidates'])
        if c['kind'] == 'several-acts':
            subject = f"{acts[0]}: changes by more than one Act, final text ({c['date']})"
            body = [f"The reprint consolidated to {p['version']['as_at']} differs from the one consolidated to "
                    f"{p['prev']['as_at']} in {n} file(s) whose notes name more than one new Act.",
                    'The intermediate wording is not in any reprint, so the final text is committed on the latest',
                    'operative date and credited to none of them.']
        else:
            subject = f"{acts[0]}: changes no Act is credited with ({c['date']})"
            body = [f"The reprint consolidated to {p['version']['as_at']} differs from the one consolidated to "
                    f"{p['prev']['as_at']} in {n} file(s), but neither the notes nor the Table of Amendments name "
                    'one Act for them.']
        trailers = [f"Kind: {c['kind']}", f"In-force: {c['date']}", f"Law: {acts[0]}",
                    f"Source: https://ronlaw.gov.nr/assets{_q(p['version']['source'])}"]
        for k in cands:
            trailers.append(f'Candidate: {law_author(k, names)[0]}')
    else:
        name, email = law_author(c['author'], names)
        subject = f"{name}: {law_list(acts)}"
        body = [f"Changes by {name} to {law_list(acts)} ({n} file(s)), operative {c['date']}."]
        ev = sorted({e for p in c['parts'] for e in p['evidence'].values()})
        trailers = ['Kind: amendment', f"In-force: {c['date']}"]
        kind, year, num = c['author']
        trailers.append(f"Cited-as: {cited_as(c['author'])}")
        trailers.append(f"Evidence: {', '.join(ev)}")
        for a in acts:
            trailers.append(f'Affecting: {a}')
        for p in c['parts']:
            trailers.append(f"Source: https://ronlaw.gov.nr/assets{_q(p['version']['source'])}")
    msg = '\n'.join([subject, '', *body, '', *trailers]) + '\n'
    return f'{name} <{email}>', msg


def _q(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s)


# ------------------------------------------------------------------------------------------------ write

def fast_import(repo: Path, commits: list[dict], names: dict, docs: dict[str, bytes], today: str) -> None:
    proc = subprocess.Popen(['git', '-C', str(repo), 'fast-import', '--quiet', '--done'], stdin=subprocess.PIPE)
    w = proc.stdin.write
    mark = 0
    for c in commits:
        author, msg = message(c, names)
        when = git_date(c['date'], mark)
        mark += 1
        w(b'commit refs/heads/main\n')
        w(f'mark :{mark}\n'.encode())
        w(f'author {author} {when}\ncommitter {COMMITTER} {when}\n'.encode('utf-8'))
        m = msg.encode('utf-8')
        w(f'data {len(m)}\n'.encode() + m + b'\n')
        if mark > 1:
            w(f'from :{mark - 1}\n'.encode())
        for p in c['parts']:
            for path, text in sorted(p['changes'].items()):
                if text is None:
                    w(f'D {path}\n'.encode('utf-8'))
                else:
                    t = text.encode('utf-8')
                    w(f'M 100644 inline {path}\ndata {len(t)}\n'.encode('utf-8') + t + b'\n')
        w(b'\n')
    when = git_date(today)
    msg = (f'Documentation: README, REPRODUCE, corpus.json, tools and data\n\nBuilt from the RONLAW cache retrieved '
           f'{today}.\n\nKind: documentation\nIn-force: {max(c["date"] for c in commits)}\n').encode('utf-8')
    mark += 1
    w(b'commit refs/heads/main\n')
    w(f'mark :{mark}\nauthor {COMMITTER} {when}\ncommitter {COMMITTER} {when}\n'.encode())
    w(f'data {len(msg)}\n'.encode() + msg + b'\n')
    w(f'from :{mark - 1}\n'.encode())
    for path, data in sorted(docs.items()):
        w(f'M 100644 inline {path}\ndata {len(data)}\n'.encode('utf-8') + data + b'\n')
    w(b'\ndone\n')
    proc.stdin.close()
    if proc.wait():
        sys.exit('fast-import failed')


def fresh_repo(repo: Path) -> None:
    """Rebuild from scratch, keeping `origin`. Refuse a non-empty folder that is not an earlier build."""
    remote = None
    if repo.exists() and any(repo.iterdir()):
        if not (repo / 'corpus.json').exists() and not (repo / '.git').exists():
            sys.exit(f'{repo} is not empty and not an earlier build; refusing')
        r = subprocess.run(['git', '-C', str(repo), 'remote', 'get-url', 'origin'], capture_output=True, text=True)
        remote = r.stdout.strip() or None
        def onerr(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        for child in repo.iterdir():
            shutil.rmtree(child, onerror=onerr) if child.is_dir() else child.unlink()
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'config', 'core.autocrlf', 'false'], check=True)
    if remote:
        subprocess.run(['git', '-C', str(repo), 'remote', 'add', 'origin', remote], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', type=Path)
    ap.add_argument('--today', required=True, help='the retrieval day; dates the documentation commit')
    ap.add_argument('--plan', action='store_true', help='print the commits and stop')
    args = ap.parse_args()
    versions, skipped = load_versions(args.today)
    events, names = plan(versions)
    commits = group(events)
    if args.plan:
        for c in commits:
            a, msg = message(c, names)
            print(c['date'], c['kind'], a.split(' <')[0], {p['act']: len(p['changes']) for p in c['parts']},
                  [l for l in msg.splitlines() if l.startswith(('Candidate', 'Evidence'))])
        for k, vs in versions.items():
            for v in vs:
                print(k, v['as_at'], v['file'], [(o['file'], len(o['differs'])) for o in v['same_date']])
        return
    import docs as docmod
    docs = docmod.render(versions, skipped, commits, names, args.today)
    fresh_repo(args.repo)
    fast_import(args.repo, commits, names, docs, args.today)
    subprocess.run(['git', '-C', str(args.repo), 'checkout', '-q', '-f', 'main'], check=True)
    head = subprocess.run(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    n = subprocess.run(['git', '-C', str(args.repo), 'rev-list', '--count', 'HEAD'], capture_output=True, text=True).stdout.strip()
    print(f'built {args.repo}: {n} commits, head {head}')


if __name__ == '__main__':
    main()
