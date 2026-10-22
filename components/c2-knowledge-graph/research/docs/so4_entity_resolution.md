# SO4: entity resolution precision and recall

Checked 18 October 2026, against the real, live graph — not a constructed set, since every
raw surface form here is a genuine value a real government page actually used.

## Agency-level resolution (the built mechanism: `canonical_agency`)

7 raw agency strings were seen across all approved facts, collapsing into exactly 4
canonical `Agency` nodes:

| Raw surface forms seen | Canonical node |
|---|---|
| "Department of Immigration & Emigration", "Department of Immigration and Emigration" | Department of Immigration and Emigration |
| "Department for Registration of Persons", "Department of Registration of Persons" | Department for Registration of Persons |
| "Inland Revenue Department", "Inland Revenue Department Sri Lanka" | Inland Revenue Department |
| "Registrar General's Department" | Registrar General's Department |

3 real merge decisions, all 3 correct, 0 incorrect merges (no two genuinely different
agencies were collapsed into one), 0 duplicate `Agency` nodes left over.

**Precision: 3/3 (100%). Recall: 3/3 (100%).** Target 95%/90% — both cleared, on the real
surface-form variation this project's four departments actually produced. The sample is
small (3 merge decisions) because only 4 agencies exist across the current departments;
it is not padded to look larger than it is.

## Service-level resolution: built as a curated alias list, not fuzzy matching

SO4 covers "agency **or service**." A similarity scan over all 186 service IDs for
near-duplicates found one confirmed real case and 19 false positives:

**`svc:tourist_vat_refund_scheme` and `svc:tourist_vat_refund_scheme_tvrs`** were the same
real-world IRD service, split into two nodes because they were extracted from two
different source pages (the scheme's own page, and the IRD downloads/forms page) under
slightly different section titles. The result, before the fix: the service's
*prerequisites* lived on one node and its *documents* lived on the other, so a citizen
asking about either ID saw only half of what the service actually requires.

The other 19 high-similarity pairs checked by the same scan (e.g. "death occurring in a
hospital" vs. "...in a house", Kandyan vs. Muslim vs. general marriage correction) were
confirmed as genuinely **different** real services. This is why service-level resolution
is *not* built the same way as `canonical_agency()`'s word-subset matching: automatic
fuzzy merging at the service level would have wrongly collapsed those 19 real, distinct
services into one. **Fixed instead** with `canonical_service()` in
`app/core/graph/writer.py`: an explicit, human-confirmed alias map (currently one entry,
the TVRS case above), applied at write time in `_write_fact()`. A new service is only
ever merged after a person has looked at it and confirmed it is the same thing, not from
a similarity score alone.

The live graph's existing duplicate was retroactively merged (10 facts + 4 facts onto one
node, the duplicate node deleted) using the real provenance already on both sets of facts.

## What this honestly supports

The agency-level mechanism this component actually built works, on real data, at the
target precision and recall — with a small but genuine sample. The service-level
mechanism is now built too, deliberately conservative (curated list, not automatic fuzzy
merging) given the 19 false positives a similarity scan produced — and the one real case
found, `tourist_vat_refund_scheme`, is fixed in both code and the live graph.
