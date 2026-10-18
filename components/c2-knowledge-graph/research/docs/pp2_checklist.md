# PP2 checklist — what's done, what's not, what's next

Audited against the proposal (`SO1`–`SO5`, Table 3's evaluation metrics, FR/NFR tables) and
`PLAN.md`'s own 70%-completeness definition. Last checked: **18 October 2026**, against the
live graph (2,385 nodes, 3,762 relationships — verified by query, not estimated).

**Rule for this file:** a line only gets a ✅ when there is a real, checked number or a real,
run command behind it. "The mechanism works" is not the same as "the target is met" — mark
those 🟡, not ✅.

---

## 1. The five specific objectives

| | Objective | Target | Status | Real result |
|---|---|---|---|---|
| SO1 | Change classification | 95% accuracy, labelled test set, zero tokens on unchanged pages | ✅ **measured 18 Oct** — see `so1_classification.md` | **100% (9/9)**, 0 false positives |
| SO2 | Typed extraction with provenance | 90%/80% precision-recall, <4,500 tokens/page | 🟡 **precision measured**, recall partial — see `so2_extraction.md` | **Precision 99.2% (123/124)**. Recall: 1 real miss found in a 2-of-10-page partial check, not yet a full number |
| SO3 | Value-change summary regeneration | Zero stale facts, <10% rebuild cost | ⬜ **not in scope for PP2** — correctly deferred per `PLAN.md` §1 and the proposal's own Appendix B ("the real service graph does not yet exist") | Needs Leiden communities first — next milestone |
| SO4 | Entity resolution + temporal versioning | 95% merge precision, 90% recall | ✅ **agency-level measured 18 Oct** — see `so4_entity_resolution.md`. 🟡 service-level: not built | **Agency: 100%/100% (3/3 merges correct)**. Service-level resolution doesn't exist — 1 real unmerged duplicate found (`tourist_vat_refund_scheme`) |
| SO5 | Dependency-ordered workflow + evaluation | 85% exact match, 95% set match vs. ground truth, no LLM judge | ✅ **measured 18 Oct** — see `so5_workflow.md` | **Graph: 80%/80% (8/10)**, below target with 2 specific understood causes. **Lexical baseline: 0%/0%** |

## 2. Evaluation metrics (Table 3)

| Metric | Status |
|---|---|
| Token cost per update | ✅ **done 18 Oct** — 909,593 tokens / 244 pages total (real, B1-style); a real repeat-crawl event showed 57% of previously-seen pages cost zero tokens. See `token_cost_and_latency.md` for what this is and isn't (a real number, not a controlled B1/B2 ablation) |
| Update latency | ✅ **done 18 Oct** — unchanged page 22.8ms median (no LLM call) vs changed page 11.8s median, ~500x apart. Real timings, see `token_cost_and_latency.md` |
| Stale-fact count | ⬜ N/A until SO3 (deferred) |
| Partition fidelity (ARI/NMI) | ⬜ N/A until SO3 (deferred) |
| **Workflow correctness (exact/set match)** | ✅ **done 18 Oct** — graph 80%/80%, lexical baseline 0%/0%, see `so5_workflow.md` |
| Query-side traversal latency/memory | 🟡 partial — `/v1/plan` measured once (153ms for a 3-step plan), not yet measured across varying graph sizes the way the proposal's Figure 5 does |

## 3. Requirements worth a direct check

| | Requirement | Status |
|---|---|---|
| FR13/FR17 | `/v1/plan` serves the real ordered procedure | ✅ **done 18 Oct** — `app.core.workflow.plan_for` now walks the live Neo4j graph (`build_plan`) instead of raising `NotImplementedError`; verified over real HTTP (`GET /v1/plan?service_id=svc:passport`) with correct ordering, real fees, real provenance (63 entries for the 3-step passport plan) |
| — | `/v1/facts/{id}` serves a real fact with version history | ✅ **done 18 Oct** — `app.core.facts.get` now queries Neo4j; verified a real closed version (`svc:nic:fee:first_issue_standard`: Rs.200/- → Rs. 200/-, the formatting fix made earlier this session, now visible as real history) |
| FR14 | Reports when no valid order exists (cycle detection) | 🟡 implemented (`plan_for` returns `None` on a detected cycle) — not yet exercised against a real cyclic case in this graph |
| — | Correction path from C3 (FR16) | ⬜ still `NotImplementedError`, correctly — C3's verified-correction contract isn't exercised against the real graph yet, this is a two-way integration point, not solo work |
| NFR7 | Evaluated at ≥4,000 nodes | ⬜ **currently 2,385**, checked 18 Oct — short by ~1,600. Decision: not rushing a 5th department just to hit the number; each of the 4 so far (crawl → read → review → write) took real hours and real LLM quota, and a low-quality fast add would undermine everything else on this list. Stated as a known shortfall for the report rather than hidden or inflated. |
| NFR9 | No personal/citizen data collected | ✅ true by construction — only public service facts |
| NFR8 | Every fact carries source URL + retrieval timestamp | ✅ confirmed throughout — this was the whole grounding design |

## 4. What's left, now that all six priority items have a real result

1. ~~Wire `/v1/plan` to the real graph.~~ ✅ done. Not yet behind the actual gateway
   container (`gateway/`) — only verified directly against the C2 service. Routing the
   gateway's own `/v1/plan` passthrough to this is a small remaining step.
2. ~~Build ground-truth journeys, score exact/set match (SO5).~~ ✅ done — 80%/80%, 2 named
   causes, both pointing at the same underlying problem (case/variant mixing and
   free-text prerequisites not becoming edges).
3. ~~Measure SO1.~~ ✅ done — 100%, exceeds target.
4. ~~Measure SO2.~~ 🟡 precision done (99.2%), recall only partially checked (2 of 10
   pages) — finishing the other 8 pages is the one real number still missing.
5. ~~Measure SO4.~~ ✅ agency-level done (100%/100%). Service-level resolution doesn't
   exist as a mechanism — building `canonical_service()` (mirroring `canonical_agency`)
   would fix the one confirmed case (`tourist_vat_refund_scheme`) and is a scoped,
   concrete next step, not yet started.
6. ~~Check NFR7.~~ ✅ checked — 2,385 of 4,000, stated as a known shortfall, not addressed
   today (see §3).

**What's actually left to reach full coverage of this list:** finish SO2's recall check
(8 more pages), and decide whether to build `canonical_service()` before 26 Oct or name it
as a limitation for the report, same as NFR7.

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
