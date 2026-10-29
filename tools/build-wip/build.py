"""Build the Nauru law repository from the RONLAW cache.

    python scripts/nauru-law/build.py ~/Documents/nauru-law --today 2026-10-28 [--offline]

Acts: the Constitution of Nauru 1968 (renamed the Constitution of Naoero by Act 21 of 2026) and the Public Service
Act 2016, from the consolidated reprints of the Laws of the Republic of Nauru on ronlaw.gov.nr (fetch.py).

Steps:
1. Parse every cached reprint (parse.py). Each reprint's Table of Amendments gives the date it is consolidated to
   (`as_at`: the latest commencement it lists). Reprints with the same as_at and the same text are one version; if
   the texts differ, the reprint with the latest PDF modification date is used and the others are listed.
2. The earliest version of each act is a baseline commit by RONLAW, `Kind: consolidated`. Each later version is
   compared with the one before, file by file (article/section, schedule, preamble).
3. A changed file is credited by the history notes the reprint prints after each provision ("[Art 21 subst Act 18
   of 2026 s 6, opn 16 Apr 2026]"): the (Act, operative date) citations new in that file since the previous version,
   with an operative date after the previous version's as_at (`Evidence: note`). One such Act: it is the author and
   its operative date is the commit date. Several: the file's final text is committed on the latest of their dates
   by RONLAW, `Kind: several-acts`, with one `Candidate:` per Act and no credit. None: if exactly one Act was added
   to the Table of Amendments between the two versions, it is credited (`Evidence: table`); otherwise the change is
   RONLAW's, `Kind: unexplained`, dated by the new version's as_at.
4. One commit per amending Act per in-force day, across both acts; noon Nauru time (UTC+12, no summer time). Written
   with one git fast-import, so the same cache gives the same hashes.
"""
import argparse
import hashlib
import json
import re
import shutil
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import parse  # noqa: E402

CACHE = HERE / 'cache'
PDF = CACHE / 'pdf'
COMMITTER = 'Lexifina <nauru-law@lexifina.com>'
PUBLISHER = ('RONLAW (Department of Justice and Border Control)', 'ronlaw@ronlaw-gov-nr.invalid')

ACTS = {
    'constitution': {'dir': 'constitution', 'name': 'Constitution of Nauru 1968', 'label': 'Constitution',
                     'unit': 'article'},
    'public-service-act-2016': {'dir': 'public-service-act-2016', 'name': 'Public Service Act 2016',
                                'label': 'Public Service Act 2016', 'unit': 'section'},
}
SKIP = re.compile(r'Repulbic|^Public_Service_Act_2016\.[0-9a-f]{8}\.pdf$')  # not reprints; see REPRODUCE.md

MON = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'June': 6, 'Jul': 7, 'July': 7, 'Aug': 8,
       'Sep': 9, 'Sept': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12, 'January': 1, 'February': 2, 'March': 3, 'April': 4,
       'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12}
# "Act 18 of 2026 s 5, opn 16 Apr 2026"; "GN No 72/1968, opn 17 May 1968"; "Act 6 of 2020 ss 18, 30, opn 4 June 2020"
CITE = re.compile(r'(Act (\d+) of (\d{4})|GN No (\d+)/(\d{4}))(?:[^;\]\[]*?)opn (\d{1,2}) ([A-Z][a-z]+) (\d{4})')


def cite_keys(text: str) -> set[tuple]:
    out = set()
    for line in text.splitlines():
        if not line.startswith('['):
            continue
        for m in CITE.finditer(line):
            kind = 'act' if m.group(2) else 'gn'
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
    return (title or f'Act {num} of {year}'), f'act-{year}-{num}@ronlaw-gov-nr.invalid'


def table_keys(amendments: list[dict]) -> dict[tuple, dict]:
    """Table rows keyed like note citations: ('act', certified year, number) or ('gn', year, number)."""
    out = {}
    for a in amendments:
        n = norm_title(a['name'])
        m = re.search(r'GN No (\d+)/(\d{4})', n)
        if m:
            out[('gn', int(m.group(2)), int(m.group(1)))] = a
            continue
        m = re.search(r'No (\d+)$', n)
        if m and a['certified']:
            out[('act', int(a['certified'][:4]), int(m.group(1)))] = a
    return out


# ------------------------------------------------------------------------------------------------ files

def unit_path(act: dict, u: dict) -> str:
    if u['kind'] == 'schedule':
        sid = re.sub(r'^schedule-?', '', u['id']).replace('-schedule', '') or 'only'
        return f"{act['dir']}/schedule/{sid}.md"
    return f"{act['dir']}/{act['unit']}/{u['id']}.md"


def unit_text(u: dict) -> str:
    lines = [f'## {h}' for h in u['heading']]
    if u['kind'] == 'schedule':
        lines.append(f"# {u['title']}")
    else:
        lines.append(f"# {'Article ' if u['kind'] == 'article' else ''}{u['id']} {u['title']}".rstrip())
    lines.extend(u['lines'])
    return '\n'.join(lines) + '\n'


def version_files(act: dict, d: dict) -> dict[str, str]:
    files = {}
    if d['preamble']:
        files[f"{act['dir']}/preamble.md"] = '\n'.join(d['preamble']) + '\n'
    for u in d['units']:
        files[unit_path(act, u)] = unit_text(u)
    return files


def squash(s: str) -> str:
    return re.sub(r'\s+', '', s)


# ------------------------------------------------------------------------------------------------ versions

def pdf_moddate(path: Path) -> str:
    import pymupdf
    return (pymupdf.open(str(path)).metadata or {}).get('modDate') or ''


def load_versions() -> tuple[dict[str, list[dict]], list[dict]]:
    manifest = json.loads((CACHE / 'manifest.json').read_text('utf-8'))
    by_act: dict[str, list[dict]] = {k: [] for k in ACTS}
    skipped = []
    for src, m in sorted(manifest.items()):
        f = PDF / m['file']
        if not f.exists():
            continue
        if SKIP.search(m['file']):
            skipped.append({'act': m['act'], 'source': src, 'file': m['file'], 'reason': 'not a reprint of the '
                            'Laws of the Republic of Nauru (no Table of Amendments, no service stamps)'})
            continue
        d = parse.parse(str(f))
        if not d['as_at'] or not d['units']:
            skipped.append({'act': m['act'], 'source': src, 'file': m['file'], 'reason': 'unreadable'})
            continue
        act = ACTS[m['act']]
        d.update({'source': src, 'file': m['file'], 'sha256': m.get('sha256', ''), 'moddate': pdf_moddate(f),
                  'files': version_files(act, d)})
        by_act[m['act']].append(d)
    versions: dict[str, list[dict]] = {}
    for key, ds in by_act.items():
        groups: dict[str, list[dict]] = {}
        for d in ds:
            groups.setdefault(d['as_at'], []).append(d)
        out = []
        for as_at, g in sorted(groups.items()):
            g.sort(key=lambda d: (d['moddate'], d['source']))
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
        act = ACTS[key]
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


def git_date(day: str) -> str:
    """Noon Nauru time (UTC+12 all year; Nauru has no summer time)."""
    d = datetime.strptime(day, '%Y-%m-%d').replace(hour=12, tzinfo=timezone(timedelta(hours=12)))
    return f'{int(d.timestamp())} +1200'


def message(c: dict, names: dict) -> tuple[str, str]:
    acts = sorted({ACTS[p['act']]['label'] for p in c['parts']})
    n = sum(len(p['changes']) for p in c['parts'])
    if c['kind'] == 'consolidated':
        p = c['parts'][0]
        v = p['version']
        name, email = PUBLISHER
        subject = f"{acts[0]}: the reprint consolidated to {c['date']}"
        body = [f"The text of the {ACTS[p['act']]['name']} as the Laws of the Republic of Nauru reprint (service "
                f"{max(v['services'])}) prints it, consolidated to {c['date']}: the earliest reprint on RONLAW.",
                'Who wrote each line before this date is not shown as commits; each provision keeps the history',
                'notes the reprint prints after it.']
        trailers = ['Kind: consolidated', f"Consolidated: {c['date']}", f"In-force: {c['date']}",
                    f"Law: {ACTS[p['act']]['label']}", f"Source: https://ronlaw.gov.nr/assets{_q(v['source'])}"]
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
        subject = f"{name}: {', '.join(acts)}"
        body = [f"Changes by {name} to {', '.join(acts)} ({n} file(s)), operative {c['date']}."]
        ev = sorted({e for p in c['parts'] for e in p['evidence'].values()})
        trailers = ['Kind: amendment', f"In-force: {c['date']}"]
        kind, year, num = c['author']
        trailers.append(f"Cited-as: {'Act ' + str(num) + ' of ' + str(year) if kind == 'act' else f'GN No {num}/{year}'}")
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
        when = git_date(c['date'])
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
    versions, skipped = load_versions()
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
