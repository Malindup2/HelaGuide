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

## Service-level resolution — not built, and here's evidence it's needed

SO4 covers "agency **or service**." There is no `canonical_service()` equivalent to
`canonical_agency()` — services are never merged. A similarity scan over all 186 service
IDs for near-duplicates found one confirmed real case:

**`svc:tourist_vat_refund_scheme` and `svc:tourist_vat_refund_scheme_tvrs`** are the same
real-world IRD service, split into two nodes because they were extracted from two
different source pages (the scheme's own page, and the IRD downloads/forms page) under
slightly different section titles. The result: the service's *prerequisites* live on one
node and its *documents* live on the other. A citizen asking about either ID sees only
half of what the service actually requires.

The other 19 high-similarity pairs checked by the same scan (e.g. "death occurring in a
hospital" vs. "...in a house", Kandyan vs. Muslim vs. general marriage correction) were
confirmed as genuinely **different** real services, correctly left unmerged — the scan is
not flagging noise.

## What this honestly supports

The agency-level mechanism this component actually built works, on real data, at the
target precision and recall — with a small but genuine sample. The service-level half of
SO4's stated scope is unbuilt, and the `tourist_vat_refund_scheme` case is concrete
evidence of the cost: one real service, fragmented, with incomplete facts under either of
its two IDs.
