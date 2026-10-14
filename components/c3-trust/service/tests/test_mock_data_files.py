"""The mock data must be valid: contract-exact where it claims to be, and consistent with itself."""
import json

from jsonschema import Draft202012Validator, FormatChecker

from helaguide_common.config import get_settings
from helaguide_common.contracts import Fact, Feedback
from app.core.lexicon import needs_translation
from app.core.util import text_hash
from app.models.internal import FreeTextFeedback
from tests.helpers import make_settings

D = make_settings().data_dir
SCHEMAS = get_settings().contracts_dir / "schema" / "v1"


def schema(name):
    return Draft202012Validator(json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8")),
                                format_checker=FormatChecker())


def rd(name):
    return json.loads((D / name).read_text(encoding="utf-8"))


def test_structured_messages_are_exactly_the_contract_feedback_message():
    v = schema("feedback")
    for m in rd("feedback_structured.json")["messages"]:
        assert not list(v.iter_errors(m)), m["feedback_id"]
        Feedback(**m)


def test_mock_facts_are_exactly_the_contract_fact_message():
    v = schema("fact")
    facts = rd("c2_facts.json")["facts"] + rd("c2_facts_updates.json")["facts"]
    for f in facts:
        assert not list(v.iter_errors(f)), f["fact_id"]
        Fact(**f)
    ids = [f["fact_id"] for f in rd("c2_facts.json")["facts"]]
    assert len(set(ids)) == len(ids)


def test_freetext_messages_follow_the_private_model():
    msgs = rd("feedback_freetext.json")["messages"]
    assert len(msgs) >= 30
    for m in msgs:
        FreeTextFeedback(**m)


def test_labels_point_at_real_messages_and_facts():
    labels = rd("expected_labels.json")["labels"]
    ids = {m["message_id"] for m in rd("feedback_freetext.json")["messages"]} | \
          {m["feedback_id"] for m in rd("feedback_structured.json")["messages"]}
    fact_ids = {f["fact_id"] for f in rd("c2_facts.json")["facts"]}
    assert {l["message_id"] for l in labels} == ids and len(labels) == len(ids)
    for l in labels:
        if l["expected_state"] == "grounded":
            assert l["expected_fact_id"] in fact_ids, l
    assert {"english", "singlish", "sinhala"} <= {l["style"] for l in labels}
    assert {"freetext", "structured"} == {l["path"] for l in labels}
    assert {"tune", "test"} == {l["split"] for l in labels}
    assert {"grounded", "clarification_needed", "no_matching_fact"} == {l["expected_state"] for l in labels}


def test_every_message_has_a_known_reporter():
    reporters = {r["reporter_id"] for r in rd("reporters.json")["reporters"]}
    for m in rd("feedback_freetext.json")["messages"] + rd("feedback_structured.json")["messages"]:
        assert m["session_id"] in reporters


def test_every_message_that_needs_translation_is_in_the_cache():
    cache = rd("normalised_cache.json")
    texts = [(m.get("language"), m["raw_text"]) for m in rd("feedback_freetext.json")["messages"]] + \
            [(None, m["text"]) for m in rd("feedback_structured.json")["messages"]]
    missing = [t for lang, t in texts if needs_translation(lang, t) and text_hash(t) not in cache]
    assert missing == []


def test_service_aliases_cover_every_service_in_the_graph():
    services = {s["service_id"] for s in rd("service_aliases.json")["services"]}
    assert {f["service_id"] for f in rd("c2_facts.json")["facts"]} <= services
