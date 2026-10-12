"""Demo: a fee changes and NOTHING ELSE does. Does the pipeline notice?

The claim of Component 2: a value change with identical structure and identical length is
invisible to a trigger that watches structure or size, and it is exactly what a citizen is hurt
by. This script runs the real pipeline code on the real passport page, with ONE controlled
edit (LKR 10,000 to LKR 11,000, same number of characters), and prints each stage.

It writes to a throwaway service id and removes it afterwards, so the real graph is untouched.
The page edit is a controlled change, stated as such: government pages rarely change on demand,
and a known edit is the only way to know what the system should have noticed.

Run from components/c2-knowledge-graph/service (needs Postgres and Neo4j up):
    python ../research/experiments/demo_property_edit.py
    python ../research/experiments/demo_property_edit.py --keep      # leave it in the graph
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
C2_ROOT = HERE.parents[2]
REPO_ROOT = HERE.parents[4]
sys.path.insert(0, str(C2_ROOT / "service"))

from app.core.acquisition.db import dsn_from_dotenv  # noqa: E402
from app.core.acquisition.discover import strip_menus  # noqa: E402
from app.core.acquisition.fingerprint import ChangeKind, classify, fingerprint  # noqa: E402
from app.core.extraction.extractor import ExtractionResult, build_facts  # noqa: E402
from app.core.extraction.ontology import DocumentItem, FeeItem, PageExtraction  # noqa: E402
from app.core.extraction.staging import StagingStore  # noqa: E402
from app.core.graph.review import ReviewStore  # noqa: E402
from app.core.graph.writer import GraphWriter, neo4j_from_dotenv  # noqa: E402

ARCHIVE = C2_ROOT / "research" / "data" / "crawl" / "archive" / "2026-10-10"
PAGE = "fce50cda6cef8adb"  # the passport page, crawled 10 Oct 2026
OLD_LINE = "Normal Basis - LKR. 10,000.00"
NEW_LINE = "Normal Basis - LKR. 11,000.00"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def extraction_for(page_text: str, fee_text: str, fee_line: str) -> PageExtraction:
    """What the model returns for this page, written out so the demo needs no model call.
    Every quote below is a real line of the page; build_facts still checks each one."""
    return PageExtraction(
        fees=[FeeItem(qualifier="Normal Basis", variant="Ordinary Passports",
                      amount_text=fee_text, evidence=fee_line)],
        documents=[
            DocumentItem(name="Original National Identity Card of the applicant",
                         variant="ordinary",
                         evidence="Original National Identity Card of the applicant with a photocopy"),
            DocumentItem(name="Original Birth Certificate of the applicant", variant="ordinary",
                         evidence="Original Birth Certificate of the applicant with a photocopy"),
        ],
    )


def topology(driver, svc: str) -> dict:
    """The graph's SHAPE for this service: nodes and links, not their values."""
    with driver.session() as s:
        rows = s.run(
            """MATCH (x:Service {service_id: $s})
               OPTIONAL MATCH (x)-[r:REQUIRES|REQUIRES_DOCUMENT|PROVIDED_BY]->(t)
               WHERE r.valid_to IS NULL
               RETURN count(DISTINCT t) AS nodes, count(r) AS edges""", s=svc).single()
    return {"linked nodes": rows["nodes"], "links": rows["edges"]}


def versions(driver, fact_id: str) -> list[dict]:
    with driver.session() as s:
        return s.run(
            """MATCH (f:Fact {fact_id: $f})
               RETURN f.value AS value, toString(f.valid_from) AS valid_from,
                      toString(f.valid_to) AS valid_to ORDER BY f.valid_from""", f=fact_id).data()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--keep", action="store_true", help="leave the demo service in the graph")
    args = ap.parse_args()

    dsn = dsn_from_dotenv(REPO_ROOT / ".env")
    conf = neo4j_from_dotenv(REPO_ROOT / ".env")
    if dsn is None or conf is None:
        print("needs POSTGRES_* and NEO4J_* in the repo .env")
        return 1

    tag = uuid.uuid4().hex[:6]
    svc = f"svc:demo{tag}"
    host = f"demo-{tag}.invalid"
    url = f"https://{host}/passport"
    t0 = datetime.now(timezone.utc)

    html_old = (ARCHIVE / f"{PAGE}.html").read_text(encoding="utf-8")
    md_old = (ARCHIVE / f"{PAGE}.md").read_text(encoding="utf-8")
    assert OLD_LINE in md_old and "LKR. 10,000.00" in html_old, "the archived page changed"
    md_new = md_old.replace(OLD_LINE, NEW_LINE, 1)
    html_new = html_old.replace("LKR. 10,000.00", "LKR. 11,000.00", 1)

    # --------------------------------------------------------------------------- 1
    rule("1. THE PAGE CHANGES: one fee, 10,000 -> 11,000 (same length, same markup)")
    print(f"  before: {OLD_LINE}\n  after : {NEW_LINE}")
    a, b = fingerprint(md_old, html_old), fingerprint(md_new, html_new)
    verdict = classify(a, b)
    print(f"\n  characters          : {a.char_count} -> {b.char_count}   (change: {b.char_count - a.char_count:+d})")
    print(f"  page structure hash : {'IDENTICAL' if a.structure_hash == b.structure_hash else 'different'}")
    print(f"  content hash        : {'IDENTICAL' if a.content_hash == b.content_hash else 'DIFFERENT'}")
    print(f"  similarity distance : {verdict.detail.get('simhash_distance')} bits (never used as a gate)")
    print("\n  a trigger that watches SIZE or STRUCTURE concludes : nothing changed")
    print(f"  this pipeline concludes                            : {verdict.kind.value}")
    assert verdict.kind is ChangeKind.CONTENT_CHANGED

    # --------------------------------------------------------------------------- 2
    rule("2. VERSION 1 goes through the gate and into the graph")
    stage, review = StagingStore(dsn), ReviewStore(dsn)
    writer = GraphWriter(dsn, *conf)
    try:
        facts, dropped = build_facts(
            extraction_for(md_old, "LKR. 10,000.00", OLD_LINE), strip_menus(md_old), svc, url,
            t0.isoformat(timespec="seconds"))
        stage.save(url, ExtractionResult(facts=facts, dropped=dropped, model="demo"), svc, "Demo")
        print(f"  staged {len(facts)} fact(s), {len(dropped)} dropped for a missing quote")
        ids = [f.staged_id for f in review.pending(svc)]
        review.decide_many(ids, "approved", "demo", "version 1, checked against the page")
        r1 = writer.write_approved(service_id=svc)
        print(f"  approved and written: {r1.new} new fact(s)")
        topo1 = topology(writer.driver, svc)
        fid = f"{svc}:fee:ordinary_normal"
        print(f"\n  graph shape now : {topo1}")
        for v in versions(writer.driver, fid):
            print(f"  fee version     : {v['value']:<16} valid_from {v['valid_from'][:19]}  valid_to {v['valid_to']}")

        # ----------------------------------------------------------------------- 3
        rule("3. VERSION 2 arrives: only the fee differs, so only the fee needs a decision")
        t1 = t0 + timedelta(days=9)
        facts2, dropped2 = build_facts(
            extraction_for(md_new, "LKR. 11,000.00", NEW_LINE), strip_menus(md_new), svc, url,
            t1.isoformat(timespec="seconds"))
        stage.save(url, ExtractionResult(facts=facts2, dropped=dropped2, model="demo"), svc, "Demo")
        pending = review.pending(svc)
        print(f"  facts in version 2          : {len(facts2)}")
        print(f"  waiting for a decision      : {len(pending)}   (the other {len(facts2) - len(pending)} are unchanged, skipped)")
        for f in pending:
            print(f"    #{f.staged_id}  {f.fact_id.replace(svc + ':', '')}   now {f.value_text}   "
                  f"(graph holds: {f.old_value})")

        # ----------------------------------------------------------------------- 4
        rule("4. YOU APPROVE: the graph versions it, nothing is overwritten")
        review.decide_many([f.staged_id for f in pending], "approved", "demo",
                           "the page now states 11,000; checked")
        r2 = writer.write_approved(service_id=svc)
        print(f"  written: {r2.new} new, {r2.changed} changed, {r2.same} unchanged")
        topo2 = topology(writer.driver, svc)
        print(f"\n  graph shape before : {topo1}")
        print(f"  graph shape after  : {topo2}   -> {'IDENTICAL' if topo1 == topo2 else 'different'}")
        print("\n  fee history:")
        for v in versions(writer.driver, fid):
            state = "current" if v["valid_to"] is None else f"closed {v['valid_to'][:10]}"
            print(f"    {v['value']:<16} from {v['valid_from'][:10]}   {state}")

        rule("RESULT")
        print("  The graph's structure did not change. A structure-only trigger would have")
        print("  regenerated nothing and kept serving 10,000. Here the old fee is closed, the")
        print("  new one is current, the decision is audited, and the citizen-facing answer")
        print("  reads the current version.")
        hist = review.history(fid)
        print(f"\n  audit trail for {fid.replace(svc + ':', '')}:")
        for when, decision, who, why, staged_id in hist:
            print(f"    {when:%Y-%m-%d %H:%M}  {decision:<9} by {who:<6} #{staged_id}  {why}")
    finally:
        if not args.keep:
            import psycopg

            with writer.driver.session() as s:
                s.run("MATCH (n) WHERE n.service_id = $s OR n.url = $u "
                      "OR (n:Fact AND n.fact_id STARTS WITH $p) DETACH DELETE n", s=svc, u=url, p=svc + ":")
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute("DELETE FROM c2.staged_facts WHERE source_url = %s", (url,))
                c.execute("DELETE FROM c2.extractions WHERE source_url = %s", (url,))
                c.execute("DELETE FROM c2.pages WHERE url = %s", (url,))
                c.execute("DELETE FROM c2.sources WHERE host = %s", (host,))
            print(f"\n  (demo data {svc} removed; the real graph was not touched)")
        stage.close()
        review.close()
        writer.close()
    return 0


if __name__ == "__main__":
    t = time.perf_counter()
    code = main()
    print(f"\n  finished in {time.perf_counter() - t:.1f} s, no language-model call")
    sys.exit(code)
