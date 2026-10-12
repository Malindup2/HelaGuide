

def test_a_note_that_looks_like_a_number_is_still_text(tmp_path):
    p = tmp_path / "seeds.yaml"
    p.write_text("seeds:\n  - url: https://a.gov.lk/x\n    agency: A\n    note: 3\n", encoding="utf-8")
    from app.core.acquisition.seeds import load_seeds

    assert load_seeds(p)[0].note == "3"
