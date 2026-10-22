"""DEMO-ONLY provisional 3.1 wording for the official procedures, and the automatic checks that gate it.

Provisional content is AI-assisted wording derived from the existing prepared demo drafts and the official-source passages.
It has NO human, expert or government review. It is never published to the strict registry, never used for standard or
LinTS-selected journeys, and is shown only in a clearly labelled research preview when the server enables the demo mode.
The checks below are authoritative gates: structural coverage, numeric and name grounding, and a payment-contradiction check.
"""
import json
import re
from pathlib import Path
from app.guidance.content_v31 import GuidanceContent31, validate_content31
from app.guidance.sources import ProcedureSource

PROVISIONAL_DIR = Path(__file__).resolve().parents[3] / "research" / "data" / "guidance" / "provisional-v31"
LABEL = ("Provisional demo wording. AI-assisted, checked only by automatic source-grounding checks. "
         "No human, expert or government review. Not independently validated guidance.")
NUMBER = re.compile(r"\d[\d,\.]*\d|\d")
CAPITALISED = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b")


def corpus(source: ProcedureSource) -> str:
    g = source.graph
    parts = [c.text for c in g.content] + [c.text for c in g.conditions] + [s.name + " " + s.agency for s in g.stages]
    for f in g.facts:
        parts.append(" ".join(str(v) for v in f.model_dump().values() if isinstance(v, (str, int, float))))
    return "\n".join(parts)


def texts(content: GuidanceContent31):
    for a in content.actions:
        for name in ("heading", "concise", "detailed", "recap", "actor", "destination"):
            field = getattr(a, name)
            if field is not None:
                yield f"{a.id}.{name}", field.text
        if a.supplement:
            yield f"{a.id}.supplement", a.supplement.text.text
    for att in content.attachments:
        if att.qualification:
            yield f"{att.id}.qualification", att.qualification.text
    for p in content.phases:
        yield f"{p.id}.label", p.label.text


def grounding_issues(source: ProcedureSource, content: GuidanceContent31) -> list[str]:
    """Every number and every mid-sentence capitalised name in provisional wording must occur in the source corpus."""
    base = corpus(source)
    plain = base.replace(",", "")
    issues = []
    for where, text in texts(content):
        for token in NUMBER.findall(text):
            if token.replace(",", "") not in plain:
                issues.append(f"{where}: number {token!r} is not in the source")
        for word in CAPITALISED.findall(text):
            if word not in base:
                issues.append(f"{where}: name {word!r} is not in the source")
    return issues


def contradiction_issues(source: ProcedureSource, content: GuidanceContent31) -> list[str]:
    """A passage that says payment is outside a step or excludes something must not be turned into a payment instruction or a free claim."""
    issues = []
    passages = {c.content_id: c.text.lower() for c in source.graph.content}
    for a in content.actions:
        ga = next(x for x in source.graph.actions if x.action_id == a.id)
        source_text = " ".join(passages[c] for c in ga.required_content_ids)
        wording = " ".join(t for k, t in texts(content) if k.startswith(a.id + ".") and not k.endswith(".heading")).lower()
        if "payment is outside" in source_text and re.search(r"\bpay(?!ment is)\b", wording) and "outside" not in wording:
            issues.append(f"{a.id}: wording asks for payment although the source says payment is outside this step")
        # "does not establish that it is free" is a caution, not a claim, so negated mentions are removed first.
        affirmed = re.sub(r"\b(not|n't|nor)\b[^.]{0,40}\b(free of charge|no fee|is free|free)\b", "", wording)
        if re.search(r"\b(free of charge|no fee|is free)\b", affirmed) and "free" not in source_text:
            issues.append(f"{a.id}: wording claims no fee but the source does not")
        if "guarantee" in wording and "does not guarantee" not in wording and "not guarantee" not in source_text:
            issues.append(f"{a.id}: wording makes a guarantee the source does not")
    return issues


def check(source: ProcedureSource, content: GuidanceContent31) -> dict:
    validate_content31(source, content)   # claim coverage, Detailed keeps Concise, supplement separate, fact ownership
    issues = grounding_issues(source, content) + contradiction_issues(source, content)
    return {"procedure_id": content.procedure_id, "structural": "passed", "grounding_and_contradiction_issues": issues, "passed": not issues}


def load(sources: dict) -> dict:
    """Load and check every provisional file for the given {procedure_id: ProcedureSource}. A failing file is refused, never shown."""
    result = {}
    if not PROVISIONAL_DIR.is_dir():
        return result
    for file in sorted(PROVISIONAL_DIR.glob("*.json")):
        packet = json.loads(file.read_text(encoding="utf-8"))
        pid = packet["procedure_id"]
        if pid not in sources or not sources[pid].graph.synthetic is False:
            raise ValueError("provisional demo content is for official-source procedures only: " + pid)
        content = GuidanceContent31.model_validate(packet["content"])
        report = check(sources[pid], content)
        if not report["passed"]:
            raise ValueError("provisional content failed automatic checks: " + "; ".join(report["grounding_and_contradiction_issues"]))
        result[pid] = content
    return result
