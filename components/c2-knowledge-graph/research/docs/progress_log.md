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
