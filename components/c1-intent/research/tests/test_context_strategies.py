"""Summary strategy (token cap, cues in both languages) and the synthetic split. Run from research/:
    python -m pytest -q tests
"""
import json
import os

import pytest

from context_strategies import (SEP, SUMMARY_MAX_TOKENS, build_input, extractive_summary, has_cue,
                                stitched_sessions, synthetic_split)

RESEARCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENIZER_DIR = os.path.join(RESEARCH, "models", "c1", "run_v2_seed1", "intent")

LONG_HISTORY = [
    "mata NIC eka nathi una, ikmanata aluth ekak ganna one",
    "Matara district eke",
    "passport ekak renew karanna one next month travel karanna",
    "මගේ හැඳුනුම්පත නැති වුණා, ඉක්මනින් අලුත් එකක් ගන්න ඕනේ",
    "duwage birth certificate copy ekak school admission walata",
    "I want to change the address on my NIC to No 12 Temple Road",
] * 3


def chars(text):        # a strict counter: every character is a token
    return len(text)


def row(text):
    return {"text": text, "tokens": text.split(), "lang_tags": ["SI"] * len(text.split()),
            "ner_tags": ["O"] * len(text.split())}


@pytest.mark.parametrize("count", [lambda t: len(t.split()), chars])
def test_summary_never_exceeds_cap(count):
    for n in range(1, len(LONG_HISTORY) + 1):
        s = extractive_summary(LONG_HISTORY[:n], count)
        assert count(s) <= SUMMARY_MAX_TOKENS


def test_summary_cap_with_xlmr_tokenizer():
    if not os.path.isdir(TOKENIZER_DIR):
        pytest.skip("run_v2_seed1 tokenizer not on this machine")
    transformers = pytest.importorskip("transformers")
    tok = transformers.AutoTokenizer.from_pretrained(TOKENIZER_DIR)
    count = lambda t: len(tok(t, add_special_tokens=False)["input_ids"])
    for n in range(1, len(LONG_HISTORY) + 1):
        s = extractive_summary(LONG_HISTORY[:n], count)
        assert s and count(s) <= SUMMARY_MAX_TOKENS


def test_most_recent_cue_sentence_kept_when_over_cap():
    s = extractive_summary(LONG_HISTORY, lambda t: len(t.split()))
    assert s.endswith(LONG_HISTORY[-1])


def test_single_long_sentence_is_cut_from_the_start():
    long = " ".join(["passport"] * 100)
    s = extractive_summary([long], lambda t: len(t.split()), max_tokens=10)
    assert s.startswith("summary: ") and len(s.split()) == 10


def test_sinhala_singlish_and_english_cues_are_kept():
    assert has_cue("මගේ හැඳුනුම්පත නැති වුණා")       # Sinhala script: NIC lost
    assert has_cue("ID eka nathi una")                # Singlish: lost
    assert has_cue("aluth ekak ganna one")            # Singlish: new
    assert has_cue("I need to renew my passport")     # English
    assert has_cue("Matara")                          # district
    assert not has_cue("hari thanks")
    assert not has_cue("ස්තූතියි")


def test_sentences_without_cues_are_dropped():
    s = extractive_summary(["hari thanks. aluth NIC ekak one", "ok"])
    assert s == "summary: aluth NIC ekak one"
    assert extractive_summary(["hari thanks", "ok"]) == ""


def test_summary_input_format():
    prev = [row("mata passport ekak aluthen ganna one")]
    assert build_input("summary", prev, row("Galle")) == "summary: mata passport ekak aluthen ganna one" + SEP + "Galle"
    assert build_input("summary", [], row("Galle")) == "Galle"


def _rows():
    rows = []
    for d, intent, n in [("s1", "a", 2), ("s2", "a", 1), ("s3", "b", 3), ("s4", "b", 2), ("s5", "a", 2)]:
        rows += [{"dialogue_id": d, "turn": 2 * i, "intent": intent, "text": f"{d} {i}"} for i in range(n)]
    return rows


def test_split_is_by_dialogue_and_deterministic():
    train, test = synthetic_split(_rows(), test_share=0.4, seed=0)
    assert not set(train) & set(test) and set(train) | set(test) == {"s1", "s2", "s3", "s4", "s5"}
    assert (train, test) == synthetic_split(_rows(), test_share=0.4, seed=0)


def test_stitched_sessions_stay_inside_their_split():
    rows = _rows()
    train, test = synthetic_split(rows, test_share=0.4, seed=0)
    for ids in (train, test):
        sessions = stitched_sessions([r for r in rows if r["dialogue_id"] in ids], seed=0)
        assert {r["dialogue_id"] for s in sessions for r in s} == set(ids)


def test_committed_split_matches_the_silver_set():
    path = os.path.join(RESEARCH, "data", "synthetic", "context_v2_split.json")
    silver = os.path.join(RESEARCH, "data", "synthetic", "silver_tokens.jsonl")
    if not (os.path.exists(path) and os.path.exists(silver)):
        pytest.skip("split or silver set missing")
    split = json.load(open(path, encoding="utf-8"))
    rows = [json.loads(l) for l in open(silver, encoding="utf-8") if l.strip()]
    train, test = synthetic_split(rows, split["test_share"], split["seed"])
    assert (train, test) == (split["train"], split["test"])
    assert not set(split["train"]) & set(split["test"])
