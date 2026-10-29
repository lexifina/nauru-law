# Reproducing this repository

Built from RONLAW data retrieved on 2026-10-29 by the scripts in `tools/build/` (copied there as run).

| Script | sha256 |
| --- | --- |
| fetch.py | `3d249cbe42158bbfd7e4dd62983e9c647899e9cd5944dcf7ece4b2c78d008670` |
| parse.py | `af87769487641402dff3f6bd19ceb471badaee5a33dd5d6664785734144aa0ef` |
| parse_all.py | `0eae275470a09df6772edf16d0e1c9ad86e0a1d8df75f529e0b66bccdf747123` |
| build.py | `1eb045e7e3c6533b12d7414357d814409b1b741bbefda03fa0b6f6b91da0ea7b` |
| docs.py | `92091b972bd4b88a087b332530cb10f538c08cea74fd14d46bb2d96e054abecf` |
| check_repo.py | `fd4e3b96b323c6bc8a5c1dbc388f78fc8d84ca6fc813b9d9c120bf546cb70808` |
| test_repo.py | `b1d36f972f1c0658e8692f15fbb8375568feff0ce3f8303241986ea842f577b6` |

Tools: Python 3.12, PyMuPDF (`pymupdf`), git 2.x, curl (Windows). The PDFs' sha256 are in
[`data/pdf-sha256.tsv`](data/pdf-sha256.tsv); every request made is in [`data/fetch-log.jsonl`](data/fetch-log.jsonl).

## Steps

```sh
# 1. RONLAW's index (one request, 33 MB JSON) and every PDF in the acts, laws and constitution categories
#    (1461 files), at most 4 requests at a time.
python fetch.py --index
# 2. Parse every PDF once (cache/parsed/, keyed by the PDF's and parse.py's sha256), then build.
#    --today is the retrieval day; it dates the documentation commit.
python -W ignore parse_all.py
python -W ignore build.py ../nauru-law --today 2026-10-29
# 3. Checks.
python check_repo.py ../nauru-law            # bytes and independent words, every version
python test_repo.py --repo ../nauru-law      # reader smoke test
python ../global-law/check_corpus.py ../nauru-law
python ../test_corpus.py ../nauru-law tools/in_force_on.py
```

## robots.txt, terms and fetch rate

Checked on 2026-10-28 before fetching; robots.txt checked again on 2026-10-29.
`https://ronlaw.gov.nr/robots.txt` returns the single-page app's HTML (status 200), so there is no robots.txt: no
Disallow, no Crawl-delay, no rule naming ClaudeBot, Claude-Web, anthropic-ai or GPTBot. `www.ronlaw.gov.nr` does not
position.

**Fetch rate:** 1464 requests in all (1463 PDF downloads; the rest are the index and checks), at most 4
at a time, with `curl --compressed` and a browser User-Agent. Every request was answered 200. There is
no bulk download; the index API is the app's own.

## Decisions made by hand

- Scope: every PDF in RONLAW's `acts`, `laws` (subsidiary legislation) and `constitution` categories, except files
  named as amending, appropriation or supplementary Acts without a service suffix (as made, never reprints). A PDF is
  used only if it is a reprint: it has a Table of Amendments (368 PDFs have none and are listed in
  `data/versions.csv` as not used).
- One reprint can hold several laws (an Act and its regulations, each with its own Table of Amendments and text);
  a subsidiary instrument is also often printed on its own. Laws are matched across PDFs by title, with case,
  punctuation, "&"/"and" and Naoero/Nauru folded. Two instruments of the same title in one reprint are numbered
  (`-2`).
- Versions are dated by their Table of Amendments (latest commencement listed). Where several PDFs give the same date
  for one law, the one with the latest PDF modification date is used; the others and how they differ are in
  `data/versions.csv`.
- The provision word of each law (section, regulation, rule, clause, article) is the column head of its Table of
  Provisions; a law with none uses `clause` (`section` for an Act).
- Changes are credited by the history notes, then by the Table of Amendments; see the README. Nothing is credited
  by guess: a change two laws could explain is `Kind: several-acts`, one nothing explains is `Kind: unexplained`.
- Text normalisation: ligatures (U+FB00-FB04) are spelled out, soft hyphens removed, the dotless i (U+0131) that some
  ligature glyphs extract as is written i, runs of white space collapsed; quotes, dashes and spelling are left as
  printed.

## What the AI did and did not do

The repository was built by Claude Code with Claude Opus 5.5 (`claude-opus-5-5`): it found the source and the API,
checked robots, terms and the Copyright Act, and wrote the scripts. No AI model writes or edits legal text, and no
model runs at fetch, data-build or git-build time.

## What the build produced

- 503 laws (the Constitution, 244 Acts, 258 subsidiary instruments), 914 versions,
  14692 files in the latest versions.
- 631 commits: 503 consolidated, 102 amendment, 14 several-acts,
  11 unexplained, and one documentation commit. In-force dates from 1921-10-15 to 2026-10-02.

## Checks

```sh
git rev-list --merges --count main                                     # 0
git log --format=%B main | tr -cd '\r' | wc -c                         # 0
git log --format='%(trailers:key=In-force,valueonly,separator=)' main  # never increases going back
```

- check_repo.py: bytes: 984 files identical, 1 differ only in white space, 0 mismatches; independent words: 8/8 versions match the raw PDF letter for letter
- test_repo.py: 6/6 passed
- Rebuild: two builds from the same cache on 2026-10-29 gave the same HEAD (see data/verification.json "rebuild_heads")
