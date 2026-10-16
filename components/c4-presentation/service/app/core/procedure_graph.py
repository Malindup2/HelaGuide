"""Build C4's canonical procedure graph and explicit dependency indexes."""

from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import heapify, heappop, heappush
from types import MappingProxyType
from typing import Literal, Mapping

from app.core.procedure_input import parse_procedure_input
from app.models.procedure import ProcedureInput
from app.models.procedure_graph import (
    ActionApplicability,
    ActionNode,
    ActionPrerequisiteEdge,
    BranchGroupNode,
    BranchOptionNode,
    CanonicalProcedureGraph,
    ConditionNode,
    ContentNode,
    DocumentFact,
    EvidenceNode,
    FactProvenance,
    FeeFact,
    GraphCompleteness,
    ParallelGroupNode,
    StageDependencyEdge,
    StageNode,
)


DependencyLevel = Literal["stage", "action"]


@dataclass(frozen=True, slots=True)
class DependencyIndex:
    """Immutable adjacency for one explicit dependency layer.

    Topological order is a deterministic DAG traversal order, not a
    resolved procedure execution schedule.
    """

    level: DependencyLevel
    predecessors: Mapping[str, tuple[str, ...]]
    successors: Mapping[str, tuple[str, ...]]
    topological_order: tuple[str, ...]


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _stage_edge_id(source_id: str, target_id: str) -> str:
    return f"stage_dependency:{source_id}->{target_id}"


def build_procedure_graph(
    procedure: ProcedureInput,
) -> CanonicalProcedureGraph:
    """Build an independent, immutable snapshot of validated input.

    Revalidation protects against a ProcedureInput mutated after loading.
    It also creates a fresh input snapshot without retaining caller-owned
    lists or model objects.
    """
    if not isinstance(procedure, ProcedureInput):
        raise TypeError("procedure must be a ProcedureInput")

    clean = parse_procedure_input(
        procedure.plan.model_dump_json(),
        procedure.enrichment.model_dump_json(),
    )
    plan = clean.plan
    enrichment = clean.enrichment

    facts = {}
    for stage in plan.steps:
        fee = stage.fee
        facts[fee.fact_id] = FeeFact(
            fact_id=fee.fact_id,
            value=fee.value,
            currency=fee.currency,
        )
        for document in stage.documents:
            facts[document.fact_id] = DocumentFact(
                fact_id=document.fact_id,
                name=document.name,
            )

    stages = tuple(
        StageNode(
            service_id=stage.service_id,
            display_order=stage.order,
            name=stage.name,
            agency=stage.agency,
            fee_fact_id=stage.fee.fact_id,
            document_fact_ids=tuple(
                document.fact_id for document in stage.documents
            ),
        )
        for stage in sorted(
            plan.steps,
            key=lambda item: (item.order, item.service_id),
        )
    )

    stage_dependencies = tuple(
        sorted(
            (
                StageDependencyEdge(
                    edge_id=_stage_edge_id(required, stage.service_id),
                    source_id=required,
                    target_id=stage.service_id,
                )
                for stage in plan.steps
                for required in stage.depends_on
            ),
            key=lambda item: item.edge_id,
        )
    )

    branch_groups = tuple(
        BranchGroupNode(
            group_id=group.group_id,
            service_id=group.service_id,
            selection=group.selection,
            options=tuple(
                BranchOptionNode(
                    option_id=option.option_id,
                    action_ids=tuple(sorted(option.action_ids)),
                    condition_ids=tuple(sorted(option.condition_ids)),
                )
                for option in sorted(
                    group.options, key=lambda item: item.option_id
                )
            ),
            evidence_ids=tuple(sorted(group.evidence_ids)),
        )
        for group in sorted(
            enrichment.branch_groups, key=lambda item: item.group_id
        )
    )

    membership = {
        action_id: (
            group.group_id,
            option.option_id,
            option.condition_ids,
        )
        for group in branch_groups
        for option in group.options
        for action_id in option.action_ids
    }

    action_nodes = []
    for action in sorted(enrichment.actions, key=lambda item: item.action_id):
        group_id = None
        option_id = None
        option_conditions = ()

        if action.action_id in membership:
            group_id, option_id, option_conditions = membership[
                action.action_id
            ]

        effective_conditions = tuple(
            sorted(set(action.condition_ids) | set(option_conditions))
        )
        action_nodes.append(
            ActionNode(
                action_id=action.action_id,
                service_id=action.service_id,
                required_content_ids=tuple(action.required_content_ids),
                supplementary_content_ids=tuple(
                    action.supplementary_content_ids
                ),
                direct_condition_ids=tuple(sorted(action.condition_ids)),
                applicability=ActionApplicability(
                    condition_ids=effective_conditions,
                    branch_group_id=group_id,
                    branch_option_id=option_id,
                ),
            )
        )

    graph = CanonicalProcedureGraph(
        enrichment_schema_version=enrichment.schema_version,
        plan_id=plan.plan_id,
        requested_service_id=plan.requested_service_id,
        generated_at=_utc(plan.generated_at),
        synthetic=enrichment.synthetic,
        disclaimer=enrichment.disclaimer,
        stages=stages,
        actions=tuple(action_nodes),
        stage_dependencies=stage_dependencies,
        action_prerequisites=tuple(
            ActionPrerequisiteEdge(
                edge_id=item.prerequisite_id,
                source_id=item.required_action_id,
                target_id=item.dependent_action_id,
                kind=item.kind,
                evidence_ids=tuple(sorted(item.evidence_ids)),
            )
            for item in sorted(
                enrichment.prerequisites,
                key=lambda item: item.prerequisite_id,
            )
        ),
        conditions=tuple(
            ConditionNode(
                condition_id=item.condition_id,
                text=item.text,
                evidence_ids=tuple(sorted(item.evidence_ids)),
            )
            for item in sorted(
                enrichment.conditions,
                key=lambda item: item.condition_id,
            )
        ),
        branch_groups=branch_groups,
        parallel_groups=tuple(
            ParallelGroupNode(
                group_id=item.group_id,
                service_id=item.service_id,
                action_ids=tuple(sorted(item.action_ids)),
                evidence_ids=tuple(sorted(item.evidence_ids)),
            )
            for item in sorted(
                enrichment.parallel_groups,
                key=lambda item: item.group_id,
            )
        ),
        content=tuple(
            ContentNode(
                content_id=item.content_id,
                role=item.role,
                text=item.text,
                evidence_ids=tuple(sorted(item.evidence_ids)),
                fact_ids=tuple(sorted(item.fact_ids)),
            )
            for item in sorted(
                enrichment.content,
                key=lambda item: item.content_id,
            )
        ),
        evidence=tuple(
            EvidenceNode(
                evidence_id=item.evidence_id,
                kind=item.kind,
                source_url=item.source_url,
                text=item.text,
                retrieved_at=(
                    _utc(item.retrieved_at)
                    if item.retrieved_at is not None
                    else None
                ),
            )
            for item in sorted(
                enrichment.evidence,
                key=lambda item: item.evidence_id,
            )
        ),
        facts=tuple(facts[fact_id] for fact_id in sorted(facts)),
        provenance=tuple(
            FactProvenance(
                fact_id=fact_id,
                source_url=source.source_url,
                retrieved_at=_utc(source.retrieved_at),
            )
            for fact_id, source in sorted(plan.provenance.items())
        ),
        completeness=GraphCompleteness(
            **enrichment.completeness.model_dump()
        ),
    )

    # Check the projected dependency layers themselves. These checks also
    # guard against future mistakes in projection code.
    dependency_index(graph, "stage")
    dependency_index(graph, "action")

    return graph


def dependency_index(
    graph: CanonicalProcedureGraph,
    level: DependencyLevel,
) -> DependencyIndex:
    """Index only the explicitly supplied edges in the requested layer.

    Every represented node appears, including isolated nodes.
    Lexical IDs break topological ties; display order is not an edge.
    """
    if level == "stage":
        node_ids = [node.service_id for node in graph.stages]
        edges = graph.stage_dependencies
    elif level == "action":
        node_ids = [node.action_id for node in graph.actions]
        edges = graph.action_prerequisites
    else:
        raise ValueError("level must be 'stage' or 'action'")

    if len(node_ids) != len(set(node_ids)):
        raise ValueError(f"{level} dependency index has duplicate nodes")

    predecessors = {node_id: set() for node_id in node_ids}
    successors = {node_id: set() for node_id in node_ids}
    seen_edges = set()

    for edge in edges:
        source = edge.source_id
        target = edge.target_id

        if source not in successors or target not in predecessors:
            raise ValueError(
                f"{level} edge '{edge.edge_id}' has an unknown endpoint"
            )
        if source == target:
            raise ValueError(f"{level} edge '{edge.edge_id}' is a self-link")
        if (source, target) in seen_edges:
            raise ValueError(
                f"{level} dependency index has a duplicate relationship"
            )

        seen_edges.add((source, target))
        successors[source].add(target)
        predecessors[target].add(source)

    indegree = {
        node_id: len(predecessors[node_id])
        for node_id in node_ids
    }
    ready = [node_id for node_id in node_ids if indegree[node_id] == 0]
    heapify(ready)
    order = []

    while ready:
        node_id = heappop(ready)
        order.append(node_id)
        for target in sorted(successors[node_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heappush(ready, target)

    if len(order) != len(node_ids):
        raise ValueError(f"{level} dependency index contains a cycle")

    return DependencyIndex(
        level=level,
        predecessors=MappingProxyType(
            {
                node_id: tuple(sorted(predecessors[node_id]))
                for node_id in sorted(node_ids)
            }
        ),
        successors=MappingProxyType(
            {
                node_id: tuple(sorted(successors[node_id]))
                for node_id in sorted(node_ids)
            }
        ),
        topological_order=tuple(order),
    )