"""V2 document finalisation for registry entries, kept for existing contracts.

Every registry entry carries a V2-era canonical document. It is served by /v2/*,
/dev/v1/procedures and the V2 journeys, and its preparation status drives the startup
preparation queue. The prepared action labels come from the captured, fingerprint-checked
V1 wording (research/data/prepared-demo); no live generation is invoked. The V3.1 guidance
pipeline reads only the canonical graph, overlay and measurements of an entry.
"""
import copy
from app.preparation.wording_views import WordingViews
from app.procedures.canonical import ROOT, digest


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
    structural = ("actions", "conditions", "prerequisites", "branch_groups", "service_dependencies")
    complete = all(doc["completeness"].get(k)=="complete" for k in structural)
    if not complete:
        doc["capabilities"]["navigation"] = {"states":["overview"], "applicable":False,"reason":"incomplete structure requires overview"}
    if not complete or doc["completeness"].get("parallel_groups") != "complete":
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
