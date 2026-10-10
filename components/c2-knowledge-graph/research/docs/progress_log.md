# C2 progress log

One dated entry per working day: what was done, the number, what is blocked.
Never edit past entries; add a new one.

## 2026-10-04 (Sunday)

**Done**

- Docker stack running locally: all components report ok, stub `/v1/guidance` returns the two
  sample steps, three Neo4j constraints applied (`service_id`, `agency_id`, `page_url`).
- Plan for PP2 (70%) written: `PLAN.md`.
- Ported the research prototype's change monitor into `service/app/core/acquisition/` as
  `fingerprint.py` (noise stripping, text digest, collapsed DOM signature, classifier), and
  split the rest into `fetch.py`, `robots.py`, `ratelimit.py`, `store.py`, `seeds.py`,
  `monitor.py`, `report.py` and a CLI.
- Tests: 53 passing, including one through real Crawl4AI 0.9.4 against a local HTTP server:
  NEW, then UNCHANGED when only a hit counter moved, then CONTENT_CHANGED when a fee changed
  with identical length.
- Seed registry started: 6 URLs, 1 verified.

**Not yet measured (do not claim)**

- Nothing has run against a live `.gov.lk` page. The tests above use a local server.
- No classification accuracy number yet; the labelled test set is still to be built from real
  pages.
- Not yet checked: `pytest` and the dev loop on the Windows machine (Python 3.11 or newer).

**Blocked / open**

- Seed list needs about 19 more service pages, each opened in a browser first.
- Decide whether PDF-hosted content (RGD forms) is in or out of scope.
- `infra/postgres` run-log tables are not written yet (planned for Wed 7 Oct).

## 2026-10-10 (Saturday): backend and database

**Done**

- Archived page text now saved as `.md`.
- PDF acquisition added: download, text layer to Markdown, archived as `.pdf` and `.md`. One real
  PDF (passport application form) checked: English labels readable, Sinhala and Tamil text
  garbled. No OCR for now.
- PostgreSQL `c2` schema applied (`002_c2.sql`): `sources`, `pages`, `crawl_runs`,
  `page_results`. The run log writes to Postgres beside the JSONL files (`--db`), and
  `page_results.file_path` points at each archived `.md`.
- Link discovery and scoring (`--discover`), ported from the research prototype. Found a false
  positive: site menus made every page score "documents", so menu lines are now stripped
  before scoring; the prerequisite pattern was narrowed.
- 82 tests pass.

**Live runs today**

- 6 seeds crawled: 4 fetched (3 thin homepages and the passport page), `police.lk` blocked by
  robots.txt, `drc.gov.lk` blocked by anti-bot protection in HTTP mode.
- Discovery from the passport page: 25 candidate pages. Their stored scores predate the menu fix.

**Not yet measured (do not claim)**

- No classification accuracy on real pages. Second crawl and labelled set skipped for now.
- No extraction run, no token numbers, Neo4j still empty.
- Seeds: 1 of about 25 verified.

**Next**

- Re-run discovery with corrected scoring; grow and verify seeds.
- Ontology models, extraction, staged facts, then the review gate and Neo4j writer.
