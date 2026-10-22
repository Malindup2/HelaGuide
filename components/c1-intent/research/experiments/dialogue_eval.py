"""
Dialogue-mode evaluation for the results chapter: the C1 dialogue layer in rules, llm and hybrid mode on the fresh
set, with the same scoring code as dst_eval.py (score_turn / summarise_rows: JGA, slot JGA, intent accuracy,
per-slot and micro F1).

NOTE: the gold dialogues (data/seed_all.json) were used to write the rules, so the fresh set
(data/fresh_dialogues_states.json, 23 dialogues / 50 user turns, written after the model was designed) is the
held-out test. Nothing is tuned on it: the hint gate was chosen on gold (gate_calibration.py: no gate helps, so the
gated setting is not run).

How a dialogue is run
  - Each user turn sees the GOLD conversation so far: gold user and bot turns as the LLM history, the gold bot
    question as the tracker's bot_text (as dst_eval.py feeds the tracker). Fresh users answer the gold bot's
    questions, so the system's own replies are not used as context. The dialogue STATE is always the system's own.
  - rules: the deployed engine (XLM-R window_3 + intent policy + rules tracker + XLM-R NER fallback), 1 run (it is
    deterministic). llm / hybrid: the LLM dialogue layer, --runs runs each (temperature 0 still varies).
  - Runs are interleaved (run 1: llm, hybrid; run 2: ...), so a stop leaves whole runs.

Scoring
  - The predicted state of a turn is its intent and the slots of that intent's schema (INTENT_SLOTS): the engine's
    internal town slot and the district it carries for context on passport requests are not schema slots.
  - Dates are scored on the user's words: an ISO date counts with the words kept in raw_slots, else the ISO value
    itself (counted as iso_fallback).
  - A failed turn (the LLM could not answer after the eval retries) counts as wrong in the main numbers, with no
    slots; jga_without_failed_dialogues leaves out every dialogue with a failed turn.
  - Strict scoring is the main number. Secondary, labelled "district relaxed" (decided before any run): the gold
    labels name a district only where the user wrote it, but the engine (and the LLM, as prompted) also fills the
    district of a named town ("Panadura" -> Kalutara). DISTRICT_RELAXED below says when such a district is not
    counted as wrong.
  - Also: intent-switch accuracy (turns whose gold intent differs from the previous turn's; few turns, anecdotal),
    hallucinated slot rate (LLM-set slots not in the gold state), validator rejection rate, fallback / failed rate,
    latency (NLU / LLM) and tokens. Turns to completion is not measured: with gold history a dialogue's length is
    fixed (future work, needs a simulated user).

Quota (free tiers)
  - --pause seconds between LLM call starts. Rate-limit 429, 5xx, timeouts and bad JSON: wait (the provider's
    retryDelay, else 30 s, then 60 s) and retry up to 3 times, then the turn is "failed". Other 4xx errors (bad key,
    model or request) fail at once. A 429 that says the quota is exceeded is retried once after 65 s (Gemini says
    the same for its per-minute limit); if it is still exceeded the run stops, as it does when nothing is
    listening at the base URL.
  - Every finished dialogue is appended to a checkpoint (JSONL, git-ignored); a restart skips finished dialogues and
    redoes an unfinished one from its start. Results are computed from the checkpoint.

Run from research/ (real engine: pip install -e "../service[research]"; LLM settings as for the service):
    set C1_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
    set C1_LLM_API_KEY=...
    python experiments/dialogue_eval.py --model gemini-3.5-flash-lite --effort low --timeout 60
Writes results/dialogue_eval_<setting>_<model>.json (summary, committed) and results/dialogue_eval_<model>.jsonl
(per-turn checkpoint, not committed).
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE = HERE.parents[1] / "service"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SERVICE))
from dst_eval import is_core_dialogue, load_json, new_slot_counts, score_turn, summarise_rows, user_turns  # noqa: E402

from app.core.dialogue import DialogueManager  # noqa: E402
from app.core.dst import DATE_SLOTS, INTENT_SLOTS, find_district, find_town, words_with_offsets  # noqa: E402
from app.core.llm_client import LLMError, OpenAICompatClient  # noqa: E402
from app.core.settings import REASONING_EFFORTS, dialogue_settings  # noqa: E402
from app.core.validator import is_iso_date  # noqa: E402

SETTINGS = ("rules", "llm", "hybrid")
DISTRICT_RELAXED = ("district relaxed: town->district counted correct when the message names a town but no district "
                    "(the predicted district is not in the gold state, a user message so far named a town in it and "
                    "no district, and no user message so far named that district)")
RETRY_WAITS = (30, 60, 60)          # eval only: waits before the 1st, 2nd, 3rd extra try
QUOTA_WAIT = 65
_QUOTA = re.compile(r"exceeded (?:your )?(?:current )?quota|quota (?:has been )?exceeded", re.IGNORECASE)
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')
_NO_RETRY = re.compile(r"HTTP 4(?!29)\d\d")
# rejections of turn-level fields, not of a slot update (the slot rejection rate counts slot updates only)
TURN_FIELDS = {"active_intent", "dialogue_act", "tasks", "reply", "asks_slot", "ready_to_confirm", "slot_updates",
               "slot_raw"}


class StopRun(Exception):
    """The quota is used up or the endpoint is unreachable: stop, resume later from the checkpoint."""


class EvalLLM:
    """Wraps the LLM client for evaluation runs: paces the calls and retries slow failures instead of letting the
    turn fall back to the rules path. After the retries it records the failure (failed / last_error) and raises, so
    the dialogue manager answers that turn from the rules path and the eval marks it failed."""

    def __init__(self, inner, pause=4.0, sleep=time.sleep, clock=time.monotonic):
        self.inner, self.pause, self._sleep, self._clock = inner, pause, sleep, clock
        self._last_start = None
        self.failed, self.last_error, self.stop, self.retries = False, None, None, 0

    def complete_json(self, system, messages):
        self.failed, self.last_error = False, None
        waits = list(RETRY_WAITS)
        quota_retried = False
        while True:
            self._pace()
            try:
                return self.inner.complete_json(system, messages)
            except LLMError as e:
                msg = str(e)
                if msg.startswith("ConnectError"):
                    self.stop, self.failed, self.last_error = "endpoint unreachable", True, msg
                    raise StopRun(msg) from e
                if _QUOTA.search(msg):
                    if quota_retried:
                        self.stop, self.failed, self.last_error = "quota exhausted", True, msg
                        raise StopRun(msg) from e
                    quota_retried = True
                    self.retries += 1
                    self._sleep(QUOTA_WAIT)
                    continue
                if _NO_RETRY.match(msg) or not waits:       # a bad key / model / request will not get better
                    self.failed, self.last_error = True, msg
                    raise
                m = _RETRY_DELAY.search(msg)
                self.retries += 1
                self._sleep(max(float(m.group(1)), waits.pop(0)) if m else waits.pop(0))

    def _pace(self):
        now = self._clock()
        if self._last_start is not None and now - self._last_start < self.pause:
            self._sleep(self.pause - (now - self._last_start))
        self._last_start = self._clock()


# ---------------------------------------------------------------- running
def gold_history(dialogue, upto):
    """The gold conversation before turn index `upto`, as chat messages."""
    return [{"role": "user" if t.get("speaker") == "user" else "assistant", "content": t["text"]}
            for t in dialogue["turns"][:upto]]


def schema_slots(intent, slots, raw_slots):
    """The slots scored for a turn: the intent's schema slots, dates as the user's words when kept.
    -> (slots, date counts {"words", "raw", "iso_fallback"})."""
    out, dates = {}, {"words": 0, "raw": 0, "iso_fallback": 0}
    for k, v in slots.items():
        if k not in INTENT_SLOTS.get(intent, []):
            continue
        if k in DATE_SLOTS:
            if is_iso_date(v):
                if raw_slots.get(k):
                    v, kind = raw_slots[k], "raw"
                else:
                    kind = "iso_fallback"
            else:
                kind = "words"
            dates[kind] += 1
        out[k] = v
    return out, dates


def place_names(text):
    """-> (district of the town the message names, if it names no district; the district it names), each or None."""
    words = list(words_with_offsets(text))
    named = find_district(words)
    town = find_town(words)
    return (town[1] if town and not named else None), (named[2] if named else None)


def district_from_town(pred_slots, gold_slots, town_districts, named_districts):
    """DISTRICT_RELAXED for one turn: the predicted district came from a town, and gold has none."""
    d = pred_slots.get("district")
    return bool(d) and "district" not in gold_slots and d in town_districts and d not in named_districts


def run_dialogue(manager, new_engine_session, dialogue, llm=None):
    """One dialogue, gold history at every turn. -> per-turn records (see score_run). Raises StopRun."""
    chat = manager.new_session(new_engine_session())
    core = is_core_dialogue(dialogue)
    records, prev_gold = [], None
    town_districts, named_districts = set(), set()
    for pos, (ti, text, gold, bot) in enumerate(user_turns(dialogue)):
        from_town, named = place_names(text)
        town_districts |= {from_town} - {None}
        named_districts |= {named} - {None}
        chat.history = gold_history(dialogue, ti)
        chat.last_bot_text = bot
        if llm is not None:
            llm.failed, llm.last_error = False, None
        r = chat.step(text)
        if llm is not None and llm.stop:
            raise StopRun(f"{llm.stop}: {llm.last_error}")
        failed = bool(llm is not None and llm.failed and r.dialogue_source == "rules_fallback")
        slots, dates = schema_slots(r.internal_intent, r.slots, r.raw_slots)
        gold_state = {"intent": gold.get("intent"), "slots": gold.get("slots", {}) or {}}
        records.append({
            "id": f"{dialogue['dialogue_id']}/{ti}", "dialogue_id": dialogue["dialogue_id"], "pos": pos,
            "core": core, "text": text, "gold": gold_state, "prev_gold_intent": prev_gold,
            "pred": {"intent": r.internal_intent, "slots": slots}, "dates": dates,
            "district_from_town": district_from_town(slots, gold_state["slots"], town_districts, named_districts),
            "dialogue_source": r.dialogue_source, "failed": failed, "error": llm.last_error if failed else None,
            "dialogue_act": r.dialogue_act, "reply": r.reply,
            "llm_slots": [k for k in r.llm_slots if k in slots],
            "llm_proposed": r.llm_proposed,
            "slot_rejections": [x for x in r.rejections if x["source"] == "llm" and x["field"] not in TURN_FIELDS],
            "rejections": len(r.rejections), "conflicts": len(r.conflicts),
            "nlu_ms": r.nlu_ms, "llm_ms": r.llm_ms, "latency_ms": r.latency_ms, "usage": r.llm_usage,
        })
        prev_gold = gold.get("intent")
    return records


# ---------------------------------------------------------------- scoring
def _mean(xs):
    return round(statistics.fmean(xs), 4) if xs else None


def _pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1)


def score_run(records):
    """Metrics of one run (one setting, one pass over the data) from its per-turn records."""
    per_slot, rows = new_slot_counts(), []
    for rec in records:
        pred = {"intent": "failed", "slots": {}} if rec["failed"] else rec["pred"]
        rows.append(score_turn(per_slot, rec["id"], rec["pos"], rec["core"], pred, rec["gold"]))
    res = summarise_rows(rows, per_slot)
    res["district_relaxed"] = _district_relaxed(records)
    res.pop("errors")
    res["errors"] = [{"id": r["id"], "pred": r["pred"], "gold": r["gold"]} for r in rows
                     if not (r["intent_ok"] and r["slots_ok"])]

    failed_dialogues = {rec["dialogue_id"] for rec in records if rec["failed"]}
    kept = [(row, rec) for row, rec in zip(rows, records) if rec["dialogue_id"] not in failed_dialogues]
    res["jga_without_failed_dialogues"] = (round(sum(r["intent_ok"] and r["slots_ok"] for r, _ in kept) / len(kept), 4)
                                           if kept else None)
    switches = [(row, rec) for row, rec in zip(rows, records)
                if rec["prev_gold_intent"] is not None and rec["gold"]["intent"] != rec["prev_gold_intent"]]
    res["intent_switch"] = {"turns": len(switches), "correct": sum(r["intent_ok"] for r, _ in switches),
                            "accuracy": round(sum(r["intent_ok"] for r, _ in switches) / len(switches), 4)
                            if switches else None, "note": "few turns: anecdotal"}

    llm_turns = [rec for rec in records if rec["dialogue_source"] != "rules"]
    llm_set = [(rec, k) for rec in records for k in rec["llm_slots"]]
    hallucinated = sum(k not in rec["gold"]["slots"] for rec, k in llm_set)
    proposed = sum(rec["llm_proposed"] for rec in records)
    rejected = sum(len(rec["slot_rejections"]) for rec in records)
    res["llm"] = {
        "turns": len(llm_turns),
        "answered": sum(rec["dialogue_source"] == "llm" for rec in records),
        "failed": sum(rec["failed"] for rec in records),
        "fallback": sum(rec["dialogue_source"] == "rules_fallback" and not rec["failed"] for rec in records),
        "hallucinated_slot_rate": round(hallucinated / len(llm_set), 4) if llm_set else None,
        "llm_slots_set": len(llm_set), "hallucinated_slots": hallucinated,
        "slot_rejection_rate": round(rejected / proposed, 4) if proposed else None,
        "slot_updates_proposed": proposed, "slot_updates_rejected": rejected,
        "rejections_per_turn": _mean([rec["rejections"] for rec in llm_turns]),
        "conflicts": sum(rec["conflicts"] for rec in records),
    }
    for k in ("fallback", "failed"):
        res["llm"][f"{k}_rate"] = round(res["llm"][k] / len(llm_turns), 4) if llm_turns else None
    res["dates"] = {k: sum(rec["dates"][k] for rec in records) for k in ("words", "raw", "iso_fallback")}
    answered = [rec for rec in records if rec["dialogue_source"] == "llm"]
    res["latency_ms"] = {
        "nlu_mean": _mean([rec["nlu_ms"] for rec in records]),
        "llm_mean": _mean([rec["llm_ms"] for rec in answered]),
        "llm_p50": _pct([rec["llm_ms"] for rec in answered], .5),
        "llm_p95": _pct([rec["llm_ms"] for rec in answered], .95),
        "llm_max": max((rec["llm_ms"] for rec in answered), default=None),
    }
    usage = [rec["usage"] for rec in answered if rec["usage"]]
    res["tokens_per_answered_turn"] = {k: _mean([u[k] for u in usage]) for k in
                                       ("prompt_tokens", "completion_tokens", "reasoning_tokens",
                                        "provider_total_tokens")} if usage else None
    res["tokens_total"] = {k: sum(u[k] for u in usage) for k in ("prompt_tokens", "completion_tokens",
                                                                  "provider_total_tokens")} if usage else None
    return res


def _district_relaxed(records):
    """The DISTRICT_RELAXED secondary scores: the same scoring, town-derived districts left out of the prediction."""
    per_slot, rows = new_slot_counts(), []
    for rec in records:
        if rec["failed"]:
            pred = {"intent": "failed", "slots": {}}
        else:
            slots = {k: v for k, v in rec["pred"]["slots"].items()
                     if not (k == "district" and rec["district_from_town"])}
            pred = {"intent": rec["pred"]["intent"], "slots": slots}
        rows.append(score_turn(per_slot, rec["id"], rec["pos"], rec["core"], pred, rec["gold"]))
    res = summarise_rows(rows, per_slot)
    return {"definition": DISTRICT_RELAXED, "turns_relaxed": sum(rec["district_from_town"] and not rec["failed"]
                                                                 for rec in records),
            "jga": res["jga"], "slot_jga": res["slot_jga"], "slot_f1": res["slot_micro"]["f1"]}


HEADLINE = {"jga": ("jga",), "jga_district_relaxed": ("district_relaxed", "jga"), "slot_jga": ("slot_jga",),
            "intent_acc": ("intent_acc",),
            "jga_turn2plus": ("jga_turn2plus",), "slot_f1": ("slot_micro", "f1"),
            "jga_without_failed_dialogues": ("jga_without_failed_dialogues",),
            "hallucinated_slot_rate": ("llm", "hallucinated_slot_rate"),
            "slot_rejection_rate": ("llm", "slot_rejection_rate"), "fallback_rate": ("llm", "fallback_rate"),
            "failed_rate": ("llm", "failed_rate"), "llm_ms_mean": ("latency_ms", "llm_mean"),
            "tokens_per_turn": ("tokens_per_answered_turn", "provider_total_tokens")}


def _get(d, path):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def aggregate(runs):
    """mean, SD and min-max over runs for the headline metrics (None when a metric is missing)."""
    out = {}
    for name, path in HEADLINE.items():
        xs = [x for x in (_get(r, path) for r in runs) if x is not None]
        out[name] = {"mean": round(statistics.fmean(xs), 4) if xs else None,
                     "sd": round(statistics.stdev(xs), 4) if len(xs) > 1 else (0.0 if xs else None),
                     "min": min(xs) if xs else None, "max": max(xs) if xs else None, "n_runs": len(xs)}
    return out


# ---------------------------------------------------------------- checkpoint
def load_checkpoint(path):
    """{(setting, run, dialogue_id): records}"""
    done = {}
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                x = json.loads(line)
                done[(x["setting"], x["run"], x["dialogue_id"])] = x["records"]
    return done


def append_checkpoint(path, setting, run, dialogue_id, records):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"setting": setting, "run": run, "dialogue_id": dialogue_id, "records": records},
                            ensure_ascii=False) + "\n")


def plan(settings, runs):
    """[(run, setting)] in the order they are run: rules once, LLM settings interleaved per run."""
    order = [(1, "rules")] if "rules" in settings else []
    return order + [(run, s) for run in range(1, runs + 1) for s in settings if s != "rules"]


def evaluate(dialogues, settings, runs, make_manager, new_engine_session, llm=None, checkpoint=None, log=print):
    """Runs everything not in the checkpoint yet. make_manager(setting) -> DialogueManager.
    -> {setting: [per-run metrics]}, stopped (True when the run had to stop: quota or endpoint)."""
    done = load_checkpoint(checkpoint)
    stopped = False
    for run, setting in plan(settings, runs):
        manager = make_manager(setting)
        for d in dialogues:
            key = (setting, run, d["dialogue_id"])
            if key in done:
                continue
            try:
                records = run_dialogue(manager, new_engine_session, d, llm if setting != "rules" else None)
            except StopRun as e:
                log(f"stopped during {setting} run {run} ({d['dialogue_id']}): {str(e)[:160]}")
                log("stopping; rerun the same command later to resume from the checkpoint")
                stopped = True
                break
            done[key] = records
            if checkpoint:
                append_checkpoint(checkpoint, setting, run, d["dialogue_id"], records)
        if stopped:
            break
        log(f"  {setting} run {run}: done")
    results = {}
    ids = [d["dialogue_id"] for d in dialogues]
    for run, setting in plan(settings, runs):
        if all((setting, run, i) in done for i in ids):
            records = [rec for i in ids for rec in done[(setting, run, i)]]
            results.setdefault(setting, []).append(score_run(records))
    return results, stopped


def print_table(summary, log=print):
    cols = [("JGA", "jga"), ("JGA district relaxed", "jga_district_relaxed"), ("slot JGA", "slot_jga"),
            ("intent", "intent_acc"), ("slot F1", "slot_f1"),
            ("halluc.", "hallucinated_slot_rate"), ("rejected", "slot_rejection_rate"), ("failed", "failed_rate"),
            ("LLM ms", "llm_ms_mean"), ("tok/turn", "tokens_per_turn")]
    def cell(a, whole):
        if a["mean"] is None:
            return "—"
        f = "{:.0f}" if whole else "{:.3f}"
        return f.format(a["mean"]) + (f" [{f.format(a['min'])}-{f.format(a['max'])}]" if a["n_runs"] > 1 else "")

    rows = [["setting", "runs"] + [c for c, _ in cols]]
    for setting, agg in summary.items():
        rows.append([setting, str(agg["jga"]["n_runs"])] +
                    [cell(agg[key], key in ("llm_ms_mean", "tokens_per_turn")) for _, key in cols])
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        log("  " + "  ".join(c.rjust(w) if i > 1 else c.ljust(w) for i, (c, w) in enumerate(zip(r, widths))))


def model_slug(model):
    return re.sub(r"[^A-Za-z0-9.]+", "-", model).strip("-")


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--data", default="data/fresh_dialogues_states.json", help="dialogues with labelled states")
    ap.add_argument("--settings", nargs="+", choices=SETTINGS, default=list(SETTINGS))
    ap.add_argument("--runs", type=int, default=3, help="runs per LLM setting (rules runs once)")
    ap.add_argument("--model", help="model name (default: C1_LLM_MODEL)")
    ap.add_argument("--effort", choices=REASONING_EFFORTS, help="reasoning effort (default: C1_LLM_REASONING_EFFORT)")
    ap.add_argument("--timeout", type=float, help="seconds per LLM request (default: C1_LLM_TIMEOUT)")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between LLM call starts (default 4)")
    ap.add_argument("--limit", type=int, help="first N dialogues only (a quick check; not for the results)")
    ap.add_argument("--out-dir", default="results")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    dialogues = load_json(a.data)
    if not all(t.get("state", {}).get("labelled", True) for d in dialogues for t in d["turns"]
               if t.get("speaker") == "user"):
        sys.exit(f"{a.data}: not every user turn is labelled")
    if a.limit:
        dialogues = dialogues[:a.limit]
    base = dialogue_settings()
    overrides = {"model": a.model, "reasoning_effort": a.effort, "timeout": a.timeout}
    base = replace(base, **{k: v for k, v in overrides.items() if v is not None})
    uses_llm = any(s != "rules" for s in a.settings)
    slug = model_slug(base.model) if uses_llm else "none"
    n_turns = sum(len(user_turns(d)) for d in dialogues)
    calls = n_turns * a.runs * sum(s != "rules" for s in a.settings)
    print(f"data      {a.data}: {len(dialogues)} dialogues, {n_turns} user turns")
    print(f"settings  {', '.join(a.settings)}; {a.runs} runs per LLM setting; {calls} LLM calls"
          + (f" (about {calls * max(a.pause, 5) / 60:.0f} min at --pause {a.pause})" if calls else ""))
    if uses_llm:
        print(f"model     {base.model} | effort {base.reasoning_effort or 'not sent'} | timeout {base.timeout}s | "
              f"api key {'set' if base.api_key else 'not set'}")
    if a.limit:
        print("NOTE      --limit: a quick check, not the results")

    from app.core import pipeline       # torch and the models load only now
    engine = pipeline.get_engine()
    llm = EvalLLM(OpenAICompatClient.from_settings(base), pause=a.pause) if uses_llm else None
    os.makedirs(a.out_dir, exist_ok=True)
    checkpoint = os.path.join(a.out_dir, f"dialogue_eval_{slug}{'_limit' + str(a.limit) if a.limit else ''}.jsonl")
    print(f"checkpoint {checkpoint}\n")

    def make_manager(setting):
        return DialogueManager(llm if setting != "rules" else None, replace(base, mode=setting))

    results, stopped = evaluate(dialogues, a.settings, a.runs, make_manager, engine.new_session, llm, checkpoint)
    summary = {s: aggregate(runs) for s, runs in results.items()}
    meta = {"run_at": time.strftime("%Y-%m-%d %H:%M"), "data": a.data, "dialogues": len(dialogues),
            "turns": n_turns, "model": base.model if uses_llm else None,
            "reasoning_effort": base.reasoning_effort or None, "history_turns": base.history_turns,
            "pause": a.pause, "limit": a.limit, "eval_retries": llm.retries if llm else 0,
            "note": "fresh = held-out (the gold set was used to write the rules); gold history at every turn; "
                    "schema slots only; dates scored on the user's words; strict scoring is the main number",
            "secondary": DISTRICT_RELAXED}
    for setting, runs in results.items():
        name = f"dialogue_eval_{setting}" + ("" if setting == "rules" else f"_{slug}") + \
               (f"_limit{a.limit}" if a.limit else "") + ".json"
        expected = 1 if setting == "rules" else a.runs
        with open(os.path.join(a.out_dir, name), "w", encoding="utf-8") as fh:
            json.dump({**meta, "setting": setting, "runs_done": len(runs), "runs_planned": expected,
                       "summary": summary[setting], "runs": runs}, fh, ensure_ascii=False, indent=1)
        print(f"saved {name} ({len(runs)}/{expected} runs)")
    print("\nmean [min-max] over runs")
    print_table(summary)
    if stopped:
        print("\nINCOMPLETE: the run stopped (quota or endpoint); rerun the same command to resume")
    sys.exit(2 if stopped else 0)


if __name__ == "__main__":
    main()
