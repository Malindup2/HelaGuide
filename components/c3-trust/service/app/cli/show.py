"""
Show what is stored in C3's database right now. READ-ONLY: it changes nothing and does not load the model.

    python -m app.cli.show                                   overview: table sizes + every fact whose confidence has moved
    python -m app.cli.show --all                             every fact version, even untouched ones
    python -m app.cli.show --fact svc:passport:fee:normal    one fact in detail: versions, reports, audit trail

Use it to show the panel the BEFORE and AFTER state:
    python -m app.cli.reset                   -> then  show   =  BEFORE (every fact at its starting confidence, no reports)
    python -m app.cli.demo                    -> then  show   =  AFTER  (confidence moved, reports and audit trail stored)
"""
import argparse

from sqlalchemy import func, inspect, select

from app.cli._common import banner, mask_url, table, utf8
from app.core import db
from app.core.config import C3Settings
from app.core.exposure import Exposure
from app.core.repo import Repo
from app.core.util import as_utc, iso

S = lambda fid: (fid or "-").replace("svc:", "")
D = lambda dt: "-" if dt is None else as_utc(dt).strftime("%Y-%m-%d")


def counts(engine) -> list[list]:
    out = []
    with engine.connect() as c:
        for t in db.metadata.sorted_tables:
            out.append([t.name, c.execute(select(func.count()).select_from(t)).scalar_one()])
    return out


def overview(engine, repo: Repo, s: C3Settings, show_all: bool) -> None:
    banner("C3 DATABASE: table sizes")
    print(table(["table (schema c3)", "rows"], counts(engine)))
    with engine.connect() as c:
        confs = c.execute(select(db.fact_confidence)).fetchall()
        regs = {(r.fact_id, as_utc(r.valid_from)): r for r in c.execute(select(db.fact_registry)).fetchall()}
        n_reports = {(r.fact_id, as_utc(r.fact_valid_from)): r.n for r in c.execute(
            select(db.reports.c.fact_id, db.reports.c.fact_valid_from, func.count().label("n"))
            .group_by(db.reports.c.fact_id, db.reports.c.fact_valid_from)).fetchall()}
    rows, untouched = [], 0
    for r in sorted(confs, key=lambda r: (r.fact_id, as_utc(r.valid_from))):
        key = (r.fact_id, as_utc(r.valid_from))
        moved = abs(r.confidence - r.base_confidence) > 1e-9 or n_reports.get(key) or r.drop_events or r.verified_by_source
        if not moved:
            untouched += 1
        if moved or show_all:
            reg = regs.get(key)
            rows.append([S(r.fact_id), D(r.valid_from), f"{reg.value_text} {reg.unit or ''}".strip() if reg else "-",
                         f"{r.confidence:.1%}", r.status, n_reports.get(key, 0), r.drop_events,
                         "yes" if r.verified_by_source else ""])
    banner("Fact confidence" + (" (all versions)" if show_all else " (versions that have moved)"))
    if rows:
        print(table(["fact", "version from", "stored value", "confidence", "status", "reports", "drops", "verified by source"], rows))
    if untouched == len(confs) and not show_all:
        print(f"BEFORE STATE: all {len(confs)} fact versions are at their starting confidence "
              f"({s.c_base:.0%}) and no reports are stored.")
        print("(Add --all to list them.)")
    elif untouched and not show_all:
        print(f"\n{untouched} other fact version(s) are untouched, still at their starting confidence. (--all lists them.)")


def detail(engine, repo: Repo, s: C3Settings, fact_id: str) -> None:
    versions = repo.versions(fact_id)
    if not versions:
        print(f"No fact called {fact_id} in the registry.")
        return
    banner(f"{fact_id}: versions (C3 keeps one confidence record per version)")
    rows = []
    for v in versions:
        rec = repo.get_confidence(fact_id, v.valid_from)
        rows.append([D(v.valid_from), D(v.valid_to), f"{v.value_text} {v.unit or ''}".strip(),
                     f"{rec.base_confidence:.0%}", f"{rec.confidence:.1%}", rec.status, rec.drop_events,
                     "yes" if rec.verified_by_source else ""])
    print(table(["from", "to", "stored value", "starts at", "confidence now", "status", "drops", "verified by source"], rows))
    for v in versions:
        reports = repo.reports_for(fact_id, v.valid_from)
        banner(f"Reports about the version starting {D(v.valid_from)} ({len(reports)})", "-")
        if reports:
            print(table(["report", "path", "citizen", "kind", "claim", "trust T", "independence I", "state"],
                        [[r.message_id, r.path, r.reporter_id, r.report_kind, r.claimed_value_raw or "-",
                          f"{r.trust_t:.3f}", f"{r.indep_i:.2f}", r.state] for r in reports]))
        else:
            print("none")
    banner("Audit trail: every change of confidence, with its reason", "-")
    audit = repo.audit_rows(fact_id)
    print(table(["date", "before", "after", "reason"],
                [[D(r["at"]), "-" if r["old"] is None else f"{r['old']:.3f}", f"{r['new']:.3f}", r["reason"]] for r in audit]))
    e = Exposure(repo, s).explain(fact_id)
    banner("What a citizen would be shown right now", "-")
    print(f"{e['confidence_pct']}%   warning: {e['warning_code']}   reports on the current version: {e['report_count']}")


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fact", help="show one fact in detail, e.g. svc:passport:fee:normal")
    ap.add_argument("--all", action="store_true", help="list every fact version, not only those that moved")
    ap.add_argument("--db", help="database URL (default: C3_DATABASE_URL)")
    args = ap.parse_args(argv)
    s = C3Settings(**({"database_url": args.db} if args.db else {}))
    print(f"database: {mask_url(s.database_url)}   (read-only)")
    engine = db.make_engine(s.database_url)
    if "fact_confidence" not in inspect(engine).get_table_names(schema="c3" if db.is_postgres(engine) else None):
        print("\nNo C3 tables yet. Run:  python -m app.cli.reset")
        return
    repo = Repo(engine)
    detail(engine, repo, s, args.fact) if args.fact else overview(engine, repo, s, args.all)


if __name__ == "__main__":
    main()
