# Reproducing this repository

Built from RONLAW data retrieved on 2026-10-28 by the scripts in `tools/build/` (copied there as run).

| Script | sha256 |
| --- | --- |
| fetch.py | `ff047b714e1bfe0c6dc2e97e4d8d3e180b13afee999e2795d03477468b66e262` |
| parse.py | `90a3ab039b624fbfa2743594436ca301373cc94b172689a1c8a208b132c7e21b` |
| build.py | `1e1085704894dba7c1f70e27246cacfa34e49a1499057b3414b69f32c33d1404` |
| docs.py | `f34b59f10fd88e2377b5c1cc77283196c088ee1d30c4ff0db113dce123ac6589` |
| check_repo.py | `ba8c1de6cd394969a1fd14ef275cce2fee9f9fb8d5c2365ef95f0357555ead69` |
| test_repo.py | `b098b1312eaca93efe1a8dd65605be7cc9091197019a3276f48b2e2ae396718b` |

Tools: Python 3.12, PyMuPDF (`pymupdf`), git 2.x, curl (Windows). The PDFs' sha256 are in
[`data/pdf-sha256.tsv`](data/pdf-sha256.tsv); every request made is in [`data/fetch-log.jsonl`](data/fetch-log.jsonl).

## Steps

```sh
# 1. RONLAW's index (one request, 33 MB JSON) and every reprint of the two acts (16 PDFs), one request at a time.
python fetch.py --index
# 2. Build. --today is the retrieval day; it dates the documentation commit.
python build.py ../nauru-law --today 2026-10-28
# 3. Checks.
python check_repo.py ../nauru-law            # bytes and independent words, every version
python test_repo.py --repo ../nauru-law      # reader smoke test
python ../global-law/check_corpus.py ../nauru-law
python ../test_corpus.py ../nauru-law tools/in_force_on.py
```

## robots.txt, terms and fetch rate

Checked on 2026-10-28 before fetching. `https://ronlaw.gov.nr/robots.txt` returns the single-page app's HTML (status
200), so there is no robots.txt: no Disallow, no Crawl-delay, no rule naming ClaudeBot, Claude-Web, anthropic-ai or
[`SOURCES.md`](SOURCES.md) for the copyright position.

**Fetch rate:** 19 requests in all (18 PDF downloads; the rest are the index and checks), one at a
time, sequential, with `curl --compressed` and a browser User-Agent. No request was retried. There is no bulk download;
the index API is the app's own.

## Decisions made by hand

- Acts: the Constitution (the user's brief) and the Public Service Act 2016, which has the most reprints on RONLAW
  (serv3 to serv6) and is frequently amended.
- Reprints are dated by their Table of Amendments (latest commencement listed). Where several PDFs share a date,
  the one with the latest PDF modification date is used; the others and how they differ are in `data/versions.csv`
  (the serv3 Public Service Act reprint orders the definitions in section 4 differently from serv4).
- Two files are not reprints and are not used (see `SOURCES.md`).
- Changes are credited by the history notes, then by the Table of Amendments; see the README. Nothing is credited
  by guess: a change two Acts could explain is `Kind: several-acts`, one nothing explains is `Kind: unexplained`.
- Text normalisation: ligatures (U+FB00-FB04) are spelled out, soft hyphens removed, runs of white space collapsed;
  quotes, dashes and spelling are left as printed.

## What the AI did and did not do

The repository was built by Claude Code with Claude Opus 5.5 (`claude-opus-5-5`): it found the source and the API,
checked robots, terms and the Copyright Act, and wrote the scripts. No AI model writes or edits legal text, and no
model runs at fetch, data-build or git-build time.

## What the build produced

- Constitution: 5 reprints, 112 files; Public Service Act 2016: 3 reprints,
  147 files.
- 13 commits: 2 consolidated, 8 amendment, 1 several-acts,
  1 unexplained, and one documentation commit. In-force dates from 2022-06-08 to 2026-07-20.

## Checks

```sh
git rev-list --merges --count main                                     # 0
git log --format=%B main | tr -cd '\r' | wc -c                         # 0
git log --format='%(trailers:key=In-force,valueonly,separator=)' main  # never increases going back
```

- check_repo.py: bytes: 984 files identical, 1 differ only in white space, 0 mismatches; independent words: 8/8 versions match the raw PDF letter for letter
- test_repo.py: 6/6 passed
- Rebuild: two builds from the same cache on 2026-10-29 gave the same HEAD (see data/verification.json "rebuild_heads")
