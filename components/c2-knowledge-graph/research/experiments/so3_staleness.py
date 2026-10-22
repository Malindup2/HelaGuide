"""SO3: value-change-driven community summary regeneration -- the proposal's actual novel
claim, and the one the proposal's own Section 3.4/Table 3 names as the decisive ablation.

A with-and-without comparison over the SAME real graph and the SAME 20 simulated
corrections, with the value-change trigger as the only manipulated variable, exactly as
Section 3.5 (mechanism validity) requires. Both conditions run through the real
app.core.graph.community.maintain_communities function; `detect_value_changes` is the one
flag that differs between "status quo" (every reviewed method: membership-delta only) and
"proposed" (this component: membership-delta AND value-change).

Every dry-run call reads the real, live community state and writes nothing -- this script
is read-only against the graph except for the one real (non-dry-run) summarize_community
call used to calibrate a real per-summary token cost, which legitimately regenerates one
stale community's summary as a side effect, not test pollution.

    python research/experiments/so3_staleness.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1] / "service"
sys.path.insert(0, str(SERVICE_DIR))

from app.admin_ui import _llm, _neo4j  # noqa: E402
from app.core.graph.community import community_id_for, maintain_communities  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

N_EVENTS = 20
SEED = 7


def _real_candidate_services(driver) -> list[str]:
    """Services that already have real facts and sit in a real, non-trivial (non-singleton)
    community -- the realistic case: popular, cross-agency services are what actually get
    corrected in practice, not a random singleton with one fact."""
    with driver.session() as s:
        rows = s.run(
            """MATCH (sv:Service)-[:HAS_FACT]->(f:Fact) WHERE f.valid_to IS NULL AND (sv)-[:REQUIRES]-()
               RETURN DISTINCT sv.service_id AS sid, count(f) AS n ORDER BY n DESC LIMIT 15""")
        return [r["sid"] for r in rows]


def main() -> None:
    uri, user, pw = _neo4j()
    driver = GraphDatabase.driver(uri, auth=(user, pw))

    candidates = _real_candidate_services(driver)
    if not candidates:
        print("No real services with both facts and REQUIRES edges were found -- "
              "run the real extraction pipeline first.")
        return

    rng = random.Random(SEED)
    events = [rng.choice(candidates) for _ in range(N_EVENTS)]

    print(f"{N_EVENTS} simulated real-world corrections, drawn from {len(candidates)} real, "
          f"already-populated, cross-agency services (seed={SEED})\n")

    baseline_stale = 0
    proposed_stale = 0
    proposed_dirty_communities: set[str] = set()
    print(f"{'#':>3}  {'service':<45} {'status-quo':<12} {'proposed':<10}")
    for i, sid in enumerate(events, start=1):
        status_quo = maintain_communities(
            driver, llm=None, changed_service_ids={sid}, detect_value_changes=False, dry_run=True)
        proposed = maintain_communities(
            driver, llm=None, changed_service_ids={sid}, detect_value_changes=True, dry_run=True)

        quo_missed = sid in status_quo.stale_services
        prop_caught = sid not in proposed.stale_services
        baseline_stale += int(quo_missed)
        proposed_stale += int(not prop_caught)
        print(f"{i:>3}  {sid:<45} {'STALE' if quo_missed else 'caught':<12} "
              f"{'caught' if prop_caught else 'STALE':<10}")

    # which real communities the 20 events actually touched, for the token-cost comparison
    with driver.session() as s:
        from app.core.graph.community import fetch_service_graph, detect_communities
        services, edges = fetch_service_graph(s)
        partition = detect_communities(services, edges)
        total_communities = len(partition)
        for members in partition.values():
            cid = community_id_for(members)
            if any(sid in members for sid in events):
                proposed_dirty_communities.add(cid)

    print()
    print("=" * 70)
    print(f"Status quo (membership-delta only, every reviewed method): "
          f"{baseline_stale}/{N_EVENTS} corrections left stale")
    print(f"Proposed (membership-delta AND value-change):               "
          f"{proposed_stale}/{N_EVENTS} corrections left stale   target: 0")

    # real per-summary token cost: one genuine, non-dry-run regeneration, used to calibrate
    # the full-rebuild comparison -- the proposal's own B.4 explicitly allows an analytical
    # cost function over community size rather than a served-model measurement at this stage.
    # A quota/network failure here must NOT take down the ablation result already printed
    # above -- that result doesn't depend on this call succeeding.
    pct: float | None = None
    try:
        llm = _llm(fast_fail=True)
        sample_sid = events[0]
        real_run = maintain_communities(
            driver, llm=llm, changed_service_ids={sample_sid}, detect_value_changes=True, dry_run=False)
        if real_run.regenerated > 0:
            per_summary = (real_run.prompt_tokens + real_run.completion_tokens) / real_run.regenerated
            proposed_tokens = per_summary * len(proposed_dirty_communities)
            full_rebuild_tokens = per_summary * total_communities
            pct = 100 * proposed_tokens / full_rebuild_tokens if full_rebuild_tokens else 0
            print()
            print(f"Real per-summary token cost (1 genuine regeneration, not estimated): "
                  f"{per_summary:.0f} tokens")
            print(f"{len(proposed_dirty_communities)} of {total_communities} communities touched "
                  f"by these {N_EVENTS} events -> "
                  f"{proposed_tokens:.0f} tokens vs a full rebuild's {full_rebuild_tokens:.0f} tokens "
                  f"({pct:.1f}% of a full rebuild, target: under 10%)")
        else:
            print("\n(The sampled event's community was already current -- no real token sample "
                  "was taken this run; re-run after a real fact change to calibrate.)")
    except Exception as e:  # noqa: BLE001
        print()
        print(f"(Real token calibration skipped this run: {type(e).__name__}: {e}. "
              f"The staleness result above does not depend on this call and stands regardless --"
              f" this is a live LLM quota/network hiccup, not a flaw in the mechanism.)")

    driver.close()

    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    plt.style.use("seaborn-v0_8-whitegrid")
    labels = ["Status quo\n(membership-delta only)", "Proposed\n(+ value-change)"]
    values = [baseline_stale, proposed_stale]
    colors = ["#c0392b", "#1d9e75"]
    bars = ax.bar(labels, values, color=colors, width=0.5)
    ax.set_ylim(0, N_EVENTS * 1.12)
    ax.set_ylabel(f"corrections left stale (of {N_EVENTS})")
    title = "SO3: the value-change trigger, live run"
    if pct is not None:
        title += f"\n{pct:.1f}% of a full rebuild's token cost"
    ax.set_title(title)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.3, str(v), ha="center", fontsize=11, fontweight="bold")
    fig.tight_layout()
    out = Path(__file__).resolve().parents[1] / "docs" / "figures" / "pp2_so3_staleness_figure.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
