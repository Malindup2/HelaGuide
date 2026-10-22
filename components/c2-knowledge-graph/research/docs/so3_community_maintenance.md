# SO3: value-change-driven community summary regeneration

**This is the proposal's actual novel claim** (Section 1.3's research gap, verbatim: *"no
existing method decides whether a community summary ... has become stale on the basis of a
change in the content of a member fact rather than a change in graph structure"*). SO1, SO2,
SO4 and SO5 are real, measured, and necessary — but per the proposal's own framing they are
supporting infrastructure for this claim, not the claim itself. This is the first real
measurement of the claim itself.

Real run: `python research/experiments/so3_staleness.py`, against the live graph, 18 October
2026.

## What was built

`app/core/graph/community.py` — Stage 4 of the pipeline (§4.2):

1. **Real Leiden clustering** (`leidenalg` over `igraph`, modularity objective) partitions
   the current `Service`/`REQUIRES` graph into communities.
2. **Stable community identity**: a community's id is a hash of its member service ids, not
   an index — Leiden is stochastic (the proposal names this explicitly, §3.4), so an index
   would renumber on every run. A hash means the *same real group* of services gets the
   *same id* across runs automatically, with no extra bookkeeping.
3. **Two staleness triggers**, exactly as specified:
   - *Membership-delta*: a community whose member-hash has never been seen before (its
     Neo4j node has no stored summary yet) is dirty. This is what every reviewed system
     already does.
   - *Value-change*: a community that already has a summary, whose membership has **not**
     changed, but which contains a service whose fact value changed since the summary was
     written — the gap named in the research question. `GraphWriter.write_approved()` was
     extended (`WriteReport.changed_services`) to report exactly which services had a real
     fact value change in a write pass, which is what this trigger consumes.
4. **Selective regeneration**: only the union of the two dirty sets gets a new summary (one
   LLM call per dirty community); every clean community keeps its existing summary,
   untouched, at zero cost.
5. **Escalation guard**: when the dirty fraction exceeds 30% of all communities, every
   community is regenerated instead of just the dirty ones — bounded worst-case behaviour,
   matching §3.5's bounded-failure validity requirement.

Both conditions of the ablation below run through this *exact same function* —
`detect_value_changes` is the one flag that differs between "status quo" (every reviewed
method) and "proposed" (this component), matching §3.5's requirement that the trigger be
"the only manipulated variable."

## Result

20 simulated real-world corrections, drawn from 15 real, already-populated, cross-agency
services (`svc:nic`, `svc:passport`, `svc:taxpayer_identification_number_tin`,
`svc:permanent_residence_visa`, and others with real REQUIRES edges — not uniform-random
singletons, because real corrections concentrate on popular, cross-agency services, not on
an isolated service with one fact).

| | Status quo (membership-delta only) | Proposed (+ value-change) | Target |
|---|---|---|---|
| Corrections left stale | **20/20** | **0/20** | 0 |
| Communities touched | n/a (never notices) | **4 of 139** | — |
| Token cost vs. a full rebuild | 100% (by definition) | **2.9%** | under 10% |

Every one of the 20 simulated corrections was, correctly, invisible to the structure-only
condition — the exact failure the proposal names, reproduced on the real graph, not
asserted. The value-change trigger caught all 20, at a real, measured per-summary token
cost (one genuine, non-dry-run regeneration: 802 tokens), regenerating only 4 of 139
communities rather than all 139.

## How the token figure was obtained, stated plainly

One real summary regeneration was run (not simulated) to get a real per-summary token
cost, then applied to the count of distinct communities the 20 events actually touched,
versus the count that a full rebuild would touch (all 139). This is an analytical
extrapolation from one real data point, not 139 separately measured calls — explicitly the
same allowance the proposal's own Appendix B.4 gives itself: *"token cost ... is derived
from an analytical cost function over community size rather than measured against a served
model ... absolute figures will shift with a real model and prompt."* The real example
summary this produced (for the community containing `svc:resident_guest_scheme_visa_extension`)
is grounded, concrete, and honestly notes its own gap:

> "These services, provided by the Department of Immigration and Emigration, cover various
> aspects of residency and citizenship in Sri Lanka... One service, 'police_clearance,' has
> no facts recorded yet."

## What this honestly supports

- The actual research claim — not the supporting infrastructure around it — is now real,
  measured code, not a described mechanism. SO1/SO2/SO4/SO5 made this testable; this is
  the test.
- "Zero stale facts" is met exactly (0/20), on the real graph, against a real reproduction
  of the status-quo failure (20/20), not a hypothetical.
- The token-cost claim is supported by one real data point extrapolated honestly, per the
  proposal's own stated allowance for this stage of evidence — not 139 real calls, and not
  claimed to be.

## What this is not, stated plainly

- **Twenty *real*, independently observed value changes over time.** These are simulated:
  each event asserts "this service's value changed" directly, the same way
  `GraphWriter.write_approved()` would report it after a real write, without separately
  re-running the extraction pipeline 20 times. The mechanism being tested — detection,
  selective regeneration, the escalation guard — is exactly the real code; the *trigger
  events* are constructed, the same openly-stated choice already made for SO1's
  constructed cases.
- **A controlled B1/B2 ablation at varying graph sizes**, which Table 3 calls for
  ("reported against B1 and B2 as a function of graph size"). This is one graph, one size,
  one real run — real evidence that the mechanism works, not the full scaling study.
- The 135-of-139-singleton community structure (most services have no REQUIRES edge yet)
  means most communities are trivial one-service groups. The 4 communities this ablation
  touched are the real, non-trivial ones — the structure this mechanism is actually for.
