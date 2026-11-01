"""
Regression replay: sends a logged conversation (default: research/data/regression_rigid_log.json) through
DialogueManager in rules, llm and hybrid mode with the real engine, and prints one table per mode like the demo log
(message, final intent, XLM-R's own top prediction and its confidence, route, slots, tasks) with the reply and
dialogue_source of each turn. Every turn is checked against the file's expect_hybrid; the checks are printed for
every mode, so the rules table shows what the LLM layer has to fix. Model outputs are not committed: save them as
replay_*.txt / replay_*.json (git-ignored).

Needs the real engine (pip install -e ".[research]" and the model folder, see ../README.md). Run from service/:

    set C1_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
    set C1_LLM_API_KEY=...
    python scripts/replay_log.py --model gemini-3.5-flash-lite --effort low > replay_lite_low.txt
    python scripts/replay_log.py --modes rules                     # no LLM needed

--model, --effort and --timeout override C1_LLM_MODEL, C1_LLM_REASONING_EFFORT and C1_LLM_TIMEOUT. --pause waits
between LLM turns to stay under free-tier per-minute limits. Exit code 1 when a hybrid expectation fails.
"""
import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))                                 # for `app`

from app.core.dialogue import DialogueManager                   # noqa: E402
from app.core.llm_client import OpenAICompatClient              # noqa: E402
from app.core.settings import REASONING_EFFORTS, dialogue_settings      # noqa: E402

DEFAULT_LOG = SERVICE.parent / "research" / "data" / "regression_rigid_log.json"
MODES = ("rules", "llm", "hybrid")
REPLY_CHARS = 110


def check(expect: dict, r) -> list[tuple[str, bool]]:
    """-> [(what was expected, met?)] for one turn's DialogueResult."""
    out = []
    for key, want in expect.items():
        if key in ("internal_intent", "route", "active_intent", "dialogue_act"):
            out.append((f"{key}={want}", getattr(r, key) == want))
        elif key == "slots":
            out += [(f"{k}={v}", r.slots.get(k) == v) for k, v in want.items()]
        elif key == "slots_present":
            out += [(f"{k} filled", k in r.slots) for k in want]
        elif key == "tasks_include":
            out += [(f"{t} in tasks", t in r.tasks) for t in want]
        elif key == "reply":
            out.append(("reply", bool(r.reply.strip())))
        else:
            raise ValueError(f"unknown expectation {key!r}")
    return out


def replay(turns, manager, new_engine_session, pause=0.0, sleep=time.sleep):
    """One conversation through `manager`. -> [DialogueResult]. pause: seconds between turns when it uses an LLM."""
    chat = manager.new_session(new_engine_session())
    results = []
    for i, turn in enumerate(turns):
        if i and pause and manager.llm is not None:
            sleep(pause)
        results.append(chat.step(turn["text"]))
    return results


def _short(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"


def table(turns, results):
    """The demo-log table, the reply and source under each row, then the expect_hybrid checks."""
    rows = [("#", "Message", "Intent", "XLM-R said", "Route", "Slots", "Tasks")]
    for i, (t, r) in enumerate(zip(turns, results)):
        slots = ", ".join(f"{k}={v}" for k, v in r.slots.items()) or "—"
        xlmr = f"{r.intent_model_output} {r.confidence:.2f}"       # XLM-R's own prediction, not the final intent
        rows.append((str(i), t["text"], r.internal_intent, xlmr, r.route, slots, ", ".join(r.tasks) or "—"))
    widths = [max(len(row[c]) for row in rows) for c in range(len(rows[0]) - 1)]
    lines = []
    for j, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(w) for cell, w in zip(row, widths)) + "  " + row[-1])
        if j == 0:
            continue
        t, r = turns[j - 1], results[j - 1]
        source = r.dialogue_source + (f" ({r.error})" if r.error else "")
        lines.append(f"      reply [{source}] {_short(r.reply, REPLY_CHARS)}")
        checks = check(t.get("expect_hybrid", {}), r)
        if checks:
            failed = [what for what, ok in checks if not ok]
            lines.append(f"      expect {'ok' if not failed else 'FAIL: ' + '; '.join(failed)}")
    return "\n".join(lines)


def summarise(mode, turns, results):
    checks = [ok for t, r in zip(turns, results) for _, ok in check(t.get("expect_hybrid", {}), r)]
    answered = [r for r in results if r.dialogue_source == "llm"]
    llm_ms = [r.llm_ms for r in answered]
    usage = [r.llm_usage for r in answered if r.llm_usage]
    return {
        "mode": mode,
        "turns": len(results),
        "expect_met": sum(checks), "expect_total": len(checks),
        "turns_met": sum(all(ok for _, ok in check(t.get("expect_hybrid", {}), r)) for t, r in zip(turns, results)),
        "llm_answered": len(answered),
        "fallbacks": sum(r.dialogue_source == "rules_fallback" for r in results),
        "mean_llm_ms": round(sum(llm_ms) / len(llm_ms), 1) if llm_ms else None,
        "max_llm_ms": max(llm_ms) if llm_ms else None,
        "tokens": {k: sum(u[k] for u in usage) for k in ("prompt_tokens", "completion_tokens", "provider_total_tokens")}
                  if usage else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG, help="conversation file (default: the rigid log)")
    ap.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    ap.add_argument("--model", help="model name (default: C1_LLM_MODEL)")
    ap.add_argument("--effort", choices=REASONING_EFFORTS, help="reasoning effort (default: C1_LLM_REASONING_EFFORT)")
    ap.add_argument("--timeout", type=float, help="seconds per LLM request (default: C1_LLM_TIMEOUT)")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between LLM turns (default 4)")
    ap.add_argument("--json-out", type=Path, help="also write every turn's full result here (replay_*.json)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")     # Sinhala in the Windows console
    if args.timeout is not None and args.timeout < 1:
        ap.error("--timeout must be at least 1")

    log = json.loads(args.log.read_text(encoding="utf-8"))
    turns = log["turns"]
    base = dialogue_settings()
    overrides = {"model": args.model, "reasoning_effort": args.effort, "timeout": args.timeout}
    base = replace(base, **{k: v for k, v in overrides.items() if v is not None})
    uses_llm = any(m != "rules" for m in args.modes)
    print(f"log       {args.log.name} ({len(turns)} turns)")
    if uses_llm:
        print(f"base url  {base.base_url}")
        print(f"model     {base.model}")
        print(f"reasoning effort {base.reasoning_effort or 'not sent'}")
        print(f"api key   {'set' if base.api_key else 'not set'}")
        print(f"timeout   {base.timeout}s, history {base.history_turns} turns, pause {args.pause}s")
    print()

    from app.core import pipeline       # loads torch and the models only now
    try:
        engine = pipeline.get_engine()
    except pipeline.EngineUnavailable as e:
        sys.exit(f"engine not available: {e}")
    client = OpenAICompatClient.from_settings(base) if uses_llm else None

    summaries, dump = [], {"log": args.log.name, "model": base.model if uses_llm else None,
                           "reasoning_effort": base.reasoning_effort or None, "modes": {}}
    for mode in args.modes:
        settings = replace(base, mode=mode)
        manager = DialogueManager(None if mode == "rules" else client, settings)
        results = replay(turns, manager, engine.new_session, pause=args.pause)
        print(f"===== {mode}" + (f" · {base.model}" if mode != "rules" else ""))
        print(table(turns, results))
        s = summarise(mode, turns, results)
        summaries.append(s)
        print(f"      → expectations met {s['expect_met']}/{s['expect_total']} "
              f"(turns fully met {s['turns_met']}/{s['turns']}), fallbacks {s['fallbacks']}\n")
        dump["modes"][mode] = {"summary": s, "turns": [
            {"text": t["text"], **{k: v for k, v in asdict(r).items() if k != "state"},
             "checks": [{"expect": what, "met": ok} for what, ok in check(t.get("expect_hybrid", {}), r)]}
            for t, r in zip(turns, results)]}

    print("summary")
    print(f"  {'mode':<7} {'expect met':>10} {'turns met':>9} {'llm answered':>12} {'fallbacks':>9} "
          f"{'llm ms mean/max':>16} {'tokens in/out/total':>20}")
    for s in summaries:
        ms = f"{s['mean_llm_ms']}/{s['max_llm_ms']}" if s["mean_llm_ms"] is not None else "—"
        tok = (f"{s['tokens']['prompt_tokens']}/{s['tokens']['completion_tokens']}/"
               f"{s['tokens']['provider_total_tokens']}") if s["tokens"] else "—"
        print(f"  {s['mode']:<7} {str(s['expect_met']) + '/' + str(s['expect_total']):>10} "
              f"{str(s['turns_met']) + '/' + str(s['turns']):>9} {s['llm_answered']:>12} {s['fallbacks']:>9} "
              f"{ms:>16} {tok:>20}")
    if args.json_out:
        args.json_out.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nfull results -> {args.json_out}")
    hybrid = next((s for s in summaries if s["mode"] == "hybrid"), None)
    sys.exit(1 if hybrid and hybrid["expect_met"] < hybrid["expect_total"] else 0)


if __name__ == "__main__":
    main()
