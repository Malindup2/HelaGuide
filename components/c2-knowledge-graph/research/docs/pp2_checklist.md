# PP2 checklist — what's done, what's not, what's next

Audited against the proposal (`SO1`–`SO5`, Table 3's evaluation metrics, FR/NFR tables) and
`PLAN.md`'s own 70%-completeness definition. Last checked: **18 October 2026**, against the
live graph (2,385 nodes, 3,762 relationships — verified by query, not estimated).

**Rule for this file:** a line only gets a ✅ when there is a real, checked number or a real,
run command behind it. "The mechanism works" is not the same as "the target is met" — mark
those 🟡, not ✅.

---

## 1. The five specific objectives

| | Objective | Target | Status | What's missing |
|---|---|---|---|---|
| SO1 | Change classification | 95% accuracy, labelled test set, zero tokens on unchanged pages | 🟡 mechanism works (confirmed live, repeatedly) | No accuracy number against a labelled set |
| SO2 | Typed extraction with provenance | 90%/80% precision-recall, <4,500 tokens/page | 🟡 extraction + grounding + provenance all work; token use is well under budget | No precision/recall number against hand-annotated pages |
| SO3 | Value-change summary regeneration | Zero stale facts, <10% rebuild cost | ⬜ **not in scope for PP2** — correctly deferred per `PLAN.md` §1 and the proposal's own Appendix B ("the real service graph does not yet exist") | Needs Leiden communities first — next milestone |
| SO4 | Entity resolution + temporal versioning | 95% merge precision, 90% recall | 🟡 mechanism works (`canonical_agency`, `validFrom`/`validTo`; a real matching bug was fixed this session) | No precision/recall number against a labelled duplicate set |
| SO5 | Dependency-ordered workflow + evaluation | 85% exact match, 95% set match vs. ground truth, no LLM judge | 🟡 workflow generation works and is demonstrated (passport→NIC→birth certificate, etc.) | **The scoring itself has never been run.** Proposal's own words: "the principal outstanding work" |

## 2. Evaluation metrics (Table 3)

| Metric | Status |
|---|---|
| Token cost per update | 🟡 logged per page, not reported as a formal comparison |
| Update latency | ⬜ not measured |
| Stale-fact count | ⬜ N/A until SO3 (deferred) |
| Partition fidelity (ARI/NMI) | ⬜ N/A until SO3 (deferred) |
| **Workflow correctness (exact/set match)** | ⬜ **not done — see SO5** |
| Query-side traversal latency/memory | ⬜ not measured (`/v1/plan` isn't wired yet, nothing to time end-to-end) |

## 3. Requirements worth a direct check

| | Requirement | Status |
|---|---|---|
| FR13/FR17 | `/v1/plan` serves the real ordered procedure | ✅ **done 18 Oct** — `app.core.workflow.plan_for` now walks the live Neo4j graph (`build_plan`) instead of raising `NotImplementedError`; verified over real HTTP (`GET /v1/plan?service_id=svc:passport`) with correct ordering, real fees, real provenance (63 entries for the 3-step passport plan) |
| — | `/v1/facts/{id}` serves a real fact with version history | ✅ **done 18 Oct** — `app.core.facts.get` now queries Neo4j; verified a real closed version (`svc:nic:fee:first_issue_standard`: Rs.200/- → Rs. 200/-, the formatting fix made earlier this session, now visible as real history) |
| FR14 | Reports when no valid order exists (cycle detection) | 🟡 implemented (`plan_for` returns `None` on a detected cycle) — not yet exercised against a real cyclic case in this graph |
| — | Correction path from C3 (FR16) | ⬜ still `NotImplementedError`, correctly — C3's verified-correction contract isn't exercised against the real graph yet, this is a two-way integration point, not solo work |
| NFR7 | Evaluated at ≥4,000 nodes | ⬜ **currently 2,385** — short by ~1,600 |
| NFR9 | No personal/citizen data collected | ✅ true by construction — only public service facts |
| NFR8 | Every fact carries source URL + retrieval timestamp | ✅ confirmed throughout — this was the whole grounding design |

## 4. What this adds up to, in order of priority before 26 Oct

1. ~~Wire `/v1/plan` to the real graph.~~ ✅ **done 18 Oct**, see §3. Not yet behind the actual
   gateway container (`gateway/`) — only verified directly against the C2 service. Routing
   the gateway's own `/v1/plan` passthrough to this is a small remaining step.
2. **Build 5–10 ground-truth journeys and score exact/set match (SO5).** The proposal's own named "principal outstanding work." Biggest single gap. Now unblocked by #1.
3. **Measure SO1**: label ~15 pages (changed/unchanged/structure), report accuracy.
4. **Measure SO2**: hand-annotate ~15 pages against the extracted facts, report precision/recall.
5. **Measure SO4**: label a duplicate-agency set, report merge precision/recall.
6. **Check NFR7**: either grow the graph past 4,000 nodes (more departments/pages) or state the real count and note it as a known shortfall.

## 5. What's correctly NOT on this list

Community detection, Leiden clustering, the real value-change staleness trigger, ARI/NMI,
the escalation guard (FR12), and the B1/B2/B3 full baseline comparison. All of these need
SO3 first, and SO3 is deferred to the next milestone by design — not a gap in PP2, a scope
decision made before the proposal was even submitted (Appendix B.4: "the real service graph
does not yet exist").

---

## Log

- **18 Oct 2026** — file created, every line above checked against the live graph or the
  actual code, not assumed. Nothing in sections 1–3 was marked ✅ on a mechanism existing
  alone; only a real measured number earns it.
- **18 Oct 2026** — `/v1/plan` and `/v1/facts/{id}` wired to the real graph (priority #1).
  Two real bugs found and fixed while verifying it, not left for later:
  - A stale `pyproject.toml` with unresolved `git stash` conflict markers (`<<<<<<<` /
    `=======` / `>>>>>>>`), which silently broke `pytest`'s own config loading. **The whole
    test suite could not run at all** until this was fixed — found only because this work
    happened to touch that file's neighbourhood.
  - `_pick_fee`'s qualifier matching picked `amended_standard` (Rs. 500) over
    `first_issue_standard` (Rs. 200) for a first-time NIC applicant, because a plain
    `"standard"` substring check matched whichever fee came first in the list. Caught by
    actually printing the real plan output before trusting it, not by the code looking
    reasonable on paper.
  - Documented limitation, not a bug: the shared `Plan` contract's `PlanStep.fee` is a
    single `Fee`, but real services often have several (first issue, lost, one-day...).
    `_pick_fee` picks one by a fixed preference order. The real fix is extending the
    contract to a list, which `PLAN.md` already names as an open decision with the team.
  - 10 new tests added (`test_workflow.py`, `test_facts.py`, plus one in `test_routes.py`),
    skip cleanly when Neo4j isn't reachable (CI, a machine with no `.env`), matching the
    existing pattern in `test_graph_writer.py`. 284 tests pass total.
