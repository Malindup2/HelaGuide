"""The graph writer. Pure rules run anywhere; the Neo4j tests skip when Neo4j or Postgres is not up.

Test data lives under a throwaway service id and is removed afterwards.
"""

import uuid
from pathlib import Path

import pytest

from app.core.graph.writer import decide_version, neo4j_from_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
WHEN1 = "2026-10-11T08:00:00+00:00"
WHEN2 = "2026-10-20T08:00:00+00:00"


# ------------------------------------------------------------------- pure rules
def test_version_decision():
    assert decide_version(None, "LKR 10,000") == "new"
    assert decide_version("LKR 10,000", "LKR 10,000") == "same"
    assert decide_version("LKR 10,000", "LKR 11,000") == "changed"


def test_container_neo4j_host_is_rewritten_for_the_host_machine(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NEO4J_URI=bolt://neo4j:7687\nNEO4J_USER=neo4j\nNEO4J_PASSWORD=pw\n", encoding="utf-8")
    assert neo4j_from_dotenv(env) == ("bolt://localhost:7687", "neo4j", "pw")
    assert neo4j_from_dotenv(tmp_path / "missing.env") is None


# ------------------------------------------------------------- against the real stores
@pytest.fixture
def stack():
    from app.core.acquisition.db import dsn_from_dotenv
    from app.core.graph.writer import GraphWriter

    dsn = dsn_from_dotenv(REPO_ROOT / ".env")
    conf = neo4j_from_dotenv(REPO_ROOT / ".env")
    if dsn is None or conf is None:
        pytest.skip("no .env with POSTGRES_* and NEO4J_* settings")
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=3) as c:
            c.execute("SELECT written_at FROM c2.staged_facts LIMIT 1")
        writer = GraphWriter(dsn, *conf)
        writer.driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"Neo4j or the c2 review tables are not reachable: {type(e).__name__}")

    tag = uuid.uuid4().hex[:6]
    svc, target = f"svc:zt{tag}", f"svc:zn{tag}"
    host = f"pgtest-{tag}.invalid"
    url = f"https://{host}/p"
    yield writer, dsn, svc, target, url
    with writer.driver.session() as s:
        s.run("MATCH (n) WHERE n.service_id IN [$a, $b] OR n.url = $u "
              "OR (n:Fact AND n.fact_id STARTS WITH $p) OR (n:Agency AND n.name = $ag) "
              "OR (n:Document AND n.document_key STARTS WITH $dk) DETACH DELETE n",
              a=svc, b=target, u=url, p=svc, ag=f"Agency {tag}", dk=f"zt{tag}")
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("DELETE FROM c2.staged_facts WHERE source_url = %s", (url,))
        c.execute("DELETE FROM c2.extractions WHERE source_url = %s", (url,))
        c.execute("DELETE FROM c2.pages WHERE url = %s", (url,))
        c.execute("DELETE FROM c2.sources WHERE host = %s", (host,))
    writer.close()


def stage(writer, svc, url, rows, when, status="approved"):
    import json

    ids = []
    for predicate, qualifier, value, num, detail in rows:
        r = writer.conn.execute(
            """INSERT INTO c2.staged_facts (fact_id, service_id, predicate, qualifier, value_text,
                   value_num, unit, detail, source_url, retrieved_at, evidence, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING staged_id""",
            (f"{svc}:{predicate}:{qualifier}" if qualifier else f"{svc}:{predicate}", svc, predicate,
             qualifier, value, num, "LKR" if num else None, json.dumps(detail), url, when,
             f"{value} on the page", status)).fetchone()
        ids.append(r[0])
    return ids


def graph_value(writer, cypher, **params):
    with writer.driver.session() as s:
        return s.run(cypher, **params).data()


def test_approved_facts_become_nodes_and_edges_and_are_marked_written(stack):
    writer, _, svc, target, url = stack
    stage(writer, svc, url, [
        ("fee", "ordinary_normal", "LKR. 10,000.00", 10000, {"kind": "base"}),
        ("document", f"zt{svc[-6:]}_nic", "National Identity Card", None,
         {"applies_to": ["ordinary"], "service_id": target}),
        ("prerequisite", f"zt{svc[-6:]}_nic", target, None,
         {"origin": "derived_from_document", "requires_service": target, "applies_to": ["ordinary"]}),
    ], WHEN1)
    report = writer.write_approved(service_id=svc)
    assert (report.new, report.changed, report.same, report.failed) == (3, 0, 0, [])

    rows = graph_value(writer, "MATCH (s:Service {service_id:$s})-[:HAS_FACT]->(f:Fact) "
                               "RETURN f.fact_id AS id, f.value_num AS n, f.valid_to AS vt", s=svc)
    fee = next(r for r in rows if r["id"].endswith("fee:ordinary_normal"))
    assert fee["n"] == 10000.0 and fee["vt"] is None
    req = graph_value(writer, "MATCH (:Service {service_id:$s})-[r:REQUIRES]->(t:Service) "
                              "RETURN t.service_id AS t, r.applies_to AS a", s=svc)
    assert req == [{"t": target, "a": ["ordinary"]}]
    left = writer.conn.execute(
        "SELECT count(*) FROM c2.staged_facts WHERE source_url = %s AND written_at IS NULL",
        (url,)).fetchone()[0]
    assert left == 0


def test_unapproved_facts_never_reach_the_graph(stack):
    writer, _, svc, _, url = stack
    stage(writer, svc, url, [("fee", "urgent", "LKR 20,000", 20000, {})], WHEN1, status="pending")
    stage(writer, svc, url, [("fee", "express", "LKR 30,000", 30000, {})], WHEN1, status="rejected")
    report = writer.write_approved(service_id=svc)
    assert report.written == 0
    assert graph_value(writer, "MATCH (f:Fact) WHERE f.fact_id STARTS WITH $p RETURN f", p=svc) == []


def test_writing_twice_changes_nothing(stack):
    writer, _, svc, _, url = stack
    stage(writer, svc, url, [("fee", "normal", "LKR 10,000", 10000, {})], WHEN1)
    assert writer.write_approved(service_id=svc).new == 1
    assert writer.write_approved(service_id=svc).written == 0
    n = graph_value(writer, "MATCH (f:Fact {fact_id:$f}) RETURN count(f) AS n", f=f"{svc}:fee:normal")
    assert n == [{"n": 1}]


def test_a_changed_value_closes_the_old_version_and_opens_a_new_one(stack):
    writer, _, svc, _, url = stack
    stage(writer, svc, url, [("fee", "normal", "LKR 10,000", 10000, {})], WHEN1)
    writer.write_approved(service_id=svc)
    stage(writer, svc, url, [("fee", "normal", "LKR 11,000", 11000, {})], WHEN2)
    report = writer.write_approved(service_id=svc)
    assert (report.new, report.changed) == (0, 1)

    versions = graph_value(
        writer, "MATCH (f:Fact {fact_id:$f}) RETURN f.value AS v, f.valid_to IS NULL AS current "
                "ORDER BY f.valid_from", f=f"{svc}:fee:normal")
    assert versions == [{"v": "LKR 10,000", "current": False}, {"v": "LKR 11,000", "current": True}]


def test_a_changed_prerequisite_closes_its_edge(stack):
    writer, _, svc, target, url = stack
    d1 = {"origin": "stated", "requires_service": target}
    stage(writer, svc, url, [("prerequisite", "needs", target, None, d1)], WHEN1)
    writer.write_approved(service_id=svc)
    d2 = {"origin": "stated", "requires_service": target + "x"}
    stage(writer, svc, url, [("prerequisite", "needs", target + "x", None, d2)], WHEN2)
    writer.write_approved(service_id=svc)
    open_edges = graph_value(writer, "MATCH (:Service {service_id:$s})-[r:REQUIRES]->(t) "
                                     "WHERE r.valid_to IS NULL RETURN t.service_id AS t", s=svc)
    assert open_edges == [{"t": target + "x"}]
    with writer.driver.session() as s:
        s.run("MATCH (n:Service {service_id:$s}) DETACH DELETE n", s=target + "x")


def test_a_form_link_becomes_a_form_node_hanging_off_the_service(stack):
    writer, _, svc, _, url = stack
    stage(writer, svc, url, [
        ("document", f"zt{svc[-6:]}_application", "Duly completed application", None,
         {"applies_to": ["ordinary"], "forms": [
             {"label": "Form D.R.P/1,7,8", "url": f"{url}/application.pdf", "kind": "form"}]}),
    ], WHEN1)
    assert writer.write_approved(service_id=svc).new == 1
    rows = graph_value(writer, "MATCH (:Service {service_id:$s})-[r:USES_FORM]->(f:Form) "
                               "RETURN f.url AS url, f.label AS label, r.valid_to IS NULL AS open", s=svc)
    assert rows == [{"url": f"{url}/application.pdf", "label": "Form D.R.P/1,7,8", "open": True}]
    with writer.driver.session() as s:  # the Form node is shared and is not part of the cleanup
        s.run("MATCH (f:Form {url: $u}) DETACH DELETE f", u=f"{url}/application.pdf")


def test_an_agency_written_slightly_differently_joins_the_existing_one():
    from app.core.graph.writer import canonical_agency

    known = ["Department for Registration of Persons", "Registrar General's Department"]
    assert canonical_agency("Department of Registration of Persons", known) == known[0]
    assert canonical_agency("Department for Registrations of Persons", known) == known[0]
    assert canonical_agency("Department of Immigration and Emigration", known) == \
        "Department of Immigration and Emigration"   # a different agency stays different


def test_a_trailing_country_name_still_matches_the_known_agency():
    from app.core.graph.writer import canonical_agency

    known = ["Inland Revenue Department"]
    assert canonical_agency("Inland Revenue Department Sri Lanka", known) == known[0]
    assert canonical_agency("Inland Revenue Department", ["Inland Revenue Department Sri Lanka"]) \
        == "Inland Revenue Department Sri Lanka"


def test_a_known_duplicate_service_id_canonicalizes_to_its_real_one():
    from app.core.graph.writer import canonical_service

    assert canonical_service("svc:tourist_vat_refund_scheme_tvrs") == "svc:tourist_vat_refund_scheme"
    assert canonical_service("svc:nic") == "svc:nic"  # untouched, no alias
