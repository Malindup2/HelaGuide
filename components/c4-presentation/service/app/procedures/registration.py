"""One C4-owned registration boundary around unchanged Plan v1.

Existing paired inputs remain accepted. A versioned registration packet embeds
those inputs plus validated additional relationships. All renderers, measurements
and feasibility consume the resulting canonical entry; wording cannot add edges.
"""
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from app.procedures.procedure_input import parse_procedure_input
from app.procedures.procedure_graph import build_procedure_graph
from app.procedures.canonical import ROOT, Overlay, digest, procedure, registry
from app.compat.v2_documents import finalize, preparation_status

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
    target = directory/(digest({"status":status, "overlay":entry["overlay"].model_dump(mode="json") if entry.get("overlay") else None})+".json")
    payload = {**status, "status":"pending_review_preparation", "graph":entry["graph"].model_dump(mode="json"),
        "base_overlay":entry["overlay"].model_dump(mode="json") if entry.get("overlay") else None}
    if not target.exists():
        import os
        from uuid import uuid4
        temporary = directory / ("." + uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(payload,indent=2),encoding="utf-8")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target
