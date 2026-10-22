"""Stage 4: community maintenance (SO3) -- the proposal's actual novel claim.

Every reviewed incremental graph-RAG method regenerates a community summary only when a
node or edge moves (membership-delta). None of them notice when a FACT'S VALUE changes with
nothing structural moving -- a fee corrected in place, same page, same layout, same edges.
This module adds that second trigger.

Communities are identified by a hash of their member service_ids, not by an index, because
Leiden is stochastic (two runs on the same graph can produce different numbering for the
same groups) and because a stable identity is what lets this module tell "this exact group
of services existed before" from "this is a new group" without extra bookkeeping. A
community whose membership is identical to a previous run keeps the same id automatically;
its stored summary is reused untouched, at zero cost, UNLESS one of its member services had
a fact change value -- the case no membership-delta check can ever see, by construction.

    (:Service)-[:IN_COMMUNITY {valid_from, valid_to}]->(:Community {community_id, summary})

An escalation guard regenerates every community, not just the dirty ones, when the dirty
fraction exceeds a threshold, so the worst case is bounded at parity with a full rebuild
rather than degrading past it (same guard the proposal names in Section 4.3/3.5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from app.core.extraction.llm import LLM, LLMReply

CONSTRAINTS = (
    "CREATE CONSTRAINT community_id IF NOT EXISTS FOR (c:Community) REQUIRE c.community_id IS UNIQUE",
)

DEFAULT_ESCALATION_THRESHOLD = 0.3  # proportion of communities dirty before a full rebuild


def ensure_schema(driver) -> None:
    with driver.session() as session:
        for statement in CONSTRAINTS:
            session.run(statement).consume()


# --------------------------------------------------------------------- graph -> partition

def fetch_service_graph(session) -> tuple[list[str], list[tuple[str, str]]]:
    """Every current Service and every current REQUIRES edge between two services, undirected
    for clustering purposes -- Leiden/modularity does not use edge direction.

    Ordered deterministically (ORDER BY, not left to Neo4j's own return order). Without this,
    two real calls with the SAME fixed seed and the SAME real graph could still produce
    slightly different vertex orderings -- Leiden breaks ties using the order vertices arrive
    in, and that would churn community membership from pure measurement noise, not a real
    change, polluting the exact signal this module exists to keep clean."""
    services = [r["sid"] for r in session.run(
        "MATCH (s:Service) RETURN s.service_id AS sid ORDER BY sid")]
    edges = [(r["a"], r["b"]) for r in session.run(
        """MATCH (a:Service)-[r:REQUIRES]->(b:Service) WHERE r.valid_to IS NULL
           RETURN DISTINCT a.service_id AS a, b.service_id AS b ORDER BY a, b""")]
    return services, edges


def detect_communities(services: list[str], edges: list[tuple[str, str]],
                       seed: int | None = None) -> dict[int, list[str]]:
    """Real Leiden community detection (leidenalg over igraph), modularity objective.
    A service with no REQUIRES edge at all is its own singleton community -- correct, not a
    bug: it genuinely has no structural relationship to anything else yet."""
    import igraph
    import leidenalg

    index = {sid: i for i, sid in enumerate(services)}
    g = igraph.Graph()
    g.add_vertices(len(services))
    g.add_edges([(index[a], index[b]) for a, b in edges if a in index and b in index])

    partition = leidenalg.find_partition(
        g, leidenalg.ModularityVertexPartition,
        seed=seed if seed is not None else 0)

    out: dict[int, list[str]] = {}
    for sid, i in index.items():
        out.setdefault(partition.membership[i], []).append(sid)
    return out


def community_id_for(member_service_ids: list[str]) -> str:
    """A stable id derived from WHO is in the community, not from Leiden's arbitrary index,
    so the same real group of services gets the same id across separate runs."""
    digest = hashlib.sha256(",".join(sorted(member_service_ids)).encode()).hexdigest()[:16]
    return f"comm:{digest}"


# --------------------------------------------------------------------------- summarising

_SUMMARY_SYSTEM = (
    "You write short, factual summaries of a cluster of related Sri Lankan government "
    "services for a knowledge-graph community layer. Use ONLY the facts given. Never state "
    "a fee, document, agency or dependency that is not present in the input. If the facts "
    "are sparse, say so plainly rather than filling in detail. Reply as JSON: "
    '{"summary": "..."} with 2-4 sentences.'
)


def _facts_for_services(session, service_ids: list[str]) -> dict[str, list[dict]]:
    rows = session.run(
        """MATCH (s:Service)-[:HAS_FACT]->(f:Fact) WHERE s.service_id IN $sids AND f.valid_to IS NULL
           OPTIONAL MATCH (s)-[:PROVIDED_BY]->(a:Agency)
           RETURN s.service_id AS sid, f.predicate AS predicate, f.value AS value,
                  f.qualifier AS qualifier, a.name AS agency
           ORDER BY s.service_id, f.predicate""", sids=service_ids)
    out: dict[str, list[dict]] = {sid: [] for sid in service_ids}
    for r in rows:
        out.setdefault(r["sid"], []).append(dict(r))
    return out


def _stub_summary(member_service_ids: list[str], facts_by_service: dict[str, list[dict]]) -> str:
    """Deterministic, zero-cost placeholder used when no LLM client is given -- the mechanism
    (staleness detection, selective regeneration, the escalation guard) is fully real and
    testable without spending language-model quota; only the prose is a stand-in."""
    n_facts = sum(len(v) for v in facts_by_service.values())
    names = ", ".join(sorted(member_service_ids)[:3])
    more = f" and {len(member_service_ids) - 3} more" if len(member_service_ids) > 3 else ""
    return f"Community of {len(member_service_ids)} service(s) ({names}{more}), {n_facts} fact(s) total."


def summarize_community(llm: LLM | None, member_service_ids: list[str],
                        facts_by_service: dict[str, list[dict]]) -> tuple[str, int, int]:
    """(summary, prompt_tokens, completion_tokens). Stub path costs 0 tokens."""
    if llm is None:
        return _stub_summary(member_service_ids, facts_by_service), 0, 0

    lines = []
    for sid in sorted(member_service_ids):
        facts = facts_by_service.get(sid, [])
        if not facts:
            lines.append(f"- {sid}: (no facts recorded yet)")
            continue
        parts = [f"{f['predicate']}={f['value']}" + (f" [{f['qualifier']}]" if f["qualifier"] else "")
                 for f in facts[:8]]
        agency = next((f["agency"] for f in facts if f.get("agency")), None)
        lines.append(f"- {sid}" + (f" ({agency})" if agency else "") + ": " + "; ".join(parts))
    user = "Services in this community:\n" + "\n".join(lines)

    reply: LLMReply = llm.complete(_SUMMARY_SYSTEM, user)
    try:
        summary = json.loads(reply.text).get("summary", "").strip()
    except (ValueError, AttributeError):
        summary = reply.text.strip()[:500]
    return summary or _stub_summary(member_service_ids, facts_by_service), reply.prompt_tokens, reply.completion_tokens


# ---------------------------------------------------------------------------- maintenance

@dataclass
class MaintenanceReport:
    total_communities: int = 0
    dirty_by_membership: int = 0
    dirty_by_value: int = 0
    regenerated: int = 0
    escalated: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stale_services: list[str] = field(default_factory=list)  # should stay empty when the trigger works

    @property
    def clean(self) -> int:
        return self.total_communities - self.regenerated


def _current_membership(session) -> dict[str, str]:
    """service_id -> the community_id it is currently (live edge) assigned to."""
    rows = session.run(
        """MATCH (s:Service)-[r:IN_COMMUNITY]->(c:Community) WHERE r.valid_to IS NULL
           RETURN s.service_id AS sid, c.community_id AS cid""")
    return {r["sid"]: r["cid"] for r in rows}


def _existing_summary(session, community_id: str) -> str | None:
    row = session.run("MATCH (c:Community {community_id: $cid}) RETURN c.summary AS s",
                      cid=community_id).single()
    return row["s"] if row else None


def maintain_communities(
    driver, llm: LLM | None, changed_service_ids: set[str] | None = None,
    detect_value_changes: bool = True, escalation_threshold: float = DEFAULT_ESCALATION_THRESHOLD,
    at: str | None = None, dry_run: bool = False,
) -> MaintenanceReport:
    """Recompute communities over the current graph, then regenerate ONLY the summaries of
    communities that are new (membership-delta) or that contain a service whose fact value
    changed since the last run (value-change) -- the proposal's named second trigger.

    detect_value_changes=False reproduces the literature's status quo (structure-only) for
    use as the "without" side of a with-and-without ablation; True is the proposed method.
    Both run through this exact function, with that flag as the only difference, matching
    the proposal's own validation requirement (Section 3.5, mechanism validity).
    """
    from datetime import datetime, timezone

    at = at or datetime.now(timezone.utc).isoformat()
    changed_service_ids = changed_service_ids or set()
    report = MaintenanceReport()

    with driver.session() as session:
        services, edges = fetch_service_graph(session)
        if not services:
            return report
        partition = detect_communities(services, edges)
        communities = {community_id_for(members): members for members in partition.values()}
        report.total_communities = len(communities)

        previous = _current_membership(session)
        dirty: dict[str, str] = {}  # community_id -> reason

        for cid, members in communities.items():
            existing_summary = _existing_summary(session, cid)
            if existing_summary is None:
                dirty[cid] = "membership"
                continue
            if detect_value_changes and any(m in changed_service_ids for m in members):
                dirty[cid] = "value"

        report.dirty_by_membership = sum(1 for r in dirty.values() if r == "membership")
        report.dirty_by_value = sum(1 for r in dirty.values() if r == "value")

        if communities and len(dirty) / len(communities) > escalation_threshold:
            report.escalated = True
            dirty = {cid: dirty.get(cid, "escalation") for cid in communities}

        if dry_run:
            report.regenerated = len(dirty)
            covered = {m for cid in dirty for m in communities[cid]}
            report.stale_services = sorted(changed_service_ids - covered)
            return report

        ensure_schema(driver)
        facts_by_service = _facts_for_services(session, services)

        for cid, members in communities.items():
            if cid not in dirty:
                continue
            summary, p_tok, c_tok = summarize_community(
                llm, members, {m: facts_by_service.get(m, []) for m in members})
            report.prompt_tokens += p_tok
            report.completion_tokens += c_tok
            report.regenerated += 1

            session.run(
                """MERGE (c:Community {community_id: $cid})
                   SET c.summary = $summary, c.summary_updated_at = datetime($at),
                       c.member_count = $n""",
                cid=cid, summary=summary, at=at, n=len(members))

            for sid in members:
                if previous.get(sid) == cid:
                    continue  # already pointing at this exact community, nothing to move
                if sid in previous:
                    session.run(
                        """MATCH (s:Service {service_id: $sid})-[r:IN_COMMUNITY]->(:Community {community_id: $old})
                           WHERE r.valid_to IS NULL SET r.valid_to = datetime($at)""",
                        sid=sid, old=previous[sid], at=at)
                session.run(
                    """MATCH (s:Service {service_id: $sid}), (c:Community {community_id: $cid})
                       MERGE (s)-[r:IN_COMMUNITY]->(c) ON CREATE SET r.valid_from = datetime($at), r.valid_to = null""",
                    sid=sid, cid=cid, at=at)

        # clean communities whose membership genuinely has no prior edge yet (first run, not
        # regenerated because dry_run was false and they weren't dirty -- shouldn't happen
        # since a never-seen community has no existing_summary and is always dirty -- but a
        # service moving INTO an already-summarised clean community still needs its edge set
        for cid, members in communities.items():
            if cid in dirty:
                continue
            for sid in members:
                if previous.get(sid) == cid:
                    continue
                if sid in previous:
                    session.run(
                        """MATCH (s:Service {service_id: $sid})-[r:IN_COMMUNITY]->(:Community {community_id: $old})
                           WHERE r.valid_to IS NULL SET r.valid_to = datetime($at)""",
                        sid=sid, old=previous[sid], at=at)
                session.run(
                    """MATCH (s:Service {service_id: $sid}), (c:Community {community_id: $cid})
                       MERGE (s)-[r:IN_COMMUNITY]->(c) ON CREATE SET r.valid_from = datetime($at), r.valid_to = null""",
                    sid=sid, cid=cid, at=at)

        covered = {m for cid in dirty for m in communities[cid]}
        report.stale_services = sorted(changed_service_ids - covered)

    return report
