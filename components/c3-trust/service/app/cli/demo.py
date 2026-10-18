"""
The PP1 demonstration of the Civic Trust and Knowledge Verification Engine (component 3).

    python -m app.cli.demo                       everything, PostgreSQL, the real model
    python -m app.cli.demo --pause               wait for Enter between parts (good for the panel)
    python -m app.cli.demo --part grounding      only one part
    python -m app.cli.demo --path freetext       only the C1-style path   (or: structured / both)
    python -m app.cli.demo --sqlite --embedding hash    plumbing check, needs no Docker and no download

Parts: setup, grounding, story, conflict, version, exposure, checks
"""
from __future__ import annotations

import argparse
import json
import math

from app.cli._common import add_common_args, banner, build, mask_url, settings_from_args, table, utf8
from app.core.confidence import calibrate_lambda, confidence_from_evidence
from app.core.dedup import independence
from app.core.evaluate import Loaded, accuracy_by, load_dataset, run_grounding
from app.core.pipeline import Pipeline, ProcessResult

PARTS = ["setup", "grounding", "story", "conflict", "version", "exposure", "checks"]
DETAIL_DEFAULT = ["ft-C1", "ft-C4", "ft-C2", "ft-C8", "ft-C12", "ft-C10", "ft-D1"]
S = lambda fid: (fid or "-").replace("svc:", "")


def pause(args, text="Press Enter to continue..."):
    if args.pause:
        input(f"\n[{text}]")


# ------------------------------------------------------------------ setup ---
def part_setup(pipe: Pipeline, args):
    s = pipe.s
    banner("PART 1 · SET-UP: C3 owns the confidence of every fact")
    facts = pipe.repo.list_current_facts()
    print(f"database        : {mask_url(s.database_url)}")
    print(f"embedding model : {pipe.embedder.name}   (inference only, no training)")
    print(f"fact source     : {s.fact_source} (a mock knowledge graph in the shape of C2's `fact` contract)")
    print(f"registered      : {len(facts)} facts across {len(pipe.grounding.by_service)} services, "
          f"{len(pipe.repo.all_reporters())} reporters")
    print(f"decay rate      : lambda = ln({s.c_base}/{s.theta_esc})/{s.policy_k} = {s.lam:.4f}   "
          "(calibration-by-design: derived from the policy, not guessed)")
    print("\nA few facts and the confidence record C3 created for each (C2's graph holds no confidence at all):")
    rows = []
    for f in sorted(facts, key=lambda x: x.fact_id)[:8]:
        rec = pipe.repo.get_confidence(f.fact_id, f.valid_from)
        rows.append([S(f.fact_id), f"{f.value_text} {f.unit or ''}".strip(), f"{rec.confidence:.0%}", rec.status])
    print(table(["fact_id", "stored value", "confidence", "status"], rows))


# -------------------------------------------------------------- grounding ---
def part_grounding(pipe: Pipeline, ds: Loaded, args):
    banner("PART 2 · FACT GROUNDING: which stored fact is the citizen disputing?")
    detail = set(args.detail.split(",")) if args.detail else set(DETAIL_DEFAULT)
    rows_all = run_grounding(pipe, ds)
    for r in rows_all:
        if r["label"]["message_id"] not in detail:
            continue
        g, lab = r["result"], r["label"]
        print(f"\n--- {lab['message_id']}  ({lab['path']}, {lab['style']}) ---")
        print(f"message : {r['raw_text']}")
        print(f"English : {r['text_en']}   [via {r['backend']}]")
        sc = g.trace.get("service_candidates")
        if sc:
            print("service : " + ", ".join(f"{S(c['service_id'])} {c.get('score')}" for c in sc[:3])
                  + f"   -> {S(g.service_id)} ({g.service_source or 'unclear'})")
        fc = g.trace.get("fact_candidates")
        if fc:
            print(table(["candidate fact", "score", "similarity", "kind", "variant", "value"],
                        [[S(c["fact_id"]), f"{c['score']:.3f}", f"{c['cos']:.3f}", c["pred"], c["qual"], c["value_quoted"]]
                         for c in fc]))
        if g.trace.get("phrase_similarity") is not None:
            words = ", ".join(g.trace.get("shared_words") or []) or "none"
            print(f"document check: phrase similarity {g.trace['phrase_similarity']:.3f}   distinctive words shared with the "
                  f"document: {words}   (needs similarity >= {pipe.s.tau_doc_sure}, or >= {pipe.s.tau_miss_cos} plus a shared word)")
        if g.trace.get("only_fact_of_its_kind"):
            print(f"only fact of its kind in this service: needed score lowered to {g.trace['needed_score']}")
        verdict = {"grounded": f"GROUNDED -> {S(g.fact_id)}",
                   "clarification_needed": f"ASK THE CITIZEN ({g.reason})",
                   "no_matching_fact": f"NOT IN THE GRAPH ({g.reason})"}[g.state]
        print(f"decision: {verdict}   | expected: {lab['expected_state']} {S(lab['expected_fact_id'])}   "
              f"{'OK' if r['ok'] else 'MISMATCH'}")
    banner("Grounding accuracy on all labelled messages", "-")
    print(table(["message", "path", "style", "decision", "chosen fact", "expected", "ok"],
                [[r["label"]["message_id"], r["label"]["path"], r["label"]["style"], r["result"].state,
                  S(r["result"].fact_id), S(r["label"]["expected_fact_id"]) if r["label"]["expected_fact_id"] else r["label"]["expected_state"],
                  "yes" if r["ok"] else "NO"] for r in rows_all]))
    good = sum(r["ok"] for r in rows_all)
    print(f"\nOVERALL: {good}/{len(rows_all)} correct ({good / len(rows_all):.0%})")
    for key in ("style", "path", "split"):
        print(f"by {key:6}: " + ", ".join(f"{k} {a}/{n}" for k, (a, n) in accuracy_by(rows_all, key).items()))


# ------------------------------------------------------------------ story ---
def play(pipe: Pipeline, ds: Loaded, story: str, path: str, verbose: bool = True) -> list[ProcessResult]:
    out = []
    for lab in ds.ordered():
        if lab["story"] != story:
            continue
        if path != "both" and lab["path"] != path:
            continue
        mid = lab["message_id"]
        if mid in ds.freetext:
            r = pipe.process_freetext(ds.freetext[mid])
        else:
            r = pipe.process_structured(ds.structured[mid], ds.extras.get(mid))
        out.append(r)
        if verbose:
            show_report(r, len(out))
    return out


def show_report(r: ProcessResult, n: int):
    how = {"cache": "translated to English", "gemini_live": "translated to English", "supplied": "English supplied",
           "not_needed": "English"}.get(r.norm_backend or "", r.norm_backend or "")
    print(f"\n[{n}] {r.message_id}   path={r.path}   reporter={r.reporter_id}")
    print(f"    message   : {r.text_en}   ({how})")
    if r.state != "grounded":
        print(f"    result    : {r.state} ({r.reason})")
        return
    t, i, c, e = r.trust, r.independence, r.confidence, r.exposure
    print(f"    grounded  : {S(r.fact_id)}   (service found via {r.grounding.get('service_source')})   kind={r.kind}  claim={r.claimed}")
    print(f"    trust     : T={t['T']:.3f}  from  R {t['R']:.2f} (a={t['a']:g}, b={t['b']:g})  S {t['S']:.2f}  "
          f"C {t['C']:.2f} (account {t['age_days']:.0f} days)  V {t['V']:.2f}{' (no visit date: neutral)' if t['v_imputed'] else ''}")
    print(f"    weight    : independence I={i['I']:.2f}   ({i['dup_count']} near-duplicate of earlier reports)")
    print(f"    evidence  : E={c['E']:.3f}   ->   confidence {c['old']:.1%} -> {c['new']:.1%}   [{c['status']}]")
    warn = {"NONE": "no warning yet", "LOW_CONFIDENCE": "WARNING: some citizens report this may have changed",
            "VERIFY_BEFORE_VISIT": "STRONG WARNING: verify before your visit", "VERIFIED_BY_SOURCE": "verified by the official source"}
    print(f"    citizen sees: {e['confidence_pct']}%  |  {warn[e['warning_code']]}   (confidence-lowering updates so far: {e['drop_events']})")


def story_table(rs: list[ProcessResult]):
    rows = [[r.message_id, r.path, r.kind, f"{r.trust['T']:.3f}", f"{r.independence['I']:.2f}",
             f"{r.confidence['E']:.3f}", f"{r.confidence['pct']}%", r.exposure["warning_code"]] for r in rs if r.state == "grounded"]
    print("\n" + table(["report", "path", "kind", "T", "I", "E", "confidence", "warning"], rows))


def plot_story(pipe, rs, name, title):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib not installed: pip install -e \".[demo]\" to save the chart)")
        return
    g = [r for r in rs if r.state == "grounded"]
    xs = [0] + list(range(1, len(g) + 1))
    ys = [pipe.s.c_base * 100] + [r.confidence["new"] * 100 for r in g]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(xs, ys, marker="o")
    ax.axhline(pipe.s.theta_esc * 100, ls="--", color="red", lw=1)
    ax.text(0.02, pipe.s.theta_esc * 100 + 1, f"flag level {pipe.s.theta_esc:.0%}", color="red", fontsize=8)
    for x, y, r in zip(xs[1:], ys[1:], g):
        ax.annotate(f"{r.message_id}\n{r.kind}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=7)
    ax.set_xticks(xs)
    ax.set_xlabel("reports processed")
    ax.set_ylabel("confidence in the stored value (%)")
    ax.set_title(title)
    ax.set_ylim(30, 100)
    pipe.s.out_dir.mkdir(parents=True, exist_ok=True)
    path = pipe.s.out_dir / f"{name}.svg"
    fig.tight_layout()
    fig.savefig(path)
    print(f"chart saved: {path}")


def part_story(pipe, ds, args):
    banner("PART 3 · CONFIDENCE STORY: passport fee, reports from both paths")
    f = pipe.repo.current_version("svc:passport:fee:normal")
    print(f"Stored fact: {S(f.fact_id)} = {f.value_text} {f.unit}.  Starting confidence {pipe.s.c_base:.0%}.")
    rs = play(pipe, ds, "A", args.path)
    story_table(rs)
    plot_story(pipe, rs, "passport_fee_story", "Passport normal fee: confidence as citizens report")
    print("\nAudit trail (every change is recorded with its reason):")
    for row in pipe.repo.audit_rows("svc:passport:fee:normal")[:12]:
        print(f"   {row['old'] if row['old'] is None else round(row['old'], 3)} -> {round(row['new'], 3)}   {row['reason']}")


def part_conflict(pipe, ds, args):
    banner("PART 4 · CITIZENS DISAGREE WITH EACH OTHER: NIC replacement fee")
    f = pipe.repo.current_version("svc:nic:fee:replacement")
    print(f"Stored fact: {S(f.fact_id)} = {f.value_text} {f.unit}.")
    rs = play(pipe, ds, "B", args.path)
    story_table(rs)
    e = pipe.exposure.explain("svc:nic:fee:replacement")
    print(f"\nclaims by different citizens: {e['claim_groups']}")
    print(f"claims_disagree = {e['claims_disagree']}  -> the system does NOT pick a winner; it records the disagreement")
    print("(in PP2 this goes to a human reviewer)")


# ---------------------------------------------------------------- version ---
def part_version(pipe, ds, args):
    banner("PART 5 · THE OFFICIAL SOURCE CHANGES A VALUE (new fact version)")
    before = {r.reporter_id: (r.a, r.b) for r in pipe.repo.all_reporters()}
    print("C2 (mock) publishes new versions: passport normal fee 11,000 -> 12,000 ; NIC replacement fee 1,000 -> 1,500")
    pipe.source.publish_updates(pipe.s.data_dir / "c2_facts_updates.json")
    results = pipe.sync_facts()
    for res in results:
        if not res.new_version:
            continue
        print(f"\n{S(res.fact_id)}: NEW VERSION, fresh confidence {res.initial_confidence:.0%}; earlier reports judged:")
        if res.verdicts:
            print(table(["report", "reporter", "claimed", "verdict", "a gained", "b gained"],
                        [[v.report_id, v.reporter_id, v.claimed or "-", v.outcome, f"{v.da:.2f}", f"{v.db:.2f}"] for v in res.verdicts]))
        e = pipe.exposure.explain(res.fact_id)
        print(f"citizen now sees: {e['confidence_pct']}% | {e['warning_code']}")
    after = {r.reporter_id: (r.a, r.b) for r in pipe.repo.all_reporters()}
    rows = []
    for rid, (a1, b1) in after.items():
        a0, b0 = before.get(rid, (0, 0))
        if (a1, b1) != (a0, b0):
            rows.append([rid, f"a={a0:g} b={b0:g}", f"a={a1:g} b={b1:g}", f"{(a0 + 1) / (a0 + b0 + 2):.2f}", f"{(a1 + 1) / (a1 + b1 + 2):.2f}"])
    print("\nReporter reputation after the official value arrived:")
    print(table(["reporter", "before", "after", "R before", "R after"], rows))


# --------------------------------------------------------------- exposure ---
def part_exposure(pipe, ds, args):
    banner("PART 6 · WHAT C4 RECEIVES (contract `trust` message) AND THE PRIVATE EXPLANATION")
    validator = _trust_validator(pipe)
    for fid in ["svc:passport:fee:normal", "svc:nic:fee:replacement", "svc:birth_certificate:fee:certified_copy"]:
        t = pipe.exposure.contract_trust(fid)
        payload = json.loads(t.model_dump_json())
        ok = "" if validator is None else ("   [valid against contracts/schema/v1/trust.schema.json]" if validator(payload) else "   [SCHEMA ERROR]")
        print(f"\n{json.dumps(payload)}{ok}")
    e = pipe.exposure.explain("svc:nic:fee:replacement")
    print("\nPrivate explanation for the NIC replacement fee:")
    print(json.dumps({k: e[k] for k in ("confidence_pct", "internal_status", "warning_code", "warning_params",
                                         "drop_events", "claims_disagree", "last_reason")}, indent=2))


def _trust_validator(pipe):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from helaguide_common.config import get_settings
        schema = json.loads((get_settings().contracts_dir / "schema" / "v1" / "trust.schema.json").read_text(encoding="utf-8"))
        v = Draft202012Validator(schema, format_checker=FormatChecker())
        return lambda payload: not list(v.iter_errors(payload))
    except Exception:
        return None


# ----------------------------------------------------------------- checks ---
def part_checks(pipe, ds, args):
    banner("PART 7 · DO THE FORMULAS BEHAVE AS CLAIMED? (live property checks)")
    s = pipe.s
    lam = s.lam
    c0 = s.c_base
    checks = []
    checks.append(("calibration: k perfect reports land exactly on the flag level",
                   abs(confidence_from_evidence(c0, s.policy_k, lam) - s.theta_esc) < 1e-9,
                   f"{confidence_from_evidence(c0, s.policy_k, lam):.4f} (target {s.theta_esc})"))
    checks.append(("lambda matches the policy formula", abs(lam - calibrate_lambda(c0, s.theta_esc, s.policy_k)) < 1e-12,
                   f"lambda={lam:.5f}"))
    es = [0, 0.5, 1, 2, 4, 8, 16]
    vals = [confidence_from_evidence(c0, e, lam) for e in es]
    checks.append(("monotone: more evidence never raises confidence", all(a >= b for a, b in zip(vals, vals[1:])), ""))
    checks.append(("bounded: confidence stays in (0, c0]", all(0 < v <= c0 for v in vals), f"E=16 -> {vals[-1]:.4f}"))
    cap = c0 * (1 - math.exp(-lam))
    checks.append(("single-report cap: one perfect report moves it by at most c0*(1-e^-lambda)",
                   abs((c0 - confidence_from_evidence(c0, 1.0, lam)) - cap) < 1e-12, f"max drop {cap:.3f}"))
    unit = [confidence_from_evidence(c0, e, lam) for e in (0, 1, 2, 3)]
    drops = [unit[i] - unit[i + 1] for i in range(3)]
    checks.append(("diminishing returns: each extra unit of evidence lowers confidence by less than the one before",
                   drops[0] > drops[1] > drops[2] > 0, "drops: " + ", ".join(f"{d:.3f}" for d in drops)))
    import numpy as np
    base = np.array([1.0, 0.0], dtype=np.float32)
    I1, d1, _ = independence(s, base, "u2", "dispute", [type("R", (), dict(reporter_id="u1", report_kind="dispute", embedding=base, report_id="x"))()])
    I2, d2, _ = independence(s, np.array([0.0, 1.0], dtype=np.float32), "u2", "dispute",
                             [type("R", (), dict(reporter_id="u1", report_kind="dispute", embedding=base, report_id="x"))()])
    checks.append(("a copy of an earlier report is discounted; a different report is not",
                   abs(I1 - s.rho) < 1e-9 and I2 == 1.0, f"copy I={I1:.2f}, different I={I2:.2f}"))
    w = (s.w_r, s.w_s, s.w_c, s.w_t)
    geo = math.exp(sum(wi * math.log(v) for wi, v in zip(w, (0.9, 0.9, 0.05, 0.9))))
    ari = sum(wi * v for wi, v in zip(w, (0.9, 0.9, 0.05, 0.9)))
    checks.append(("geometric trust is more cautious than arithmetic when one signal (account age) is weak",
                   geo < ari, f"geometric {geo:.3f} < arithmetic {ari:.3f}"))
    print(table(["property", "result", "detail"], [[n, "PASS" if ok else "FAIL", d] for n, ok, d in checks], max_width=78))
    print(f"\n{sum(ok for _, ok, _ in checks)}/{len(checks)} checks passed")


# ------------------------------------------------------------------- main ---
def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--part", choices=["all"] + PARTS, default="all")
    ap.add_argument("--path", choices=["both", "freetext", "structured"], default="both",
                    help="which feedback path to feed into the confidence stories")
    ap.add_argument("--pause", action="store_true", help="wait for Enter between parts")
    ap.add_argument("--detail", help="comma-separated message ids to show in full in the grounding part")
    args = ap.parse_args(argv)
    pipe = build(args, reset=True)
    pipe.load_reporters()
    pipe.sync_facts()
    ds = load_dataset(pipe.s.data_dir)
    steps = {"setup": part_setup, "grounding": part_grounding, "story": part_story, "conflict": part_conflict,
             "version": part_version, "exposure": part_exposure, "checks": part_checks}
    selected = PARTS if args.part == "all" else [args.part]
    for name in selected:
        if name == "setup":
            part_setup(pipe, args)
        else:
            steps[name](pipe, ds, args)
        pause(args)
    print("\nDemo finished. Run `python -m app.cli.reset` to get back to the clean starting state.")


if __name__ == "__main__":
    main()
