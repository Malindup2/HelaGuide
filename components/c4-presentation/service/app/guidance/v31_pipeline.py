"""Isolated c4-guidance-content-3.1 pipeline: versions, registry, composition and demo installation.

Nothing here edits or reuses 3.0 stored artifacts, journeys, policy tables or checkpoints. A 3.1 runtime is selected only by
an explicit flavour (see flavours.py) and uses its own registry schema, cache keys, action-semantics label and feasibility fingerprint.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.guidance import features
from app.guidance.catalogue import CATALOGUE, Configuration, Constraints
from app.guidance.content_v31 import SCHEMA31, GuidanceContent31, evaluate31, validate_content31
from app.learning.lints import PolicyProfile
from app.guidance.sources import ProcedureSource, digest

ACTION_SCHEMA31 = "c4-scaffolds-v3.1"
FEATURE_SCHEMA31 = "c4-features-pp1-1.1-525"
REGISTRY_SCHEMA31 = "c4-prepared-registry-3.1"
RENDER_SCHEMA31 = "c4-render-plan-3.1"
FIXTURES31 = Path(__file__).resolve().parents[3] / "research" / "data" / "guidance" / "fictional-v31"
FEATURE_FINGERPRINT31 = digest({**features.SPEC, "schema": FEATURE_SCHEMA31, "action": ACTION_SCHEMA31})


def config_key31(config: Configuration) -> str:
    return ACTION_SCHEMA31 + ":" + ":".join(config.model_dump().values())


def feasibility_fingerprint(candidates) -> str:
    """Identity of the whole feasible set under 3.1 semantics: configuration keys, feasibility and reasons."""
    return digest([[config_key31(c.configuration), c.feasible, sorted(c.reasons), list(c.disclosable_action_ids)] for c in candidates])


def manifest31(variant="525", *, exploration=1.0):
    """What a 3.1 PP1 policy checkpoint must declare. Same 525-feature structure; versions differ in action, content, feature schema and fingerprint."""
    from app.learning import lints as policy
    return {**policy.manifest(variant, exploration=exploration), "action": ACTION_SCHEMA31, "features": FEATURE_SCHEMA31,
            "feature_fingerprint": FEATURE_FINGERPRINT31, "content": SCHEMA31}


PROFILE_31 = PolicyProfile("3.1", manifest31, ACTION_SCHEMA31, FEATURE_SCHEMA31, FEATURE_FINGERPRINT31, config_key31)


def cache_key31(source: ProcedureSource, language: str) -> str:
    return digest({"procedure": source.graph.plan_id, "graph": source.graph_fingerprint, "relationships": source.relationship_fingerprint,
                   "language": language, "schema": SCHEMA31})


def semantic_body31(content: GuidanceContent31):
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in ("status", "review")}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip(content.model_dump(mode="json"))


class ContentRegistry31:
    """Separate sqlite registry. A 3.0 registry directory is refused, and so is this one by the 3.0 registry."""

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        c4 = Path(__file__).resolve().parents[3]
        if not self.directory.is_relative_to(c4) or "prepared-content" not in self.directory.parts or "v31" not in self.directory.parts:
            raise ValueError("a 3.1 registry needs its own C4/prepared-content/.../v31 directory")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "registry.sqlite3"
        with self.connect() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and "registry_manifest" not in tables:
                raise ValueError("refusing an unrelated existing database")
            if tables and db.execute("SELECT schema FROM registry_manifest").fetchone() != (REGISTRY_SCHEMA31,):
                raise ValueError("incompatible content registry")
            db.execute("CREATE TABLE IF NOT EXISTS registry_manifest(schema TEXT NOT NULL)")
            if not tables:
                db.execute("INSERT INTO registry_manifest VALUES (?)", (REGISTRY_SCHEMA31,))
            db.execute("CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, cache_key TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL, review_kind TEXT, parent TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS publications(cache_key TEXT PRIMARY KEY, artifact_id TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _write(self, source, content, state, kind=None, parent=None):
        body = content.model_dump(mode="json")
        identifier = digest({"body": body, "state": state, "review_kind": kind, "parent": parent})
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?)", (identifier, cache_key31(source, content.language), state, json.dumps(body), kind, parent))
        return identifier

    def draft(self, source, content):
        validate_content31(source, content)
        def reviewed(value):
            if isinstance(value, dict):
                return value.get("status") == "reviewed" or any(reviewed(v) for v in value.values())
            return isinstance(value, list) and any(reviewed(v) for v in value)
        if content.review is not None or reviewed(content.model_dump(mode="json")):
            raise ValueError("draft cannot self-declare review")
        return self._write(source, content, "draft")

    def inspect(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT state,body,review_kind,parent FROM artifacts WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("unknown content artifact")
        state, body, kind, parent = row
        content = GuidanceContent31.model_validate_json(body)
        original = "reviewed" if state == "published" else state
        if identifier != digest({"body": content.model_dump(mode="json"), "state": original, "review_kind": kind, "parent": parent}):
            raise ValueError("changed stored content artifact")
        return {"id": identifier, "state": state, "content": content, "review_kind": kind, "parent": parent, "provisional": state == "draft"}

    def review(self, source, draft_id, content, *, kind):
        original = self.inspect(draft_id)
        if original["state"] != "draft" or semantic_body31(original["content"]) != semantic_body31(content):
            raise ValueError("review must match a stored draft exactly apart from review/status")
        validate_content31(source, content)
        if not content.review or content.review.status != "reviewed":
            raise ValueError("named statement-level source review required")
        if kind not in ("internal_fictional_author", "human_source_fidelity"):
            raise ValueError("unknown review kind")
        if kind == "internal_fictional_author" and not source.graph.synthetic:
            raise ValueError("internal fictional review cannot approve government guidance")
        return self._write(source, content, "reviewed", kind, draft_id)

    def publish(self, source, identifier):
        artifact = self.inspect(identifier)
        if artifact["state"] not in ("reviewed", "published"):
            raise ValueError("only reviewed content can be published")
        validate_content31(source, artifact["content"])
        with self.connect() as db:
            db.execute("INSERT INTO publications VALUES (?,?) ON CONFLICT(cache_key) DO UPDATE SET artifact_id=excluded.artifact_id", (cache_key31(source, artifact["content"].language), identifier))
            db.execute("UPDATE artifacts SET state='published' WHERE id=?", (identifier,))
        return identifier

    def get(self, source, language="en"):
        with self.connect() as db:
            row = db.execute("SELECT artifact_id FROM publications WHERE cache_key=?", (cache_key31(source, language),)).fetchone()
        if row is None:
            return None
        artifact = self.inspect(row[0])
        if artifact["state"] != "published" or artifact["content"].language != language:
            raise ValueError("invalid publication index")
        validate_content31(source, artifact["content"])
        return artifact


def evaluate_for_runtime(source, content, constraints=None):
    return evaluate31(source, content, constraints)


def compose31(source: ProcedureSource, content: GuidanceContent31 | None, config: Configuration, constraints: Constraints | None = None, *, assume: bool = False, relax_map: bool = False):
    """Render plan under 3.1 meanings. `essential` is the selected primary explanation and is always visible;
    only the separate supplement can sit behind Disclosure; the exact source wording is carried alongside, never instead."""
    candidates = evaluate31(source, content, constraints, assume_reviewed=assume, relax_map=relax_map)
    candidate = next(c for c in candidates if c.configuration == config)
    ok = lambda t: t is not None and (assume or t.status != "draft")   # assume = provisional research preview: drafts are shown, clearly labelled by the caller
    if not candidate.feasible:
        raise ValueError("infeasible guidance configuration: " + ", ".join(candidate.reasons))
    g = source.graph
    prepared = {} if content is None else {a.id: a for a in content.actions}
    passages = {c.content_id: c for c in g.content}
    conditions = {c.condition_id: c.text for c in g.conditions}
    facts = {f.fact_id: f.model_dump(mode="json") for f in g.facts}
    attachments, scoped = [], set()
    for f in content.attachments if content else ():
        if f.status == "draft" and not assume:
            continue
        item = f.model_dump(mode="json", exclude={"qualification"})
        item["fact"] = facts[f.fact_id]
        item["qualification"] = f.qualification.text if ok(f.qualification) else None
        item["conditions"] = [conditions[c] for c in f.condition_ids]
        attachments.append(item)
        scoped.add(f.fact_id)   # a fact attributed to a step or route is not repeated in the whole-service list
    for stage in g.stages:
        for fid in (stage.fee_fact_id, *stage.document_fact_ids):
            if fid not in scoped:
                attachments.append({"id": "source:" + stage.service_id + ":" + fid, "fact": facts[fid], "fact_id": fid, "scope": "stage",
                                    "stage_id": stage.service_id, "qualification": None, "conditions": [], "status": "source_fallback"})
    result = []
    for action in g.actions:
        a = prepared.get(action.action_id)
        raw = "\n\n".join(passages[c].text for c in action.required_content_ids)
        primary_field = getattr(a, config.explanation) if a else None
        usable = bool(primary_field and (primary_field.status == "reviewed" or (assume and primary_field.text)))
        essential = primary_field.text if usable else raw
        heading = a.heading.text if a and ok(a.heading) else raw.split(". ")[0]
        supplement = a.supplement if a and usable and a.supplement and (assume or a.supplement.text.status == "reviewed") and (assume or a.supplement.adds_information) else None
        disclosable = action.action_id in candidate.disclosable_action_ids
        result.append({"id": action.action_id, "heading": heading, "essential": essential,
            "source_wording": a.source_wording.text if usable and ok(a.source_wording) else None,
            "conditions": [conditions[c] for c in action.applicability.condition_ids],
            "actor": a.actor.text if a and ok(a.actor) else None,
            "destination": a.destination.text if a and ok(a.destination) else None,
            "facts": [f for f in attachments if f["scope"] == "action" and f["action_id"] == action.action_id],
            "explanation_visible": None if disclosable or not supplement else supplement.text.text,
            "explanation_hidden": supplement.text.text if disclosable and supplement else None,
            "supplement_role": supplement.role if supplement else None,
            "recap": a.recap.text if config.recap == "on" and a and ok(a.recap) else None,
            "branch": action.applicability.branch_group_id, "option": action.applicability.branch_option_id})
    rel = source.relationships
    return {"schema": RENDER_SCHEMA31, "content_schema": SCHEMA31, "configuration": config.model_dump(), "source_limit": g.disclaimer,
        "source_graph_fingerprint": source.graph_fingerprint, "relationship_fingerprint": source.relationship_fingerprint,
        "content_fingerprint": content.fingerprint if content else None, "actions": result, "facts": attachments,
        "branches": [b.model_dump(mode="json") for b in g.branch_groups], "stages": [s.model_dump(mode="json") for s in g.stages],
        "stage_edges": [e.model_dump(mode="json") for e in g.stage_dependencies], "edges": [e.model_dump(mode="json") for e in g.action_prerequisites],
        "parallel": [p.model_dump(mode="json") for p in g.parallel_groups],
        "joins": [j.model_dump(mode="json") for j in rel.joins] if rel else [],
        "parallel_areas": [[e.model_dump(mode="json") for e in group] for group in rel.parallel_areas] if rel else [],
        "completeness": g.completeness.model_dump(), "sources": [e.model_dump(mode="json") for e in g.evidence],
        "map_labels": {a["id"]: a["heading"] for a in result},
        "phases": [p.model_dump(mode="json") for p in content.phases] if content and config.segmentation == "on" else [],
        "phase_order": list(content.phase_order) if content and config.segmentation == "on" else [],
        "supplementary": [], "required_source_notes": [passages[c].text for action in g.actions for c in action.supplementary_content_ids]}


def install_fictional_content31(service):
    """Install the internally author-reviewed fictional 3.1 artifacts (never official ones) into a 3.1 registry."""
    installed = []
    for file in sorted(FIXTURES31.glob("*.json")):
        packet = json.loads(file.read_text(encoding="utf-8"))
        source = service.source(packet["procedure_id"])
        if not source.graph.synthetic:
            raise ValueError("demo fixture must be fictional")
        content = GuidanceContent31.model_validate(packet["content"])
        if service.registry.get(source, content.language) is not None:
            continue
        draft = GuidanceContent31.model_validate(packet["draft"])
        identifier = service.registry.draft(source, draft)
        reviewed = service.registry.review(source, identifier, content, kind=packet["review_kind"])
        installed.append(service.registry.publish(source, reviewed))
    return installed


ALL_CONFIGS = CATALOGUE
