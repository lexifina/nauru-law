"""README, REPRODUCE.md, SOURCES.md, LICENSE, corpus.json, data/ and tools/ for the Nauru law repository."""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
REPO_FILES = HERE / 'repo'
CACHE = HERE / 'cache'
SCRIPTS = ('fetch.py', 'parse.py', 'build.py', 'docs.py', 'check_repo.py', 'test_repo.py')


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _csv(rows: list[list]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, lineterminator='\n')
    for r in rows:
        w.writerow(r)
    return out.getvalue().encode('utf-8')


def render(versions: dict, skipped: list, commits: list, names: dict, today: str) -> dict[str, bytes]:
    from build import ACTS, law_author, message  # noqa: E402
    kinds = Counter(c['kind'] for c in commits)
    law_dates = [c['date'] for c in commits]
    first, last = min(law_dates), max(law_dates)
    ev = Counter(e for c in commits if c['kind'] == 'amendment' for p in c['parts'] for e in p['evidence'].values())
    n_files = {k: len(vs[-1]['files']) for k, vs in versions.items()}
    authors = sorted({law_author(c['author'], names)[0] for c in commits if c['kind'] == 'amendment'})
    log_fetch = [json.loads(l) for l in (CACHE / 'fetch-log.jsonl').read_text('utf-8').splitlines() if l.strip()]
    verification = {}
    vp = HERE / 'verification.json'
    if vp.exists():
        verification = json.loads(vp.read_text('utf-8'))

    vrows = [['act', 'as_at', 'source', 'sha256', 'services', 'pdf_moddate', 'amendments_listed', 'files', 'role']]
    arows = [['act', 'version_as_at', 'amending_legislation', 'certified', 'commencement', 'commencement_as_printed']]
    for key, vs in versions.items():
        for v in vs:
            vrows.append([key, v['as_at'], v['source'], v['sha256'], ' '.join(map(str, v['services'])), v['moddate'],
                          len(v['amendments']), len(v['files']), 'used'])
            for o in v['same_date']:
                vrows.append([key, v['as_at'], o['source'], '', '', '', '', '',
                              f"same date; differs in {len(o['differs'])} file(s): {' '.join(o['differs'])}".strip()])
        for a in vs[-1]['amendments']:
            arows.append([key, vs[-1]['as_at'], a['name'].replace('*', '').strip(), a['certified'], a['commenced'], a['raw']])
    for s in skipped:
        vrows.append([s['act'], '', s['source'], '', '', '', '', '', 'not used: ' + s['reason']])
    sums = ''.join(f"{m['sha256']}\t{src}\n" for src, m in sorted(json.loads((CACHE / 'manifest.json').read_text('utf-8')).items())
                   if m.get('sha256'))
    crows = [['date', 'kind', 'author', 'files', 'acts']]
    for c in commits:
        a, _ = message(c, names)
        crows.append([c['date'], c['kind'], a.split(' <')[0], sum(len(p['changes']) for p in c['parts']),
                      ' '.join(sorted({p['act'] for p in c['parts']}))])

    stats = {
        'TODAY': today, 'FIRST': first, 'LAST': last, 'COMMITS': len(commits) + 1,
        'CONSOLIDATED': kinds['consolidated'], 'AMENDMENT': kinds['amendment'], 'SEVERAL': kinds['several-acts'],
        'UNEXPLAINED': kinds['unexplained'], 'AUTHORS': len(authors),
        'CON_FILES': n_files['constitution'], 'PSA_FILES': n_files['public-service-act-2016'],
        'CON_VERSIONS': len(versions['constitution']), 'PSA_VERSIONS': len(versions['public-service-act-2016']),
        'EV_NOTE': ev['note'], 'EV_TABLE': ev['table'], 'REQUESTS': len(log_fetch),
        'PDFS': sum(1 for l in log_fetch if '/assets/' in l['url']),
        'CHECK': verification.get('check', {}).get('summary', 'see tools/build/check_repo.py'),
        'SMOKE': verification.get('smoke', {}).get('summary', 'see tools/build/test_repo.py'),
        'REBUILD': verification.get('rebuild', 'see REPRODUCE.md'),
    }
    for name in SCRIPTS:
        p = HERE / name
        stats['SHA_' + name.upper().replace('.', '_')] = _sha(p) if p.exists() else '(missing)'

    def fill(t: str) -> str:
        for k, v in stats.items():
            t = t.replace('{{' + k + '}}', str(v))
        return t

    corpus = {
        'corpus': 'nr/national/acts',
        'name': 'Laws of the Republic of Nauru (Constitution and Public Service Act 2016)',
        'label': 'Nauru',
        'language': 'en',
        'history_from': first,
        'record_to': last,
        'checked_on': today,
        'record_note': (f'The Constitution of Nauru 1968 and the Public Service Act 2016 from the RONLAW reprints of '
                        f'the Laws of the Republic of Nauru: each act from its earliest reprint on RONLAW '
                        f'(consolidated to {versions["constitution"][0]["as_at"]} and '
                        f'{versions["public-service-act-2016"][0]["as_at"]}) to the latest ({last}); checked {today}.'),
        'history': 'in-force',
        'in_force_trailer': 'In-force',
        'baseline_trailer': 'Consolidated',
        'has_future_branch': False,
        'acts': {k: {'path': ACTS[k]['dir'] + '/', 'files': n_files[k], 'versions': len(versions[k])} for k in ACTS},
        'built': today,
        'dates': {'commit': 'in-force (the operative date printed in the history note, else the commencement in the '
                            'Table of Amendments, else the reprint\'s consolidation date)',
                  'baseline_trailer': 'Consolidated', 'other_trailers': ['Cited-as', 'Evidence', 'Candidate'],
                  'time': '12:00 Pacific/Nauru (UTC+12, no summer time)', 'before_1970': 'none'},
        'author': {'amendment': 'the amending Act (or GN)', 'consolidated': 'RONLAW (Department of Justice and Border Control)',
                   'several-acts': 'RONLAW, with Candidate trailers', 'unexplained': 'RONLAW, with Candidate trailers',
                   'evidence_trailer': 'Evidence'},
        'scope': {
            'trailer': 'Applies', 'groups': 'any one line', 'conditions': 'all of a line',
            'when_absent': 'no scope note found; not a statement that the change reaches every case',
            'default_reach': {
                'rule': 'presumption against retroactivity',
                'meaning': 'a written law does not commence retrospectively unless it clearly says so, and a repeal or '
                           'amendment does not affect the previous operation of the law, rights acquired or accrued, '
                           'or proceedings already begun under it',
                'authority': 'Interpretation Act 2011 (Nauru), sections 22(3) and 28(1); section 21: a provision '
                             'commences at the beginning of its day',
                'decided_here': False,
            },
        },
        'tool': 'tools/in_force_on.py',
        'citation': {'file': r'(constitution/article|public-service-act-2016/section)/0*([0-9]+[A-Z]*)\.md',
                     'cites': r'([Aa]rticle|[Ss]ection) ?{n}([^0-9A-Z]|$)'},
    }

    files = {
        'corpus.json': (json.dumps(corpus, indent=2, ensure_ascii=False) + '\n').encode('utf-8'),
        'README.md': fill((REPO_FILES / 'README.md').read_text('utf-8')).encode('utf-8'),
        'REPRODUCE.md': fill((REPO_FILES / 'REPRODUCE.md').read_text('utf-8')).encode('utf-8'),
        'SOURCES.md': fill((REPO_FILES / 'SOURCES.md').read_text('utf-8')).encode('utf-8'),
        'LICENSE': (REPO_FILES / 'LICENSE').read_bytes(),
        'data/versions.csv': _csv(vrows),
        'data/amendments.csv': _csv(arows),
        'data/commits.csv': _csv(crows),
        'data/pdf-sha256.tsv': sums.encode('utf-8'),
        'data/fetch-log.jsonl': (CACHE / 'fetch-log.jsonl').read_bytes().replace(b'\r\n', b'\n'),
        'tools/in_force_on.py': (REPO_FILES / 'tools' / 'in_force_on.py').read_bytes(),
    }
    if vp.exists():
        files['data/verification.json'] = vp.read_bytes().replace(b'\r\n', b'\n')
    for name in SCRIPTS:
        p = HERE / name
        if p.exists():
            files[f'tools/build/{name}'] = p.read_bytes().replace(b'\r\n', b'\n')
    for name in ('README.md', 'REPRODUCE.md', 'SOURCES.md', 'LICENSE'):
        files[f'tools/build/repo/{name}'] = (REPO_FILES / name).read_bytes().replace(b'\r\n', b'\n')
    return files
