"""Stage 4 community maintenance (SO3). Pure rules run anywhere; the Neo4j tests skip when
Neo4j is not up. Test data lives under throwaway service ids and is removed afterwards.
"""

import uuid
from pathlib import Path

import pytest

from app.core.graph.community import (
    DEFAULT_ESCALATION_THRESHOLD,
    community_id_for,
    detect_communities,
    maintain_communities,
    summarize_community,
)
from app.core.graph.writer import neo4j_from_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]


# ------------------------------------------------------------------- pure rules
def test_community_id_is_stable_regardless_of_member_order():
    assert community_id_for(["a", "b", "c"]) == community_id_for(["c", "a", "b"])


def test_community_id_differs_for_a_different_member_set():
    assert community_id_for(["a", "b"]) != community_id_for(["a", "b", "c"])


def test_detect_communities_separates_disconnected_components():
    services = ["a", "b", "c", "d", "e"]
    edges = [("a", "b"), ("b", "c"), ("d", "e")]
    partition = detect_communities(services, edges)
    groups = sorted(sorted(members) for members in partition.values())
    assert groups == [["a", "b", "c"], ["d", "e"]]


def test_detect_communities_is_deterministic_given_the_same_vertex_order():
    """Real bug found 19 Oct 2026: fetch_service_graph had no ORDER BY, so two real calls
    with the same fixed seed on the same real graph could still produce different vertex
    orderings, and Leiden breaks ties by arrival order -- this churned membership from pure
    measurement noise. detect_communities itself must be stable given a stable input order."""
    services = [f"svc:n{i}" for i in range(40)]
    edges = [(f"svc:n{i}", f"svc:n{i + 1}") for i in range(0, 40, 2) if i + 1 < 40]
    ids_a = sorted(community_id_for(m) for m in detect_communities(services, edges).values())
    ids_b = sorted(community_id_for(m) for m in detect_communities(services, edges).values())
    assert ids_a == ids_b


def test_a_service_with_no_edges_is_its_own_singleton_community():
    partition = detect_communities(["lonely"], [])
    assert list(partition.values()) == [["lonely"]]


def test_stub_summary_costs_nothing_and_names_the_members():
    summary, p_tok, c_tok = summarize_community(None, ["svc:a", "svc:b"], {"svc:a": [], "svc:b": []})
    assert p_tok == 0 and c_tok == 0
    assert "svc:a" in summary and "svc:b" in summary


# ------------------------------------------------------------- against the real graph
@pytest.fixture
def driver():
    from neo4j import GraphDatabase

    conf = neo4j_from_dotenv(REPO_ROOT / ".env")
    if conf is None:
        pytest.skip("no .env with NEO4J_* settings")
    drv = GraphDatabase.driver(conf[0], auth=(conf[1], conf[2]))
    try:
        drv.verify_connectivity()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Neo4j is not reachable: {type(e).__name__}")

    tag = uuid.uuid4().hex[:6]
    a, b = f"svc:zc{tag}a", f"svc:zc{tag}b"
    with drv.session() as s:
        s.run(
            """CREATE (sa:Service {service_id: $a}), (sb:Service {service_id: $b})
               CREATE (sa)-[:REQUIRES {fact_id: $fid, valid_from: datetime(), valid_to: null}]->(sb)
               CREATE (fa:Fact {fact_id: $ffa, predicate: 'fee', value: 'LKR 200', qualifier: '',
                                 valid_from: datetime(), valid_to: null})
               CREATE (sa)-[:HAS_FACT]->(fa)""",
            a=a, b=b, fid=f"{a}:prerequisite:{b}", ffa=f"{a}:fee:")
    yield drv, a, b
    with drv.session() as s:
        s.run(
            """MATCH (n) WHERE n.service_id IN [$a, $b] DETACH DELETE n""", a=a, b=b)
        # communities this tiny test graph produced are throwaway too, but only ones whose
        # ONLY members were these two services -- never touch a real community
        s.run(
            """MATCH (c:Community) WHERE NOT (c)<-[:IN_COMMUNITY]-() DETACH DELETE c""")
    drv.close()


def test_first_run_regenerates_and_a_repeat_run_with_no_change_regenerates_nothing(driver):
    drv, a, b = driver
    first = maintain_communities(drv, llm=None, changed_service_ids=set(), dry_run=False)
    assert first.regenerated >= 1  # at least the community this fixture created

    again = maintain_communities(drv, llm=None, changed_service_ids=set(), dry_run=False)
    # nothing changed anywhere in the graph since 'first' -- real zero-cost re-run
    assert again.regenerated == 0
    assert again.dirty_by_membership == 0
    assert again.dirty_by_value == 0


def test_a_value_change_with_no_structural_change_is_missed_by_the_status_quo_and_caught_by_the_trigger(driver):
    drv, a, b = driver
    maintain_communities(drv, llm=None, changed_service_ids=set(), dry_run=False)  # establish baseline state

    # the exact case the proposal names: a fact's value changes, no node or edge moves
    with drv.session() as s:
        s.run("MATCH (f:Fact {fact_id: $fid}) SET f.value = 'LKR 500'", fid=f"{a}:fee:")

    status_quo = maintain_communities(
        drv, llm=None, changed_service_ids={a}, detect_value_changes=False, dry_run=True)
    assert status_quo.regenerated == 0
    assert a in status_quo.stale_services  # exactly the failure mode the proposal describes

    proposed = maintain_communities(
        drv, llm=None, changed_service_ids={a}, detect_value_changes=True, dry_run=True)
    assert proposed.regenerated >= 1
    assert a not in proposed.stale_services


def test_escalation_guard_falls_back_to_full_regeneration_past_the_threshold(driver):
    drv, a, b = driver
    report = maintain_communities(
        drv, llm=None, changed_service_ids={a, b}, detect_value_changes=True,
        escalation_threshold=0.0, dry_run=True)
    assert report.escalated is True
    assert report.regenerated == report.total_communities


def test_default_escalation_threshold_is_a_minority_not_a_majority():
    assert 0 < DEFAULT_ESCALATION_THRESHOLD < 0.5
