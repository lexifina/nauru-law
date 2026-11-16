# Tools

The scripts behind this Nauru-only run of global-law's vulnerability detectors. They run inside a copy of
[global-law/vulnerabilities/scripts](https://github.com/lexifina/global-law/tree/main/vulnerabilities/scripts) (Python 3.11+,
`pip install duckdb pyarrow`), with a bare clone of this repository at `sources/corpus/nauru-law.git`, a blobless bare
clone of global-law at `sources/global-law.git`, and a `pins.json` that names only nauru-law, its commit, its language
(`en`) and its code (`NR`). `build_vulns.py`, `flags_chart.py`, `late_ext_select.py`, `late_ext_rebut.py` and
`config.json` sit three folders up, next to the copy of global-law (`gl/vulnerabilities/scripts/`).

| Script | What it does |
| --- | --- |
| `run.sh` | Indexes the history and texts, adds this repository's history rows, and runs the detectors (`bash run.sh <shards>`; run here with 6) |
| `add_root.py` | Builds the history rows from this repository's own commits (global-law replays it only up to an earlier commit), so the history detectors read every change; changed for this repository (below) |
| `run_triage.sh` | The model review: the 40 strongest flags per category, the 40 strongest lapsed time limits in law texts, and the empty periods (none here) |
| `late_ext_select.py` | Chooses the empty periods for global-law's review of that category (there were none here) |
| `late_ext_rebut.py` | Adds the second, arguing-against pass to the empty-period review, as `triage.py` does for the other categories |
| `build_vulns.py` | Builds `data/flags.csv`, `data/reviewed.csv` and `data/by_category.csv` from the findings and the model review |
| `flags_chart.py` | Draws the chart at the top of the README, in English, light and dark |
| `config.json` | The repository, its language (English), the category names, the files and folders that are not law, and the chart's labels |
| `patch_detectors.py` | Fixes blind spots found in runs on several country repositories in the copy of global-law's scripts (`python -X utf8 patch_detectors.py <scripts dir>`; a fix already in place is skipped) |
| `patch_en.py`, `patch_en_et.py` | The same for English text in the search for references to repealed placeholders (found by the Bhutan and Ethiopia runs): "vacated" only as a marker, not "vacation" or "null and void", "shall be deleted" not as the mark of a deleted provision, and a provision that repeals another section or a whole earlier law not as a placeholder |
| `patch_detectors_vi.py`, `patch_es.py`, `patch_ca.py`, `patch_de.py`, `patch_co.py`, `patch_sv.py`, `patch_pt.py`, `patch_ru.py`, `patch_r18.py`, `patch_xk.py`, `patch_mo.py`, `patch_lu.py`, `patch_li.py`, `patch_mx.py`, `patch_mn.py`, `patch_mt.py` | The same for other languages and jurisdictions (found by other runs); they change nothing in this repository's English text, but `apply_patches.py` and `redo.py` run them on every repository. `patch_mn.py` and `patch_mt.py` were applied after the first run and left every count as it was |
| `patch_en_nr.py` | Written for this run (below): RONLAW's history notes, "a repealed Act", and days written "1st" or "31st" |
| `apply_patches.py` | Runs the patches above once each, in a fixed order (`patch_en_nr.py` last), and records them in the scripts folder (`.kit_patches.json`) |
| `map_moved.py` | For a repository that moved its act folders (`data/paths.json`), rewrites the paths in the history table to each act's folder since the move; this repository has not moved its folders, so it does nothing here |
| `redo.py` | Runs the patches, then again only the scans and detectors the fixes change, the model review of lapsed time limits, references to deleted provisions and empty periods, and the build (`python -X utf8 redo.py <run folder> [--keep-reviews] [--full]`; `--keep-reviews` keeps every review already made and reviews only new strong flags; `--full` runs every step again through `run.sh`, sends every category to the model and keeps every review already made; `EMBED_FONTS` names the script that embeds the chart's fonts); not needed here, as the steps were re-run by hand after each fix |

The model review needs `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` and `LLM_AUTH` set for an OpenAI-compatible Responses API.
It was run as `bash run_triage.sh '^(data|tools|vulnerabilities)/'` (the root files, `data/` and `tools/` are not law; every
flag is in `acts/`). It reviewed the five lapsed time limits found first, and, after the fix for ordinal days, the five
new ones; the first five reviews were kept.

Changes made for this repository:

- `add_root.py`: this repository marks each single current text and the first versions of the Constitution and the Public
  Service Act `Kind: consolidated` (334 commits), and two changes to the Public Service Act `Kind: several-acts` and
  `Kind: unexplained`; the kit's `add_root.py` counted only the eight amending Acts (`Kind: amendment`) as law, so the
  scans read only the files those eight changed. All three kinds now count as law: 344 commits of kind `law`. The three
  `Kind: documentation` commits keep their kind and are left out.
- `patch_en_nr.py`, in the copy of global-law's scripts:
  - `ingest/refscan.py`: RONLAW's reprints print a history note under a provision ("[s 18 (formerly section 15) renum No
    25 of 1967 s 5 and Sch 3, opn 29 Dec 1967]", "[s 50 omitted by the Law Revision Commission under powers authorised by
    Act 10 of 2019]"), and the former number in it was read as a reference to the provision that has that number now. A
    line that is only such a note (in square brackets, ending with the operative day "opn <day> <month> <year>" or naming
    the Law Revision Commission) is no longer read for references. References to repealed placeholders went from 3 to 2
    and dead fines from 1 to 0 (section 18 of the Public Health Act 1925 citing its own former number, 15);
  - `detectors/placeholder_ref.py`: "repealed" after "a", "any" or "the" ("A reference to the Administrator or Registrar
    under a repealed Act …") describes another law, not the mark of a repealed provision. References to repealed
    placeholders went from 2 to 1 (section 86 of the Vessel Registration Act 2024, which amends section 80(2) of the Ports
    and Navigation Act 2019, read as citing its own section 80);
  - `ingest/textscan.py`: a day with an ordinal suffix ("until 1st January 1978") and a comma between the month and the
    year ("until 31st October, 1963") were not read as dates. A day may now end in st, nd, rd or th, and a comma may stand
    before the year. Lapsed time limits went from 5 to 10.

  Each change carries a marker (`NR_HISTORY_NOTE`, `NR_REPEALED_ADJ`, `NR_ORDINAL_DATE`) and is skipped where the marker
  is already there.
- `config.json` counts as not law `data/`, `tools/`, `vulnerabilities/` and the root files (`README.md`, `REPRODUCE.md`,
  `SOURCES.md`, `LICENSE`, `corpus.json`).
