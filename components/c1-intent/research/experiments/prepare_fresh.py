r"""
Fresh, human-written test set: labelled FROM SCRATCH (no pre-labels), so neither the
heuristic nor an LLM influenced the labels. Used only for testing, never for training.

Run from the research folder (conda activate nlp):

1) python experiments\prepare_fresh.py --to-labelstudio
       reads  data/fresh_dialogues.txt
       writes data/fresh_dialogues.json      (parsed dialogues with intents)
              data/fresh_ls_tasks.json       (Label Studio tasks, NO pre-labels)
   Import into a NEW Label Studio project "CS-Intent Fresh Test" (same labelling config).
   Label every word's language and every entity yourself, submit all, export JSON as
   data/fresh_ls_export.json

2) python experiments\prepare_fresh.py --from-export
       writes data/fresh_tokens.jsonl        (same format as gold_tokens.jsonl, + baseline predictions)
              results/fresh_baselines.json   (heuristic and fastText scores on the fresh set)
   Upload fresh_tokens.jsonl to the Colab notebook to score XLM-R on it.

File format for fresh_dialogues.txt:
    # intent: nic_update          starts a dialogue
    U: user message               citizen turn
    B: bot message                bot turn (not labelled)
    U(passport_new): message      citizen switches to another service from this turn on
    (blank line between dialogues)
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prepare_labelstudio import guess_lang, words_with_offsets
from baseline_fasttext import submitted_result, to_example

DATA, RESULTS = Path("data"), Path("results")
TXT, DLG = DATA / "fresh_dialogues.txt", DATA / "fresh_dialogues.json"
TASKS, EXPORT, TOKENS = DATA / "fresh_ls_tasks.json", DATA / "fresh_ls_export.json", DATA / "fresh_tokens.jsonl"
MODEL = Path("models/lid.176.bin")
SINHALA = re.compile(r"[඀-෿]")
LINE = re.compile(r"^(U|B)(?:\(([a-z_]+)\))?\s*:\s*(.*)$")


def known_intents():
    schema = json.loads((DATA / "schema_v1.json").read_text(encoding="utf-8"))
    return set(schema["intents"])


def script_of(user_texts):
    return "sinhala" if SINHALA.search(" ".join(user_texts)) else "romanized"


def style_from_labels(tags):
    """Writing style of a dialogue from YOUR language labels (SI/EN words only)."""
    si, en = tags.count("SI"), tags.count("EN")
    if en and not si:
        return "pure_en"
    if si and not en:
        return "pure_si"
    return "mixed"


def parse(path, intents):
    dialogues, cur, errors = [], None, []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        m_int = re.match(r"^#\s*intent\s*:\s*([a-z_]+)\s*$", line)
        if m_int:
            cur = {"intent": m_int.group(1), "turns": []}
            dialogues.append(cur)
            if cur["intent"] not in intents:
                errors.append(f"line {n}: unknown intent '{cur['intent']}'")
            continue
        m = LINE.match(line)
        if not m or cur is None:
            errors.append(f"line {n}: not understood: {line[:60]}")
            continue
        who, switch, text = m.groups()
        if who == "B":
            cur["turns"].append({"speaker": "bot", "text": text})
            continue
        state = {"intent": cur["intent"]}
        if switch:
            if switch not in intents:
                errors.append(f"line {n}: unknown intent '{switch}'")
            state = {"intent": switch, "previous_intent": cur["intent"]}
            cur["intent"] = switch
        cur["turns"].append({"speaker": "user", "text": text, "state": state})
    if errors:
        sys.exit("Fix these lines in fresh_dialogues.txt:\n  " + "\n  ".join(errors))
    out = []
    for i, d in enumerate(dialogues, 1):
        users = [t["text"] for t in d["turns"] if t["speaker"] == "user"]
        first = next(t["state"]["intent"] for t in d["turns"] if t["speaker"] == "user")
        out.append({"dialogue_id": f"f{i:03d}", "source": "fresh_human", "script": script_of(users),
                    "first_intent": first, "turns": d["turns"]})
    return out


def to_labelstudio():
    dialogues = parse(TXT, known_intents())
    DLG.write_text(json.dumps(dialogues, ensure_ascii=False, indent=1), encoding="utf-8")
    tasks = []
    for d in dialogues:
        prev_bot = ""
        for i, t in enumerate(d["turns"]):
            if t["speaker"] == "bot":
                prev_bot = t["text"]
                continue
            tasks.append({"data": {
                "text": t["text"], "context": f"Bot asked: {prev_bot}" if prev_bot else "(no bot turn before)",
                "info": f"{d['dialogue_id']} | turn {i} | {t['state']['intent']}",
                "dialogue_id": d["dialogue_id"], "turn": i, "intent": t["state"]["intent"],
            }})                                    # no "predictions": labelled from scratch
            prev_bot = ""
    TASKS.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
    words = sum(len(list(words_with_offsets(t["data"]["text"]))) for t in tasks)
    print(f"{len(dialogues)} dialogues, {len(tasks)} user turns, {words} words -> {TASKS}")
    print("Script:", dict(Counter(d["script"] for d in dialogues)), "(style is worked out from your labels later)")
    print("Intents:", dict(Counter(d["first_intent"] for d in dialogues)))
    print("Switches:", sum(1 for d in dialogues for t in d["turns"] if "previous_intent" in t.get("state", {})))
    print("\nImport into a NEW Label Studio project (not the gold one). No pre-labels: label every word.")


def from_export():
    if not EXPORT.exists():
        sys.exit(f"{EXPORT} not found. Export the Fresh Test project as JSON to that path.")
    dlg = {d["dialogue_id"]: d for d in json.loads(DLG.read_text(encoding="utf-8"))}
    rows, missing = [], 0
    for task in json.loads(EXPORT.read_text(encoding="utf-8")):
        res = submitted_result(task)
        if res is None:
            missing += 1
            continue
        ex = to_example(task, res)
        d = dlg[ex["dialogue_id"]]
        ex.update({"intent": d["turns"][ex["turn"]]["state"]["intent"],
                   "script": d["script"], "source": "fresh_human",
                   "heuristic_tags": [guess_lang(w) for w in ex["tokens"]]})
        rows.append(ex)
    rows.sort(key=lambda r: (r["dialogue_id"], r["turn"]))
    by_dlg = defaultdict(list)
    for r in rows:
        by_dlg[r["dialogue_id"]] += r["lang_tags"]
    for r in rows:
        r["code_mix"] = style_from_labels(by_dlg[r["dialogue_id"]])
    unl = sum(t == "UNLABELLED" for r in rows for t in r["lang_tags"])

    ft = None
    if MODEL.exists():
        import fasttext
        model = fasttext.load_model(str(MODEL))
        ft_map = {"__label__si": "SI", "__label__en": "EN"}
        ft = lambda w: ft_map.get(model.predict(w.replace("\n", " "), k=1)[0][0], "OTHER_LANG")
        for r in rows:
            r["fasttext_tags"] = [ft(w) for w in r["tokens"]]
    with open(TOKENS, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def group(r):
        return f"{r['code_mix']} / {r['script']}"
    scores = {}
    for name, field in [("heuristic", "heuristic_tags"), ("fasttext", "fasttext_tags")]:
        if not rows or field not in rows[0]:
            continue
        acc = defaultdict(list)
        for r in rows:
            for g, p in zip(r["lang_tags"], r[field]):
                if g in ("SI", "EN"):
                    acc["ALL"].append(g == p)
                    acc[group(r)].append(g == p)
                    acc[f"gold={g}"].append(g == p)
                if name == "heuristic" and g != "UNLABELLED":
                    acc["all_tags"].append(g == p)
        scores[name] = {k: {"acc": round(sum(v) / len(v), 4), "n": len(v)} for k, v in sorted(acc.items())}
    RESULTS.mkdir(exist_ok=True)
    out = {"turns": len(rows), "tokens": sum(len(r["tokens"]) for r in rows),
           "lang_tag_counts": dict(Counter(t for r in rows for t in r["lang_tags"])),
           "entity_counts": dict(Counter(t[2:] for r in rows for t in r["ner_tags"] if t.startswith("B-"))),
           "scores_si_en": scores}
    (RESULTS / "fresh_baselines.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Turns: {len(rows)} (not submitted: {missing})   tokens: {out['tokens']}")
    print("Language tags:", out["lang_tag_counts"])
    styles = Counter((r["code_mix"], r["script"]) for r in rows if r["turn"] == min(x["turn"] for x in rows if x["dialogue_id"] == r["dialogue_id"]))
    print("Dialogue styles (from your labels):", {f"{a} / {b}": n for (a, b), n in styles.items()})
    print("Entities:", out["entity_counts"])
    if unl:
        print(f"WARNING: {unl} words have no language tag. Fix those tasks and export again.")
    print("\nAccuracy on SI/EN words (fresh set):")
    keys = sorted({k for s in scores.values() for k in s})
    print(f"  {'group':32s}" + "".join(f"{n:>12}" for n in scores))
    for k in keys:
        print(f"  {k:32s}" + "".join(f"{scores[n].get(k, {}).get('acc', '-'):>12}" for n in scores))
    if ft is None:
        print(f"(fastText skipped: {MODEL} not found)")
    print(f"\nSaved {TOKENS} and results/fresh_baselines.json. Upload fresh_tokens.jsonl to Colab.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to-labelstudio", action="store_true")
    ap.add_argument("--from-export", action="store_true")
    a = ap.parse_args()
    if a.to_labelstudio:
        to_labelstudio()
    elif a.from_export:
        from_export()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
