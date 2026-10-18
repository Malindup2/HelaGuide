"""The demo and tools run end to end (SQLite + stand-in embedder: no Docker, no download, no key)."""
import pytest

import json
import shutil

from app.cli import demo, export_ddl, reset, translate_cache
from app.core.config import C3Settings
from app.core.normaliser import QuotaExhausted, RateLimited, TranslationError
from app.core.util import numbers_in


def test_demo_runs_every_part(capsys):
    demo.main(["--sqlite", "--embedding", "hash"])
    out = capsys.readouterr().out
    for part in ("PART 1", "PART 2", "PART 3", "PART 4", "PART 5", "PART 6", "PART 7"):
        assert part in out
    assert "8/8 checks passed" in out
    assert "valid against contracts/schema/v1/trust.schema.json" in out


@pytest.mark.parametrize("path", ["freetext", "structured"])
def test_each_path_can_be_shown_on_its_own(capsys, path):
    demo.main(["--sqlite", "--embedding", "hash", "--part", "story", "--path", path])
    out = capsys.readouterr().out
    assert f"path={path}" in out
    assert "path=" + ("structured" if path == "freetext" else "freetext") not in out


def test_reset_gives_a_clean_start(capsys):
    reset.main(["--sqlite", "--embedding", "hash"])
    assert "15 reporters loaded" in capsys.readouterr().out


def test_ddl_export_prints_create_table(capsys):
    export_ddl.main()
    out = capsys.readouterr().out
    assert "CREATE TABLE IF NOT EXISTS fact_confidence" in out and "CREATE SCHEMA IF NOT EXISTS c3" in out


# ------------------------------------------------------------------ translate_cache
class FakeGemini:
    """Stands in for Gemini. `script` lists, call by call, what happens: 'ok' or an exception."""

    def __init__(self, script=None):
        self.script, self.calls = list(script or []), []

    def translate(self, raw):
        self.calls.append(raw)
        step = self.script.pop(0) if self.script else "ok"
        if step != "ok":
            raise step
        return "They said " + " ".join(f"{n:g}" for n in numbers_in(raw)) + " (gemini)"


@pytest.fixture
def tc(tmp_path, monkeypatch):
    """A private copy of the mock data, a fake Gemini, and no real waiting."""
    src = C3Settings(_env_file=None).data_dir
    data = tmp_path / "mock"
    shutil.copytree(src, data)
    monkeypatch.setenv("C3_DATA_DIR", str(data))
    monkeypatch.setenv("C3_GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(translate_cache, "SLEEP", lambda s: None)
    holder = {"fake": FakeGemini()}
    monkeypatch.setattr("app.core.normaliser.Normaliser.client", lambda self: holder["fake"])
    holder["cache"] = data / "normalised_cache.json"
    return holder


def sources(path):
    return [e["source"] for e in json.loads(path.read_text(encoding="utf-8")).values()]


def test_overwrite_replaces_the_authored_translations_and_keeps_the_old_wording(tc, capsys):
    translate_cache.main(["--overwrite", "--pause", "0"])
    cache = json.loads(tc["cache"].read_text(encoding="utf-8"))
    assert set(sources(tc["cache"])) == {"gemini"} and len(cache) == 17
    first = next(iter(cache.values()))
    assert first["reviewed"] is False and first["previous_text_en"] and first["text_en"].endswith("(gemini)")
    assert "REVIEW them" in capsys.readouterr().out


def test_running_again_only_does_what_is_left(tc):
    translate_cache.main(["--overwrite", "--limit", "5", "--pause", "0"])
    assert len(tc["fake"].calls) == 5 and sources(tc["cache"]).count("gemini") == 5
    translate_cache.main(["--overwrite", "--pause", "0"])
    assert len(tc["fake"].calls) == 17            # the other 12, not all 17 again
    assert set(sources(tc["cache"])) == {"gemini"}
    translate_cache.main(["--overwrite", "--pause", "0"])
    assert len(tc["fake"].calls) == 17            # nothing left: no calls


def test_a_per_minute_limit_stops_the_run_but_keeps_what_was_done(tc, capsys):
    tc["fake"].script = ["ok", "ok", RateLimited("too many", retry_after=33.0)]
    translate_cache.main(["--overwrite", "--pause", "0"])
    out = capsys.readouterr().out
    assert len(tc["fake"].calls) == 3             # it stopped at the limit instead of hammering the other 14
    assert sources(tc["cache"]).count("gemini") == 2 and sources(tc["cache"]).count("authored") == 15
    assert "about 34 seconds" in out and "SAME command again" in out


def test_the_daily_quota_stops_the_run_with_a_clear_message(tc, capsys):
    tc["fake"].script = [QuotaExhausted("the DAILY free quota is used up")]
    translate_cache.main(["--overwrite", "--pause", "0"])
    assert "STOPPED: the DAILY free quota" in capsys.readouterr().out
    assert set(sources(tc["cache"])) == {"authored"}


def test_a_temporary_overload_skips_that_message_and_continues(tc, capsys):
    tc["fake"].script = [TranslationError("gave up after 3 tries (HTTP 503)")]
    translate_cache.main(["--overwrite", "--pause", "0"])
    out = capsys.readouterr().out
    assert sources(tc["cache"]).count("gemini") == 16 and sources(tc["cache"]).count("authored") == 1
    assert "1 failed" in out and "HTTP 503" in out


def test_compare_saves_nothing_and_dry_run_sends_nothing(tc, capsys):
    translate_cache.main(["--compare", "--pause", "0"])
    assert set(sources(tc["cache"])) == {"authored"} and len(tc["fake"].calls) == 17
    tc["fake"].calls.clear()
    translate_cache.main(["--dry-run"])
    assert tc["fake"].calls == []


# ------------------------------------------------------------------ tune_grounding
def test_the_tuner_picks_from_the_middle_of_the_best_plateau_and_never_uses_test_accuracy():
    from app.cli.tune_grounding import choose
    # (tune acc, test acc, tau_f, delta_f, miss): three settings tie on tune accuracy 0.9
    combos = [
        (0.9, 0.2, 0.40, 0.02, 0.20), (0.9, 0.2, 0.50, 0.02, 0.30), (0.9, 0.2, 0.60, 0.02, 0.40),
        (0.9, 0.2, 0.40, 0.06, 0.20), (0.9, 0.2, 0.50, 0.06, 0.30), (0.9, 0.2, 0.60, 0.06, 0.40),
        (0.8, 1.0, 0.45, 0.10, 0.25),                      # better TEST accuracy, worse tune accuracy: must not win
    ]
    pick, n_ties = choose(combos)
    assert n_ties == 6
    assert pick == (0.9, 0.2, 0.50, 0.06, 0.30)            # most cautious margin, middle of the rest


def test_the_tuner_runs_end_to_end(capsys):
    from app.cli import tune_grounding
    tune_grounding.main(["--embedding", "hash", "--top", "3"])
    out = capsys.readouterr().out
    assert "Paste these into service/.env" in out and "C3_TAU_MISS_COS=" in out
    assert "the test messages were NOT used to choose" in out


# --------------------------------------------------------------------------- show
def test_show_gives_a_before_and_an_after_view(tmp_path, capsys):
    from app.cli import show
    url = f"sqlite:///{(tmp_path / 'c3.db').as_posix()}"
    show.main(["--db", url])
    assert "No C3 tables yet" in capsys.readouterr().out

    reset.main(["--db", url, "--embedding", "hash"])
    capsys.readouterr()
    show.main(["--db", url])
    before = capsys.readouterr().out
    assert "BEFORE STATE: all 58 fact versions are at their starting confidence (90%)" in before
    assert "reports" in before and " 0" in before                       # the table sizes show 0 reports

    demo.main(["--db", url, "--embedding", "hash", "--part", "story"])
    capsys.readouterr()
    show.main(["--db", url])
    after = capsys.readouterr().out
    assert "passport:fee:normal" in after and "49.7%" in after and "flagged" in after
    assert "BEFORE STATE" not in after

    show.main(["--db", url, "--fact", "svc:passport:fee:normal"])
    detail = capsys.readouterr().out
    for must in ("Audit trail", "ft-A1", "ft-A4", "0.60", "VERIFY_BEFORE_VISIT", "initial confidence (Algorithm 0a)"):
        assert must in detail, must
    show.main(["--db", url, "--fact", "svc:passport:fee:ghost"])
    assert "No fact called" in capsys.readouterr().out
