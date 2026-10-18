

def test_a_note_that_looks_like_a_number_is_still_text(tmp_path):
    p = tmp_path / "seeds.yaml"
    p.write_text("seeds:\n  - url: https://a.gov.lk/x\n    agency: A\n    note: 3\n", encoding="utf-8")
    from app.core.acquisition.seeds import load_seeds

    assert load_seeds(p)[0].note == "3"


def test_only_keeps_the_seeds_of_one_site():
    from urllib.parse import urlsplit

    urls = ["https://www.ird.gov.lk/en/a", "https://www.drp.gov.lk/en/b", "https://ird.gov.lk/en/c"]
    kept = [u for u in urls if "ird.gov.lk" in urlsplit(u).netloc.lower()]
    assert kept == ["https://www.ird.gov.lk/en/a", "https://ird.gov.lk/en/c"]
