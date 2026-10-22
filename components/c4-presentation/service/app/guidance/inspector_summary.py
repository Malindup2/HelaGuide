"""Readable, honest summary of ONE stored guidance decision for the Research Inspector.

Pure function of the frozen journey record (decision, views, availability, context) and its frozen source. It states only values that were
recorded and never claims why a particular scaffold won: LinTS picks the highest sampled-scoring feasible configuration, and context
features act through the feature representation, which a single decision cannot attribute to one feature.
"""
from app.guidance.catalogue import DIMENSIONS

PHRASE = {
    "navigation": {"overview": "Overview navigation", "guided": "Guided navigation"},
    "explanation": {"concise": "Concise explanation", "detailed": "Detailed explanation"},
    "disclosure": {"off": "Progressive Disclosure OFF", "on": "Progressive Disclosure ON"},
    "relationships": {"none": "text-only relationships", "inline": "Inline relationships", "map": "Map relationships"},
    "recap": {"off": "Recap OFF", "on": "Recap ON"},
    "segmentation": {"off": "Segmentation OFF", "on": "Segmentation ON"},
}
MEASURES = ("step_count", "information_volume", "branch_count", "condition_count", "dependency_count", "dependency_depth", "parallel_group_count")


def describe(configuration: dict) -> str:
    return ", ".join(PHRASE[d][configuration[d]] for d in DIMENSIONS)


def map_availability(graph, constraints: dict, candidates: list, selected: dict) -> dict:
    """Why a process map is or is not on offer, separating the possible causes."""
    structural = {k: getattr(graph.completeness, k) for k in ("actions", "conditions", "prerequisites", "branch_groups", "service_dependencies")}
    parallel = graph.completeness.parallel_groups
    has_relations = bool(graph.action_prerequisites or graph.branch_groups or graph.parallel_groups or graph.stage_dependencies)
    on_offer = [c for c in candidates if c["feasible"] and c["configuration"]["relationships"] == "map"]
    locks = constraints.get("locks", {})
    if constraints.get("no_map"):
        status, detail = "accessibility_restriction", "The citizen's accessibility settings do not allow diagrams."
    elif "relationships" in locks and locks["relationships"] != "map":
        status, detail = "explicit_lock", "An explicit lock fixes relationships to '" + locks["relationships"] + "'."
    elif not has_relations:
        status, detail = "no_verified_relationship_data", "The procedure has no verified prerequisites, branches or parallel groups to draw."
    elif any(v != "complete" for v in structural.values()) or parallel != "complete":
        gaps = [k for k, v in {**structural, "parallel_groups": parallel}.items() if v != "complete"]
        status, detail = "coverage_incomplete", "The source does not give complete coverage for: " + ", ".join(gaps) + ". The strict map rule needs all of them complete."
    elif not on_offer:
        status, detail = "not_feasible_other_reason", "Another feasibility rule excludes every map configuration."
    elif selected["relationships"] == "map":
        status, detail = "selected", "A map was selected from the feasible set."
    else:
        status, detail = "feasible_not_selected", "Map configurations were feasible; the sampled scores favoured another feasible configuration."
    return {"status": status, "detail": detail, "map_configurations_feasible": len(on_offer)}


def summarize(journey: dict, source, measurement_dump: dict, events: list) -> dict:
    views = list(journey["views"].values())
    original = next(v for v in views if v["parent_view_id"] is None)
    current = journey["views"][journey["current_view_id"]]
    selection, config = original["selection"], original["selection"]["configuration"]
    decision, context, availability = journey.get("decision"), journey["context"], journey["availability"]
    adjusted = bool(journey.get("ever_adjusted"))
    chosen = next((c for c in decision["candidates"] if c["id"] == decision["selected_id"]), None) if decision else None
    rated = any(e.get("type") == "rating" and e.get("view_id") == original["id"] for e in events)
    if decision is None:
        eligibility = {"eligible": False, "reason": {"standard": "Standard guidance is a fixed baseline and never trains the model.", "constraint_standard": "Standard guidance is a fixed baseline and never trains the model.",
                                                     "research_preview": "A research preview is a researcher's choice and never trains the model."}.get(selection["kind"], "Not a model selection.")}
    elif adjusted:
        eligibility = {"eligible": False, "reason": "The citizen adjusted this journey manually, so the original selection can no longer train the model."}
    elif not context["personalization_enabled"]:
        eligibility = {"eligible": False, "reason": "Personalization is switched off for this profile."}
    elif rated:
        eligibility = {"eligible": False, "reason": "The original view has already been rated; one rating updates the model once."}
    else:
        eligibility = {"eligible": True, "reason": "A genuine, unadjusted personalized selection: one Fits / Does not fit rating updates the model once."}
    if decision:
        text = ("The model evaluated the " + str(availability["feasible_count"]) + " feasible presentation configurations using the citizen's stated context and the procedure's structural features. "
                "LinTS selects the feasible configuration with the highest sampled score; individual context features influence the scores through the feature representation. "
                "The selected configuration was " + describe(config) + ".")
    elif selection["kind"] == "research_preview":
        text = "No model scoring was run. A researcher chose this configuration: " + describe(config) + "."
    else:
        text = "No model scoring was run. The fixed standard baseline within the citizen's hard constraints was used: " + describe(config) + "."
    if adjusted:
        text += " The citizen later adjusted the view to " + describe(current["selection"]["configuration"]) + "."
    return {
        "kind": selection["kind"], "personalized": decision is not None, "label": selection["label"],
        "selected_configuration": config, "selected_description": describe(config),
        "displayed_configuration": current["selection"]["configuration"], "adjusted_by_citizen": adjusted,
        "effective_context": {"familiarity": context["familiarity"], "confidence": context["confidence"], "personalization_enabled": context["personalization_enabled"],
                              "soft_preferences": context["preferences"], "preference_origin": context["sources"].get("preferences")},
        "hard_restrictions": {"no_guided": context["constraints"]["no_guided"], "no_map": context["constraints"]["no_map"], "no_disclosure": context["constraints"]["no_disclosure"],
                              "locks": context["constraints"]["locks"]},
        "structure": {k: {"observed": measurement_dump[k]["observed"], "completeness": measurement_dump[k]["completeness"]} for k in MEASURES},
        "feasible_count": availability["feasible_count"], "nominal_count": availability["nominal_count"],
        "sampled_score": chosen["sampled_score"] if chosen else None, "posterior_mean": chosen["posterior_mean"] if chosen else None,
        "policy": ({"algorithm": decision["policy"]["algorithm"], "action_schema": decision["policy"]["action_schema"], "encoder_schema": decision["policy"]["encoder_schema"],
                    "posterior_revision": decision["policy"]["posterior_revision"], "decision_id": decision["policy"]["decision_id"],
                    "model_manifest_fingerprint": decision["policy"]["model_manifest_fingerprint"], "training_provenance": decision["policy"]["training_provenance"]} if decision else None),
        "learning": eligibility, "map": map_availability(source.graph, context["constraints"], availability["candidates"], config),
        "explanation": text,
    }
