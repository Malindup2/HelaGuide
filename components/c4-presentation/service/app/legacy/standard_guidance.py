"""Fixed neutral guidance using existing grounding and source preservation.

No user-context encoding, scaffold filtering, policy selection, exposure
registration or reward update occurs here. Standard results are reproducible
from their supplied inputs and do not require persisted policy attribution.
"""

import hashlib
import json

from app.preparation.presentation import action_navigation_order, build_source_cards, item
from app.models.guidance import StandardGuidance
from app.models.presentation import ActionPage
from app.models.scaffolds import ScaffoldConfiguration, VisibilityDeclaration


def build_standard_guidance(
    graph,
    explanation_service,
    *,
    safety=None,
    writing_style="plain",
):
    explanation = explanation_service.explain_standard(
        graph,
        safety=safety,
        writing_style=writing_style,
    )
    # Reuse source formatting only. This constant is never selected by a
    # policy or registered as a scaffold offer.
    layout = ScaffoldConfiguration(
        presentation_mode="OVERVIEW",
        progressive_disclosure=False,
        previous_context_recap=False,
        relationship_visual="NONE",
        prerequisite_cue=False,
    )
    cards = build_source_cards(graph, explanation.source, layout)
    actions = {action.action_id: action for action in graph.actions}
    pages = []
    for action_id in action_navigation_order(graph):
        action = actions[action_id]
        pages.append(
            ActionPage(
                action_id=action_id,
                service_id=action.service_id,
                items=(item("action", action_id),) + tuple(
                    item("content", content_id)
                    for content_id in (
                        action.required_content_ids + action.supplementary_content_ids
                    )
                ),
                condition_ids=action.applicability.condition_ids,
                branch_group_id=action.applicability.branch_group_id,
                branch_option_id=action.applicability.branch_option_id,
                prerequisite_cues=(),
            )
        )
    located = {reference for page in pages for reference in page.items}
    document = StandardGuidance(
        standard_id="pending",
        graph_fingerprint=explanation.graph_fingerprint,
        writing_style=writing_style,
        explanation=explanation,
        cards=cards,
        global_items=tuple(
            card.source for card in cards if card.source not in located
        ),
        pages=tuple(pages),
        visibility=VisibilityDeclaration(
            visible=tuple(card.source for card in cards),
        ),
    )
    encoded = json.dumps(
        document.model_dump(
            mode="json",
            exclude={
                "standard_id": True,
                "explanation": {"cache_hit"},
            },
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    identifier = "standard:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    values = {
        name: getattr(document, name)
        for name in type(document).model_fields
    }
    values["standard_id"] = identifier
    return StandardGuidance(**values)
