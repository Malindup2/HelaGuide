"""The graph writer: approved facts go into Neo4j, and only approved facts.

Model (matches infra/neo4j/constraints.cypher):

    (Service {service_id}) -[:HAS_FACT]-> (Fact {fact_id, value, valid_from, valid_to, ...})
    (Fact) -[:FROM_SOURCE]-> (SourcePage {url})
    (Service) -[:PROVIDED_BY {fact_id}]-> (Agency {agency_id, name})
    (Service) -[:REQUIRES_DOCUMENT {fact_id, applies_to}]-> (Document {document_key, name})
    (Service) -[:USES_FORM {fact_id, document_key}]-> (Form {url, label})
    (Service) -[:REQUIRES {fact_id, origin, applies_to}]-> (Service)      the ordering edge

Versioning: a Fact node is one version of one position. A changed value closes the current
node (valid_to) and opens a new one; an unchanged value writes nothing. The relationships a
fact created carry its fact_id, so closing a fact closes its edges too.

Idempotent: a fact is marked written in PostgreSQL only after Neo4j accepted it, and a fact
Neo4j already holds at the same value is skipped, so a half-finished run can simply be re-run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core.acquisition.db import PageRegistry, read_dotenv
from app.core.extraction.ontology import slug

CONSTRAINTS = (
    "CREATE CONSTRAINT service_id IF NOT EXISTS FOR (s:Service) REQUIRE s.service_id IS UNIQUE",
    "CREATE CONSTRAINT agency_id IF NOT EXISTS FOR (a:Agency) REQUIRE a.agency_id IS UNIQUE",
    "CREATE CONSTRAINT document_key IF NOT EXISTS FOR (d:Document) REQUIRE d.document_key IS UNIQUE",
    "CREATE CONSTRAINT page_url IF NOT EXISTS FOR (p:SourcePage) REQUIRE p.url IS UNIQUE",
    "CREATE CONSTRAINT form_url IF NOT EXISTS FOR (f:Form) REQUIRE f.url IS UNIQUE",
    "CREATE INDEX fact_id IF NOT EXISTS FOR (f:Fact) ON (f.fact_id)",
    "CREATE INDEX fact_current IF NOT EXISTS FOR (f:Fact) ON (f.fact_id, f.valid_to)",
)


def neo4j_from_dotenv(path: Path) -> tuple[str, str, str] | None:
    """(uri, user, password) for a client on the host. The .env URI names the docker network
    host 'neo4j'; from the host the published port is on localhost."""
    env = read_dotenv(path)
    if "NEO4J_PASSWORD" not in env:
        return None
    uri = env.get("NEO4J_URI", "bolt://localhost:7687").replace("//neo4j:", "//localhost:")
    return uri, env.get("NEO4J_USER", "neo4j"), env["NEO4J_PASSWORD"]


def decide_version(current_value: str | None, new_value: str) -> str:
    """'new' (nothing there), 'same' (skip) or 'changed' (close the old version, open a new)."""
    if current_value is None:
        return "new"
    return "same" if current_value == new_value else "changed"


@dataclass
class WriteReport:
    new: int = 0
    changed: int = 0
    same: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)
    by_predicate: dict[str, int] = field(default_factory=dict)

    @property
    def written(self) -> int:
        return self.new + self.changed


AUTO_REVIEWER = "auto-rules"  # same name autoreview.py records; kept here to avoid an import cycle


_AGENCY_STOP = {"of", "for", "the", "and", "&", "in"}


def _agency_key(name: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    return frozenset((w[:-1] if len(w) > 4 and w.endswith("s") else w) for w in words
                     if w not in _AGENCY_STOP)


def canonical_agency(name: str, known: list[str]) -> str:
    """A page may write the agency's name slightly differently ("Department of Registration of
    Persons"). If an agency with the same words already exists, use its name, so one agency is
    never split in two."""
    key = _agency_key(name)
    for k in known:
        if _agency_key(k) == key:
            return k
    return name


def _agency_id(name: str) -> str:
    return f"agency:{slug(name, 60)}"


def _write_fact(tx, f: dict) -> str:
    """One approved fact, one transaction. Returns 'new', 'same' or 'changed'."""
    sid = f["service_id"]
    tx.run("MERGE (s:Service {service_id: $sid})", sid=sid)
    tx.run("MERGE (p:SourcePage {url: $url})", url=f["source_url"])

    current = tx.run(
        "MATCH (x:Fact {fact_id: $fid}) WHERE x.valid_to IS NULL "
        "RETURN x.value AS value, elementId(x) AS eid",
        fid=f["fact_id"]).single()
    verdict = decide_version(current["value"] if current else None, f["value_text"])
    if verdict == "same":
        return verdict

    if current is not None:  # close the old version and every edge it created
        tx.run("MATCH (x) WHERE elementId(x) = $eid SET x.valid_to = datetime($at)",
               eid=current["eid"], at=f["retrieved_at"])
        tx.run("MATCH ()-[r {fact_id: $fid}]->() WHERE r.valid_to IS NULL "
               "SET r.valid_to = datetime($at)", fid=f["fact_id"], at=f["retrieved_at"])

    detail = f["detail"] or {}
    tx.run(
        """MATCH (s:Service {service_id: $sid}), (p:SourcePage {url: $url})
           CREATE (n:Fact {fact_id: $fid, predicate: $pred, qualifier: $qual, value: $value,
                           value_num: $num, unit: $unit, evidence: $evidence,
                           detail_json: $detail, staged_id: $staged, review: $review,
                           valid_from: datetime($at), valid_to: null})
           CREATE (s)-[:HAS_FACT]->(n)
           CREATE (n)-[:FROM_SOURCE]->(p)""",
        sid=sid, url=f["source_url"], fid=f["fact_id"], pred=f["predicate"], qual=f["qualifier"],
        value=f["value_text"], num=f["value_num"], unit=f["unit"], evidence=f["evidence"],
        detail=json.dumps(detail, ensure_ascii=False), staged=f["staged_id"], at=f["retrieved_at"],
        review="auto" if f.get("reviewer") == AUTO_REVIEWER else "human")

    pred = f["predicate"]
    if pred == "agency":
        known = [r["name"] for r in tx.run("MATCH (a:Agency) RETURN a.name AS name") if r["name"]]
        f = dict(f, value_text=canonical_agency(f["value_text"], known))
        tx.run(
            """MATCH (s:Service {service_id: $sid})
               MERGE (a:Agency {agency_id: $aid}) SET a.name = $name
               CREATE (s)-[:PROVIDED_BY {fact_id: $fid, valid_from: datetime($at), valid_to: null}]->(a)""",
            sid=sid, aid=_agency_id(f["value_text"]), name=f["value_text"], fid=f["fact_id"],
            at=f["retrieved_at"])
    elif pred == "document":
        tx.run(
            """MATCH (s:Service {service_id: $sid})
               MERGE (d:Document {document_key: $key})
               ON CREATE SET d.name = $name
               CREATE (s)-[:REQUIRES_DOCUMENT {fact_id: $fid, applies_to: $applies,
                         applies_to_all: $all, valid_from: datetime($at), valid_to: null}]->(d)""",
            sid=sid, key=f["qualifier"], name=f["value_text"], fid=f["fact_id"],
            applies=detail.get("applies_to") or [], all=bool(detail.get("applies_to_all", False)),
            at=f["retrieved_at"])
        for form in detail.get("forms") or []:
            # The form belongs to what THIS service asks for, so the link hangs off the service.
            tx.run(
                """MATCH (s:Service {service_id: $sid})
                   MERGE (f:Form {url: $url})
                   ON CREATE SET f.label = $label
                   CREATE (s)-[:USES_FORM {fact_id: $fid, document_key: $key,
                                           valid_from: datetime($at), valid_to: null}]->(f)""",
                sid=sid, url=form["url"], label=form.get("label") or "", fid=f["fact_id"],
                key=f["qualifier"], at=f["retrieved_at"])
    elif pred == "prerequisite" and detail.get("requires_service"):
        tx.run(
            """MATCH (s:Service {service_id: $sid})
               MERGE (t:Service {service_id: $target})
               CREATE (s)-[:REQUIRES {fact_id: $fid, origin: $origin, applies_to: $applies,
                         applies_to_all: $all, valid_from: datetime($at), valid_to: null}]->(t)""",
            sid=sid, target=detail["requires_service"], fid=f["fact_id"],
            origin=detail.get("origin", "stated"), applies=detail.get("applies_to") or [],
            all=bool(detail.get("applies_to_all", False)), at=f["retrieved_at"])
    return verdict


class GraphWriter:
    def __init__(self, pg_dsn: str, uri: str, user: str, password: str) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as e:  # pragma: no cover
            raise RuntimeError('neo4j driver is missing: pip install -e ".[graph]"') from e
        self.registry = PageRegistry(pg_dsn)
        self.conn = self.registry.conn
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()
        self.registry.close()

    def ensure_schema(self) -> None:
        with self.driver.session() as session:
            for statement in CONSTRAINTS:
                session.run(statement).consume()

    def _approved_unwritten(self, limit: int | None, service_id: str | None) -> list[dict]:
        rows = self.conn.execute(
            """SELECT s.staged_id, s.fact_id, s.service_id, s.predicate, s.qualifier, s.value_text,
                      s.value_num, s.unit, s.detail, s.source_url, s.retrieved_at, s.evidence,
                      (SELECT l.reviewer FROM c2.review_log l WHERE l.staged_id = s.staged_id
                        ORDER BY l.decided_at DESC LIMIT 1) AS reviewer
               FROM c2.staged_facts s
               WHERE s.status = 'approved' AND s.written_at IS NULL
                 AND (%s::text IS NULL OR s.service_id = %s)
               ORDER BY s.staged_id LIMIT %s""",
            (service_id, service_id, limit or 100000),
        ).fetchall()
        keys = ("staged_id", "fact_id", "service_id", "predicate", "qualifier", "value_text",
                "value_num", "unit", "detail", "source_url", "retrieved_at", "evidence", "reviewer")
        out = []
        for r in rows:
            d = dict(zip(keys, r, strict=True))
            d["value_num"] = float(d["value_num"]) if d["value_num"] is not None else None
            d["retrieved_at"] = d["retrieved_at"].isoformat()
            out.append(d)
        return out

    def write_approved(self, service_id: str | None = None, limit: int | None = None,
                       dry_run: bool = False) -> WriteReport:
        report = WriteReport()
        facts = self._approved_unwritten(limit, service_id)
        if dry_run:
            report.new = len(facts)
            for f in facts:
                report.by_predicate[f["predicate"]] = report.by_predicate.get(f["predicate"], 0) + 1
            return report
        self.ensure_schema()
        with self.driver.session() as session:
            for f in facts:
                try:
                    verdict = session.execute_write(_write_fact, f)
                except Exception as e:  # keep going; this fact stays unwritten and is retried
                    report.failed.append((f["staged_id"], f"{type(e).__name__}: {str(e)[:100]}"))
                    continue
                self.conn.execute(
                    "UPDATE c2.staged_facts SET written_at = now() WHERE staged_id = %s",
                    (f["staged_id"],))
                setattr(report, verdict, getattr(report, verdict) + 1)
                if verdict != "same":
                    report.by_predicate[f["predicate"]] = report.by_predicate.get(f["predicate"], 0) + 1
        return report

    def summary(self) -> dict:
        with self.driver.session() as session:
            def count(q):
                return session.run(q).single()["n"]
            return {
                "services": count("MATCH (s:Service) RETURN count(s) AS n"),
                "agencies": count("MATCH (a:Agency) RETURN count(a) AS n"),
                "documents": count("MATCH (d:Document) RETURN count(d) AS n"),
                "facts (current)": count("MATCH (f:Fact) WHERE f.valid_to IS NULL RETURN count(f) AS n"),
                "facts (all versions)": count("MATCH (f:Fact) RETURN count(f) AS n"),
                "REQUIRES edges": count("MATCH ()-[r:REQUIRES]->() WHERE r.valid_to IS NULL RETURN count(r) AS n"),
            }
