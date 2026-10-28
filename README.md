# Nauru law, change by change

Two laws of the Republic of Nauru (Naoero) as a git repository: the **Constitution of Nauru 1968** (since 12 May 2026
the Constitution of Naoero) and the **Public Service Act 2016**. The source is the official consolidated reprints of
the Laws of the Republic of Nauru on [RONLAW](https://ronlaw.gov.nr), Nauru's online legal database, run by the
Department of Justice and Border Control. There is one file per article, section or schedule. Each change is a commit
credited to the Act that made it, dated the day it became operative, at noon Nauru time. The text is English.

The record runs from 2022-06-08 to 2026-07-20 in 13 commits, built from 5 reprints of the
Constitution and 3 of the Public Service Act.

## The questions, as git commands

| Question | Command |
| --- | --- |
| What did Article 19 of the Constitution say on 1 April 2026? | `python tools/in_force_on.py 2026-04-01 constitution article/19` |
| The whole Constitution on a date | `python tools/in_force_on.py 2026-01-01 constitution` |
| A section of the Public Service Act on a date | `python tools/in_force_on.py 2025-09-01 public-service-act-2016 section/94A` |
| Which Act last changed each line of an article? | `git blame constitution/article/19.md` |
| Every change to an article, with the Act behind it | `git log -p constitution/article/19.md` |
| The words that changed, not whole lines | `git log -p --word-diff constitution/article/19.md` |
| Everything one Act changed, across both laws | `git log --author='No 21' --stat` |
| Every Act that changed the Public Service Act, in order | `git log --format='%(trailers:key=In-force,valueonly,separator=) %an' -- public-service-act-2016` |
| Changes no single Act is credited with | `git log --format='%h %s' --grep='Kind: unexplained' --grep='Kind: several-acts'` |
| The reprints used, and the Table of Amendments | [`data/versions.csv`](data/versions.csv), [`data/amendments.csv`](data/amendments.csv) |

In PowerShell, a `$(...)` revision written straight before `:path` in git show splits into two arguments. Use `$r = git rev-list -1 main; git show "$($r):constitution/article/19.md"`.
A raw-git date query must name the end of the day in Nauru time, e.g. `git rev-list -1 --before="2026-04-01T23:59:59+12:00" main`;
a bare date takes the current time of day. `tools/in_force_on.py` reads the `In-force:` trailer and avoids this.

Each file starts with any Part or Division headings above the provision (`## PART III — THE PRESIDENT AND THE
EXECUTIVE`), then the provision's heading as printed (`# Article 19 Appointment of Ministers and Vice President`, or
`# 94A Secondment of a permanent employee`), then one line per clause, paragraph or definition. The reprint's history
notes stay where it prints them, in brackets: `[Art 21 subst Act 18 of 2026 s 6, opn 16 Apr 2026]` means Article 21
was substituted by section 6 of Act 18 of 2026, operative 16 April 2026.

## The dates, and which one we use

Each RONLAW reprint is consolidated to a date (the latest commencement in its Table of Amendments). Between two
reprints, **each change is dated by the operative date its history note prints** ("opn 16 Apr 2026"), the day the
changed text took effect. Where a changed provision has no new note, the commencement the Table of Amendments gives
for the one Act newly listed is used. Commits are at noon Nauru time (UTC+12; Nauru has no summer time). Under the
Interpretation Act 2011, s 21, a provision commences at the beginning of its day, so any time that day is correct.

The Acts are numbered by the year they were certified: the Constitution (Amendment) Act 2025 No 15, certified on
31 March 2026, is cited in the notes as "Act 15 of 2026". Each commit gives that citation as `Cited-as:`.

The record starts at each act's **earliest reprint on RONLAW**: the Constitution as consolidated to
8 June 2022, and the Public Service Act as consolidated to 10 June 2022. That first version is a commit labelled
`Kind: consolidated` by RONLAW. It has the whole text as it then stood, with every history note, so the earlier history
(from 1968 and 2016) is listed but is not separate commits.

## What "author" means

The author of a commit is the Act that made the change, at an address that cannot exist:
`Constitution (Amendment) Act 2026 No 18 <act-2026-18@ronlaw-gov-nr.invalid>`. So `git blame` names, for each line,
the Act that last wrote it. One commit holds everything one Act changed on one day, across both laws (`Affecting:`).

A change is credited by the evidence in the reprint itself (`Evidence:` trailer):
1. **note**: the changed provision's history note gains a citation of exactly one Act, operative after the previous
   reprint (73 files);
2. **table**: no new note, but exactly one Act was added to the Table of Amendments between the two reprints
   (1 files).

Where the notes of one provision name more than one new Act, the reprint shows only the final wording, so it is
committed on the latest operative date by RONLAW, labelled `Kind: several-acts`, with one `Candidate:` trailer per
Act and credit to none (1 commit(s)). A change with no evidence is RONLAW's, labelled `Kind: unexplained`
and dated by the reprint (1 commit(s)); for example, section 37A of the Public Service Act appears in
the reprint consolidated to 20 July 2026 with no history note.

In total: 2 consolidated baselines, 8 amendment commits by 8 Acts,
1 several-acts and 1 unexplained commit(s), and one documentation commit.

## What it does not show

- Text before each act's earliest reprint on RONLAW, except as the history notes list it.
- Intermediate wording between two reprints where one provision was changed by more than one Act.
- Commencement of parts of an Act later than the reprint shows (the Table of Amendments prints these, e.g.
  "s 5: 12 May 2026"; see `data/amendments.csv`), and savings or transitional rules in the amending Acts.
- The subsidiary legislation printed in the same reprint as the Public Service Act (regulations, rules, notices).
- The Tables of Provisions and Tables of Amendments themselves (kept as data, not as law files), running heads, and
  page furniture.
- Words a later reprint reproduces unchanged under a new number; renumbering shows as a deletion and an insertion.
- `git blame` credits whole lines: a clause written by two Acts is credited to the later one. Use `--word-diff`.

This is a research aid. RONLAW's reprints are the Government's consolidations, but the certified Acts and the
Government Gazette prevail.

## How it is checked

- `tools/build/check_repo.py`: every reprint's files, rebuilt from the PDF, equal the files in git on its
  consolidation date, byte for byte; and an independent letters-and-digits check compares each version in git with
  the raw words of the PDF, read without the build's parser. Result: bytes: 984 files identical, 1 differ only in white space, 0 mismatches; independent words: 8/8 versions match the raw PDF letter for letter
- `tools/build/test_repo.py`: blame, the on-date tool across amendments, `log --follow` order, trailers, authors and
  every command in the table above. Result: 6/6 passed
- Determinism: two builds from the same cache on 2026-10-29 gave the same HEAD (see data/verification.json "rebuild_heads")

## How it is built

`fetch.py` reads RONLAW's index (its own JSON API, one request) and downloads each reprint of the two acts, one
request at a time. `parse.py` reads each PDF by its typography: 12pt bold provision headings, Part and Division
headings, 10pt text and 8pt history notes. `build.py` compares consecutive reprints file by file, credits each change
as above, and writes the history with one `git fast-import`. No AI model takes part in building or checking it. See
[`REPRODUCE.md`](REPRODUCE.md) and [`SOURCES.md`](SOURCES.md).

## Licence

Source: RONLAW, Republic of Nauru Law, the Department of Justice and Border Control, Government of Nauru
(ronlaw.gov.nr). The site footer reads "Copyright 2023 — Ronlaw. All rights reserved." The texts themselves are not
protected: the Copyright Act 2019 (Nauru), section 15(4), says "The Republic has no copyright over nor there exists
any copyright in the following works: ... (b) any Act as defined in the Interpretation Act 2011; (c) any regulations",
and section 19(b) excludes "any official text of a legislative, administrative or legal nature". The texts were split
into files and arranged as commits; the wording was not changed. Lexifina's own contributions (the tools, the
arrangement and the commit messages) are CC0. See [`LICENSE`](LICENSE).
