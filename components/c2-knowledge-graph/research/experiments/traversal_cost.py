"""Appendix B.3 (proposal): query-side traversal cost, scoped vs whole-graph, across
graph sizes. Scoped traversal is the REAL algorithm this component runs, lifted straight
out of app.core.graph.plan.build_plan -- a DFS from the requested service that only ever
visits REQUIRES-ancestors of the target, same post-order / cycle-guard structure, same
MAX_DEPTH. It is re-implemented over a plain in-memory adjacency dict here only so the
experiment can vary total graph size cheaply; the traversal logic itself is not a stand-in.

Whole-graph traversal is the natural non-scoped alternative: visit every node in the
graph once (a full topological pass), the way an implementation would have to if it did
not bound itself to the ancestor set first.

The real live graph has only 185 Service nodes and 75 REQUIRES edges (verified by query,
18 Oct 2026) -- far too small to show a size trend on its own. So, exactly as the
proposal's own B.2/B.3 did ("executed on synthetic clustered graphs... to establish that
the mechanism is measurable"), this uses synthetic graphs of controlled, varying size.
That is stated plainly, not hidden: this is the same kind of preliminary feasibility
evidence the proposal itself reported, now run against this project's actual algorithm
instead of an abstract model.

    python research/experiments/traversal_cost.py
"""
from __future__ import annotations

import random
import time
import tracemalloc
from pathlib import Path

MAX_DEPTH = 64  # mirrors app.core.graph.plan.MAX_DEPTH


def make_graph(n_nodes: int, ancestor_set_size: int, seed: int = 7) -> tuple[str, dict[str, list[str]]]:
    """A synthetic REQUIRES graph with n_nodes total, where exactly one target has a
    fixed-size chain of real ancestors (so growing the graph does not grow the target's
    own ancestor set -- the thing the proposal's claim is actually about)."""
    rng = random.Random(seed)
    nodes = [f"svc:n{i}" for i in range(n_nodes)]
    target = nodes[0]
    edges: dict[str, list[str]] = {sid: [] for sid in nodes}

    # the target's real ancestor chain: a small, fixed-depth dependency path
    chain = nodes[1:1 + ancestor_set_size]
    prev = target
    for sid in chain:
        edges[prev].append(sid)
        prev = sid

    # everything else: unrelated services with their own small, unrelated REQUIRES edges,
    # so the graph has real size and real edges, just none of them reachable from target
    rest = nodes[1 + ancestor_set_size:]
    for sid in rest:
        if rng.random() < 0.3 and rest:
            edges[sid].append(rng.choice(rest))
    return target, edges


def scoped_traversal(target: str, edges: dict[str, list[str]]) -> int:
    """The real algorithm in app.core.graph.plan.build_plan: DFS from target, following
    REQUIRES forward, post-order, with the same on-path/done state machine for cycles."""
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(sid: str, depth: int) -> None:
        if state.get(sid) == 2:
            return
        if state.get(sid) == 1:
            return  # cycle: same guard as build_plan
        if depth > MAX_DEPTH:
            return
        state[sid] = 1
        for dep in edges.get(sid, []):
            visit(dep, depth + 1)
        state[sid] = 2
        order.append(sid)

    visit(target, 0)
    return len(order)


def whole_graph_traversal(target: str, edges: dict[str, list[str]], all_nodes: list[str]) -> int:
    """The non-scoped alternative: resolve the target only after visiting every node in
    the graph once, as an implementation without ancestor-scoping would have to."""
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(sid: str, depth: int) -> None:
        if state.get(sid) == 2:
            return
        if state.get(sid) == 1:
            return
        if depth > MAX_DEPTH:
            return
        state[sid] = 1
        for dep in edges.get(sid, []):
            visit(dep, depth + 1)
        state[sid] = 2
        order.append(sid)

    for sid in all_nodes:  # the whole-graph cost: every node gets resolved, not just target's ancestors
        visit(sid, 0)
    assert target in state
    return len(order)


def timeit_ms(fn, repeats: int = 30) -> float:
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - t0) * 1000)
    return best


def peak_kb(fn) -> float:
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024


SIZES = [100, 500, 1_000, 5_000, 10_000, 50_000]
ANCESTOR_SET_SIZE = 8  # the target's own real ancestor chain stays this size at every graph size

print(f"{'N nodes':>8}  {'scoped ms':>10}  {'whole-graph ms':>15}  {'scoped KB':>10}  {'whole-graph KB':>15}")
rows = []
for n in SIZES:
    target, edges = make_graph(n, ANCESTOR_SET_SIZE)
    all_nodes = list(edges.keys())

    scoped_ms = timeit_ms(lambda: scoped_traversal(target, edges))
    whole_ms = timeit_ms(lambda: whole_graph_traversal(target, edges, all_nodes), repeats=5)
    scoped_kb = peak_kb(lambda: scoped_traversal(target, edges))
    whole_kb = peak_kb(lambda: whole_graph_traversal(target, edges, all_nodes))

    rows.append((n, scoped_ms, whole_ms, scoped_kb, whole_kb))
    print(f"{n:>8}  {scoped_ms:>10.4f}  {whole_ms:>15.4f}  {scoped_kb:>10.2f}  {whole_kb:>15.2f}")

print()
print(f"Scoped traversal cost stays within "
      f"{max(r[1] for r in rows) / min(r[1] for r in rows):.1f}x across a "
      f"{SIZES[-1] // SIZES[0]}x range of total graph size.")
print(f"Whole-graph traversal grows {max(r[2] for r in rows) / min(r[2] for r in rows):.1f}x "
      f"over the same range.")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({"font.size": 10.5, "axes.titlesize": 11.5})
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))

ns = [r[0] for r in rows]
ax = axes[0]
ax.plot(ns, [r[1] for r in rows], marker="o", color="#1d9e75", label="scoped (this component's real algorithm)")
ax.plot(ns, [r[2] for r in rows], marker="o", color="#993c1d", label="whole-graph")
ax.set_xscale("log")
ax.set_xlabel("total graph size (nodes)")
ax.set_ylabel("latency (ms)")
ax.set_title("Query-side traversal latency\nscoped vs whole-graph, by graph size")
ax.legend(fontsize=8)

ax = axes[1]
ax.plot(ns, [r[3] for r in rows], marker="o", color="#1d9e75", label="scoped")
ax.plot(ns, [r[4] for r in rows], marker="o", color="#993c1d", label="whole-graph")
ax.set_xscale("log")
ax.set_xlabel("total graph size (nodes)")
ax.set_ylabel("peak memory (KB)")
ax.set_title("Query-side traversal memory\nscoped vs whole-graph, by graph size")
ax.legend(fontsize=8)

fig.suptitle("Appendix B.3: scoped traversal is the real build_plan() algorithm, on synthetic graphs of varying size",
             fontsize=9.5, y=1.04)
fig.tight_layout()
out = Path(__file__).resolve().parents[1] / "docs" / "figures" / "pp2_b3_traversal_cost_figure.png"
fig.savefig(out, dpi=200, bbox_inches="tight")
print("saved", out)
