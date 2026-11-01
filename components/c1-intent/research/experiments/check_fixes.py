import json
WORDS = {"bus", "purse", "transfer", "add", "saturday", "apply", "bakery", "number", "one"}
for line in open("data/gold_tokens.jsonl", encoding="utf-8"):
    e = json.loads(line)
    for w, tag in zip(e["tokens"], e["lang_tags"]):
        if w.lower() in WORDS and (w.lower() != "one" or e["dialogue_id"] == "d018"):
            print(e["dialogue_id"], "turn", e["turn"], w, tag, "" if tag == "EN" else "<-- fix")