# Department for Registration of Persons (drp.gov.lk): completion log

Working document. Each line records something that happened or something still to do.
Updated as the work goes on. Not part of the progress log.

## Status (2026-10-11)

| Step | State |
|---|---|
| Find the English entry page | done: the language cards are JavaScript buttons (`changelang('en')` -> `en/home.php`), so the walk starts at `https://www.drp.gov.lk/en/home.php` |
| Discover pages (depth 2, limit 150) | done: 83 pages found, the list ended before the limit |
| Pick the service-relevant pages | done: 16 added as seeds (URL and agency only) |
| Crawl and save them | done: 16 new pages saved, 8 old pages unchanged, run `1be388aedc92` |
| Read pages with the model | **not started for the 16 new pages**: ready, the two fixes under "Before reading" are in, waiting for you to press Read by sections |
| Review, approve, write to graph | not started for the new pages |
| Completeness check per service | not built yet |

## Pages in scope (16 added)

| Page | Signals | Why it is in |
|---|---|---|
| `nicverification.php` | -D- | NIC information verification service |
| `icao.php` | FD- | Obtaining the ICAO photograph (fee and documents) |
| `oneday_branch.php` | FD- | One-day service: fees and documents |
| `faq.php` | FD- | Answers about fees and documents |
| `divisions.php` | -DP | Divisions and what each handles |
| `divisional_office.php` | -DP | Where and how to apply at a divisional office |
| `downloads.php` | -D- | Index of forms |
| `slu.php` | -D- | e-NIC project |
| `assets/formats/Purawesi Eng.pdf` | -D- | Citizen charter |
| `assets/formats/application.pdf` | FD- | Application form text (large, 35k characters) |
| `assets/downloads/D.R.POP023.pdf` | FD- | Form |
| `assets/formats/0008.pdf` | -D- | Form |
| `assets/formats/minimum-requirement.pdf` | -D- | ICAO studio requirements |
| `assets/formats/studio-app.pdf` | -D- | ICAO studio application |
| `assets/formats/english_translation.pdf` | -D- | English translation form |
| `return_application.php` | --- | Incomplete application return. Blocked by the free check (no fee, document or prerequisite on the page) |

Already read before this log: `normal.php` (34 facts in graph), `other_service.php` (24 in graph, 4 rejected), `GN.php` (4 waiting rows, advice was not to approve).

## Not in scope, and why

- Organisation and branch pages (structure, staff, history, provincial offices, numbering, registration, printing, postal branches, media, RTI, suggestions): they describe the department, not a service someone applies for.
- RTI Act PDFs, the Sinhala RTI PDF, tiny or empty PDFs (11 to 129 characters).
- Gazette PDFs `rules/08-2016_E.pdf`, `2015 english.pdf`, `2017 english.pdf` (signals FDP, 24k to 68k characters): legal rules. **Decision needed**: they may hold the official fee schedule. Not read yet.
- `rules/RPD ACT NO 32 OF 1968.pdf`: could not be read (empty text).
- `front.php`, `home_en.php`: 404.
- 8 PDFs share identical text with another PDF (duplicates).

## Before reading (do first, to avoid wasting tokens)

1. **Give the model the list of services already in the graph** and tell it to attach to one of them when the page is about it. Without this, `GN.php` produced four service shells with only an agency fact.
2. **A service with no fee, document or prerequisite never enters review.**
3. Then read in this order: `oneday_branch`, `icao`, `faq`, `nicverification`, `divisional_office`, `divisions`, `Purawesi Eng.pdf`, `application.pdf`.

## What remains

- [x] Build steps 1 and 2 above (2026-10-11): known services go into the sections prompt; a heading with no fee, document, prerequisite or time is not staged. 221 tests pass
- [ ] Re-read `GN.php` (its 4 rows are still waiting, do not approve them)
- [ ] Read the 15 pages with signals
- [ ] Review the exceptions, approve, write
- [ ] Decide about the gazette PDFs
- [ ] Completeness check: for each DRP service, fee / documents / prerequisites / source present
- [ ] `svc:birth_certificate` has no facts yet: read the RGD birth page (a NIC and passport prerequisite)

## Known limits

- The language choice on the home page is JavaScript, so the walk had to start at `en/home.php` by hand. The rule "pick English" is a human decision here, not found by the crawler.
- Discovery went two link levels from `en/home.php`. Pages linked only from deeper levels, or only reached through JavaScript, would be missed.
- Menu pages already known as seeds (`normal.php`, `GN.php`, `other_service.php`) are skipped by discovery by design.
- Two other seeds were not scraped, and are not being worked around: `police.lk` (blocked by its robots.txt) and `drc.gov.lk` (blocked by anti-bot protection).

## Update 2026-10-11: gazette PDFs added

Seeded and crawled (run `74c09bece800`, 3 NEW, no model used): `rules/08-2016_E.pdf`, `rules/2015 english.pdf`, `rules/2017 english.pdf`.

What they hold (checked by text search only, not read by the model):
- `08-2016_E.pdf`: the Registration of Persons (Amendment) Act No. 8 of 2016. Legal text. The "Rs. 20.00" is the printing price of the publication, not a service fee.
- `2015 english.pdf` and `2017 english.pdf`: gazette regulations. The fees visible by search are for registering a **photographer** (ten thousand rupees; renewal two thousand rupees) and a fee for a certificate on the authenticity of a national identity card. They are not the NIC application fee schedule.

Decision pending: whether to send these three (up to 70k characters each) to the model. Expected yield is small (photographer registration is not one of our target services). Not read yet.

## Update 2026-10-11: 13 of the 15 pages read

Read by sections with the known-services prompt (tokens roughly 40k in, 17k out in total). Read: `oneday_branch`, `icao`, `faq`, `nicverification`, `divisional_office`, `divisions`, `Purawesi Eng.pdf`, `application.pdf`, `D.R.POP023.pdf`, `0008.pdf`, `minimum-requirement.pdf`, `studio-app.pdf`, `english_translation.pdf`. Facts are waiting for review, none approved yet.

- **Not read:** `downloads.php`, `slu.php`. The model returned HTTP 429 (quota exceeded) on `downloads.php`. Re-run after the quota resets.
- **Fixed:** when several parts of a page were about a service already in the graph, they were given numbered ids (`svc:nic_2`, `_3`). They now join the known service. Re-processed `faq.php` (extraction 583 to 613).
- **Mistake and repair:** the re-process script rejected the old rows of `faq.php` before checking that their replacements existed, so 20 facts were wrongly rejected. They were put back to waiting, and the script's own review_log rows were removed. Two rows that duplicate `svc:nic` facts stay rejected.
- `divisions.php`: 3 facts were dropped and nothing was staged (its headings carry no fee, document or prerequisite).
- Scope note: several pages are about **ICAO photograph studio registration** (businesses, not citizens): `svc:icao_studio_*`, `svc:studio_registration*`. Decide whether to keep them in the graph.

## Update 2026-10-11: review done and written

43 approved, 22 rejected with reasons, the rest left waiting. Written to the graph: 31 new, 3 changed, 9 unchanged, none failed. Graph now: 11 services, 2 agencies, 41 documents, 128 current facts, 8 REQUIRES edges.

Rejected, by reason: service shells (4), value not an amount or duration (5), too vague (1), less specific than what the graph holds or only different wording (5), agency spelled differently on the page (2), wrong derived link (3), duplicate (1), form-filling instruction (1).

Left waiting on purpose:
- All ICAO photo-studio services (business registration, not a citizen service): decide the scope.
- Conditional facts that depend on the applicant's case: the relatives' certificates for deceased verification, the Grama Niladhari letter for translation, lost-card documents.
- `surrender_nic_deceased -> requires -> svc:nic`: the person already holds the card, so this is not a "get it first" link. Still in the graph from earlier; to revisit.

## Update 2026-10-11: automatic approval of clean facts

`app/core/graph/autoreview.py`, button "Auto-approve the clean ones" in the review screen (shows what it would do before it does it).

A waiting fact is approved by rule when: its predicate is fee, document, prerequisite, processing time or agency; its service already has an approved fact; no other waiting value competes for the position; it does not replace a different value in the graph; the value is not a blank, label or placeholder; a fee has an amount; a duration looks like one; the quote has no case wording (if, unless, in the event, in lieu, on behalf, not presented); and a derived "requires" link is not about a deceased, lost, surrendered or penalty item.

Held for a person: new services, changed values, free-text eligibility, conflicts, case-dependent wording, doubtful values. Each held fact carries the reason.

Recorded as reviewer `auto-rules` in review_log, and written to the graph with `review: "auto"` on the Fact node (`"human"` otherwise), so automatic facts can be told apart and sampled ("Spot-check 10 auto-approved").

Known hole (seen on the real waiting list): a document that depends on the applicant's relationship (parents' death certificates, a marriage certificate) carries no "if" in its quote, so the rules would let 6 such rows through. The sample check is the safeguard.

## Update 2026-10-11: answering without a model

`python -m app.core.graph.plan svc:passport [--case ordinary] [--json]` and `GET /api/plan?service=svc:passport&case=ordinary` (review app). Walks `REQUIRES` from the graph, orders prerequisites first, lists fees, documents, steps and times with their page and quote, and marks required services that have no facts as INCOMPLETE. No model call.

Known limits: (1) the case filter only narrows the requested service, prerequisite services show all of their cases; (2) a fee or time whose variant is not one of the document case names (for example a lost-passport fine) is kept, not removed; (3) the shared `Plan` contract in `shared/helaguide_common/contracts.py` requires a single `fee` per step, which cannot say "fee not stated" or hold several fees by case, so `/v1/plan` is not wired to this yet. That is a change to a shared contract and needs the team.

## Update 2026-10-11: pages nested by where they were found

`/tree` in the review app. Each page sits under the page it was found on, with its state: not saved, saved (to read / nothing to read), read, changed since read, in graph (with fact count and services found). Discovery now records the parent of every page it finds in `research/data/crawl/tree.json`, merged across runs. The two discovery runs already done (Immigration `pages_e.php?id=8`, DRP `en/home.php`) were imported into it.

At the time of writing: 117 pages known, 27 saved, 18 read, 12 with facts in the graph. 25 pages under the Immigration passport page and 60 or so DRP pages are known but not saved.

## Update 2026-10-11: contact details and form links

`python -m app.core.graph.profile --agency "..." --contact <url> --downloads <url> [--write]`. Read by plain parsing, no model, no fact review. Each contact keeps the page and the line it came from; no personal names are kept (offices and roles only). The profile is also saved to `research/data/agency_profile/department_for_registration_of_persons.json`.

Written to the graph for DRP: 78 contact items (call-centre numbers and hours, fax, email, head-office address, branch phone/fax/email, four provincial offices) as `(Agency)-[:HAS_CONTACT]->(Contact)`, and 28 form and act links from `downloads.php` as `(Agency)-[:PUBLISHES_FORM]->(Form)`. Form files themselves were not read.

Notes: the Central provincial office (Nuwara Eliya) is not in the contact table, so it is missing; its page `nuwaraeliya.php` is unsaved. One email is spelled `ac_vavuniya@grp.lk` on the page and kept as written. Two rows on `downloads.php` link back to the page itself and were skipped. Contact data has no versions yet, so a change on the page needs the command run again.

## Update 2026-10-11: scope changed to a knowledge base

Decision (Malin): the aim is a knowledge base for questions of any kind (a phone number, an address, an office), not only services. Pages are kept unless they are clearly irrelevant: vacancies, tenders, greetings and messages, photo galleries, mission, vision and goals, history, past commissioners, staff lists (personal names), the Sinhala and Tamil copies, and empty or tiny PDFs.

Done for DRP: 32 more pages saved (branch pages, the five provincial offices, RTI pages and English RTI PDFs, forms, notice to the public). Overview was left out because it holds the mission and vision. Cut into 493 chunks (`c2.chunks`, migration `006_c2_chunks.sql`) with the page, heading and time they came from. Search: `python -m app.core.knowledge.chunks "question"` and `GET /api/search?q=`. Contacts are looked up exactly first, then the saved text by words.

Honest limits: this is word search, not meaning search. A question phrased with different words than the page ("where is the Galle office" for a page that says "Southern Province") may miss, and the OR fallback is noisy. The next step is embeddings, which need a model and cost tokens. Chunks are replaced when a page changes and are not versioned. Chunks are not yet linked to graph entities (service, office).

## Update 2026-10-11: DRP closed out (links only for documents)

- Discovery fixed: known seed pages now have their links read, the exclusion file is applied, and the depth limit was raised to 6. Found 48 more pages, mostly form and letter PDFs linked from `normal.php`, `GN.php` and `other_service.php`, including `fees-english.pdf` ("Notice on revision of fees charged").
- PDFs are linked, not read (Malin's decision): the graph now has 53 `PUBLISHES_FORM` links for DRP (forms, guides, the citizen charter, Acts), each with its page, and the files are not parsed.
- Agency spelling: the writer now maps a name that has the same words as an existing agency to that agency, so `svc:nic_number_verification` got its agency link without creating a second agency node. Fact 2440 was re-opened (its earlier rejection stays in the log) and approved.
- Central provincial office: contact added from `nuwaraeliya.php` (0115226175). 79 contact items now.
- `Run_Monthly_Refresh.bat`: crawl pass, chunk, and a discovery listing, logged to `crawl/refresh_log.txt`. New pages are listed, not added, and reading changed pages stays a decision in the review screen. To schedule: Windows Task Scheduler, monthly.

Still open for DRP: 6 case-dependent facts waiting; branches are contacts only (no unit nodes); `fees-english.pdf` and the other PDFs are not read, so the revised fee amounts are not in the graph; depth was 6 and the site ended before the page cap, so nothing more was found at that depth.

## Update 2026-10-11: completeness check of the DRP site

- `robots.txt` and `sitemap.xml` do not exist on drp.gov.lk (HTTP 404), so there is no list of hidden pages to add. Nothing is disallowed.
- Every link found on the 36 saved DRP pages was checked against the tree. 77 same-site links were not added: about 70 are the Sinhala and Tamil copies of English pages, 3 are the main pages already seeded under the other host spelling, `procument orgin.php` (Procurement) and `Circular English.pdf` are excluded by rule, and two are PNG specimens.
- One external link found: an online NIC verification portal (`http://203.115.11.154:8083/nic-portal/`, from `nicverification.php`). Added as a link (section `online`), not crawled.
- 54 form and document links, 79 contact items, 8 services with about 100 facts, 6 facts waiting.
