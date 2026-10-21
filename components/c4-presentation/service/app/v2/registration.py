"""One C4-owned registration boundary around unchanged Plan v1.

Existing paired inputs remain accepted. A versioned registration packet embeds
those inputs plus validated additional relationships. All renderers, measurements
and feasibility consume the resulting canonical entry; wording cannot add edges.
"""
import copy
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from app.core.procedure_input import parse_procedure_input
from app.core.procedure_graph import build_procedure_graph
from app.core.wording_views import WordingViews
from app.v2.content import ROOT, Overlay, digest, procedure, registry

class RegistrationPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "c4-registration-1.0"
    plan: dict
    enrichment: dict
    relationships: Overlay | None = None


def register(packet: RegistrationPacket):
    if packet.schema_version != "c4-registration-1.0":
        raise ValueError("unsupported C4 registration packet")
    if packet.relationships and packet.relationships.reviewer.strip().upper().startswith("PENDING"):
        raise ValueError("pending generated content cannot be registered as approved")
    graph = build_procedure_graph(parse_procedure_input(json.dumps(packet.plan), json.dumps(packet.enrichment)))
    return finalize(procedure(graph, packet.relationships))


def finalize(entry, *, demo=True):
    entry = dict(entry)
    doc = copy.deepcopy(entry["document"])
    graph = entry["graph"]
    # Read the same captured, fingerprint-validated wording used by V1.
    # No live generation or familiarity-based writing-style rule is invoked.
    words = WordingViews(demo_directory=ROOT/"prepared-demo" if demo else None)
    plain, artifact = words.prepare(graph, writing_style="plain")
    resolved = {i.slot_id:i for i in plain.items} if plain else {}
    variant_ids = {v.action_id for v in entry["overlay"].variants} if entry.get("overlay") else set()
    for action in doc["actions"]:
        aid = action["id"]
        heading = resolved.get(f"action_heading/action/{aid}")
        recap = resolved.get(f"action_summary/action/{aid}")
        if aid not in variant_ids and heading and heading.origin != "source_fallback":
            action["title"] = heading.text
        elif action["title"].lower().replace(" ", "_") == aid.split(":")[-1]:
            # Verbatim source excerpt, never an invented official action name.
            action["title"] = action["concise"].split(". ")[0][:115].rstrip(".")
        if aid not in variant_ids and recap and recap.origin != "source_fallback":
            action["recap"] = recap.text
        if action["recap"] == action["title"]:
            # Reuse an exact approved/source sentence rather than pretending a
            # navigation label is a contextual summary. No generated facts.
            action["recap"] = action["concise"].split(". ")[0].rstrip(".") + "."
        action["wording_status"] = {"title":"v2_variant" if aid in variant_ids else ("prepared_demo" if heading and heading.origin!="source_fallback" else "source_excerpt"),
            "instructions":"v2_variant" if aid in variant_ids else "source_preserving"}
    if artifact and not entry.get("overlay"):
        # Legacy wording slots are not full depth variants: appending a shorter
        # paraphrase to the source merely duplicates facts. Keep them available
        # for offline preparation; do not relabel them as approved V2 expansion.
        doc["content_origin"] = "prepared demo labels; source-preserving instructions"
    # A map may show only supplied relationships, but incomplete structure must
    # not be promoted to a complete procedure map or focused execution sequence.
    structural = ("actions", "conditions", "action_prerequisites", "branch_groups", "stage_dependencies")
    complete = all(doc["completeness"].get(k)=="complete" for k in structural if k in doc["completeness"])
    if not complete:
        doc["capabilities"]["navigation"] = {"states":["overview"], "applicable":False,"reason":"incomplete structure requires overview"}
        relation = doc["capabilities"]["relationships"]
        relation["states"] = [s for s in relation["states"] if s != "map"]
        relation["reason"] = "full map unavailable: structural coverage is incomplete"
    doc["canonical_schema"] = "c4-canonical-journey-1.0"
    structure = {k:doc[k] for k in ("edges", "stage_edges", "branches", "parallel", "joins", "parallel_areas", "completeness")}
    doc["structure_fingerprint"] = digest({"graph":doc["graph_fingerprint"], "structure":structure})
    doc.pop("content_fingerprint",None)
    doc["content_fingerprint"] = digest(doc)
    entry["document"] = doc
    entry["canonical"] = {"schema":doc["canonical_schema"], "base_graph":graph, "relationships":entry.get("overlay"), "fingerprint":doc["structure_fingerprint"]}
    entry["preparation"] = preparation_status(entry)
    return entry


def preparation_status(entry):
    doc = entry["document"]
    missing = []
    for action in doc["actions"]:
        if not action["title"].strip() or action.get("wording_status",{}).get("title")=="source_excerpt":
            missing.append({"action":action["id"],"slot":"title"})
        if action.get("wording_status",{}).get("instructions")=="source_preserving":
            missing.append({"action":action["id"],"slot":"concise_variant"})
        if action["expanded"] == action["concise"]:
            missing.append({"action":action["id"],"slot":"expanded"})
    return {"procedure_id":doc["id"], "graph_fingerprint":doc["graph_fingerprint"],
        "missing":missing, "status":"needs_preparation" if missing else "prepared",
        "live_generation_enabled":False, "approval":"explicit named review required for generated content"}


def workspace_registry():
    return {key:finalize(value) for key,value in registry().items()}


def queue_preparation(entry, directory):
    """Idempotent offline job request. No provider, auto approval or DB write."""
    root = Path(__file__).resolve().parents[3]
    directory = Path(directory).resolve()
    if not directory.is_relative_to(root) or "v2" not in directory.parts:
        raise ValueError("preparation jobs must stay in C4/v2")
    status = preparation_status(entry)
    directory.mkdir(parents=True,exist_ok=True)
    target = directory/(digest(status)+".json")
    payload = {**status, "status":"pending_review_preparation", "graph":entry["graph"].model_dump(mode="json"),
        "base_overlay":entry["overlay"].model_dump(mode="json") if entry.get("overlay") else None}
    if not target.exists():
        target.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return target
