# SO5: workflow-correctness evaluation

![Workflow correctness, graph vs. baseline, and coverage across all five objectives](figures/pp2_results_figure.png)

Real run: `python research/experiments/workflow_scoring.py`, against the live graph
(2,385 nodes) on 18 October 2026. No LLM judge, no human grading in the scoring path —
exact match and set match are computed programmatically, as the proposal specifies.

## Result

| | Graph | Lexical baseline (B3) | Target |
|---|---|---|---|
| Exact match | **8/10 (80%)** | 0/10 (0%) | 85% |
| Set match | **8/10 (80%)** | 0/10 (0%) | 95% |

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

**A correction made during this run, worth stating:** the first draft of the ground truth
missed that dependencies are transitive. J3 (dual citizenship) needs a passport, and a
passport itself needs an NIC — so NIC is a real requirement even though dual citizenship's
own page never mentions it directly. The graph's answer was right; my first ground truth
was short one step. Caught by checking, not assumed.

## The two real remaining gaps

**J9 — VAT registration.** The graph currently returns `[svc:value_added_tax]` with no
prerequisites, but the page genuinely states one: *"The TIN Certificate should be obtained
from Primary Registration Unit"* — correctly extracted as a `prerequisite` fact, with its
quote. It just never became a `REQUIRES` edge to `svc:taxpayer_identification_number_tin`,
because the derived-link logic only fires on a document-name match, not on free prose like
this. **A specific, fixable extraction gap**, not a vague shortfall.

**J10 — Taxpayer ID (TIN).** The graph derives `requires: svc:passport`, but the
underlying document is *"Photocopies of valid Passports of Directors"* — a **company's**
TIN registration requirement, not the individual citizen's own passport. This is the same
case-mixing problem flagged earlier this session for the NIC service (first-issue, lost,
one-day variants bleeding together): the business and individual TIN variants were never
separated during extraction, so a business-only document leaked into the general service's
derived prerequisites.

## What this honestly supports

- The graph is far ahead of plain lexical search on multi-step, cross-agency questions —
  the core claim this component exists to test.
- It is close to, but under, the stated targets, with two concrete, well-understood causes
  rather than an unexplained gap. Both point at the same underlying class of problem
  already known from this session: case/variant mixing during extraction, and prerequisite
  derivation that only recognises document-name matches, not free-text prerequisite facts.
- Growing the journey set past 10 would tighten the percentage; it would not change what
  these two cases already show.
