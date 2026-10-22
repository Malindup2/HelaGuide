"""Candidate content contract 3.1: validators and independent D2 x D3 feasibility. Nothing here touches the runtime, policy or checkpoint."""
import json
from pathlib import Path
import pytest
from app.guidance.catalogue import Constraints
from app.guidance.content import GuidanceContent, validate_content
from app.guidance.content_v31 import GuidanceContent31, evaluate31, validate_content31
from app.guidance.feasibility import evaluate
from app.guidance.sources import ProcedureSource
from app.v2.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
CANDIDATES = C4 / "research" / "data" / "guidance" / "fictional-v31-candidates"
CURRENT = C4 / "research" / "data" / "guidance" / "fictional"
PIDS = ["synthetic-linear-v1", "synthetic-conditional-v1", "synthetic-parallel-v1", "synthetic-practice-v2"]


@pytest.fixture(scope="module")
def entries():
    return workspace_registry()


def source(entries, pid):
    entry = entries[pid]
    return ProcedureSource(graph=entry["graph"], relationships=entry.get("overlay"))


def candidate(pid):
    return GuidanceContent31.model_validate(json.loads((CANDIDATES / (pid + "-v31.json")).read_text(encoding="utf-8"))["content"])


def combo(candidates, explanation, disclosure):
    return [c for c in candidates if c.configuration.explanation == explanation and c.configuration.disclosure == disclosure]


@pytest.mark.parametrize("pid", PIDS)
def test_candidates_validate_and_stay_unreviewed(entries, pid):
    content = validate_content31(source(entries, pid), candidate(pid))
    assert content.review.status == "draft"
    assert all(a.concise.status == "draft" and a.supplement.text.status == "draft" for a in content.actions)


@pytest.mark.parametrize("pid", PIDS)
def test_concise_is_short_detailed_extends_it_and_supplement_is_separate(entries, pid):
    for a in candidate(pid).actions:
        assert len(a.concise.text) < len(a.detailed.text)
        assert len(a.concise.text) < len(a.source_wording.text) or len(a.source_wording.text) < 100
        assert set(a.concise.claim_ids) <= set(a.detailed.claim_ids)
        assert a.supplement.text.text not in a.concise.text + a.detailed.text
        assert a.concise.text != a.heading.text


def test_all_four_d2_d3_combinations_are_feasible_and_equal_when_content_is_reviewed(entries):
    src, content = source(entries, "synthetic-practice-v2"), candidate("synthetic-practice-v2")
    hypothetical = evaluate31(src, content, assume_reviewed=True)
    counts = {(e, d): sum(c.feasible for c in combo(hypothetical, e, d)) for e in ("concise", "detailed") for d in ("off", "on")}
    assert len(set(counts.values())) == 1 and counts[("concise", "off")] > 0
    assert all(len(c.disclosable_action_ids) == 5 for c in combo(hypothetical, "detailed", "on") if c.feasible)


def test_unreviewed_candidates_do_not_make_detailed_or_disclosure_feasible(entries):
    src, content = source(entries, "synthetic-practice-v2"), candidate("synthetic-practice-v2")
    real = evaluate31(src, content)
    assert not any(c.feasible for c in combo(real, "detailed", "off") + combo(real, "concise", "on"))
    assert any(c.feasible for c in combo(real, "concise", "off"))


def test_disclosure_needs_a_supplement_and_depth_does_not_matter(entries):
    src, content = source(entries, "synthetic-practice-v2"), candidate("synthetic-practice-v2")
    none = content.model_copy(update={"actions": tuple(a.model_copy(update={"supplement": None}) for a in content.actions)})
    result = evaluate31(src, none, assume_reviewed=True)
    assert not any(c.feasible for c in combo(result, "concise", "on") + combo(result, "detailed", "on"))
    assert any("disclosure:no_reviewed_supplement" in c.reasons for c in combo(result, "concise", "on"))
    one = content.model_copy(update={"actions": tuple(a if i == 0 else a.model_copy(update={"supplement": None}) for i, a in enumerate(content.actions))})
    partial = evaluate31(src, one, assume_reviewed=True)
    assert {c.disclosable_action_ids for c in combo(partial, "concise", "on") if c.feasible} == {(content.actions[0].id,)}
    assert {c.disclosable_action_ids for c in combo(partial, "detailed", "on") if c.feasible} == {(content.actions[0].id,)}


def test_hard_accessibility_restriction_forces_disclosure_off(entries):
    src, content = source(entries, "synthetic-practice-v2"), candidate("synthetic-practice-v2")
    result = evaluate31(src, content, Constraints(no_disclosure=True), assume_reviewed=True)
    assert not any(c.feasible for c in result if c.configuration.disclosure == "on")
    assert any(c.feasible for c in result if c.configuration.disclosure == "off")


def test_validators_reject_unsafe_wording(entries):
    src, content = source(entries, "synthetic-practice-v2"), candidate("synthetic-practice-v2")
    a0 = content.actions[0]

    def with_action(**changes):
        return content.model_copy(update={"actions": (a0.model_copy(update=changes),) + content.actions[1:]})

    with pytest.raises(ValueError, match="keep everything Concise"):
        validate_content31(src, with_action(detailed=a0.detailed.model_copy(update={"claim_ids": ()})))
    with pytest.raises(ValueError, match="every required instruction"):
        validate_content31(src, with_action(concise=a0.concise.model_copy(update={"status": "source_fallback", "claim_ids": ()})))
    required = next(c.id for c in content.claims if c.required and a0.id in c.action_ids)
    with pytest.raises(ValueError, match="required claim"):
        validate_content31(src, with_action(supplement=a0.supplement.model_copy(update={"text": a0.supplement.text.model_copy(update={"claim_ids": (required,)})})))
    with pytest.raises(ValueError, match="repeat the primary"):
        validate_content31(src, with_action(supplement=a0.supplement.model_copy(update={"text": a0.supplement.text.model_copy(update={"text": a0.concise.text[:30]})})))
    with pytest.raises(ValueError, match="source-fidelity review"):
        validate_content31(src, with_action(concise=a0.concise.model_copy(update={"status": "reviewed"})))
    with pytest.raises(ValueError, match="fuller"):
        validate_content31(src, with_action(detailed=a0.detailed.model_copy(update={"status": "source_fallback", "text": "Short."})))


def test_existing_3_0_content_and_feasibility_are_untouched(entries):
    for pid in PIDS:
        packet = json.loads((CURRENT / (pid + ".json")).read_text(encoding="utf-8"))
        content = GuidanceContent.model_validate(packet["content"])
        assert content.schema_version == "c4-guidance-content-3.0"
        validate_content(source(entries, pid), content)
    practice = GuidanceContent.model_validate(json.loads((CURRENT / "synthetic-practice-v2.json").read_text(encoding="utf-8"))["content"])
    assert sum(c.feasible for c in evaluate(source(entries, "synthetic-practice-v2"), practice)) == 96


def test_3_0_modules_and_the_policy_never_import_the_3_1_code():
    guidance = C4 / "service" / "app" / "guidance"
    for name in ("content.py", "feasibility.py", "composition.py", "registry.py", "policy.py", "features.py", "catalogue.py", "decision.py"):
        text = (guidance / name).read_text(encoding="utf-8")
        assert "content_v31" not in text and "v31_pipeline" not in text and "flavours" not in text, name
