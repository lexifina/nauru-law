# Nauru law, change by change

The laws of the Republic of Nauru (Naoero) as a git repository: the **Constitution**, **244 Acts** and
**258 subsidiary instruments** (regulations, rules, orders, notices), every law that RONLAW, Nauru's online
legal database run by the Department of Justice and Border Control, publishes as a consolidated reprint of the Laws of
the Republic of Nauru. There is one file per article, section, regulation, rule, clause or schedule. Each change is a
commit credited to the law that made it, dated the day it became operative, at noon Nauru time. The text is English.

The record runs from 1921-10-15 to 2026-10-02 in 631 commits, built from 914 dated versions in
672 reprint PDFs; 315 of the 503 laws have more than one version. The list of laws, with their
paths, is [`data/laws.csv`](data/laws.csv).

## The questions, as git commands

| Question | Command |
| --- | --- |
| What did Article 19 of the Constitution say on 1 April 2026? | `python tools/in_force_on.py 2026-04-01 constitution article/19` |
| The whole Constitution on a date | `python tools/in_force_on.py 2026-01-01 constitution` |
| A section of an Act on a date | `python tools/in_force_on.py 2025-09-01 acts/public-service-act-2016 section/94A` |
| A regulation on a date | `python tools/in_force_on.py 2026-06-01 subsidiary/public-service-disciplinary-regulations-2020 regulation/3` |
| Which law last changed each line of an article? | `git blame constitution/article/19.md` |
| Every change to an article, with the law behind it | `git log -p constitution/article/19.md` |
| The words that changed, not whole lines | `git log -p --word-diff constitution/article/19.md` |
| Everything one Act changed, across all laws | `git log --author='Act 2026 No 21' --stat --format='%h %s'` |
| Every law that changed the Crimes Act, in order | `git log --format='%(trailers:key=In-force,valueonly,separator=) %an' -- acts/crimes-act-2016` |
| Changes no single law is credited with | `git log --format='%h %s' --grep='Kind: unexplained' --grep='Kind: several-acts'` |
| The laws, the reprints used, and their Tables of Amendments | [`data/laws.csv`](data/laws.csv), [`data/versions.csv`](data/versions.csv), [`data/amendments.csv`](data/amendments.csv) |

In PowerShell, a `$(...)` revision written straight before `:path` in git show splits into two arguments. Use `$r = git rev-list -1 main; git show "$($r):constitution/article/19.md"`.
A raw-git date query must name the end of the day in Nauru time, e.g. `git rev-list -1 --before="2026-04-01T23:59:59+12:00" main`;
a bare date takes the current time of day. `tools/in_force_on.py` reads the `In-force:` trailer and avoids this.

## The layout

- `constitution/` (`article/19.md`, `schedule/...`), `acts/<title>/` (`section/94A.md`), `subsidiary/<title>/`
  (`regulation/3.md`, `rule/...`, `clause/...`): the folder name is the law's title in lower case, Naoero written
  Nauru, cut at 90 characters (`data/laws.csv` gives the full title). A subsidiary instrument printed both in its
  Act's reprint and on its own is one law here.
- `preamble.md`: the text before the first provision (long title, enacting words, or the whole text of a short
  notice or order that has no numbered provisions).
- Each file starts with any Part or Division headings above the provision (`## PART III — THE PRESIDENT AND THE
  EXECUTIVE`), then the provision's heading as printed (`# Article 19 Appointment of Ministers and Vice President`,
  or `# 94A Secondment of a permanent employee`), then one line per clause, paragraph or definition. The reprint's
  history notes stay where it prints them, in brackets: `[Art 21 subst Act 18 of 2026 s 6, opn 16 Apr 2026]` means
  Article 21 was substituted by section 6 of Act 18 of 2026, operative 16 April 2026.

## The dates, and which one we use

Each RONLAW reprint of a law is consolidated to a date (the latest commencement in its Table of Amendments). Between
two reprints, **each change is dated by the operative date its history note prints** ("opn 16 Apr 2026"), the day the
changed text took effect. Where a changed provision has no new note, the commencement the Table of Amendments gives
for the one law newly listed is used. Commits are at noon Nauru time (UTC+12; Nauru has no summer time). Under the
Interpretation Act 2011, s 21, a provision commences at the beginning of its day, so any time that day is correct.
Git cannot date a commit before 1970, so the few reprints consolidated to earlier days are dated 1 January 1970 (one
second apart, in order) and keep their real day in `In-force:`.

Acts are numbered by the year they were certified: the Constitution (Amendment) Act 2025 No 15, certified on
31 March 2026, is cited in the notes as "Act 15 of 2026". Subsidiary legislation is cited by its SL number ("SL 7 of
2023"). Each commit gives the citation as `Cited-as:`.

The record starts at each law's **earliest reprint on RONLAW** (for most laws the 2021 revision under the Revised
Written Laws Act 2021; the Constitution from 2022-06-08). That first version is a commit labelled
`Kind: consolidated` by RONLAW. It has the whole text as it then stood, with every history note, so the earlier
history is listed but is not separate commits.

## What "author" means

The author of a commit is the law that made the change, at an address that cannot exist:
`Constitution (Amendment) Act 2026 No 18 <act-2026-18@ronlaw-gov-nr.invalid>`. So `git blame` names, for each line,
the law that last wrote it. One commit holds everything one law changed on one day, across all laws (`Affecting:`).

A change is credited by the evidence in the reprint itself (`Evidence:` trailer):
1. **note**: the changed provision's history note gains a citation of exactly one law, operative after the previous
   reprint (1718 files);
2. **table**: no new note, but exactly one law was added to the Table of Amendments between the two reprints
   (78 files).

Where the notes of one provision name more than one new law, the reprint shows only the final wording, so it is
committed on the latest operative date by RONLAW, labelled `Kind: several-acts`, with one `Candidate:` trailer per
law and credit to none (14 commit(s)). A change with no evidence is RONLAW's, labelled `Kind: unexplained`
and dated by the reprint (11 commit(s)).

In total: 503 consolidated baselines, 102 amendment commits by 97 laws,
14 several-acts and 11 unexplained commit(s), and one documentation commit.

## What it does not show

- Laws with no reprint on RONLAW: 368 of the 1461 PDFs fetched are Acts or instruments as made
  (no Table of Amendments), and are listed in `data/versions.csv` but not used.
- Text before each law's earliest reprint on RONLAW, except as the history notes list it.
- Repeal or expiry: a law stays as its last reprint prints it. A law whose title changed between reprints (for
  example "Nauruan" to "Naoero citizen" in 2026) may appear under both titles.
- Intermediate wording between two reprints where one provision was changed by more than one law.
- Commencement of parts of a law later than the reprint shows (the Table of Amendments prints these, e.g.
  "s 5: 12 May 2026"; see `data/amendments.csv`), and savings or transitional rules in the amending laws.
- The Tables of Contents, Provisions and Amendments themselves (kept as data, not as law files), running heads, and
  page furniture. Tables and forms in schedules are kept as their words, one printed line per line, not as tables.
- Words a later reprint reproduces unchanged under a new number; renumbering shows as a deletion and an insertion.
- `git blame` credits whole lines: a clause written by two laws is credited to the later one. Use `--word-diff`.

This is a research aid. RONLAW's reprints are the Government's consolidations, but the certified Acts, the notified
subsidiary legislation and the Government Gazette prevail.

## How it is checked

- `tools/build/check_repo.py`: every reprint's files, rebuilt from the PDF, equal the files in git on its
  consolidation date, byte for byte; and an independent letters-and-digits check compares each version in git with
  the raw words of the PDF, read without the build's parser. Result: bytes: 984 files identical, 1 differ only in white space, 0 mismatches; independent words: 8/8 versions match the raw PDF letter for letter
- `tools/build/test_repo.py`: blame, the on-date tool across amendments, `log --follow` order, trailers, authors and
  every command in the table above. Result: 6/6 passed
- Determinism: two builds from the same cache on 2026-10-29 gave the same HEAD (see data/verification.json "rebuild_heads")

## How it is built

`fetch.py` reads RONLAW's index (its own JSON API, one request) and downloads every PDF in its Acts, subsidiary
legislation and Constitution categories except files named as amending, appropriation or supplementary Acts as made.
`parse.py` reads each PDF by its typography: the Table of Contents (one reprint can hold an Act and its subsidiary
legislation), each instrument's Table of Amendments, 12pt bold provision headings, Part and Division headings, 10pt
text and 8pt history notes. `build.py` compares consecutive reprints of each law file by file, credits each change as
above, and writes the history with one `git fast-import`. No AI model takes part in building or checking it. See
[`REPRODUCE.md`](REPRODUCE.md) and [`SOURCES.md`](SOURCES.md).

## Licence

Source: RONLAW, Republic of Nauru Law, the Department of Justice and Border Control, Government of Nauru
(ronlaw.gov.nr). The site footer reads "Copyright 2023 — Ronlaw. All rights reserved." The texts themselves are not
protected: the Copyright Act 2019 (Nauru), section 15(4), says "The Republic has no copyright over nor there exists
any copyright in the following works: ... (b) any Act as defined in the Interpretation Act 2011; (c) any regulations;
(d) any bylaw", and section 19(b) excludes "any official text of a legislative, administrative or legal nature". The
texts were split into files and arranged as commits; the wording was not changed. Lexifina's own contributions (the
tools, the arrangement and the commit messages) are CC0. See [`LICENSE`](LICENSE).
