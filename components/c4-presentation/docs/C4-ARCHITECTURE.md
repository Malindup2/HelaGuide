# C4 architecture (current, verified against the code)

C4 is the adaptive presentation component of HelaGuide. It studies which of six presentation scaffolds helps which citizen with which procedure, and it personalises the choice with a Shared Gaussian Linear Thompson Sampling (LinTS) bandit trained on explicit "Fits / Does not fit" feedback. Everything below is a research prototype. Synthetic training results are not evidence about real citizens.

## 1. The six scaffolding dimensions (action semantics `c4-scaffolds-v3.1`)
| | Values | Meaning in 3.1 |
|---|---|---|
| D1 Navigation | Overview, Guided | all steps at once, or one step with Back/Next |
| D2 Explanation | Concise, Detailed | the always-visible primary explanation: short and complete, or fuller with reviewed clarification |
| D3 Disclosure | Off, On | shows or hides only the separate reviewed supplement behind More/Less |
| D4 Relationships | None, Inline, Map | prerequisites in words only, inline cues, or a compact map |
| D5 Recap | Off, On | reminders of earlier steps the citizen actually viewed; never "done" |
| D6 Segmentation | Off, On | reviewed phase groupings; phase membership never implies order |
96 nominal configurations. Hard constraints (accessibility, locks) and structural feasibility remove configurations; the policy only ever sees the feasible set.

## 2. Data flow
```
 official/fictional Plan + enrichment  ->  ProcedureSource (graph, verified relationships)       service/app/core, app/guidance/sources.py
             |                                      |
             |                          measurements (7 structural values + completeness)       app/v2/measurements.py
             v                                      |
 prepared content 3.1 (reviewed)  ->  ContentRegistry31 (draft -> review -> publish)            app/guidance/content_v31.py, v31_pipeline.py
             |                                      |
             +-------------> feasibility (evaluate31, hard constraints, feasibility fingerprint)
                                                    |
 citizen context (familiarity, confidence,          v
 soft preferences, accessibility)  ---->  encoder (525 features) -> Shared Gaussian LinTS -> one configuration     app/guidance/features.py, policy.py
                                                    |
                                      compose31 -> render plan -> GuidanceAPI frozen journey                       frontend_runtime.py
                                                    |
                          React Guidance Card  <----+----> events, ratings -> posterior update (once, attributed)  demo-frontend/src/citizen
                                                    |
                                      Research Inspector (stored decision record + recorded events)
```
Guest requests and personalisation-OFF requests receive complete standard guidance and never train. Previews, manual "Adjusted by you" views and comparison views never train.

## 3. Prepared content (`c4-guidance-content-3.1`)
Per action: heading, exact `source_wording`, short `concise`, fuller `detailed`, an optional separate `supplement` (role, adds-information), optional recap line, actor, destination and scoped fact attachments; per procedure: reviewed phases. Validators prove claim coverage (every required source passage is bound to an always-visible text), that Detailed keeps everything Concise covers, and that a supplement holds no required claim. They prove assignment, not semantic entailment; a named review is still needed. Official procedures have no 3.1 content and stay on source fallback.

## 4. Context and measurements
Context: per-procedure familiarity and navigation confidence (ratings 1 to 5 or unknown), soft preferences per dimension, hard accessibility constraints. Procedure: step count, information volume, branch count, condition count, dependency count, dependency depth, parallel-group count, each with a completeness state. Identity and history are not features (history scoring is deferred to PP2).

## 5. Encoder and policy
`features.encode` builds a bounded 525-feature vector (variants 416, 451, 516 are prefixes used as ablations): context blocks crossed with eight action indicators, three-way terms, and nine scaffold pairs. Shared Gaussian LinTS (`policy.Model`, numerical kernel in `core/policy.py`) keeps one precision matrix and response vector. A decision samples one posterior draw, scores all feasible candidates and picks the maximum sampled score. Reward is 1 for Fits and 0 for Does not fit; eligible feedback updates the posterior once.
Versions: the 3.1 manifest differs from 3.0 in `action`, `features`, `feature_fingerprint` and `content`; `PolicyStore` and `Model.restore` refuse any mismatch, so a 3.0 posterior can never load into 3.1 and vice versa.

## 6. Synthetic training and evaluation
`experiment31.py` trains from a hypothetical simulator (`synthetic31.py`) in which each scaffold has a need and both under-support and over-support lower the chance of a good fit. Study procedures (`procedures31.py`) add varied structure. Training, development and final test cases are separate. Every run writes a trace, checkpoints and an update chain that `replay` re-derives exactly. See `PP1-V31-SIMULATOR-FINDINGS.md` and `PP1-V31-RESULTS.md`.

## 7. Feedback and posterior update
`ratings` endpoint: the view must be the original unadjusted personalised view, its display acknowledged, one rating per view. `PolicyStore.update` runs inside the same transaction as the receipt, so a rating updates the policy exactly once or not at all.

## 8. Research Inspector
Part A is a stored record of the completed request (effective context, measurements, feasibility counts with reasons, versions, feasibility fingerprint, sampled scores and features of the real decision). Part B is the recorded client events. It shows no live pipeline and no causal explanation of why a configuration was sampled.

## 9. Persistence
| Store | Location | Contents |
|---|---|---|
| Workspace | `service/.local/v2/workspace/...` | demo identities, profiles, settings revisions |
| Content registry | `service/.local/prepared-content/.../` (3.1: a `v31` directory) | `artifacts`, `publications` (3.0 and 3.1 use different registry schemas) |
| Journey store | `<registry>/frontend-api/` | `journeys`, `operations`, `settings` |
| Policy | `service/.local/pp1-learning/...` | `pp1_manifest`, `posterior`, `updates` |
| Study output | `service/.local/pp1-learning/v31-study-*` | traces, checkpoints (`.npz`), reports, plots |

## 10. Folder structure (active)
```
components/c4-presentation/
  service/app/guidance/   content, content_v31, feasibility, composition, v31_pipeline, flavours, features, policy,
                          frontend_runtime, frontend_api, frontend_contracts, frontend_presentation, synthetic31, procedures31, experiment31
  service/app/v2, core    identity, measurements, registration, procedure graph and input (shared foundations)
  demo-frontend/src/citizen   the one citizen interface (Workspace, GuidanceCard, Research)
  research/               exports, verification scripts, fictional content, study fixtures
  docs/                   specifications, results, this document
```
Superseded V1/V2/3.0 code is listed, with its remaining dependencies, in `C4-CLEANUP-AUDIT.md`. Nothing was deleted.

## 11. Run and test
See `C4-RUN-AND-REPRODUCE.md`.

## 12. Versioning and limitations
Content 3.1, actions v3.1, features 1.1-525, registry 3.1 and the policy manifest move together. The 3.0 system, trained 3.0 posterior and its results are preserved unchanged. Limitations: synthetic simulator only; fictional study procedures with templated wording; official procedures are source-fallback; fictional 3.1 content has internal AI-assisted review only; PP2 history-aware scoring is not implemented.
