"""perturb.py (H4): perturbations are deterministic, never touch NE / OTHER tokens (romanisation only through the
district-spelling table) or gold free-text spans, and keep words aligned with the entity tags.
Run from research/:  python -m pytest -q tests
"""
import os

import pytest

RESEARCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def data():
    cwd = os.getcwd()
    os.chdir(RESEARCH)
    try:
        import perturb as pt
        lex = pt.load_lexicon()
        rows = pt.load_test_set("fresh")[0] + pt.load_test_set("synthetic")[0]
    finally:
        os.chdir(cwd)
    return pt, lex, rows


def test_perturbations_are_deterministic(data):
    pt, lex, rows = data
    for kind in pt.PERTURBATIONS:
        assert pt.perturb_set(rows, kind, lex, seed=7, draw=0) == pt.perturb_set(rows, kind, lex, seed=7, draw=0)
    a = pt.perturb_set(rows, "typos", lex, seed=7, draw=0)
    b = pt.perturb_set(rows, "typos", lex, seed=7, draw=1)
    assert [r["text"] for r in a] != [r["text"] for r in b]                 # another draw is another sample


def test_never_touch_ne_or_other_tokens(data):
    pt, lex, rows = data
    for kind in pt.PERTURBATIONS:
        for seed in (1, 2):
            for old, new in zip(rows, pt.perturb_set(rows, kind, lex, seed=seed, draw=0)):
                for i in new["changed"]:
                    tag = old["lang_tags"][i]
                    assert tag != "OTHER", (kind, old["tokens"][i])
                    if tag == "NE":                                           # only district spellings, only here
                        assert kind == "romanisation", (kind, old["tokens"][i])
                        assert old["tokens"][i].lower() in lex["district_spellings"]
                        assert new["tokens"][i].lower() in lex["district_spellings"][old["tokens"][i].lower()]


def test_free_text_spans_are_protected_and_words_stay_aligned(data):
    pt, lex, rows = data
    from c1_dst import FREE_TEXT, words_with_offsets
    for kind in pt.PERTURBATIONS:
        for old, new in zip(rows, pt.perturb_set(rows, kind, lex, seed=3, draw=0)):
            assert len(new["tokens"]) == len(old["tokens"]) and new["ner_tags"] == old["ner_tags"]
            assert [w for w, _, _ in words_with_offsets(new["text"])] == new["tokens"]
            for i in new["changed"]:
                t = old["ner_tags"][i]
                assert t == "O" or t[2:] not in FREE_TEXT, (kind, old["tokens"][i], t)
            unchanged = set(range(len(old["tokens"]))) - set(new["changed"])
            assert all(new["tokens"][i] == old["tokens"][i] for i in unchanged)


def test_typo_rate_is_about_15_percent_of_eligible_words(data):
    pt, lex, rows = data
    from c1_dst import FREE_TEXT
    eligible = changed = 0
    for old, new in zip(rows, pt.perturb_set(rows, "typos", lex, seed=11, draw=0)):
        for i, (w, t) in enumerate(zip(old["tokens"], old["lang_tags"])):
            nt = old["ner_tags"][i]
            if t in ("SI", "EN", "MIXED") and len(w) >= 3 and not (nt != "O" and nt[2:] in FREE_TEXT):
                eligible += 1
        changed += len(new["changed"])
    assert 0.10 <= changed / eligible <= 0.20, changed / eligible


def test_h4_row_verdict():
    import perturb as pt
    assert pt.h4_row_verdict(50, 0.01, 0.05, True) == "hybrid degrades less"
    assert pt.h4_row_verdict(50, -0.05, -0.01, True) == "hybrid degrades more"
    assert pt.h4_row_verdict(50, -0.05, 0.0, True).startswith("inconclusive")
    assert pt.h4_row_verdict(20, 0.01, 0.05, True).startswith("inconclusive")
    assert pt.h4_row_verdict(199, 0.01, 0.05, False).startswith("INVALID")
