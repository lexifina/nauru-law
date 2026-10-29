# Reproducing this repository

Built from RONLAW data retrieved on {{TODAY}} by the scripts in `tools/build/` (copied there as run).

| Script | sha256 |
| --- | --- |
| fetch.py | `{{SHA_FETCH_PY}}` |
| parse.py | `{{SHA_PARSE_PY}}` |
| parse_all.py | `{{SHA_PARSE_ALL_PY}}` |
| build.py | `{{SHA_BUILD_PY}}` |
| docs.py | `{{SHA_DOCS_PY}}` |
| check_repo.py | `{{SHA_CHECK_REPO_PY}}` |
| test_repo.py | `{{SHA_TEST_REPO_PY}}` |

Tools: Python 3.12, PyMuPDF (`pymupdf`), git 2.x, curl (Windows). The PDFs' sha256 are in
[`data/pdf-sha256.tsv`](data/pdf-sha256.tsv); every request made is in [`data/fetch-log.jsonl`](data/fetch-log.jsonl).

## Steps

```sh
# 1. RONLAW's index (one request, 33 MB JSON) and every PDF in the acts, laws and constitution categories
#    ({{PDFS_ALL}} files), at most 4 requests at a time.
python fetch.py --index
# 2. Parse every PDF once (cache/parsed/, keyed by the PDF's and parse.py's sha256), then build.
#    --today is the retrieval day; it dates the documentation commit.
python -W ignore parse_all.py
python -W ignore build.py ../nauru-law --today {{TODAY}}
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

**Fetch rate:** {{REQUESTS}} requests in all ({{PDFS}} PDF downloads; the rest are the index and checks), at most 4
at a time, with `curl --compressed` and a browser User-Agent. Every request was answered 200. There is
no bulk download; the index API is the app's own.

## Decisions made by hand

- Scope: every PDF in RONLAW's `acts`, `laws` (subsidiary legislation) and `constitution` categories, except files
  named as amending, appropriation or supplementary Acts without a service suffix (as made, never reprints). A PDF is
  used only if it is a reprint: it has a Table of Amendments ({{NOT_REPRINTS}} PDFs have none and are listed in
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

- {{LAWS}} laws (the Constitution, {{ACTS}} Acts, {{SUBSIDIARY}} subsidiary instruments), {{VERSIONS}} versions,
  {{FILES}} files in the latest versions.
- {{COMMITS}} commits: {{CONSOLIDATED}} consolidated, {{AMENDMENT}} amendment, {{SEVERAL}} several-acts,
  {{UNEXPLAINED}} unexplained, and one documentation commit. In-force dates from {{FIRST}} to {{LAST}}.

## Checks

```sh
git rev-list --merges --count main                                     # 0
git log --format=%B main | tr -cd '\r' | wc -c                         # 0
git log --format='%(trailers:key=In-force,valueonly,separator=)' main  # never increases going back
```

- check_repo.py: {{CHECK}}
- test_repo.py: {{SMOKE}}
- Rebuild: {{REBUILD}}
