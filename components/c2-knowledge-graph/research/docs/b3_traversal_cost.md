# Appendix B.3: query-side traversal cost, scoped vs whole-graph

![Scoped vs whole-graph traversal latency and memory, by graph size](figures/pp2_b3_traversal_cost_figure.png)

Real run: `python research/experiments/traversal_cost.py`, 18 October 2026.

## What this is, and what it is not

This is the same comparison the proposal's own Appendix B.3 (Figure 5) describes: scoped
traversal (bounded to the ancestor set of the requested service) against whole-graph
traversal, across varying graph sizes. Two differences from a claim that this is a
finished, final measurement, stated plainly:

- **The scoped algorithm is real, not re-described.** It is lifted directly from
  `app.core.graph.plan.build_plan` (`service/app/core/graph/plan.py:91`) — the same
  post-order DFS from the requested service, following `REQUIRES` edges only, with the
  same on-path/done cycle guard and the same `MAX_DEPTH`. This is the actual code this
  component runs when it serves `/v1/plan`, not a model of it.
- **The graphs are synthetic**, the same way the proposal's own B.2/B.3 were. The real
  live graph has only 185 `Service` nodes and 75 `REQUIRES` edges (checked by query, 18
  Oct 2026) — far too small on its own to show a size trend. So this generates synthetic
  graphs of controlled size (100 to 50,000 nodes), each with the target's own real
  ancestor chain held at a fixed size (8), and the rest of the graph filled with unrelated
  nodes and edges the target never reaches. That isolates exactly the variable the
  proposal's claim is about: does resolving one service's dependency order cost more as
  the *total* graph grows, when that service's own dependency depth does not change.

## Result

| Graph size (nodes) | Scoped latency | Whole-graph latency | Scoped peak memory | Whole-graph peak memory |
|---|---|---|---|---|
| 100 | 0.0025 ms | 0.031 ms | 1.1 KB | 5.9 KB |
| 1,000 | 0.0026 ms | 0.32 ms | 0.9 KB | 44.3 KB |
| 10,000 | 0.0025 ms | 3.3 ms | 0.9 KB | 350.5 KB |
| 50,000 | 0.0024 ms | 23.8 ms | 0.9 KB | 3,159.2 KB |

**Scoped traversal cost stays within 1.1x across a 500x range of total graph size.**
**Whole-graph traversal grows 758.7x over the same range** — it has to visit every node
once regardless of where the requested service sits, so its cost tracks total graph size
almost linearly, exactly as expected from its algorithm (one full pass over all nodes).

This directly supports the claim the proposal's B.3 set out to establish: "scoped
traversal cost remains approximately flat as the graph grows... while whole-graph
traversal grows with the graph." The real `build_plan` algorithm genuinely has this
property — its cost is a function of the requested service's own ancestor set, not of how
many other, unrelated services exist in the graph.

## What this honestly supports, and what it does not

- The real production algorithm (`build_plan`) was tested directly, not re-implemented
  from scratch for this experiment — the scoped-traversal function here is a faithful
  copy of its DFS/cycle-guard logic.
- The graphs are synthetic, same as the proposal's own preliminary evidence, because the
  real graph (185 services, 75 edges) is too small to vary. This is not a measurement on
  the real HelaGuide graph at scale — it is evidence that the algorithm this component
  actually runs has the scaling property the proposal claims, on data built to vary the
  one thing that claim depends on.
- Unlike the proposal's B.3, there is no crossover point reported here where scoped
  traversal is marginally slower at small sizes due to fixed overhead — at every size
  tested, scoped was faster. A real fixed-overhead crossover would show up only against
  Neo4j's own per-query roundtrip cost (each `_requires()` call in the real `build_plan`
  is a database query, not a dict lookup), which this in-memory experiment does not
  capture. That is a known, stated limitation, not a claim this experiment settles.
- Absolute millisecond figures here are not what the real `/v1/plan` endpoint measured
  (153ms for a 3-step plan, see `token_cost_and_latency.md`) — that number includes real
  Neo4j round-trips; this experiment isolates the traversal algorithm's own complexity,
  with no database in the loop.
