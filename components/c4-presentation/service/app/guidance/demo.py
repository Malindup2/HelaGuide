"""Install explicit internally author-reviewed fictional artifacts, never official ones."""
import json
from pathlib import Path
from app.guidance.content import GuidanceContent

FIXTURES = Path(__file__).resolve().parents[3] / "research" / "data" / "guidance" / "fictional"


def install_fictional_content(service):
    installed = []
    for file in sorted(FIXTURES.glob("*.json")):
        packet = json.loads(file.read_text(encoding="utf-8"))
        source = service.source(packet["procedure_id"])
        if not source.graph.synthetic:
            raise ValueError("demo fixture must be fictional")
        content = GuidanceContent.model_validate(packet["content"])
        if service.registry.get(source, content.language) is not None:
            continue  # Restart/cache hit never republishes or rewrites an artifact.
        draft = GuidanceContent.model_validate(packet["draft"])
        identifier = service.registry.draft(source, draft)
        reviewed = service.registry.review(source, identifier, content, kind=packet["review_kind"])
        installed.append(service.registry.publish(source, reviewed))
    return installed
