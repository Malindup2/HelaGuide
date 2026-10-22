# Which fact belongs to which step (content 3.1): audit, changes and verification

Path of every value: source Plan facts and passages -> reviewed 3.1 content (`attachments`, `destination`) -> `compose31` -> `/workspace/guidance` response (`document.actions[].facts`, `.destination`, `document.requirements`) -> Guidance Card ("At this step" card per step, whole-service panel at the top).

## 1. Rule applied
A fact reaches a step only through a reviewed `attachment` with `scope: action`. The validator requires that (a) a claim binds the fact to an exact span of that action's own source passage, (b) the Plan assigns the fact to the stage the action belongs to, and (c) a named review check exists. A passage that merely mentions a fact is not enough, and a sentence that lists several fees is not attribution. Stage and service facts stay in the whole-service panel and are never shown inside a step. A fee is never attached to a step, so no fee can appear twice or imply a repeated payment.

## 2. Procedure-by-procedure attribution (what a step receives today)
| Procedure | Step | Documents shown at the step | Where | Fees at the step | Source basis |
|---|---|---|---|---|---|
| Practice (fictional) | Register | none | Fictional Registration Desk | none | passage names the desk |
| | Obtain the copy | none | Fictional Records Desk | none | passage names the desk |
| | Prepare form / Prepare copy | none | none | none | no desk or document stated for these steps in their own stage |
| | Submit | completed application form; supporting copy | Fictional Submission Desk | none | passage: "Include both the fictional completed form and supporting copy"; both documents belong to the submission stage |
| Parallel (fictional) | Submit | completed application form; supporting copy | none stated | none | same pattern |
| Linear (fictional) | Collect the pack | demo token | none stated | none | passage names the token; it belongs to the pack stage |
| Conditional (fictional) | Counter collection | registration reference | Fictional counter | none | passage names both |
| | Locker collection | registration reference | Fictional locker | none | passage names both |
| | Register | none | none | none | one sentence lists several fees; not attributable to this step |
| Birth certificate copy (official) | all | none | none | none | source fallback; needs a separate source-fidelity review |
| NIC amendment (official) | all | none | none | none | source fallback |
| Private company (official) | all | none | none | none | source fallback |

Whole-service panel (all procedures): every document and every stage fee, exactly once each, labelled with its stage when there is more than one. Verified by `tests/test_action_fact_attribution.py` (28 tests).

## 3. What is source-supported versus unavailable
| Item | Status |
|---|---|
| Documents needed at a step (fictional procedures above) | supported and shown |
| Desk or place per step (practice, conditional) | supported and shown |
| Agency per step | supported by the Plan, but all fictional procedures have a single agency, so it is shown once in the header; a per-step Agency tile appears only when a procedure has several agencies |
| Fees at a step | **unavailable**: no passage attributes a fee to one step, and the Plan states fees per stage |
| Fee qualifications | **none exist** in any Plan fact; nothing is shown. If one is added, it travels with the fee |
| Documents produced by one step and used later | **unavailable in the current contract**: the stage-ownership rule ties a document to the stage that needs it (for example the form belongs to the submission stage, so it cannot be attached to "Prepare form"). Proposal: add an attachment `role` (requires, produces, retains) and let a reviewer attest a producing step explicitly |
| Any action-level fact for the three official procedures | **unavailable by design** until a named source-fidelity review |
| Route-scoped fees or documents | supported by the contract, not needed by any current fictional content |

## 4. Before and after (real responses, practice procedure, submit step)
Before (previous commit): heading, primary text, and nothing step-specific; documents and fees only in the whole-service panel; no desk.
After: the same heading and primary text, followed by
```
AT THIS STEP
WHERE  Fictional Submission Desk
BRING  Fictional completed application form   Fictional supporting copy
```
The Register step shows only `WHERE Fictional Registration Desk`. The panel still lists the two documents and the three LKR 0 stage fees once each.
Screenshots from the running trained application (`docs/screenshots-functional-review/`): `compact-experienced-submit-step.jpg` (Overview, Concise, supplement behind More, inline cues, phases), `rich-novice-submit-step.jpg` and `rich-novice-register-step.jpg` (Guided, Detailed, map, recap, phases).

## 5. Live verification (trained checkpoint, `docs/C4-FUNCTIONAL-REVIEW-LIVE.json`)
- Guest: standard (overview, concise, nothing else), no support control, no feedback control.
- Compact personalised candidate (experienced citizen): overview, concise, Off, inline, no recap, phases on; feedback eligible.
- Rich personalised (novice): guided, detailed, On, map, recap, phases; feedback eligible.
- Four D2 x D3 combinations on the practice procedure (previews, labelled as such):
  | | Register primary text | Supplement | Step card (Submit) |
  |---|---|---|---|
  | Concise + Off | 84 characters | shown, no control | desk + 2 documents |
  | Concise + On | same 84 characters | behind More | same |
  | Detailed + Off | 218 characters | shown, no control | same |
  | Detailed + On | same 218 characters | behind More | same |
  The step card, conditions and source wording are identical in all four; only the supplement moves.
- Feedback: rating the original model-selected view moved the posterior revision 5000 -> 5001 (reward 1); a manual adjustment's rating did not update the policy; the original view can no longer be rated after it was adjusted (409); a guest rating is refused (403); revision stayed 5001.

## 6. Compatibility
Prepared-content changes: four fictional 3.1 files gained claims, attachments and destinations, so their content fingerprints and review digests changed. Unchanged and tested: feasible counts (96, 96, 96, 48), measurements and the 525-feature vectors (they come from the source graph, not the 3.1 wording), the policy manifest, and loading of the trained checkpoint (`seed-23-x0.25-525-n5000.npz`, revision 5000). Stored decisions keep the content fingerprint they were made under. No breaking compatibility change occurred.

## 7. Remaining functional and visual issues
- A step with no facts, desk or document shows no card (by design); Prepare form / Prepare copy therefore show only their instruction.
- Documents appear both at their step and in the whole-service panel (intended: the panel answers "what do I bring overall"); fees appear only in the panel.
- The Register primary text of the rich view is long because Detailed was selected; Concise stays at one sentence.
- Browser screenshot images were captured with a narrow pane and crop the right edge; DOM measurements (no horizontal overflow at 320, 390, 768, 1280) were used for width checks.
- "Source passages" and "What the source says" no longer appear together in one step.
