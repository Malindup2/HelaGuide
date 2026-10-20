"""
Ablation study: switch ONE part of the trust and confidence logic off and show what changes.

    python -m app.cli.ablation                       all four ablations, as tables in the terminal
    python -m app.cli.ablation --only independence   one of: independence, aggregation, reputation, age-recency
    python -m app.cli.ablation --html                also write research/experiments/out/pp1_ablation.html and open it
    python -m app.cli.ablation --html --no-open      write the page without opening it

An ablation removes one component (or swaps it for a naive version) and compares the result with the full
system on the same scenario. If the result gets worse, the component earns its place.

  1. Independence weighting off (rho = 1.0)   copies would flag a correct fact
  2. Arithmetic mean instead of geometric     a new, vague report would count too much
  3. Reputation off (weight 0)                an unreliable citizen would count as much as a reliable one
  4. Account age off / visit recency off      old and one-off accounts, old and fresh visits, would count equally

Every scenario runs on its own clean in-memory database with hand-made citizens, so no Docker and no model download
are needed. The reports arrive through the contract path (the fact is named), so grounding plays no part: only the
part being switched off differs between the two columns. The copy scenario uses IDENTICAL texts, where the choice of
embedding model makes no difference. Add --embedding sbert to use the real model anyway.
"""
import argparse
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.cli._common import banner, table, utf8
from app.core.config import C3Settings
from app.core.pipeline import Pipeline
from app.core.util import iso
from app.models.internal import Reporter

FACT = "svc:passport:fee:normal"                  # stored value 11,000 LKR; every report below claims 12,000
NOW = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
SPECIFIC = ("I paid Rs. 12,000 for the normal passport at the Immigration office in Battaramulla yesterday. "
            "The guide says 11,000.")
VAGUE = "I think the passport fee is different from what your guide says."
COPY = ("I went to the Department of Immigration yesterday and the normal passport fee at the counter was Rs. 12,000, "
        "not 11,000 as your guide said.")


@dataclass
class Cit:
    """A hand-made citizen: a reputation history (a, b) and the age of the account in days."""
    name: str
    a: float = 0.0
    b: float = 0.0
    age_days: float = 200.0


@dataclass
class Rep:
    cit: Cit
    text: str = SPECIFIC
    visit_days_ago: int | None = 1
    claim: float | None = 12000


def run(reports: list[Rep], embedding: str = "hash", **override) -> list[dict]:
    """Process the reports one after another on a clean database; return the outcome of each."""
    s = C3Settings(database_url="sqlite://", embedding_backend=embedding, **override)
    p = Pipeline.build(s, reset=True)
    p.sync_facts()
    out = []
    for i, r in enumerate(reports):
        rid = f"anon-{r.cit.name}"
        p.repo.upsert_reporter(Reporter(reporter_id=rid, created_at=NOW - timedelta(days=r.cit.age_days),
                                        a=r.cit.a, b=r.cit.b))
        when = NOW + timedelta(minutes=i)
        fb = {"feedback_id": f"ab-{i}", "session_id": rid, "fact_id": FACT, "text": r.text,
              "submitted_at": iso(when), "proposed_value": r.claim}
        extras = {"visit_date": (NOW.date() - timedelta(days=r.visit_days_ago)).isoformat()
                  if r.visit_days_ago is not None else None}
        res = p.process_structured(fb, extras)
        out.append({"T": res.trust["T"], "I": res.independence["I"], "pct": 100 * res.confidence["new"],
                    "status": res.confidence["status"], "E": res.confidence["E"], "state": res.state})
    return out


def pct(x: float) -> str:
    return f"{x:.1f}%"


# ---------------------------------------------------------------------------------------------- the four ablations
def independence(embedding: str) -> dict:
    copies = [Rep(Cit(f"copy{i}", age_days=30), COPY) for i in range(5)]
    full, off = run(copies, embedding), run(copies, embedding, rho=1.0)
    rows = [[f"copy {i + 1}", f"{full[i]['I']:.2f}", f"{off[i]['I']:.2f}", pct(full[i]["pct"]), pct(off[i]["pct"])]
            for i in range(5)]
    last_f, last_o = full[-1], off[-1]
    return {
        "key": "independence", "title": "INDEPENDENCE WEIGHTING OFF (rho = 1.0)",
        "scenario": "Five new accounts (30 days old, no history) paste the same complaint: the passport fee is 12,000, "
                    "not 11,000. Ten pastes are one observation repeated, not ten observations.",
        "tables": [("Confidence in the passport fee after each copy",
                    ["report", "weight (full)", "weight (ablated)", "confidence (full)", "confidence (ablated)"], rows),
                   ("After all five copies", ["version", "confidence", "status", "evidence E"],
                    [["full system", pct(last_f["pct"]), last_f["status"], f"{last_f['E']:.2f}"],
                     ["independence off", pct(last_o["pct"]), last_o["status"], f"{last_o['E']:.2f}"]])],
        "proves": f"Without independence weighting, five copies of one message push a correct fact down to "
                  f"{pct(last_o['pct'])} ({last_o['status']}). With it the fact stays at {pct(last_f['pct'])} "
                  f"({last_f['status']}): copies are not extra witnesses.",
        "summary": ("copies: confidence after 5 pasted copies", pct(last_f["pct"]), pct(last_o["pct"])),
        "check": last_o["pct"] < last_f["pct"] and last_o["status"] == "flagged" and last_f["status"] != "flagged",
    }


def aggregation(embedding: str) -> dict:
    vague = Rep(Cit("firstseen", age_days=0), VAGUE, visit_days_ago=None, claim=None)
    strong = Rep(Cit("veteran", a=6, age_days=200), SPECIFIC)
    stale = Rep(Cit("oldvisit", a=6, age_days=200), SPECIFIC, visit_days_ago=60)
    cases = (("vague report, brand-new account", vague), ("specific report, established citizen", strong),
             ("excellent citizen, visit 60 days ago", stale))
    rows, info = [], {}
    for name, rep in cases:
        g, a = run([rep], embedding)[0], run([rep], embedding, trust_mean="arithmetic")[0]
        info[name] = (g, a)
        rows.append([name, f"{g['T']:.3f}", f"{a['T']:.3f}", pct(g["pct"]), pct(a["pct"])])
    gv, av = info[cases[0][0]]
    gs, as_ = info[cases[1][0]]
    gt, at = info[cases[2][0]]
    return {
        "key": "aggregation", "title": "ARITHMETIC MEAN INSTEAD OF GEOMETRIC",
        "scenario": "The trust score combines four signals. A geometric mean lets one weak signal drag the whole score "
                    "down; an arithmetic mean lets strong signals cover for a weak one. One report each, on a clean database. "
                    "The first case is what every citizen's very first report looks like: a brand-new account, no history, "
                    "no visit date, a vague text.",
        "tables": [("Trust score T of one report, and the confidence it leaves",
                    ["report", "T (geometric)", "T (arithmetic)", "confidence (geometric)", "confidence (arithmetic)"], rows)],
        "proves": f"A vague report from a brand-new account is trusted {av['T'] / gv['T']:.1f} times more under an arithmetic "
                  f"mean (T {av['T']:.2f} against {gv['T']:.2f}), and a very old visit is excused (T {at['T']:.2f} against "
                  f"{gt['T']:.2f}). A strong report is barely affected (T {gs['T']:.2f} against {as_['T']:.2f}). "
                  f"The geometric mean makes a weak signal count, which is the cautious choice.",
        "summary": ("vague report, new account: trust score T", f"{gv['T']:.3f}", f"{av['T']:.3f}"),
        "check": av["T"] > gv["T"] * 1.5 and at["T"] > gt["T"] * 1.2 and abs(as_["T"] - gs["T"]) < 0.15,
    }


def reputation(embedding: str) -> dict:
    good, bad = Rep(Cit("reliable", a=8, age_days=200)), Rep(Cit("unreliable", b=8, age_days=200))
    rows, res = [], {}
    for name, rep in (("reliable (8 reports confirmed)", good), ("unreliable (8 reports contradicted)", bad)):
        f, o = run([rep], embedding)[0], run([rep], embedding, w_r=0.0)[0]
        res[name] = (f, o)
        rows.append([name, f"{f['T']:.3f}", f"{o['T']:.3f}", pct(f["pct"]), pct(o["pct"])])
    (gf, go), (bf, bo) = res["reliable (8 reports confirmed)"], res["unreliable (8 reports contradicted)"]
    return {
        "key": "reputation", "title": "REPUTATION OFF (weight 0)",
        "scenario": "Two citizens with the same account age send the identical, specific report. One has a record of "
                    "confirmed reports, the other of contradicted ones.",
        "tables": [("The same report from two different citizens",
                    ["citizen", "T (full)", "T (reputation off)", "confidence (full)", "confidence (reputation off)"], rows)],
        "proves": f"With reputation the reliable citizen counts {gf['T'] / bf['T']:.1f} times more than the unreliable one "
                  f"(T {gf['T']:.2f} against {bf['T']:.2f}). With reputation switched off both count the same "
                  f"(T {go['T']:.2f} and {bo['T']:.2f}), so a citizen with a bad record would carry the same weight.",
        "summary": ("unreliable citizen: trust score T", f"{bf['T']:.3f}", f"{bo['T']:.3f}"),
        "check": gf["T"] > bf["T"] * 1.2 and abs(go["T"] - bo["T"]) < 1e-9,
    }


def age_recency(embedding: str) -> dict:
    old, fresh = Rep(Cit("old", age_days=200)), Rep(Cit("fresh", age_days=1))
    today, month = Rep(Cit("visit-today", age_days=200), visit_days_ago=0), Rep(Cit("visit-month", age_days=200), visit_days_ago=40)
    rows_a, rows_r, res = [], [], {}
    for name, rep in (("200-day-old account", old), ("1-day-old account", fresh)):
        f, o = run([rep], embedding)[0], run([rep], embedding, w_c=0.0)[0]
        res[name] = (f, o)
        rows_a.append([name, f"{f['T']:.3f}", f"{o['T']:.3f}", pct(f["pct"]), pct(o["pct"])])
    for name, rep in (("visited today", today), ("visited 40 days ago", month)):
        f, o = run([rep], embedding)[0], run([rep], embedding, w_t=0.0)[0]
        res[name] = (f, o)
        rows_r.append([name, f"{f['T']:.3f}", f"{o['T']:.3f}", pct(f["pct"]), pct(o["pct"])])
    (of_, oo), (ff, fo) = res["200-day-old account"], res["1-day-old account"]
    (tf, to_), (mf, mo) = res["visited today"], res["visited 40 days ago"]
    return {
        "key": "age-recency", "title": "ACCOUNT AGE OFF / VISIT RECENCY OFF",
        "scenario": "The same specific report from an old account and from a one-day-old account, and from a visit today "
                    "and a visit 40 days ago. A one-off account is cheap to create, and an old visit says little about today's counter.",
        "tables": [("Account age (switch: account-age weight 0)",
                    ["citizen", "T (full)", "T (age off)", "confidence (full)", "confidence (age off)"], rows_a),
                   ("Visit recency (switch: recency weight 0)",
                    ["visit", "T (full)", "T (recency off)", "confidence (full)", "confidence (recency off)"], rows_r)],
        "proves": f"With account age, a one-day-old account counts {ff['T'] / of_['T']:.0%} as much as an established one "
                  f"(T {ff['T']:.2f} against {of_['T']:.2f}); switched off, both count the same. With recency, a visit 40 days ago "
                  f"counts {mf['T'] / tf['T']:.0%} as much as a visit today; switched off, both count the same.",
        "summary": ("1-day-old account: trust score T", f"{ff['T']:.3f}", f"{fo['T']:.3f}"),
        "check": ff["T"] < of_["T"] * 0.8 and abs(fo["T"] - oo["T"]) < 1e-9 and mf["T"] < tf["T"] * 0.8 and abs(mo["T"] - to_["T"]) < 1e-9,
    }


ABLATIONS = {"independence": independence, "aggregation": aggregation, "reputation": reputation, "age-recency": age_recency}


def run_all(only: str | None = None, embedding: str = "hash") -> list[dict]:
    return [fn(embedding) for key, fn in ABLATIONS.items() if only in (None, key)]


# ---------------------------------------------------------------------------------------------- output
def print_text(results: list[dict]) -> None:
    for n, ab in enumerate(results, 1):
        banner(f"ABLATION {n} · {ab['title']}")
        print("Scenario:", ab["scenario"], "\n")
        for caption, headers, rows in ab["tables"]:
            print(caption + ":")
            print(table(headers, rows) + "\n")
        print("WHAT IT PROVES:", ab["proves"])
    banner("SUMMARY: what each component adds")
    print(table(["measure", "full system", "component switched off"], [list(ab["summary"]) for ab in results]))
    print("\nEvery claim above was checked by the program: " +
          ("all hold." if all(ab["check"] for ab in results) else "NOT ALL HOLD, see the tables."))


def html_page(results: list[dict]) -> str:
    from app.cli.report import CSS, esc, table_html
    parts = []
    for n, ab in enumerate(results, 1):
        tables = "".join(table_html({"headers": h, "rows": r}, c) for c, h, r in ab["tables"])
        parts.append(f'<section><h2><span class="p">ABLATION {n}</span>{esc(ab["title"].capitalize())}</h2>'
                     f'<div class="explain">{esc(ab["scenario"])}</div><div class="body">{tables}'
                     f'<div class="decision ok"><b>What it proves</b> {esc(ab["proves"])}</div></div></section>')
    summary = table_html({"headers": ["measure", "full system", "component switched off"],
                          "rows": [list(ab["summary"]) for ab in results]}, "Summary: what each component adds")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>HelaGuide · Component 3 · Ablation study</title><style>{CSS}</style></head><body>"
            '<header><span class="mark">H</span><b>HelaGuide</b><span class="d">helaguide.lk</span>'
            '<span class="r">Component 3 · ablation study · mock data</span></header>'
            '<div class="wrap" style="display:block;max-width:1100px"><main>'
            '<div class="intro"><b>What an ablation is.</b> One component is switched off, or replaced by a naive version, '
            "and the result is compared with the full system on the same scenario. If the result gets worse, the component "
            "earns its place. All numbers were calculated by the program, with hand-made citizens.</div>"
            f'{"".join(parts)}<section><div class="body">{summary}</div></section></main></div></body></html>')


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=list(ABLATIONS), help="run a single ablation")
    ap.add_argument("--embedding", choices=["hash", "sbert"], default="hash",
                    help="hash (default, instant) or sbert (the real model)")
    ap.add_argument("--html", action="store_true", help="also write a readable HTML page")
    ap.add_argument("--no-open", action="store_true", help="do not open the HTML page")
    args = ap.parse_args(argv)
    results = run_all(args.only, args.embedding)
    print_text(results)
    if args.html:
        out = C3Settings().out_dir / "pp1_ablation.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_page(results), encoding="utf-8")
        print(f"\nHTML page written: {out}")
        if not args.no_open:
            webbrowser.open(Path(out).resolve().as_uri())


if __name__ == "__main__":
    main()
