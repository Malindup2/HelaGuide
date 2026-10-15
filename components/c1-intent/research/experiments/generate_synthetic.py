r"""
Generate synthetic TRAINING dialogues with an LLM, using the hand-checked seed
dialogues as few-shot examples, and validate every dialogue against the schema.
The 70 hand-checked seed dialogues stay as the TEST set.

Three ways to run it. All produce the same validated output.

A) FREE, no API key: let Claude Code (or any chat model) write the dialogues
    python experiments\generate_synthetic.py --export 5
        -> writes prompt files to data/synthetic/prompts/
    Ask Claude Code: "For each .txt file in data/synthetic/prompts/, follow its
    instructions and save the JSON answer to data/synthetic/responses/ with the
    same name but .json"   (or paste prompts into Gemini/ChatGPT web and save the answers)
    python experiments\generate_synthetic.py --ingest --model claude-code
        -> validates the answers and adds the good ones

B) Gemini API free tier (key from aistudio.google.com)
    pip install google-genai
    set GEMINI_API_KEY=your-key
    python experiments\generate_synthetic.py --provider gemini --model <model name from AI Studio> --per-intent 5

C) Anthropic API (paid)
    pip install anthropic
    set ANTHROPIC_API_KEY=your-key
    python experiments\generate_synthetic.py --provider anthropic --per-intent 5

Always try first:  python experiments\generate_synthetic.py --dry-run

Outputs (data/synthetic/):
    synthetic_dialogues.json    accepted dialogues (appended across runs, each records its model)
    rejected.jsonl              rejected dialogues with the reason
    generation_log.json         settings, counts and acceptance rate per run, for the report
"""
import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

DATA = Path("data")
OUT = DATA / "synthetic"
PROMPT_VERSION = "v3-literal-examples"
DEFAULT_MODEL = "claude-sonnet-5-5"
PER_CALL = 5

DISTRICTS = [
    "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo", "Galle", "Gampaha",
    "Hambantota", "Jaffna", "Kalutara", "Kandy", "Kegalle", "Kilinochchi", "Kurunegala",
    "Mannar", "Matale", "Matara", "Monaragala", "Mullaitivu", "Nuwara Eliya", "Polonnaruwa",
    "Puttalam", "Ratnapura", "Trincomalee", "Vavuniya",
]
# Slots whose value must be copied exactly from the user's words (they become entity spans)
EXTRACTIVE = {"new_value", "purpose", "service_mentioned", "issue", "travel_date", "date", "date_of_birth"}

STYLES = {  # style -> (weight, instruction)
    "singlish": (0.50, "User writes romanized Sinhala (Singlish) mixed with English words, e.g. 'mata NIC eka ganna one'."),
    "sinhala_mixed": (0.25, "User writes in Sinhala script with some English words left in Latin letters, e.g. 'මට passport එකක් ඕනේ'."),
    "pure_si": (0.25, "User writes only Sinhala script, no English words at all, e.g. 'මට ගමන් බලපත්‍රයක් ඕනේ'."),
}
PHENOMENA = {
    "none": 0.45,
    "correction": 0.25,       # user corrects a value they gave earlier
    "intent_switch": 0.15,    # user moves to a different core service mid-dialogue
    "multi_slot": 0.15,       # user gives two or more details in one message
}

# Grounded in C2's scraped pages (kg_service_map.json). Things citizens naturally mention.
DOMAIN_HINTS = {
    "nic_new": "first NIC for a teenager or adult; birth certificate needed; apply through the Grama Niladhari / divisional secretariat or the one-day service at the DRP head office in Battaramulla; photo from an approved (ICAO) photo studio",
    "nic_update": "changing address (needs a GN letter / certificate of residence), name after marriage (marriage certificate), civil status or photo; can use the one-day service",
    "nic_replace_lost": "NIC lost, stolen or damaged; needs a police report (police entry) first; may want it urgently via the one-day service",
    "passport_new": "first passport; NIC needed first; passport for a child (both parents involved); normal or urgent service; photo from an approved studio; application form K 35 A",
    "passport_renew": "passport expiring or expired, full pages, or lost/stolen (complaint needed); bring the current passport and NIC; normal or urgent service",
    "birth_cert_copy": "certified copy of a birth certificate, own or a family member's; for NIC, passport, school, visa or a job abroad; can be requested online through e-BMD; may need an English translation",
    "marriage_registration": "registering an upcoming marriage; giving notice of marriage to the registrar; Kandyan marriage; birth certificates of both parties",
    "death_cert_copy": "copy of a family member's death certificate; for land, bank, pension or insurance matters; can be requested online through e-BMD; may need a translation",
}


# ------------------------------------------------------------------ prompt
def weighted(d):
    keys = list(d)
    weights = [v[0] if isinstance(v, tuple) else v for v in d.values()]
    return random.choices(keys, weights=weights)[0]


def make_specs(intent, core, n):
    specs = []
    for _ in range(n):
        ph = weighted(PHENOMENA)
        spec = {
            "intent": intent,
            "style": weighted(STYLES),
            "phenomenon": ph,
            "user_turns": random.choice([1, 2, 3, 3, 4]) if ph == "none" else random.choice([2, 3, 4]),
        }
        if ph == "intent_switch":
            spec["switch_to"] = random.choice([i for i in core if i != intent])
        specs.append(spec)
    return specs


def follows_literal_rule(d):
    """True if every extractive slot value is the user's exact words (seed examples must obey the prompt's rules)."""
    said = ""
    for t in d["turns"]:
        if t.get("speaker") != "user" or "state" not in t:
            continue
        said += " " + t["text"]
        for k, v in t["state"].get("slots", {}).items():
            if k in EXTRACTIVE and str(v).lower() not in said.lower():
                return False
    return True


def pick_examples(seed, intent, core, k=3):
    seed = [d for d in seed if follows_literal_rule(d)]
    same = [d for d in seed if first_intent(d) == intent]
    other = [d for d in seed if first_intent(d) in core and first_intent(d) != intent]
    ex = random.sample(same, min(1, len(same))) + random.sample(other, k - min(1, len(same)))
    return [{"turns": d["turns"]} for d in ex]


def build_prompt(schema, intent, specs, examples):
    core = {k: v for k, v in schema["intents"].items() if v["route"] == "orchestration" and v["department"]}
    slot_defs = {s: schema["slots"][s] for s in sorted({s for v in core.values() for s in v["slots"]})}
    spec_lines = "\n".join(
        f"{i+1}. intent={s['intent']}, style={s['style']}, phenomenon={s['phenomenon']}"
        + (f" (switch to {s['switch_to']})" if s.get("switch_to") else "")
        + f", user turns={s['user_turns']}"
        for i, s in enumerate(specs)
    )
    style_rules = "\n".join(f"- {k}: {v[1]}" for k, v in STYLES.items())
    used = [intent] + [x["switch_to"] for x in specs if x.get("switch_to")]
    hint_lines = "\n".join(f"- {i}: {DOMAIN_HINTS[i]}" for i in dict.fromkeys(used) if i in DOMAIN_HINTS)
    return f"""You are generating realistic training data for a Sri Lankan government-service assistant.
Citizens chat in Sinhala, English and code-mixed Singlish. Write {len(specs)} dialogues, one per spec below.

## Specs
{spec_lines}

## Styles
{style_rules}

## What citizens typically mention (use naturally and vary it; not every dialogue)
{hint_lines}

## Intents and their slots
{json.dumps({k: v["slots"] for k, v in core.items()}, indent=1)}

## Slot definitions
{json.dumps(slot_defs, ensure_ascii=False, indent=1)}
district must be one of: {", ".join(DISTRICTS)} (always written in English in the state, whatever the user wrote).

## Labelling rules (strict)
1. Every user turn has a "state" with the intent and ALL slots filled so far (cumulative), not just new ones.
2. Only fill a slot when the user actually said it. Never infer or guess.
3. These slots must be an EXACT substring of the user's own words, in the script they used: {", ".join(sorted(EXTRACTIVE))}.
   Example: user wrote "ලබන මාසේ" -> travel_date is "ලබන මාසේ", not "next month".
4. Enum slots must use the exact listed values.
5. Correction: the new value replaces the old one. Intent switch: add "previous_intent" to that turn's state.
6. Bot turns have no state. Bot asks short, natural follow-up questions in the user's style.
7. Use fake but realistic details. Never real NIC numbers. Vary names, places, dates and wording;
   do not copy the examples. Write the way real people type: short, casual, sometimes misspelled.
8. For nic_new, include date_of_birth in some dialogues (e.g. "1998.05.12", "2008 march 3").

## Examples of the format
{json.dumps(examples, ensure_ascii=False, indent=1)}

Return ONLY a JSON array of {len(specs)} objects, each {{"turns": [...]}}, in spec order. No commentary."""


# ------------------------------------------------------------------ validation
def first_intent(d):
    return next(t["state"]["intent"] for t in d["turns"] if "state" in t)


def validate(d, schema, spec):
    intents = schema["intents"]
    turns = d.get("turns")
    if not isinstance(turns, list) or not turns:
        return "format: no turns"
    users = [t for t in turns if t.get("speaker") == "user"]
    if not users or any("state" not in t for t in users):
        return "format: user turn without state"
    if any(t.get("speaker") not in ("user", "bot") for t in turns):
        return "format: bad speaker"
    if first_intent(d) != spec["intent"]:
        return f"wrong_intent: started with {first_intent(d)}"

    said, prev = "", None
    for t in users:
        said += " " + t["text"]
        st = t["state"]
        intent, slots = st.get("intent"), st.get("slots", {})
        if intent not in intents:
            return f"unknown_intent: {intent}"
        allowed = set(intents[intent]["slots"])
        if st.get("previous_intent") in intents:
            allowed |= set(intents[st["previous_intent"]]["slots"])
        for k, v in slots.items():
            if k not in allowed:
                return f"slot_not_allowed: {k} for {intent}"
            sd = schema["slots"][k]
            if k == "district":
                if v not in DISTRICTS:
                    return f"bad_district: {v}"
            elif sd["type"] == "enum" and v not in sd["values"]:
                return f"bad_enum: {k}={v}"
            elif k in EXTRACTIVE and str(v).lower() not in said.lower():
                return f"value_not_in_text: {k}='{v}'"
        if prev and prev["intent"] == intent:
            lost = set(prev.get("slots", {})) - set(slots)
            if lost:
                return f"state_dropped: {sorted(lost)}"
        prev = st

    user_text = " ".join(t["text"] for t in users)
    leaked = [k for k in list(schema["slots"]) + list(intents) if "_" in k and k in user_text]
    if leaked:
        return f"leaked_field_name: {leaked[0]} in user text"
    has_si = bool(re.search(r"[\u0D80-\u0DFF]", user_text))
    if spec["style"] == "pure_si" and re.search(r"[A-Za-z]{3,}", user_text):
        return "style_mismatch: English letters in pure_si"
    if spec["style"] == "singlish" and has_si:
        return "style_mismatch: Sinhala script in singlish"
    if spec["style"] in ("sinhala_mixed", "pure_si") and not has_si:
        return "style_mismatch: no Sinhala script"
    if spec["phenomenon"] == "intent_switch" and not any("previous_intent" in t["state"] for t in users):
        return "switch_missing: no previous_intent"
    return None


def norm(text):
    return re.sub(r"\W+", " ", text.lower()).strip()



# ------------------------------------------------------------------ LLM backends
def parse_json_array(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("["), text.rfind("]")
    return json.loads(text[start:end + 1] if start != -1 else text)


def make_caller(provider, model):
    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY is not set. Run:  set ANTHROPIC_API_KEY=your-key")
        import anthropic
        client = anthropic.Anthropic()

        def call(prompt):
            msg = client.messages.create(model=model, max_tokens=8000,
                                         messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            return parse_json_array(text), {"input_tokens": msg.usage.input_tokens,
                                            "output_tokens": msg.usage.output_tokens}
        return call

    if provider == "gemini":
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            sys.exit("GEMINI_API_KEY is not set. Get one at aistudio.google.com, then: set GEMINI_API_KEY=your-key")
        from google import genai
        client = genai.Client()

        def call(prompt):
            resp = client.models.generate_content(           # JSON mode: forces valid JSON output
                model=model, contents=prompt, config={"response_mime_type": "application/json"})
            meta = getattr(resp, "usage_metadata", None)
            usage = {"input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
                     "output_tokens": getattr(meta, "candidates_token_count", 0) or 0}
            return parse_json_array(resp.text), usage
        return call

    sys.exit(f"Unknown provider {provider}")


def write_safely(path, text, tries=10):
    """Write via a temp file and swap it in. On Windows the swap fails while another
    program (VS Code, antivirus, a second run) has the file open, so retry, then
    fall back to writing in place."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for i in range(tries):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.5 * (i + 1))
    path.write_text(text, encoding="utf-8")
    tmp.unlink(missing_ok=True)
    print(f"  note: {path.name} was locked by another program; wrote it directly")


# ------------------------------------------------------------------ accept / reject
class Collector:
    def __init__(self, seed, model):
        OUT.mkdir(parents=True, exist_ok=True)
        self.out_file = OUT / "synthetic_dialogues.json"
        self.accepted = self._load()
        self.new = []                      # dialogues accepted in this run (ids assigned when saving)
        self.seen = {norm(t["text"]) for d in seed + self.accepted for t in d["turns"][:1]}
        self.model = model
        self.stats, self.reasons, self.usage = Counter(), Counter(), Counter()

    def _load(self):
        return json.loads(self.out_file.read_text(encoding="utf-8")) if self.out_file.exists() else []

    def add(self, dialogues, specs, schema):
        """Validate one batch. Returns number accepted."""
        got = 0
        if len(dialogues) != len(specs):
            self.reasons["count_mismatch"] += abs(len(specs) - len(dialogues))
        for d, spec in zip(dialogues, specs):
            self.stats["generated"] += 1
            try:
                why = validate(d, schema, spec)
            except Exception as e:           # malformed dialogue structure
                why = f"format: {type(e).__name__}"
            key = norm(d["turns"][0]["text"]) if not why else ""
            if not why and key in self.seen:
                why = "duplicate: first turn already exists"
            if why:
                self.reasons[why.split(":")[0]] += 1
                with open(OUT / "rejected.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"reason": why, "spec": spec, "model": self.model, "dialogue": d},
                                        ensure_ascii=False) + "\n")
                continue
            self.seen.add(key)
            self.new.append({
                "dialogue_id": None, "source": "synthetic", "model": self.model,
                "prompt_version": PROMPT_VERSION,
                "script": "romanized" if spec["style"] == "singlish" else "sinhala",
                "code_mix": "pure_si" if spec["style"] == "pure_si" else "mixed",
                "phenomena": [] if spec["phenomenon"] == "none" else [spec["phenomenon"]],
                "turns": d["turns"],
            })
            self.stats["accepted"] += 1
            got += 1
        return got

    def flush(self):
        """Merge this run's new dialogues into the file as it is NOW, so two runs
        at the same time (e.g. Gemini + ingest) never overwrite each other."""
        current = self._load()
        taken = {norm(d["turns"][0]["text"]) for d in current}
        added = 0
        for d in self.new:
            if norm(d["turns"][0]["text"]) in taken:      # another run added it meanwhile
                self.stats["accepted"] -= 1
                self.reasons["duplicate"] += 1
                continue
            d["dialogue_id"] = f"s{len(current) + 1:04d}"
            current.append(d)
            taken.add(norm(d["turns"][0]["text"]))
            added += 1
        if added:
            write_safely(self.out_file, json.dumps(current, ensure_ascii=False, indent=2))
        self.accepted, self.new = current, []
        return added

    def save(self, args, mode):
        self.flush()
        rate = round(self.stats["accepted"] / self.stats["generated"], 3) if self.stats["generated"] else 0
        log = {
            "run_at": datetime.now().isoformat(timespec="seconds"), "mode": mode, "model": self.model,
            "prompt_version": PROMPT_VERSION, "random_seed": args.seed,
            "generated": self.stats["generated"], "accepted": self.stats["accepted"], "acceptance_rate": rate,
            "rejection_reasons": dict(self.reasons), "token_usage": dict(self.usage),
            "total_synthetic": len(self.accepted),
        }
        log_file = OUT / "generation_log.json"
        runs = json.loads(log_file.read_text(encoding="utf-8")) if log_file.exists() else []
        write_safely(log_file, json.dumps(runs + [log], ensure_ascii=False, indent=2))
        print(f"\nGenerated {self.stats['generated']}, accepted {self.stats['accepted']} ({rate:.0%}). "
              f"Total synthetic dialogues: {len(self.accepted)}")
        if self.reasons:
            print("Rejections:", dict(self.reasons.most_common()))
        print("Details of rejections: data/synthetic/rejected.jsonl")


# ------------------------------------------------------------------ modes
def run_api(args, schema, seed, core):
    call = make_caller(args.provider, args.model)
    col = Collector(seed, args.model)
    for intent in core:
        got, attempts = 0, 0
        while got < args.per_intent and attempts < args.per_intent * 3:
            n = min(PER_CALL, args.per_intent - got)
            specs = make_specs(intent, core, n)
            prompt = build_prompt(schema, intent, specs, pick_examples(seed, intent, core))
            attempts += n
            try:
                dialogues, usage = call(prompt)
                col.usage.update(usage)
            except Exception as e:  # bad JSON, rate limit, API error: log, wait, retry
                msg = str(e)
                if any(x in msg for x in ("404", "NOT_FOUND", "PERMISSION_DENIED", "API key not valid",
                                          "API_KEY_INVALID", "401", "403")):
                    col.save(args, f"api:{args.provider}")
                    sys.exit(f"\nStopped: this will not fix itself by retrying.\n{msg[:300]}\n"
                             "Check the model name (try another one) and the API key.")
                col.reasons[f"call_failed_{type(e).__name__}"] += n
                col.stats["generated"] += n
                print(f"  call failed ({type(e).__name__}: {str(e)[:120]}), waiting {args.wait}s")
                time.sleep(args.wait)
                continue
            got += col.add(dialogues, specs, schema)
            time.sleep(args.wait if args.provider == "gemini" else 0)   # stay inside free-tier rate limits
        col.flush()
        print(f"  {intent:24s} +{got}")
    col.save(args, f"api:{args.provider}")


def run_export(args, schema, seed, core):
    pdir, rdir = OUT / "prompts", OUT / "responses"
    pdir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    n_files = 0
    for intent in core:
        left, k = args.export, 0
        while left > 0:
            n = min(PER_CALL, left)
            specs = make_specs(intent, core, n)
            name = f"{stamp}_{intent}_{k:02d}"
            (pdir / f"{name}.txt").write_text(
                build_prompt(schema, intent, specs, pick_examples(seed, intent, core)), encoding="utf-8")
            (pdir / f"{name}.spec.json").write_text(json.dumps(specs, ensure_ascii=False, indent=1), encoding="utf-8")
            left, k, n_files = left - n, k + 1, n_files + 1
    print(f"Wrote {n_files} prompt files to {pdir} ({args.export} dialogues per intent).")
    print(f"Save each answer as {rdir}\\<same name>.json  (only the JSON array), then run:")
    print("  python experiments\\generate_synthetic.py --ingest --model <who wrote them, e.g. claude-code>")


def run_ingest(args, schema, seed, core):
    pdir, rdir, done = OUT / "prompts", OUT / "responses", OUT / "done"
    done.mkdir(parents=True, exist_ok=True)
    col = Collector(seed, args.model)
    missing = 0
    for spec_file in sorted(pdir.glob("*.spec.json")):
        name = spec_file.name[: -len(".spec.json")]
        resp = rdir / f"{name}.json"
        if not resp.exists():
            missing += 1
            continue
        specs = json.loads(spec_file.read_text(encoding="utf-8"))
        try:
            dialogues = parse_json_array(resp.read_text(encoding="utf-8"))
        except Exception as e:
            col.reasons[f"bad_json_{type(e).__name__}"] += len(specs)
            col.stats["generated"] += len(specs)
            print(f"  {name}: could not parse JSON ({e}); left in place to fix")
            continue
        got = col.add(dialogues, specs, schema)
        print(f"  {name}: +{got}/{len(specs)}")
        for f in (spec_file, pdir / f"{name}.txt", resp):        # processed: move out of the queue
            f.replace(done / f.name)
    if missing:
        print(f"  {missing} prompt(s) have no answer yet in {rdir}")
    col.save(args, "ingest")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["anthropic", "gemini"], help="call an API directly")
    ap.add_argument("--per-intent", type=int, default=5, help="API mode: accepted dialogues to add per core intent")
    ap.add_argument("--export", type=int, metavar="N", help="write prompt files for N dialogues per intent")
    ap.add_argument("--ingest", action="store_true", help="validate answers saved in data/synthetic/responses/")
    ap.add_argument("--model", help="API model name, or who wrote the answers in --ingest mode")
    ap.add_argument("--wait", type=int, default=15, help="seconds between Gemini calls / after errors")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true", help="print one prompt and exit")
    args = ap.parse_args()
    random.seed(args.seed)

    with open(DATA / "schema_v1.json", encoding="utf-8") as fh:
        schema = json.load(fh)
    with open(DATA / "seed_all.json", encoding="utf-8") as fh:
        seed = json.load(fh)
    core = [k for k, v in schema["intents"].items() if v.get("route") == "orchestration" and v.get("department")]
    if not core:
        sys.exit("No core intents found in schema (need route=orchestration and a department).")

    if args.dry_run:
        print(build_prompt(schema, core[0], make_specs(core[0], core, PER_CALL), pick_examples(seed, core[0], core)))
    elif args.export:
        run_export(args, schema, seed, core)
    elif args.ingest:
        if not args.model:
            sys.exit("Say who wrote the answers, e.g.  --model claude-code  or  --model gemini-web")
        run_ingest(args, schema, seed, core)
    elif args.provider:
        if not args.model:
            args.model = DEFAULT_MODEL if args.provider == "anthropic" else None
        if not args.model:
            sys.exit("Give the Gemini model name from AI Studio, e.g.  --model <name>")
        run_api(args, schema, seed, core)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
