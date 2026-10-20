# M6: bounded official-source examples

The development server now appends three local source snapshots to the three
existing synthetic scenarios. This is a manual C4 input adapter, not a C2
scraper integration or an agency transaction service. No network request is
made at startup. Failures in any registered input stop startup visibly.

## Scope and structural interpretation

| Folder | Bounded task | Representation | Excluded |
| --- | --- | --- | --- |
| `birth_copy` | Counter submission for one copy with known registration details | Receipt payment precedes submission | Search, postal and online routes |
| `nic_amendment` | Select the certifying route for an amendment | XOR estate/non-estate; GN certification precedes DS countersignature in the latter option | Full document checklist, adjudication and issuance |
| `company_pack` | Manual preparation after name approval, domestic non-BOI company | Four required document sets precede format check; no alternative branch | Current eROC workflow, foreign/BOI cases, incorporation and subsequent compliance |

The company example concerns incorporation of a private company, not registration
of a sole trader's business name. It deliberately models the older government's
manual preparation description. It must not be presented as a complete current
business-registration guide. The DRC site carries newer beneficial-ownership
notices. They are outside this snapshot, not silently treated as completed.

All action and relationship completeness flags describe only the explicitly
bounded task. They do not certify that the entire real-world procedure is
complete. Parallel coverage is **unknown** for every example: a checklist is not
evidence of independent preparation. The unchanged feasibility rules therefore
allow supported branch/dependency maps, but exclude guided mode and parallel
maps. Unknown parallel count remains null, not a confirmed zero. Use the
synthetic parallel fixture to demonstrate explicit parallel structure.

## Sources and review status

Retrieved with the web tool on 2026-10-19; recorded UTC retrieval time is in
each input. Evidence contains short verbatim anchors; content is a manually
authored paraphrase. The full source pages are not redistributed.

- [RGD copy requests](https://www.rgd.gov.lk/web/index.php/en/services/civil-registration/birth/obtain-certified-copies-translations): `birth_request` maps to the receipt-backed counter request, its charge and documents.
- [DRP NIC services](https://drp.gov.lk/en/normal.php): use the **Amending National Identity card** section for `nic_routes`, its estate/non-estate distinction, countersignature and fees. Do not substitute the first-time school-applicant table.
- [Government Trade Portal](https://srilankatradeportal.gov.lk/index.php?id=40&r=searchProcedure/view1): manual required-document list and format-check step support `company_docs` and prerequisites; required documents are not alternative routes.
- [DRC fee schedule](https://drc.gov.lk/en/?p=3968): `company_fee` and fee fact provenance. VAT is excluded; no historical percentage is encoded as current.

No human expert or agency has validated these interpretations. The engine's
existing `supplied_sources_unverified` status remains truthful. All text is
required and protected, including task boundaries and fee qualifiers. No
official content receives automatic supplementary-disclosure approval.

## Fees

The mandatory shared fee field cannot express an unknown amount. Each example
therefore uses one documented fee for one service, never a fabricated zero.
NIC records only its base issue fee; company records only the base Form 1 fee.
The protected scope card explicitly explains excluded charges. A service fee
repeated beside actions belongs to the same service; it is not a charge per
action. Do not sum action cards as a transaction total.

## Compatibility and maintenance

`load_demo_procedures()` and factory-created test apps retain the synthetic
catalogue by default. The environment-created server opts into the mixed
catalogue for either PostgreSQL or SQLite. Tests can opt in with
`create_app(include_official_examples=True)`; explicit `graphs` take precedence.

Existing synthetic graphs, fingerprints, prior, feature schema, policy state,
profiles and histories are unchanged. There is no database migration or reset.
The restart test opens an existing saved run with the larger catalogue and
checks its original presentation and policy identity survive.

To revise an example, verify its official sources, edit the paired `plan.json`
and `enrichment.json` through the existing input contract, and version both the
plan ID; update retrieval timestamps only when sources are actually retrieved again. Reassess the exact task scope, evidence and completeness;
never infer new dependencies or parallelism from display order. Add structural
and rendering tests. A changed graph gets a new fingerprint; saved presentations
retain their original embedded graph and attribution. Run the backend suite
with live generation disabled and the frontend tests/build/lint before review.

## Manual check

Start backend/frontend normally; no new environment variables are required.
Expect six catalogue entries. Select each official-source snapshot, request
guidance, and check the scope, fee qualification and source information remain
visible. Personalization still selects only a feasible presentation; it does
not select NIC eligibility or a business transaction. With the LLM disabled,
simulation mode uses the bundled, explicitly labelled prepared demo wording when a matching artifact exists; otherwise source-preserving fallback is expected. Existing synthetic examples, saved
profiles, Inspector and presentation controls should continue to work.


## Action preparation correction (v3 inputs)

Each action links to applicable fee/document facts through its required content's
`fact_ids`. The UI renders these beside that action. Unassigned service facts
remain in the service summary. Shared scope notices do not assign requirements
to every action. A repeated fact reference represents the same charge, not a new
charge. Missing links mean unspecified, never free or no documents required.

Company preparation has four prerequisites feeding the format check, without an
alternative branch. NIC retains two applicant routes, with two consecutive steps
inside the non-estate route. Neither display order nor absent edges establishes
parallel work.

Nine bundled artifacts provide titles, explanations and diagram labels for three
examples in three wording styles. They are assistant-authored `demo_mock`
artifacts, not live provider output or expert-reviewed content. They are enabled
only by the environment-created simulation server. Normal prepared artifacts
retain their review gate. Source facts and required instructions remain visible.

Saved presentations retain their embedded graph and wording; request fresh
guidance to see v3. These remain bounded examples, not complete citizenship or
eROC workflows. See [content architecture](CONTENT-PREPARATION-ARCHITECTURE.md)
for the findings, preparation lifecycle, provenance and contract limitations.
