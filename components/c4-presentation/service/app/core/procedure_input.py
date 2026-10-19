"""Load and validate independent C4 procedure input.

No network, database, application startup or rendering dependency is used.
"""

import json
import re
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from helaguide_common.contracts import FACT_ID, Plan
from app.models.procedure import ProcedureEnrichment, ProcedureInput


class ProcedureInputError(ValueError):
    """Invalid file, JSON, model or procedure relationship."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProcedureInputError(message)


def _unique(values, label: str) -> None:
    seen = set()
    for value in values:
        _require(value not in seen, f"{label}: duplicate '{value}'")
        seen.add(value)


def _index(items, field: str, label: str) -> dict:
    _unique([getattr(item, field) for item in items], label)
    return {getattr(item, field): item for item in items}


def _references(values, known, label: str) -> None:
    _unique(values, label)
    for value in values:
        _require(value in known, f"{label}: unknown reference '{value}'")


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"JSON: duplicate object key '{key}'")
        result[key] = value
    return result


def _reject_constant(value):
    raise ProcedureInputError(f"JSON: non-finite number '{value}'")


def _json_text(text: str, label: str) -> str:
    """Validate JSON syntax and prevent duplicate keys/non-finite values."""
    _require(isinstance(text, str), f"{label}: expected JSON text")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
        _require(isinstance(value, dict), f"{label}: root must be an object")
        return json.dumps(value, allow_nan=False)
    except ProcedureInputError:
        raise
    except json.JSONDecodeError as exc:
        raise ProcedureInputError(
            f"{label}: invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}"
        ) from exc
    except ValueError as exc:
        raise ProcedureInputError(
            f"{label}: JSON numbers must be finite"
        ) from exc


def _read(path: str | Path, label: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ProcedureInputError(
            f"{label}: cannot read UTF-8 file '{path}' "
            f"({type(exc).__name__})"
        ) from exc


def _typed(model, text: str, label: str):
    try:
        return model.model_validate_json(
            _json_text(text, label),
            strict=True,
        )
    except ValidationError as exc:
        first = exc.errors(include_url=False, include_input=False)[0]
        location = ".".join(map(str, first["loc"])) or "<root>"
        raise ProcedureInputError(
            f"{label}.{location}: {first['msg']}"
        ) from exc


def _aware(timestamp, label: str) -> None:
    _require(
        timestamp.tzinfo is not None and timestamp.utcoffset() is not None,
        f"{label}: timezone is required",
    )


def _source_url(url: str, label: str, *, web: bool) -> str:
    """Validate syntax while preserving the original source string."""
    _require(
        not any(char.isspace() for char in url),
        f"{label}: source identifier contains whitespace",
    )
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ProcedureInputError(
            f"{label}: invalid source identifier"
        ) from exc

    _require(bool(parsed.scheme), f"{label}: absolute source URI required")
    _require(
        parsed.username is None and parsed.password is None,
        f"{label}: source URI must not contain credentials",
    )
    if web or parsed.scheme.lower() in {"http", "https"}:
        _require(
            parsed.scheme.lower() in {"http", "https"} and bool(hostname),
            f"{label}: absolute HTTP(S) source URL required",
        )
    return (hostname or "").lower().rstrip(".")


def _example_host(host: str) -> bool:
    return any(
        host == domain or host.endswith("." + domain)
        for domain in ("example.org", "example.com", "example.net")
    )


def _dag_reachability(nodes, edges, label: str) -> dict[str, set[str]]:
    adjacency = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    seen_edges = set()

    for source, target in edges:
        _require(
            source in adjacency and target in adjacency,
            f"{label}: unknown endpoint '{source}' -> '{target}'",
        )
        _require(source != target, f"{label}: self-link '{source}'")
        _require(
            (source, target) not in seen_edges,
            f"{label}: duplicate edge '{source}' -> '{target}'",
        )
        seen_edges.add((source, target))
        adjacency[source].add(target)
        indegree[target] += 1

    ready = deque(node for node in adjacency if indegree[node] == 0)
    order = []

    while ready:
        node = ready.popleft()
        order.append(node)
        for target in adjacency[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)

    _require(
        len(order) == len(adjacency),
        f"{label}: cycle detected among "
        f"{sorted(node for node in adjacency if indegree[node] > 0)}",
    )

    reachable = {node: set() for node in adjacency}
    for node in reversed(order):
        for target in adjacency[node]:
            reachable[node].add(target)
            reachable[node].update(reachable[target])
    return reachable


def _validate(procedure: ProcedureInput) -> None:
    plan = procedure.plan
    enrichment = procedure.enrichment

    _require(bool(plan.plan_id.strip()), "Plan.plan_id must not be blank")
    _require(
        plan.plan_id == enrichment.plan_id,
        "Plan/enrichment plan_id mismatch",
    )
    _aware(plan.generated_at, "Plan.generated_at")
    _require(
        plan.generated_at == enrichment.base_generated_at,
        "Plan/enrichment generation timestamp mismatch",
    )

    stages = _index(plan.steps, "service_id", "stages")
    _require(
        plan.requested_service_id in stages,
        "requested_service_id does not reference a Plan stage",
    )
    orders = [stage.order for stage in plan.steps]
    _unique(orders, "stage display orders")
    _require(orders == sorted(orders), "Plan steps are not in display order")

    stage_edges = []
    for stage in plan.steps:
        _references(stage.depends_on, stages, f"{stage.service_id}.depends_on")
        stage_edges.extend(
            (required, stage.service_id) for required in stage.depends_on
        )
    stage_reach = _dag_reachability(stages, stage_edges, "stage dependencies")
    for required, dependent in stage_edges:
        _require(
            stages[required].order < stages[dependent].order,
            f"required stage '{required}' must precede '{dependent}'",
        )

    facts = {}
    for stage in plan.steps:
        for fact in [stage.fee, *stage.documents]:
            definition = fact.model_dump(mode="json")
            _require(
                fact.fact_id not in facts or facts[fact.fact_id] == definition,
                f"conflicting definitions for fact '{fact.fact_id}'",
            )
            facts[fact.fact_id] = definition

    for fact_id, source in plan.provenance.items():
        _require(
            re.fullmatch(FACT_ID, fact_id) is not None,
            f"invalid provenance fact ID '{fact_id}'",
        )
        host = _source_url(
            source.source_url, f"provenance '{fact_id}'", web=True
        )
        _aware(source.retrieved_at, f"provenance '{fact_id}'.retrieved_at")
        if enrichment.synthetic:
            _require(
                _example_host(host),
                "synthetic Plan provenance must use reserved example domains",
            )

    actions = _index(enrichment.actions, "action_id", "actions")
    content = _index(enrichment.content, "content_id", "content")
    evidence = _index(enrichment.evidence, "evidence_id", "evidence")
    conditions = _index(enrichment.conditions, "condition_id", "conditions")
    prerequisites = _index(
        enrichment.prerequisites, "prerequisite_id", "prerequisites"
    )
    branches = _index(enrichment.branch_groups, "group_id", "branch groups")
    parallels = _index(enrichment.parallel_groups, "group_id", "parallel groups")

    expected_kind = (
        "synthetic_authored" if enrichment.synthetic else "source_passage"
    )
    for item in evidence.values():
        _require(
            item.kind == expected_kind,
            f"evidence '{item.evidence_id}' conflicts with synthetic status",
        )
        host = _source_url(item.source_url, item.evidence_id, web=True)
        if enrichment.synthetic:
            _require(
                item.retrieved_at is None and _example_host(host),
                f"synthetic evidence '{item.evidence_id}' must use an example "
                "domain and retrieved_at=null",
            )
        else:
            _require(
                item.retrieved_at is not None,
                f"source passage '{item.evidence_id}' needs retrieved_at",
            )

    for item in content.values():
        _references(item.evidence_ids, evidence, f"{item.content_id}.evidence")
        _references(item.fact_ids, facts, f"{item.content_id}.facts")
    for item in conditions.values():
        _references(
            item.evidence_ids, evidence, f"{item.condition_id}.evidence"
        )

    represented_stages = set()
    guards = {}
    for action in actions.values():
        _require(
            action.service_id in stages,
            f"action '{action.action_id}' has unknown parent stage",
        )
        represented_stages.add(action.service_id)
        _references(
            action.condition_ids, conditions, f"{action.action_id}.conditions"
        )
        guards[action.action_id] = set(action.condition_ids)

        _require(
            not set(action.required_content_ids)
            & set(action.supplementary_content_ids),
            f"action '{action.action_id}' assigns conflicting content roles",
        )
        for role, ids in (
            ("required", action.required_content_ids),
            ("supplementary", action.supplementary_content_ids),
        ):
            _references(ids, content, f"{action.action_id}.{role}_content")
            for content_id in ids:
                _require(
                    content[content_id].role == role,
                    f"content '{content_id}' has the wrong role for "
                    f"action '{action.action_id}'",
                )

    if enrichment.completeness.actions == "complete":
        _require(
            represented_stages == set(stages),
            "complete actions must cover every Plan stage",
        )

    memberships = {}
    option_ids = set()
    for group in branches.values():
        _require(
            group.service_id in stages,
            f"branch '{group.group_id}' has unknown stage",
        )
        _references(group.evidence_ids, evidence, f"{group.group_id}.evidence")
        for option in group.options:
            _require(
                option.option_id not in option_ids,
                f"duplicate option ID '{option.option_id}'",
            )
            option_ids.add(option.option_id)
            _references(option.action_ids, actions, f"{option.option_id}.actions")
            _references(
                option.condition_ids, conditions, f"{option.option_id}.conditions"
            )
            for action_id in option.action_ids:
                _require(
                    actions[action_id].service_id == group.service_id,
                    f"branch action '{action_id}' belongs to another stage",
                )
                _require(
                    action_id not in memberships,
                    f"action '{action_id}' belongs to multiple branch options",
                )
                memberships[action_id] = (group.group_id, option.option_id)
                guards[action_id].update(option.condition_ids)

    action_edges = []
    for item in prerequisites.values():
        required = item.required_action_id
        dependent = item.dependent_action_id
        _require(
            required in actions and dependent in actions,
            f"prerequisite '{item.prerequisite_id}' has unknown action",
        )
        _references(item.evidence_ids, evidence, f"{item.prerequisite_id}.evidence")

        source_stage = actions[required].service_id
        target_stage = actions[dependent].service_id
        _require(
            source_stage == target_stage
            or target_stage in stage_reach[source_stage],
            f"prerequisite '{item.prerequisite_id}' contradicts or lacks "
            "an explicit stage dependency path",
        )

        _require(
            guards[required] <= guards[dependent],
            f"prerequisite '{item.prerequisite_id}' requires a conditional "
            "action whose applicability is not guaranteed",
        )

        source_membership = memberships.get(required)
        if source_membership is not None:
            group_id, _ = source_membership
            if branches[group_id].selection in {"OR", "XOR"}:
                _require(
                    memberships.get(dependent) == source_membership,
                    f"prerequisite '{item.prerequisite_id}' requires an "
                    "optional branch outside its selected option",
                )
        action_edges.append((required, dependent))

    action_reach = _dag_reachability(
        actions, action_edges, "action prerequisites"
    )

    if parallels:
        completeness = enrichment.completeness
        for category in (
            "actions",
            "service_dependencies",
            "prerequisites",
            "conditions",
            "branch_groups",
        ):
            _require(
                getattr(completeness, category) == "complete",
                f"parallel claims require complete '{category}' information",
            )

    parallel_memberships = set()
    for group in parallels.values():
        _require(
            group.service_id in stages,
            f"parallel group '{group.group_id}' has unknown stage",
        )
        _references(group.action_ids, actions, f"{group.group_id}.actions")
        _references(group.evidence_ids, evidence, f"{group.group_id}.evidence")
        member_set = frozenset(group.action_ids)
        _require(
            member_set not in parallel_memberships,
            f"parallel group '{group.group_id}' duplicates an existing group",
        )
        parallel_memberships.add(member_set)

        first = group.action_ids[0]
        for action_id in group.action_ids:
            _require(
                actions[action_id].service_id == group.service_id,
                f"parallel action '{action_id}' belongs to another stage",
            )
            _require(
                guards[action_id] == guards[first]
                and memberships.get(action_id) == memberships.get(first),
                f"parallel group '{group.group_id}' has incompatible applicability",
            )

        for index, left in enumerate(group.action_ids):
            for right in group.action_ids[index + 1:]:
                _require(
                    right not in action_reach[left]
                    and left not in action_reach[right],
                    f"parallel group '{group.group_id}' contains a "
                    "prerequisite path between its members",
                )


def parse_procedure_input(
    plan_json: str,
    enrichment_json: str,
) -> ProcedureInput:
    """Return typed, semantically validated input from two JSON strings."""
    plan = _typed(Plan, plan_json, "Plan")
    enrichment = _typed(
        ProcedureEnrichment, enrichment_json, "Enrichment"
    )
    procedure = ProcedureInput(plan=plan, enrichment=enrichment)
    _validate(procedure)
    return procedure


def load_procedure_input(
    plan_path: str | Path,
    enrichment_path: str | Path,
) -> ProcedureInput:
    """Read local UTF-8 files and run the complete input boundary."""
    return parse_procedure_input(
        _read(plan_path, "Plan"),
        _read(enrichment_path, "Enrichment"),
    )