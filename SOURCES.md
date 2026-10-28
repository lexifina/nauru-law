# Sources and legal basis

## Source

**RONLAW, Nauru's Online Legal Database** (https://ronlaw.gov.nr), "a project of the Nauru Government, through the
Department of Justice and Border Control". It holds the Laws of the Republic of Nauru as consolidated reprints
("Service N"), each with a Table of Contents, Table of Provisions, Table of Amendments and history notes, plus the
as-made Acts, bills, gazettes and court decisions.

- The app reads an Elasticsearch index through `https://ronlaw.gov.nr/api/pdf/...`; `related/<docId>` returns every
  indexed record (74,824 rows). PDFs are served at `https://ronlaw.gov.nr/assets/docs/<category>/<year>/<file>.pdf`.
- Reprints used, with sha256: [`data/versions.csv`](data/versions.csv) and [`data/pdf-sha256.tsv`](data/pdf-sha256.tsv).
- Not used: "Constitution of The Repulbic of Nauru.pdf" (twice; a 41-page Word-made copy with no Table of
  Amendments, service stamps or history notes) and "Public Service Act 2016.pdf" (the Act as made in 2016, a
  different template; the history before the 2022 reprint is kept only as the reprint's notes).

## Checks before fetching (2026-10-28)

- robots.txt: `https://ronlaw.gov.nr/robots.txt` answers 200 with the app's HTML page (the single-page app serves
  every unknown path), so there is no robots.txt and no rule for ClaudeBot, Claude-Web, anthropic-ai or GPTBot.
  `www.ronlaw.gov.nr` does not resolve.
- Terms: the site has About, Help, Privacy Policy and Feedback pages and no terms of use. Nothing forbids automated
  access or reuse. The footer reads "Copyright 2023 — Ronlaw. All rights reserved. Developed & Maintain by Digitity".

## Legal basis for reuse

Copyright Act 2019 (Nauru), No 17, as reprinted on RONLAW (service 6):

- section 15(4): "The Republic has no copyright over nor there exists any copyright in the following works: (a) any
  Bill introduced into the Parliament; (b) any Act as defined in the Interpretation Act 2011; (c) any regulations;
  (d) any bylaw; (e) the Hansard reports; and (f) judgments of any court or tribunal."
- section 19(b): matters not protected include "any official text of a legislative, administrative or legal nature,
  as well as any official translation thereof".

Section 15(3)(a) gives the Republic a 25-year copyright in "a typographical arrangement of a published edition"; this
repository does not reproduce the reprints' typography or page layout, only the words, in its own arrangement.

## Default reach

Interpretation Act 2011 (Nauru), as reprinted on RONLAW: section 22(3), "A written law shall not be taken to provide
for the law (or another law) to commence retrospectively unless the law clearly indicates that it commences
retrospectively"; section 28(1), a repeal or amendment does not "(b) affect the previous operation of the repealed or
amended law, or anything done, begun or suffered under the repealed or amended law; (c) affect an existing right,
privilege, obligation or liability acquired, accrued or incurred under the repealed or amended law"; section 21, a
provision commences "at the beginning of the day".
