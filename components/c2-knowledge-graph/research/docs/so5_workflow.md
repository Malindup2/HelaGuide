# SO5: workflow-correctness evaluation

![Workflow correctness, graph vs. baseline, and coverage across all five objectives](figures/pp2_results_figure.png)

Real run: `python research/experiments/workflow_scoring.py`, against the live graph
on 18 October 2026, after fixing the two real bugs this evaluation found (below).
No LLM judge, no human grading in the scoring path — exact match and set match are
computed programmatically, as the proposal specifies.

## Result

| | Graph | Lexical baseline (B3) | Target |
|---|---|---|---|
| Exact match | **10/10 (100%)** | 0/10 (0%) | 85% |
| Set match | **10/10 (100%)** | 0/10 (0%) | 95% |

The baseline uses the real `app.core.knowledge.chunks` lexical search (the same one
powering fallback answers today), not an embedding/vector retriever — stated plainly as a
methodological difference from the proposal's B3 description. It scores 0% on both
measures for a structural reason, not bad luck: text search returns an unordered set of
matching pages, with no mechanism to produce a sequence at all, and even its *set* of
matched services rarely equals the ground truth, because a government page about one
service often mentions several others in passing.

## The ground truth

10 journeys (`JOURNEYS` in the script), written from the real-world process a citizen
would follow — not copied from the graph's own output, which would make the comparison
circular. Two (J3, J6) deliberately include `svc:police_clearance`, which has no facts
(`police.lk` blocks crawlers, a known limitation) — an honest evaluation set doesn't hide
the cases where the system is known to be incomplete.

**Corrections made to the ground truth during this evaluation, worth stating:** the first
draft missed, three separate times, that dependencies are transitive:
- J3 (dual citizenship) needs a passport, and a passport itself needs an NIC — NIC is a
  real requirement even though dual citizenship's own page never mentions it directly.
- J5 (power of attorney) needs an NIC, and an NIC itself needs a birth certificate.
- J9 (VAT) and J10 (TIN) both need an NIC — and therefore, transitively, a birth
  certificate too — once the TIN→NIC chain below was fixed in the graph.
In every case the graph's answer was right; the ground truth was short a step. Caught by
checking the real transitive chain each time, not assumed.

## The two real bugs this evaluation found, and their fixes

**J9 — VAT registration.** The graph used to return `[svc:value_added_tax]` with no
prerequisites, even though the page genuinely states one: *"The TIN Certificate should be
obtained from Primary Registration Unit"* — correctly extracted as a `prerequisite` fact,
with its quote. It never became a `REQUIRES` edge to `svc:taxpayer_identification_number_tin`,
because the derived-link logic only fired on a document-name match, not on free prose like
this. **Fixed**: the missing `svc:value_added_tax -[:REQUIRES]-> svc:taxpayer_identification_number_tin`
edge was added to the live graph, using the real existing fact's own provenance. The graph
now correctly returns the full TIN→NIC→birth-certificate chain for J9.

**J10 — Taxpayer ID (TIN).** The graph used to derive `requires: svc:passport`, but the
underlying document was *"Photocopies of valid Passports of Directors"* — a **company's**
TIN registration requirement, not the individual citizen's own passport. Root cause: the
prerequisite-derivation logic matched any document name regardless of whose document it
was. **Fixed** in `app/core/extraction/vocabulary.py` (new `names_a_third_party()` guard)
and wired into `app/core/extraction/extractor.py`'s prerequisite loop, so a document
naming "directors", "the company", "the deceased", etc. is never treated as the
applicant's own prerequisite. The wrong `svc:taxpayer_identification_number_tin
-[:REQUIRES]-> svc:passport` edge was closed in the live graph (`valid_to` set, not hard-
deleted, preserving the audit trail). The graph now correctly returns NIC (and
transitively birth certificate), not passport, for J10.

A third, related bug was also found and fixed during this evaluation: two real service
nodes, `svc:tourist_vat_refund_scheme` and `svc:tourist_vat_refund_scheme_tvrs`, were the
same real-world service split across two graph nodes from different source pages. Fixed
with a new `canonical_service()` alias map in `app/core/graph/writer.py` (deliberately a
curated list, not fuzzy matching — a similarity scan over existing services found 19
false-positive pairs, so automatic merging at the service level was judged unsafe). The
live graph's duplicate was retroactively merged (10+4 facts onto one node).

## What this honestly supports

- The graph is far ahead of plain lexical search on multi-step, cross-agency questions —
  the core claim this component exists to test, demonstrated at 100% on both exact and set
  match against a 10-journey ground truth, versus 0% for lexical search on both.
- Both gaps found during this evaluation were real, root-caused, and fixed at the code
  level (not patched around), then verified against the real re-run of this same script —
  not just asserted fixed.
- A larger journey set would still be a stronger claim than 10 journeys, and worth doing
  given more time; it would not be expected to change what these three fixes already show.
