# Content preparation and action requirements

## Findings

The earlier duplication correction addressed display symptoms. It did not supply
prepared wording or action fact attribution. The service-level Plan fee/documents
were being treated as the only available facts for every action. Moving them to
the top avoided repeated charges but lost their practical relationship to steps.

The input contract already has a useful association: action → required content →
fact_ids. The official examples left these lists empty and placed the fee on a
shared scope paragraph instead. The frontend did not consume these associations.
This was both an example-authoring issue and a presentation implementation gap.

The existing preparation pipeline supports headings, explanations, summaries,
diagram labels and prerequisite explanations, with graph-bound storage and
immutable presentation snapshots. Missing reviewed artifacts caused source-copy
fallback and sentence truncation. The previous screen did not demonstrate LLM
preparation even though that infrastructure existed.

The company document pack was encoded as an AND branch as well as four incoming
prerequisites. All four documents are required, but this example has no route
choice. Its branch duplicated the join and produced misleading “options” labels.
The v3 example retains four prerequisites and removes the branch. The NIC example
retains two mutually exclusive routes; one route has two successive actions.
Neither a join nor absence of edges proves that tasks can proceed in parallel.

## Implemented boundary

1. The validated Plan/enrichment supplies facts, action content, conditions and
   dependencies. C4 never derives legal applicability from user familiarity.
2. Each action's own required content explicitly links the facts it uses or
   discusses. The exact procedure-wide disclaimer is excluded from action fact
   placement. No parent-service inheritance and no text matching infer a link.
3. Wording preparation receives the source graph, referenced facts and evidence.
   It prepares short titles, diagram labels, summaries and explanations. It cannot
   create or change the canonical actions, fees, documents or edges.
4. Validated wording is stored by graph/style/recipe/prompt/schema key. Actual
   provider preparation still uses generation plus semantic assessment and an
   explicit human-review operation before normal resolution.
5. New guidance resolves stored wording without a live model call. A presentation
   captures its wording artifact and digest. Restore and Inspector reads use that
   snapshot, not the newest registry. The policy database schema is unchanged.
6. The renderer uses prepared headings and explanations, places explicitly linked
   fees/documents at the relevant action, and keeps unallocated service facts in
   a separate service section. Source instructions and qualifications remain.

Fact links establish relevance, not a new fee charge at each occurrence. For
example, Form 1's base charge is associated with Form 1 preparation, but its text
explicitly says payment is outside that preparation action. A receipt is used at
submission; it is not presented as something needed before paying. The document
label therefore says “used or prepared”, with the instruction explaining its role.
Missing action links mean unknown, never free or no documents required.

## Demo preparation

`research/data/prepared-demo` contains nine assistant-authored mock bundles: three
official examples × three existing writing styles. These are stored preparation
outputs, not fabricated external-provider transcripts or expert-reviewed content.
Their origin is `demo_mock`; provider calls and review are absent. A mock artifact
cannot carry a human-review record. The workspace and Inspector identify it.

The independent dev application enables this registry only in simulation mode.
The ordinary resolver refuses mocks unless explicitly enabled. A real registry
bundle takes precedence; a pending or invalid real bundle does not silently fall
back to a mock. Participant mode does not enable the demo registry. Previously
captured mock presentations remain honestly identifiable when restored.

The versions contain concise, plain and expanded easy-language explanations.
These are the existing writing styles, not a newly learned detail-level arm.
The existing policy selects a scaffold; the existing context-to-style rule still
selects writing style. No new learning dimension or auxiliary reward is claimed.
All essential instructions remain visible even with concise prepared wording.

For real generation use the existing `app.wording_artifacts` CLI with `--plan`,
`--enrichment` and `--style`: plan the batches, generate using configured provider
credentials, inspect the artifact, then explicitly review it after checking the
sources. Save it in `C4_PREPARED_WORDING_DIR`. Fresh requests then use that reviewed
bundle before the mock. Never give a mock a fake reviewer or provider identity.

## Verification and limits

Regression tests cover action-only fee placement, receipt/form links, unchanged
source documents, missing references, the company join, NIC route membership,
three distinct wording versions, mock refusal outside demo resolution, graph
change invalidation, restart recovery and unchanged posterior on trace reads.

Numeric/reference checks do not prove semantic correctness. Mock wording remains
pending validation. The real provider's assessment is also not expert validation.
These examples remain bounded source snapshots, not complete citizenship or
current company incorporation services. The UI reference screenshots are design
examples; their prices, timings, confidence percentages and parallel claims are
not imported as government facts.

Future ingestion should explicitly model fact roles (input document, produced
document, payable fee, informational fee), payment timing, unknown amounts and
per-action completeness. The current shared Plan fee is mandatory and numeric;
therefore this change does not fabricate zeros or silently claim that a partial
fee covers the full procedure. Extending that upstream contract requires a
versioned migration and producer/consumer tests, not an LLM guessing the gaps.
