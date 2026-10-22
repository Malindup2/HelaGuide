# Step-first guidance, demo-only provisional wording and the NIC investigation

Branch `c4/final-guidance-ux` (the preserved `c4/scaffolding-dimensions` branch and commit `4bee944` were only read). The trained 3.1 Shared LinTS checkpoint, the 525-feature encoder, the synthetic evidence and every policy behaviour are unchanged.

## 1. What is genuine, what is a preview, what is unavailable
| Behaviour | Status |
|---|---|
| Guest standard guidance (strict, reviewed content only) | genuine standard baseline, never trains |
| Experienced and novice personalised views (strict, reviewed content only) | genuine trained-model decisions (checkpoint revision 5000), learning-eligible |
| The four Explanation x Disclosure views, NIC map, birth/company/NIC provisional wording | **research previews**, labelled, never train |
| Provisional official wording in any model-selected or standard journey | **unavailable by design** until you decide (section 5) |
| Phases for NIC and birth certificate copy | structurally unavailable (one stage, no verified grouping) |
| Fees attributed to one step in the fictional procedures | unavailable: no passage attributes a fee to one step |

## 2. Progressive Disclosure against the 3.1 contract
- **Achievable under the current D3 meaning, now implemented:** Concise primary text is short and complete; documents, desks, fees, conditions and "Before this" cues are small labelled cards (Where, Bring, Prepare, Submit, Keep, Pay, Charge); only the separate supplement sits behind a compact "More guidance" control; with Disclosure OFF the supplement is visible with no control. Concise + ON is exactly the compact layout you described (screenshots `after-4b`).
- **Not achievable without a compatibility decision:** a compact first view for **Detailed + ON**. Under the 3.1 contract D3 hides only the supplement and the Detailed primary text is always visible (that is what makes D2 and D3 independent). Hiding the Detailed primary would change what D3 means.
- **Minimum change if you want it:** (a) content-only, compatible: shorten Detailed and move its extra clarification into the supplement. This keeps the trained meaning but makes Detailed + ON look like Concise + ON, so D2 only shows when D3 is OFF; (b) semantic: add a separate always-visible essential core and let D3 ON hide the whole D2 explanation. That changes the meaning of the `disclosure_on` feature, so it needs a new action version (`c4-scaffolds-v3.2`), new content schema, new feature fingerprint and manifest, and a fresh policy plus re-run study. The current checkpoint would be refused by the manifest check and must not be reused.
- Recommendation: keep the current meaning. I did not change it.

## 3. Documents, fees, destinations
- The step is the information unit. Each step shows its own facts in one small grey card; a step with none shows no card.
- The old procedure-wide documents and charges panel is gone. A slim "For the whole service" strip shows only facts that no step or route can claim (for example the three LKR 0 stage fees of the fictional procedures). A fact shown at a step is not repeated in the strip.
- Route-scoped fact: the NIC LKR 500 issue fee belongs to the choice of routes (both route passages state it), so it is shown once at the choice, with "Can be paid through the certifying officer" and the postal-delivery note.
- Honest roles: Birth certificate copy shows Pay LKR 120 and Keep the payment receipt at the payment step. Company Form 1 shows a Charge (not Pay) because the source says payment is outside that step, with that qualification beside it.
- Source wording moved out of every step into Sources, "Source wording, step by step".

## 4. The NIC discrepancy, investigated
- **Procedure graph, unchanged:** 3 actions, 1 choice between two routes, 1 dependency (Grama Niladhari then Divisional Secretary), 1 stage, parallel coverage "unknown". The estate route has 1 step; the non-estate route has 2. Nothing was lost.
- **Why it looked like one step:** one top-level choice group (layer 1) contains all three actions. The Guided view and the compact route block showed only the two conditions and no steps until a route was chosen, and unchosen routes had no per-route step list. Fixed: before a choice, each route now lists its own numbered steps (estate: 1, non-estate: 2), in Overview and Guided. After a choice the steps appear as cards (screenshots `after-5a`, `after-5c`).
- **Where the earlier "branch visualisation" came from:** the older V1 interface offered a separate Branch map (branch groups only) and Dependency map. From V2 onward (V2, 3.0 and 3.1) there is one unified Map that is withheld when the source does not state parallel work ("parallel coverage unknown"); this was already so before. It is a feasibility rule, not missing presentation content.
- **Truthfulness:** a map of the NIC verified routes and the one dependency claims nothing about parallelism, so it is truthful. It is enabled only in the labelled provisional research preview (`relax_map`), where it draws exactly 3 nodes, one route frame and the single verified edge (tested, no invented dependency). In strict and model-selected journeys the rule is unchanged.

## 5. Demo-only provisional wording
- **What:** `research/data/guidance/provisional-v31/` for the three official procedures, built by `research/build_provisional_content.py` from the existing assistant-authored prepared demo drafts (styles concise, plain, extra_plain) and the official-source passages. Concise, Detailed, supplement, recap lines, short headings, destinations, documents, the NIC route fee, birth-copy Pay/Keep, the company Form 1 charge and two company phases are all derived or bound to exact source spans.
- **Checks (authoritative gates, all passed for all three files):** claim coverage and fact ownership (the 3.1 validator), Detailed keeps everything Concise covers, supplement separate, every number and mid-sentence name must occur in the source, and a payment/free/guarantee contradiction check. Unit tests show the checks reject an invented amount, an invented name, a payment at a step the source says is outside, and a free-of-charge claim.
- **Labels:** every file is `draft`, `origin demo_mock`, with no review record; the API reports `content_state: provisional_demo` and "No human review"; the card shows a provisional notice. Nobody's approval is recorded or implied.
- **Isolation:** enabled only by `C4_DEMO_PROVISIONAL_CONTENT=true` and an explicit preview request (`allow_provisional`); never published to the strict registry; standard guidance and LinTS-selected journeys keep the reviewed-only feasible set (4 configurations for each official procedure, verified).
- **Compatibility impact before any integration into LinTS journeys:** provisional wording for NIC alone makes 48 of 96 configurations feasible (company 96; the map needs the relaxed rule). Feature vectors, the manifest and the checkpoint are unaffected, but the policy would be selecting among official-procedure configurations it never saw during training, which also changes the meaning of the earlier synthetic evaluation for those procedures. Needs your approval and a re-evaluation; not done.

## 6. Verification
- Backend 599 passed (24 skipped); frontend 294 passed; typecheck, lint and production build clean.
- Live against the running trained app (`docs/C4-STEP-FIRST-LIVE.json`): guest standard; compact personalised (experienced: overview, concise, inline, phases); rich personalised (novice: guided, detailed, disclosure On, map, recap, phases); four D2 x D3 combinations (primary 84 characters Concise, 255 Detailed; supplement visible when Off, hidden when On; step cards identical in all four); feedback: original view 5000 -> 5001, manual view and guest do not train, parent not ratable after adjusting.
- Screenshots: `docs/screenshots-step-first/` (`before-*` from the earlier build, `after-1` to `after-7`).

## 7. Still open
- Detailed + ON is not compact (section 2).
- Provisional wording and the NIC map are previews only until you approve integration and re-evaluation.
- Fee attribution to a single step for the fictional procedures, and documents produced by one step and used later, remain unavailable.
- Screenshots were taken at an 800 px pane; narrower widths were checked by DOM measurement earlier.
