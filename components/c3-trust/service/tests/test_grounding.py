"""Module A: grounding, tested directly (registry + grounding engine + translation cache, no pipeline)."""
import json
from datetime import datetime

import pytest

from app.core.catalog import ServiceCatalog
from app.core.db import make_engine, reset_db
from app.core.embeddings import HashEmbedder
from app.core.factsource import FileFactSource
from app.core.grounding import GroundingEngine, distinctive_words, document_is_listed, required_score
from app.core.normaliser import Normaliser
from app.core.registry import Registry
from app.core.repo import Repo
from tests.helpers import make_settings


def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class Env:
    def __init__(self, **over):
        self.s = make_settings(**over)
        engine = make_engine(self.s.database_url)
        reset_db(engine)
        self.repo = Repo(engine)
        emb = HashEmbedder()
        cat = ServiceCatalog(self.s.data_dir / "service_aliases.json")
        Registry(self.repo, emb, cat, self.s).sync(FileFactSource(self.s.data_dir / "c2_facts.json"))
        self.engine = GroundingEngine(self.repo, cat, emb, self.s)
        self.norm = Normaliser(self.s)
        self.messages = {m["message_id"]: m for m in json.loads(
            (self.s.data_dir / "feedback_freetext.json").read_text(encoding="utf-8"))["messages"]}
        self.labels = {l["message_id"]: l for l in json.loads(
            (self.s.data_dir / "expected_labels.json").read_text(encoding="utf-8"))["labels"]}

    def ground(self, mid, session_service=None):
        m = self.messages[mid]
        e = m["entities"]
        n = self.norm.normalise(m["raw_text"], m.get("language"), m.get("text_en"))
        return self.engine.ground_text(n.text_en, m["raw_text"], service_hint=e.get("service_id"),
                                       predicate_hint=e.get("predicate_hint"), session_service=session_service,
                                       when=dt(m["timestamp"]))


@pytest.fixture(scope="module")
def env():
    return Env()


def test_structured_path_validates_the_fact_and_picks_the_version(env):
    g = env.engine.ground_structured("svc:passport:fee:normal", dt("2026-10-20T10:00:00Z"))
    assert g.state == "grounded" and g.fact_id == "svc:passport:fee:normal"
    assert env.engine.ground_structured("svc:passport:fee:ghost", dt("2026-10-20T10:00:00Z")).reason == "unknown_fact_id"


def test_a_hint_from_c1_decides_the_service(env):
    g = env.ground("ft-A1")
    assert g.state == "grounded" and g.service_source == "hint" and g.fact_id == "svc:passport:fee:normal"


def test_one_clear_service_name_decides_the_service(env):
    g = env.ground("ft-C2")                          # Singlish, names "death certificate", no hint
    assert g.service_source == "alias" and g.fact_id == "svc:death_certificate:fee:certified_copy"


def test_singlish_and_sinhala_are_grounded_after_translation(env):
    assert env.ground("ft-A3").fact_id == "svc:passport:fee:normal"                    # Singlish
    assert env.ground("ft-A5").fact_id == "svc:passport:fee:normal"                    # Sinhala script
    assert env.ground("ft-C3").fact_id == "svc:marriage_certificate:fee:certified_copy"


def test_near_miss_facts_are_told_apart(env):
    assert env.ground("ft-C4").fact_id == "svc:passport:fee:one_day"                   # not the normal fee
    assert env.ground("ft-C5").fact_id == "svc:passport:fee:minor_normal"              # a child's passport
    assert env.ground("ft-C7").fact_id == "svc:nic:fee:one_day"
    assert env.ground("ft-C1").fact_id == "svc:birth_certificate:fee:certified_copy"   # same words, other service
    assert env.ground("ft-C6").fact_id == "svc:passport:processing_time:normal"        # time, not fee
    assert env.ground("ft-C8").fact_id == "svc:passport:document:birth_certificate"    # a document, not a fee


def test_an_unclear_message_asks_a_question(env):
    for mid in ("ft-D1", "ft-D2"):
        g = env.ground(mid)
        assert g.state == "clarification_needed" and g.reason == "service_unclear"


def test_the_session_remembers_the_service():
    e = Env(tau_f=0.30)
    g = e.ground("ft-C12", session_service="svc:death_certificate")
    assert g.state == "grounded" and g.service_source == "session"
    assert g.fact_id == "svc:death_certificate:fee:certified_copy"


def test_a_document_that_is_not_in_the_graph_is_reported_missing():
    e = Env(tau_miss_cos=0.25)
    for mid in ("ft-C9", "ft-C10"):
        g = e.ground(mid)
        assert g.state == "no_matching_fact" and g.reason == "nothing_in_graph_resembles_this", mid
    assert e.ground("ft-C8").state == "grounded"          # a document that IS listed is not "missing"


def test_the_missing_check_compares_the_document_not_the_service_name():
    """Every description starts with the service name, and so does a complaint about that service.
    Comparing whole texts therefore makes every document look similar; comparing the phrase alone does not."""
    e = Env(tau_miss_cos=0.35)
    when = dt("2026-10-25T10:00:00Z")
    msg = "birth certificate required document: they wanted a letter from the hospital"
    g = e.engine.ground_text(msg, msg, service_hint="svc:birth_certificate", predicate_hint="document", when=when)
    assert g.trace["fact_candidates"][0]["cos"] >= 0.35          # whole texts: looks like a match
    assert g.trace["phrase_similarity"] < 0.35                   # the document phrase alone: it is not
    assert g.state == "no_matching_fact"
    ok = "they did not want the National Identity Card of the informant"
    g2 = e.engine.ground_text(ok, ok, service_hint="svc:birth_certificate", predicate_hint="document", when=when)
    assert g2.state == "grounded" and g2.trace["phrase_similarity"] > 0.6


def test_no_translation_means_a_question_not_a_guess(env):
    g = env.engine.ground_text(None, "passport eke fee eka 12000", when=dt("2026-10-20T10:00:00Z"))
    assert g.state == "clarification_needed" and g.reason == "translation_unavailable"


def test_the_decision_can_be_explained(env):
    t = env.ground("ft-C4").trace
    top = t["fact_candidates"][0]
    assert top["fact_id"] == "svc:passport:fee:one_day" and top["value_quoted"] == 1.0   # "not 22,000" quoted back
    assert len(t["fact_candidates"]) == 3 and t["margin"] > 0


def test_accuracy_on_the_labelled_free_text_messages(env):
    sessions, ok, n = {}, 0, 0
    for mid, m in sorted(env.messages.items(), key=lambda kv: kv[1]["timestamp"]):
        g = env.ground(mid, sessions.get(m["session_id"]))
        if g.service_id:
            sessions[m["session_id"]] = g.service_id
        lab = env.labels[mid]
        good = g.state == lab["expected_state"] and (g.state != "grounded" or g.fact_id == lab["expected_fact_id"])
        ok += good
        n += 1
    assert n == 33 and ok / n >= 0.85       # stand-in embedder; the real model is tuned with `python -m app.cli.tune_grounding`


# ---------------------------------------------------------------- the two refinements
def test_distinctive_words_ignore_generic_words_and_match_word_forms():
    assert distinctive_words("Birth certificate") == {"birth"}
    assert distinctive_words("ICAO standard photograph from a registered studio") == {"icao", "stand", "photo", "regis", "studi"}
    assert distinctive_words("They also asked for a medical certificate") == {"medic"}
    assert distinctive_words("Two passport photographs") & distinctive_words("they wanted a photo") == {"photo"}   # photo ~ photographs


def test_a_document_needs_a_high_similarity_or_a_shared_distinctive_word():
    # the real-model numbers from the first tuning run (similarity of the document phrase, thresholds 0.45 / 0.60)
    assert document_is_listed(0.4802, shares_word=False, tau_miss=0.45, tau_sure=0.60) is False    # "medical certificate": NOT listed
    assert document_is_listed(0.47, shares_word=True, tau_miss=0.45, tau_sure=0.60) is True        # "ICAO photograph": listed
    assert document_is_listed(0.62, shares_word=False, tau_miss=0.45, tau_sure=0.60) is True       # very similar: trusted alone
    assert document_is_listed(0.30, shares_word=True, tau_miss=0.45, tau_sure=0.60) is False       # shares a word but nothing like it
    assert document_is_listed(0.20, shares_word=False, tau_miss=0.45, tau_sure=0.60) is False


def test_the_only_fact_of_its_kind_needs_a_lower_score():
    # ft-C12 from the real run: best score 0.5388, chosen tau_f 0.55, the service has exactly one fee fact
    assert required_score(0.55, 0.10, only_fact_of_its_kind=True) == pytest.approx(0.45) and 0.5388 >= 0.45
    assert required_score(0.55, 0.10, only_fact_of_its_kind=False) == pytest.approx(0.55) and 0.5388 < 0.55
    assert required_score(0.55, 0.0, only_fact_of_its_kind=True) == pytest.approx(0.55)


def test_a_message_that_shares_only_generic_words_is_not_a_listed_document():
    e = Env(tau_miss_cos=0.10)                      # a low floor: only the shared-word check can say "not listed"
    c10 = e.ground("ft-C10")                        # "a medical certificate" vs the NIC documents
    assert c10.state == "no_matching_fact" and c10.trace["shares_distinctive_word"] is False
    h1 = e.ground("ft-H1")                          # "ICAO photograph" IS a listed document
    assert h1.state == "grounded" and h1.fact_id == "svc:nic:document:icao_photograph"
    assert {"icao", "photo"} <= set(h1.trace["shared_words"])
    c8 = e.ground("ft-C8")
    assert c8.state == "grounded" and c8.trace["shared_words"] == ["birth"]


def test_the_single_fee_of_a_service_is_grounded_without_a_high_score():
    with_relief = Env().ground("ft-C12", session_service="svc:death_certificate")
    assert with_relief.state == "grounded" and with_relief.trace["only_fact_of_its_kind"] is True
    assert with_relief.trace["needed_score"] < Env().s.tau_f
    without = Env(tau_f_unique_relief=0.0).ground("ft-C12", session_service="svc:death_certificate")
    assert without.state == "clarification_needed"           # the same message is refused when the relief is switched off
    # with several fee facts (passport) there is real competition, so no relief
    assert Env().ground("ft-C4").trace["only_fact_of_its_kind"] is False
