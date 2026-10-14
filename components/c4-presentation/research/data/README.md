# Data

Small files only (under a few MB). Large datasets, raw crawls and model weights stay
**out of git**. Store them on the team drive and record the location here:

| Dataset | Location | Owner | Notes |
|---|---|---|---|
| | | | |

## C4 procedure fixtures

`fixtures/linear/plan.json` follows the shared Plan v1 structure.
`fixtures/linear/enrichment.json` supplies C4-only procedure information.

The linear example is entirely fictional: request a demo token, then use it
to collect a demo pack. Fees are explicitly zero in this scenario. Zero must
not be used to represent an unknown real fee.

The example.org URLs are reserved example identifiers, not retrieved sources.
Plan v1 requires retrieved_at fields; their values in this fixture are
illustrative metadata. No official government material was retrieved.

The enrichment declares synthetic=true. Its evidence has
kind=synthetic_authored and retrieved_at=null. Preserve the disclaimer and
synthetic status whenever displaying this procedure.

## Ownership of input information

The Plan owns service identity, display order, agencies, fees, required
documents, service dependencies and shared provenance.

The enrichment owns detailed actions, required/supplementary content,
evidence passages, conditions, action prerequisites, branch groups,
parallel groups and structural completeness.

Content fact_ids reference facts already present in the Plan. A fact reference
or shared source URL does not establish that a passage supports a claim.
Source-passage evidence is supplied text with retrieval metadata; that label
does not mean the passage has been independently verified.

Plan/enrichment matching uses plan_id and base_generated_at. This guards
against mismatched generations, but is not a cryptographic content identity.

## Relationship semantics

Prerequisites point from required_action_id to dependent_action_id.

Display order does not create dependencies. Missing dependencies do not
create parallelism.

Condition references are conjunctive: every listed condition must apply.
The input layer preserves conditions; it does not evaluate a citizen's
eligibility or execute natural-language conditions.

Branch groups are explicit and stage-local:

- AND selects all applicable options.
- OR selects one or more applicable options.
- XOR selects exactly one applicable option.

An option without conditions is unconditionally applicable. Actual selection
and applicability evaluation occur later. No applicable option must be treated
as an unresolved or inapplicable situation, not silently invented guidance.

An action belongs to at most one option. Nested groups and conditional joins
are not represented in enrichment version 1.0. In particular, do not encode
"complete whichever alternative was selected" as an unconditional prerequisite
on one optional action.

Parallel groups explicitly permit concurrent execution. They require evidence,
compatible applicability and sufficiently complete dependency information.
Overlapping groups do not imply that their union is parallel.

## Completeness

Each structural category explicitly declares:

- complete: exhaustive within the declared procedure scope;
- partial: some information is supplied, but it is not exhaustive;
- unknown: coverage has not been established.

An empty complete collection is known zero within that scope.
An empty partial or unknown collection is not known zero.

Completeness is an input assertion, not proof of official accuracy.
The linear fixture is complete only for its authored fictional scenario.

## Loading

Use app.core.procedure_input.load_procedure_input for local files.
Use parse_procedure_input for two JSON strings.

Both perform typed and semantic validation before returning ProcedureInput.
Do not mutate accepted input and assume it remains validated; revalidate
changed input.

The existing shared rendering stub does not load these fixtures.