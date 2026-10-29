"""Functional smoke test of the built Nauru law repository: the things a reader does with it work. Standard library only.

    python test_repo.py [--repo ../../../nauru-law] [--record]
    python tools/build/test_repo.py --repo .           # from inside the repository

It asserts that:
1. `git blame` on a changed provision names an amending Act as author of its lines;
2. tools/in_force_on.py gives the text before and after known amendments, and each equals the file at the commit
   that made the change and at its parent;
3. `git log --follow` on files lists their changes newest first, by date;
4. every commit carries an ISO `In-force:` trailer, every trailer block parses, and there are no merges or CRs;
5. no commit is authored by Lexifina except the documentation commit (the last one), and law authors use .invalid;
6. every git or tool command in the README's table runs and prints something.
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLISHER = 'RONLAW (Department of Justice and Border Control)'
ACT = re.compile(r'^(.+ No \d+|.+ SL \d+|GN No \d+/\d{4}|(?:Act|SL|Ordinance) \d+ of \d{4})$')


class Smoke:
    def __init__(self, repo: Path):
        self.repo = repo
        self.results: list[tuple[str, bool, str]] = []

    def git(self, *args: str) -> str:
        out = subprocess.run(['git', *args], cwd=self.repo, capture_output=True, text=True, encoding='utf-8')
        if out.returncode:
            raise AssertionError(f'git {" ".join(args)}: {out.stderr.strip()}')
        return out.stdout

    def tool(self, *args: str) -> str:
        out = subprocess.run([sys.executable, '-X', 'utf8', 'tools/in_force_on.py', *args], cwd=self.repo,
                             capture_output=True, text=True, encoding='utf-8')
        if out.returncode:
            raise AssertionError(f'in_force_on {" ".join(args)}: {out.stderr.strip()}')
        return out.stdout

    def check(self, name: str, fn):
        try:
            detail = fn() or ''
            self.results.append((name, True, detail))
            print(f'PASS {name}: {detail}')
        except AssertionError as exc:
            self.results.append((name, False, str(exc)))
            print(f'FAIL {name}: {exc}')

    def blame(self):
        out = self.git('blame', '--line-porcelain', 'main', '--', 'constitution/article/19.md')
        authors = {l[7:] for l in out.splitlines() if l.startswith('author ')}
        assert 'Constitution (Amendment) Act 2026 No 18' in authors, f'Act 18 of 2026 not among {authors}'
        assert all(ACT.match(a) or a == PUBLISHER for a in authors), f'unexpected authors {authors}'
        return f'constitution/article/19.md lines by {"; ".join(sorted(authors))}'

    def on_date(self):
        done = []
        for act, prov, before, after, author in [
                ('constitution', 'article/21', '2026-04-15', '2026-04-16', 'Constitution (Amendment) Act 2026 No 18'),
                ('constitution', 'article/19', '2026-01-13', '2026-01-14', 'Constitution (Amendment) Act 2025 No 1'),
                ('constitution', 'article/1', '2026-05-11', '2026-05-12', 'Constitution (Amendment) (No 2) Act 2026 No 21'),
                ('subsidiary/immigration-regulations-2014', 'schedule/3', '2024-05-06', '2024-05-07',
                 'Immigration (Amendment) Regulations 2024 SL 14'),
                ('acts/public-service-act-2016', 'section/10', '2026-07-19', '2026-07-20',
                 'Public Service (Amendment) Act 2026 No 28')]:
            path = f'{act}/{prov}.md'
            a, b = self.tool(before, act, prov), self.tool(after, act, prov)
            assert a and b and a != b, f'{path}: no change between {before} and {after}'
            h = self.git('log', '-1', '--format=%H', f'--author={author}', 'main', '--', path).strip()
            assert h, f'{path}: no commit by {author}'
            assert b == self.git('show', f'{h}:{path}'), f'{path} on {after} is not the file at {h[:7]}'
            assert a == self.git('show', f'{h}~1:{path}'), f'{path} on {before} is not the file before {h[:7]}'
            done.append(f'{path} {before}->{after}')
        new = self.tool('2026-03-26', 'constitution', 'article/84A')
        assert 'Revision of the Constitution' in new, 'Article 84A missing on 2026-03-26'
        try:
            self.tool('2026-03-25', 'constitution', 'article/84A')
            raise AssertionError('Article 84A printed before it was inserted')
        except AssertionError as e:
            if 'printed before' in str(e):
                raise
        whole = self.tool('2022-06-08', 'constitution')
        assert 'Article 84 Amendment of the Constitution' in whole, 'whole Constitution on 2022-06-08 lacks Art 84'
        return '; '.join(done) + '; 84A absent on 2026-03-25'

    def follow(self):
        checked = []
        for path in ('constitution/article/19.md', 'acts/public-service-act-2016/section/4.md', 'constitution/article/1.md'):
            out = self.git('log', '--follow', '--format=%an%x09%(trailers:key=In-force,valueonly,separator=)', 'main', '--', path)
            rows = [l.split('\t') for l in out.splitlines() if l]
            assert len(rows) >= 2, f'{path}: {len(rows)} commits'
            days = [d.strip() for _, d in rows]
            assert days == sorted(days, reverse=True), f'{path}: not in date order {days}'
            checked.append(f'{path} {len(rows)} commits')
        return '; '.join(checked)

    def trailers(self):
        rows = self.git('log', '--format=%H%x1f%(trailers:key=In-force,valueonly,separator=)', 'main').splitlines()
        bad = [r for r in rows if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', r.split('\x1f')[1].strip())]
        assert not bad, f'{len(bad)} commits without an ISO In-force'
        for r in rows:
            msg = self.git('log', '-1', '--format=%B', r.split('\x1f')[0])
            parsed = subprocess.run(['git', 'interpret-trailers', '--parse'], input=msg, capture_output=True,
                                    text=True, encoding='utf-8', cwd=self.repo).stdout
            assert 'In-force:' in parsed, f'{r[:7]}: trailers do not parse'
        assert self.git('rev-list', '--merges', '--count', 'main').strip() == '0', 'merge commits'
        assert '\r' not in self.git('log', '--format=%B', 'main'), 'CR in a commit message'
        days = [r.split('\x1f')[1].strip() for r in rows]
        assert days == sorted(days, reverse=True), 'In-force goes backwards'
        return f'{len(rows)} commits: In-force on all, trailers parse, 0 merges, 0 CRs, dates monotone'

    def authors(self):
        rows = self.git('log', '--format=%an%x09%ae%x09%cn', 'main').splitlines()
        lex = [i for i, r in enumerate(rows) if r.split('\t')[0] == 'Lexifina']
        assert lex == [0], f'Lexifina-authored commits at {lex}'
        assert all(r.split('\t')[2] == 'Lexifina' for r in rows), 'a committer other than Lexifina'
        laws = rows[1:]
        assert all(r.split('\t')[1].endswith('.invalid') for r in laws), 'a law author without .invalid'
        assert all(ACT.match(r.split('\t')[0]) or r.split('\t')[0] == PUBLISHER for r in laws), 'unexpected author'
        return f'only the documentation commit is by Lexifina; {len({r.split(chr(9))[0] for r in laws})} authors'

    def readme(self):
        text = (self.repo / 'README.md').read_text(encoding='utf-8')
        table = text[text.index('## The questions'):text.index('## The dates')]
        cmds = [c for c in re.findall(r'`([^`]+)`', table) if c.startswith(('git ', 'python '))]
        assert len(cmds) >= 8, f'only {len(cmds)} commands found'
        for c in cmds:
            args = shlex.split(c)
            if args[0] == 'python':
                args = [sys.executable, '-X', 'utf8', *args[1:]]
            out = subprocess.run(args, cwd=self.repo, capture_output=True, text=True, encoding='utf-8')
            assert out.returncode == 0, f'{c}: exit {out.returncode} {out.stderr.strip()[:200]}'
            assert out.stdout.strip(), f'{c}: printed nothing'
        return f'{len(cmds)} README commands ran and printed output'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=str(HERE.parents[2] / 'nauru-law'))
    ap.add_argument('--record', action='store_true')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    s = Smoke(Path(args.repo))
    s.check('blame names an Act', s.blame)
    s.check('text before and after amendments', s.on_date)
    s.check('log --follow in date order', s.follow)
    s.check('In-force, trailers, merges, CRs', s.trailers)
    s.check('authors', s.authors)
    s.check('README commands run', s.readme)
    passed = sum(r[1] for r in s.results)
    print(f'{passed}/{len(s.results)} passed')
    if args.record:
        p = HERE / 'verification.json'
        rec = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        rec['smoke'] = {'summary': f'{passed}/{len(s.results)} passed',
                        'results': [{'test': n, 'ok': o, 'detail': d} for n, o, d in s.results]}
        p.write_text(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    raise SystemExit(0 if passed == len(s.results) else 1)


if __name__ == '__main__':
    main()
