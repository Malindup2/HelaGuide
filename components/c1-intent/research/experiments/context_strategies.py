"""
Context strategies for the intent model (sub-objective 3): how the model input is built at each user turn.

Shared by c1_context_experiment.ipynb (Colab) and the local scripts, so training, evaluation and the CPU
benchmark build exactly the same inputs. Pure Python; the only import is c1_dst.py (keyword lists).

Strategies
  current_only      the current message
  window_2/3        the last 2/3 user messages
  keyword_summary   EN/NE words of earlier messages (gold tags; loses Sinhala cues, Observation 8)
  structured_state  previous intent + slots so far (gold entity tags) + the current message
  summary           extractive summary of earlier messages: the sentences with a service or slot cue in
                    Sinhala, Singlish or English (c1_dst keyword lists), at most SUMMARY_MAX_TOKENS tokens
  full_history      every user message so far

Also: dialogue-level synthetic train/test split (written once to data/synthetic/context_v2_split.json) and
session stitching (2-4 dialogues joined into one session, within one split only).

    python experiments/context_strategies.py --write-split     # from research/; never overwrites
"""
import argparse
import collections
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c1_dst import (APPLICANT, CHANGE_FIELD, ISSUES, NORMAL, PURPOSES, SERVICE_KEYWORDS, SERVICES,  # noqa: E402
                    URGENT, VARIANT_KEYWORDS, find_date, find_district, find_town, has_any, low, words_with_offsets)

SEP = " </s> "
STRATEGIES = ["current_only", "window_2", "window_3", "keyword_summary", "structured_state", "summary",
              "full_history"]
KEYWORDS_MAX = 12          # keyword_summary keeps at most this many earlier keywords
SUMMARY_MAX_TOKENS = 48    # cap for the summary (XLM-R tokens in the notebook)
SUMMARY_PREFIX = "summary: "
SESSION_SIZES = (2, 3, 4)  # dialogues joined into one session
SPLIT_PATH = "data/synthetic/context_v2_split.json"


def whitespace_count(text):
    """Fallback token counter (words). The notebook passes the XLM-R tokenizer instead."""
    return len(text.split())


# ---------------------------------------------------------------- sessions and split
def dialogues(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["dialogue_id"]].append(r)
    return {d: sorted(v, key=lambda r: r["turn"]) for d, v in by.items()}


def stitched_sessions(rows, seed, sizes=SESSION_SIZES):
    """Join 2-4 whole dialogues (shuffled with `seed`) into sessions. Only the rows given are used, so
    sessions built from one split never contain a dialogue of another."""
    by = dialogues(rows)
    ids = sorted(by)
    rng = random.Random(seed)
    rng.shuffle(ids)
    out, i = [], 0
    while i < len(ids):
        k = rng.choice(sizes)
        out.append([r for d in ids[i:i + k] for r in by[d]])
        i += k
    return out


def synthetic_split(rows, test_share=0.2, seed=0):
    """Dialogue-level split, stratified by each dialogue's first-turn intent. Returns (train_ids, test_ids)."""
    by_intent = collections.defaultdict(list)
    for d, turns in dialogues(rows).items():
        by_intent[turns[0]["intent"]].append(d)
    rng = random.Random(seed)
    test = []
    for intent in sorted(by_intent):
        ids = sorted(by_intent[intent])
        rng.shuffle(ids)
        test += ids[:round(len(ids) * test_share)]
    test = sorted(test)
    train = sorted(set(d for ids in by_intent.values() for d in ids) - set(test))
    return train, test


def write_split(silver_path="data/synthetic/silver_tokens.jsonl", out=SPLIT_PATH, test_share=0.2, seed=0):
    if os.path.exists(out):
        sys.exit(f"{out} already exists; not overwriting it.")
    with open(silver_path, encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    train, test = synthetic_split(rows, test_share, seed)
    n_turns = collections.Counter("test" if r["dialogue_id"] in set(test) else "train" for r in rows)
    first = {d: t[0]["intent"] for d, t in dialogues(rows).items()}
    split = {
        "description": "Synthetic dialogues held out from intent training in the context v2 experiment "
                       "(c1_context_experiment.ipynb) and used as the synthetic test set there and in perturb.py. "
                       "Split by dialogue, stratified by first-turn intent.",
        "source": silver_path, "seed": seed, "test_share": test_share,
        "train_dialogues": len(train), "test_dialogues": len(test),
        "train_turns": n_turns["train"], "test_turns": n_turns["test"],
        "test_by_first_intent": dict(sorted(collections.Counter(first[d] for d in test).items())),
        "test": test, "train": train,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(split, fh, ensure_ascii=False, indent=2)
    print(f"wrote {out}: {len(train)} train / {len(test)} test dialogues, "
          f"{n_turns['train']} / {n_turns['test']} turns")


# ---------------------------------------------------------------- summary (extractive, both languages)
def _forms():
    forms = []
    for f in SERVICE_KEYWORDS.values():
        forms += f
    for _, f in SERVICES:
        forms += f
    for variants in VARIANT_KEYWORDS.values():
        for _, f in variants:
            forms += f
    for canon, f in APPLICANT:
        if canon != "self":            # mata / my / me occur in almost every message
            forms += f
    for table in (CHANGE_FIELD, PURPOSES, ISSUES):
        for _, f in table:
            forms += f
    return sorted(set(forms + URGENT + NORMAL))


CUE_FORMS = _forms()
_NUMBER = re.compile(r"\d")


def has_cue(sentence):
    """True if the sentence names a service, a variant (aluth / nathi una / renew ...), a district or town,
    a date, a number, an applicant, a field to change, a purpose or an urgency, in any script."""
    words = list(words_with_offsets(sentence))
    if not words:
        return False
    return bool(has_any(words, CUE_FORMS) or find_district(words, skip_negated=False) or find_town(words)
                or find_date(words) or _NUMBER.search(sentence))


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?।])\s+|\n+", text or "") if s.strip()]


def cap_tokens(text, count_tokens=whitespace_count, max_tokens=SUMMARY_MAX_TOKENS):
    """Drop words from the start until `text` fits (the end of a summary is the most recent part)."""
    words = text.split()
    while words and count_tokens(" ".join(words)) > max_tokens:
        words = words[1:]
    return " ".join(words)


def extractive_summary(prev_texts, count_tokens=whitespace_count, max_tokens=SUMMARY_MAX_TOKENS,
                       prefix=SUMMARY_PREFIX):
    """The earlier sentences that carry a cue, most recent first until the cap, returned oldest first as
    "summary: s1 | s2". The whole string, prefix included, is at most `max_tokens` by `count_tokens`.
    Returns "" when no earlier sentence has a cue."""
    cands = [s for t in prev_texts for s in split_sentences(t) if has_cue(s)]
    picked, seen = [], set()
    render = lambda ss: prefix + " | ".join(ss)
    for s in reversed(cands):
        key = low(s)
        if key in seen:
            continue
        if count_tokens(render([s] + picked)) <= max_tokens:
            picked.insert(0, s)
            seen.add(key)
        elif not picked:           # the newest cue sentence alone is too long: keep its end
            budget = max_tokens - count_tokens(prefix)
            cut = cap_tokens(s, count_tokens, budget) if budget > 0 else ""
            if cut and count_tokens(render([cut])) <= max_tokens:
                picked = [cut]
            break
        else:
            break
    return render(picked) if picked else ""


# ---------------------------------------------------------------- oracle-tag helpers (keyword / state)
def words_of_type(rows, keep):
    return [w for r in rows for w, t in zip(r["tokens"], r["lang_tags"]) if t in keep]


def slots_so_far(rows):
    """Slot values mentioned in earlier turns (latest value wins), from the entity tags."""
    slots = {}
    for r in rows:
        cur_type, words = None, []
        for w, t in list(zip(r["tokens"], r["ner_tags"])) + [("", "O")]:
            if t.startswith("I-") and t[2:] == cur_type:
                words.append(w)
                continue
            if cur_type:
                slots[cur_type] = " ".join(words)
            cur_type, words = (t[2:], [w]) if t != "O" else (None, [])
    return slots


# ---------------------------------------------------------------- the model input
def build_input(strategy, prev, cur, prev_intent=None, count_tokens=whitespace_count):
    """prev: earlier user turns in this session (rows, oldest first); cur: the current row; prev_intent: the
    intent of the previous turn (gold when training, the model's own prediction when testing).
    count_tokens: the token counter for the summary cap (the XLM-R tokenizer in the notebook)."""
    texts = [r["text"] for r in prev] + [cur["text"]]
    if strategy == "current_only":
        return cur["text"]
    if strategy.startswith("window_"):
        return SEP.join(texts[-int(strategy.split("_")[1]):])
    if strategy == "full_history":
        return SEP.join(texts)
    if strategy == "keyword_summary":
        seen, kw = set(), []
        for w in reversed(words_of_type(prev, ("EN", "NE"))):       # most recent first, no repeats
            if w.lower() not in seen:
                seen.add(w.lower())
                kw.append(w)
        kw = list(reversed(kw[:KEYWORDS_MAX]))
        return ("keywords: " + " ".join(kw) + SEP + cur["text"]) if kw else cur["text"]
    if strategy == "structured_state":
        if not prev:
            return cur["text"]
        state = f"intent: {prev_intent or 'none'}" + "".join(
            f" | {k}: {v}" for k, v in sorted(slots_so_far(prev).items()))
        return state + SEP + cur["text"]
    if strategy == "summary":
        s = extractive_summary([r["text"] for r in prev], count_tokens)
        return s + SEP + cur["text"] if s else cur["text"]
    raise ValueError(strategy)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-split", action="store_true", help=f"write {SPLIT_PATH} (run from research/)")
    a = ap.parse_args()
    if a.write_split:
        write_split()
    else:
        ap.print_help()
