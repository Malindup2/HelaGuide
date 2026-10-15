r"""
Word-level language tags for the synthetic dialogues (option C):
an LLM tags every word, you hand-check a sample in Label Studio, and the
script measures how good the LLM tags are before they are used for training.

Run from the research folder (conda activate nlp). Steps, in order:

1) python experiments\tag_synthetic.py --export
       writes tagging prompts to data/synthetic/tagging/prompts/
   Then ask Claude Code: "For each .txt file in data/synthetic/tagging/prompts/,
   follow its instructions and save only the JSON answer to
   data/synthetic/tagging/responses/ with the same name but .json"
   (or: python experiments\tag_synthetic.py --provider gemini --model <name>)

2) python experiments\tag_synthetic.py --ingest --model claude-code
       checks the answers and stores the tags

3) python experiments\tag_synthetic.py --to-labelstudio 30
       picks 30 dialogues and writes data/synthetic/ls_check_tasks.json
   Import it into a NEW Label Studio project ("CS-Intent Synthetic Check",
   same labelling config). NOT into the gold project. Correct and submit all.
   Export JSON as data/synthetic/ls_check_export.json

4) python experiments\tag_synthetic.py --compare
       LLM tags and heuristic tags vs your corrections -> results/synthetic_tag_quality.json

5) python experiments\tag_synthetic.py --build
       writes data/synthetic/silver_tokens.jsonl (same format as gold_tokens.jsonl)
       language tags: your correction > LLM tag > heuristic; entities from slot values
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prepare_labelstudio import guess_lang, rid, slot_spans, words_with_offsets   # same tokens as gold
from baseline_fasttext import submitted_result, to_example
from generate_synthetic import make_caller, write_safely

DATA = Path("data")
SYN = DATA / "synthetic"
TAG = SYN / "tagging"
TAGS_FILE = SYN / "synthetic_lang_tags.json"
CHECK_TASKS = SYN / "ls_check_tasks.json"
CHECK_EXPORT = SYN / "ls_check_export.json"
RESULTS = Path("results")
LABELS = ["SI", "EN", "MIXED", "NE", "OTHER"]
TURNS_PER_PROMPT = 40
PROMPT_VERSION = "tag-v1"
FEWSHOT_KEYS = [("d001", 0), ("d011", 0), ("d014", 0), ("d028", 0), ("d036", 2), ("d051", 0), ("d004", 0)]


# ------------------------------------------------------------------ helpers
def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def synthetic_turns():
    """(key, dialogue, turn_index, tokens) for every user turn of every synthetic dialogue."""
    for d in load_json(SYN / "synthetic_dialogues.json", []):
        for i, t in enumerate(d["turns"]):
            if t.get("speaker") == "user":
                yield f"{d['dialogue_id']}|{i}", d, i, [w for w, _, _ in words_with_offsets(t["text"])]


def fewshot():
    gold = {}
    gf = DATA / "gold_tokens.jsonl"
    if gf.exists():
        for line in gf.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            gold[(e["dialogue_id"], e["turn"])] = e
    ex = [gold[k] for k in FEWSHOT_KEYS if k in gold]
    return [{"tokens": e["tokens"], "tags": e["lang_tags"]} for e in ex]


def build_prompt(items):
    examples = "\n".join(json.dumps(e, ensure_ascii=False) for e in fewshot())
    todo = json.dumps([{"key": k, "tokens": toks} for k, toks in items], ensure_ascii=False, indent=0)
    return f"""Tag the language of every token in these Sri Lankan citizen messages (Sinhala, English, code-mixed Singlish).

## Tags
- SI: a Sinhala word, in Sinhala script OR romanized. Romanized examples: mata, eka, ganna, karanna, oya,
  kohomada, ow, na. Note: "one" in Singlish usually means ඕනේ (need) -> SI; only English "one" (e.g. "one day") is EN.
- EN: an English word or English acronym: address, NIC, ID, passport, renew, certificate, urgent, GN, office.
  An English word written inside a Sinhala sentence is still EN (e.g. "passport" in "මට passport එකක් ඕනේ").
- MIXED: one token that combines both, e.g. "16i" (number + Sinhala suffix), "NIC-eka", "passportekata".
- NE: names of places, people, countries, institutions used as names: Colombo, කොළඹ, Kandy, Nimali, Canada, Battaramulla.
- OTHER: numbers, dates written in digits, symbols: 45, 18, 1998.05.12.

## Examples (tokens -> tags)
{examples}

## Rules
- Return exactly one tag per token, in the same order. Never merge, split or skip tokens.
- Return ONLY a JSON object mapping each key to its list of tags, e.g. {{"s0001|0": ["SI","EN","SI"]}}.

## Tokens to tag
{todo}"""


def parse_obj(text):
    import re
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    a, b = text.find("{"), text.rfind("}")
    return json.loads(text[a:b + 1] if a != -1 else text)


def accept_answer(answer, items, store, model, stats):
    want = dict(items)
    for key, toks in want.items():
        tags = answer.get(key)
        if not isinstance(tags, list):
            stats["missing"] += 1
        elif len(tags) != len(toks):
            stats["length_mismatch"] += 1
        elif any(t not in LABELS for t in tags):
            stats["bad_label"] += 1
        else:
            store[key] = {"tags": tags, "model": model, "prompt_version": PROMPT_VERSION}
            stats["accepted"] += 1


def untagged(store):
    return [(k, toks) for k, _, _, toks in synthetic_turns() if k not in store and toks]


# ------------------------------------------------------------------ steps
def step_export(args):
    store = load_json(TAGS_FILE, {})
    todo = untagged(store)
    (TAG / "prompts").mkdir(parents=True, exist_ok=True)
    (TAG / "responses").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for n, start in enumerate(range(0, len(todo), TURNS_PER_PROMPT)):
        chunk = todo[start:start + TURNS_PER_PROMPT]
        name = f"{stamp}_tags_{n:03d}"
        (TAG / "prompts" / f"{name}.txt").write_text(build_prompt(chunk), encoding="utf-8")
        (TAG / "prompts" / f"{name}.items.json").write_text(json.dumps(chunk, ensure_ascii=False), encoding="utf-8")
    print(f"{len(todo)} user turns need tags -> {-(-len(todo) // TURNS_PER_PROMPT)} prompt files in {TAG / 'prompts'}")


def step_ingest(args):
    store = load_json(TAGS_FILE, {})
    done = TAG / "done"
    done.mkdir(parents=True, exist_ok=True)
    stats, waiting = Counter(), 0
    for items_file in sorted((TAG / "prompts").glob("*.items.json")):
        name = items_file.name[: -len(".items.json")]
        resp = TAG / "responses" / f"{name}.json"
        if not resp.exists():
            waiting += 1
            continue
        items = json.loads(items_file.read_text(encoding="utf-8"))
        try:
            answer = parse_obj(resp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  {name}: bad JSON ({e}); fix or delete the response and retry")
            continue
        before = stats["accepted"]
        accept_answer(answer, items, store, args.model, stats)
        print(f"  {name}: {stats['accepted'] - before}/{len(items)} turns tagged")
        for f in (items_file, TAG / "prompts" / f"{name}.txt", resp):
            f.replace(done / f.name)
    write_safely(TAGS_FILE, json.dumps(store, ensure_ascii=False, indent=1))
    left = len(untagged(store))
    print(f"\nTagged {stats['accepted']} turns. Problems: {dict((k, v) for k, v in stats.items() if k != 'accepted')}")
    print(f"{waiting} prompt(s) still waiting for answers. {left} turns still untagged "
          f"(run --export again to create prompts for them).")


def step_api(args):
    call = make_caller(args.provider, args.model)
    store = load_json(TAGS_FILE, {})
    todo, stats = untagged(store), Counter()
    import time
    for start in range(0, len(todo), TURNS_PER_PROMPT):
        chunk = todo[start:start + TURNS_PER_PROMPT]
        try:
            # make_caller expects a JSON array; wrap the object so it parses
            answer, _ = call(build_prompt(chunk) + "\n\nWrap your JSON object in a one-element array: [ {...} ]")
            answer = answer[0] if isinstance(answer, list) else answer
            accept_answer(answer, chunk, store, args.model, stats)
        except SystemExit:
            raise
        except Exception as e:
            print(f"  call failed ({type(e).__name__}: {str(e)[:100]})")
        write_safely(TAGS_FILE, json.dumps(store, ensure_ascii=False, indent=1))
        print(f"  {min(start + TURNS_PER_PROMPT, len(todo))}/{len(todo)} turns processed")
        time.sleep(args.wait)
    print(f"Tagged {stats['accepted']}. Problems: {dict((k, v) for k, v in stats.items() if k != 'accepted')}")


def step_to_labelstudio(args):
    store = load_json(TAGS_FILE, {})
    dialogues = load_json(SYN / "synthetic_dialogues.json", [])
    tagged = [d for d in dialogues
              if all(f"{d['dialogue_id']}|{i}" in store for i, t in enumerate(d["turns"]) if t["speaker"] == "user")]
    if not tagged:
        sys.exit("No fully tagged dialogues yet. Run --ingest first.")
    random.seed(args.seed)
    groups = defaultdict(list)                         # stratify by generator x code-mix
    for d in tagged:
        groups[(d["model"], d["code_mix"])].append(d)
    pick, keys = [], sorted(groups)
    while len(pick) < min(args.to_labelstudio, len(tagged)):
        for k in keys:
            if groups[k] and len(pick) < args.to_labelstudio:
                pick.append(groups[k].pop(random.randrange(len(groups[k]))))
    tasks = []
    for d in pick:
        prev_bot = ""
        for i, t in enumerate(d["turns"]):
            if t["speaker"] == "bot":
                prev_bot = t["text"]
                continue
            text, state = t["text"], t.get("state", {})
            tags = store[f"{d['dialogue_id']}|{i}"]["tags"]
            lang = [{"id": rid(), "from_name": "lang", "to_name": "text", "type": "labels",
                     "value": {"start": s, "end": e, "text": w, "labels": [tag]}}
                    for (w, s, e), tag in zip(words_with_offsets(text), tags)]
            tasks.append({
                "data": {"text": text, "context": f"Bot asked: {prev_bot}" if prev_bot else "(first turn)",
                         "info": f"{d['dialogue_id']} | turn {i} | {state.get('intent')} | {d['code_mix']} | {d['model']}",
                         "dialogue_id": d["dialogue_id"], "turn": i, "intent": state.get("intent"),
                         "code_mix": d["code_mix"], "model": d["model"]},
                "predictions": [{"model_version": "llm_tags", "result": lang + slot_spans(text, state.get("slots", {}))}],
            })
    write_safely(CHECK_TASKS, json.dumps(tasks, ensure_ascii=False, indent=1))
    print(f"{len(pick)} dialogues ({len(tasks)} turns) -> {CHECK_TASKS}")
    print("Mix:", dict(Counter(f"{d['model']} / {d['code_mix']}" for d in pick)))
    print("Import into a NEW Label Studio project, not the gold one.")


def human_checked():
    if not CHECK_EXPORT.exists():
        return {}
    out = {}
    for task in json.loads(CHECK_EXPORT.read_text(encoding="utf-8")):
        res = submitted_result(task)
        if res is not None:
            ex = to_example(task, res)
            out[f"{ex['dialogue_id']}|{ex['turn']}"] = ex
    return out


def step_compare(args):
    checked, store = human_checked(), load_json(TAGS_FILE, {})
    if not checked:
        sys.exit(f"{CHECK_EXPORT} not found or has no submitted tasks.")
    writer = {d["dialogue_id"]: d["model"] for d in load_json(SYN / "synthetic_dialogues.json", [])}
    pairs = defaultdict(list)
    for key, ex in checked.items():
        llm = store.get(key, {})
        for i, (w, gold) in enumerate(zip(ex["tokens"], ex["lang_tags"])):
            if gold == "UNLABELLED":
                continue
            grp = f"written by {writer.get(ex['dialogue_id'], '?')} / {ex.get('code_mix')}"
            if "tags" in llm:
                pairs["llm:ALL"].append((gold, llm["tags"][i]))
                pairs[f"llm:{grp}"].append((gold, llm["tags"][i]))
            pairs["heuristic:ALL"].append((gold, guess_lang(w)))
            pairs[f"heuristic:{grp}"].append((gold, guess_lang(w)))
    acc = {k: {"acc": round(sum(g == p for g, p in v) / len(v), 4), "n": len(v)} for k, v in sorted(pairs.items())}
    errors = Counter(f"{g}->{p}" for g, p in pairs["llm:ALL"] if g != p)
    RESULTS.mkdir(exist_ok=True)
    out = {"checked_turns": len(checked), "accuracy_vs_human": acc, "llm_error_types": dict(errors.most_common(10))}
    write_safely(RESULTS / "synthetic_tag_quality.json", json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Checked turns: {len(checked)}\n\nTag accuracy against your corrections:")
    for k, v in acc.items():
        print(f"  {k:42s}{v['acc']:>7}   n={v['n']}")
    print("\nMost common LLM mistakes (gold->llm):", dict(errors.most_common(5)))
    print("Saved results/synthetic_tag_quality.json")


def step_build(args):
    store, checked = load_json(TAGS_FILE, {}), human_checked()
    src_count, n = Counter(), 0
    with open(SYN / "silver_tokens.jsonl", "w", encoding="utf-8") as fh:
        for key, d, i, tokens in synthetic_turns():
            if not tokens:
                continue
            t = d["turns"][i]
            if key in checked:
                ex = checked[key]
                lang, ner, src = ex["lang_tags"], ex["ner_tags"], "human"
            else:
                if key in store:
                    lang, src = store[key]["tags"], "llm"
                else:
                    lang, src = [guess_lang(w) for w in tokens], "heuristic"
                fake_task = {"data": {"text": t["text"], "dialogue_id": d["dialogue_id"], "turn": i,
                                      "intent": t["state"].get("intent"), "code_mix": d["code_mix"]}}
                ner = to_example(fake_task, slot_spans(t["text"], t["state"].get("slots", {})))["ner_tags"]
            src_count[src] += 1
            fh.write(json.dumps({
                "dialogue_id": d["dialogue_id"], "turn": i, "intent": t["state"].get("intent"),
                "code_mix": d["code_mix"], "text": t["text"], "tokens": tokens, "lang_tags": lang,
                "ner_tags": ner, "source": "synthetic", "model": d["model"], "tag_source": src,
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"Wrote {n} turns to {SYN / 'silver_tokens.jsonl'}")
    print("Language tags came from:", dict(src_count))
    if src_count["heuristic"]:
        print("Note: some turns used heuristic tags because no LLM tags exist for them yet.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--provider", choices=["anthropic", "gemini"])
    ap.add_argument("--model")
    ap.add_argument("--wait", type=int, default=15)
    ap.add_argument("--to-labelstudio", type=int, metavar="N")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.export:
        step_export(args)
    elif args.ingest:
        if not args.model:
            sys.exit("Say who tagged them, e.g.  --model claude-code")
        step_ingest(args)
    elif args.provider:
        if not args.model:
            sys.exit("Give the model name, e.g.  --model gemini-3.5-flash-lite")
        step_api(args)
    elif args.to_labelstudio:
        step_to_labelstudio(args)
    elif args.compare:
        step_compare(args)
    elif args.build:
        step_build(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
