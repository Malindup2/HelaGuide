# C4 Research and UX Semantics Specification

**Status:** approved as a specification (revision 2, with three implementation safeguards). This approval covers the documentation only. No frontend or backend implementation, model training, database change, content migration, commit or push is authorised by this document.

**Scope:** `components/c4-presentation/`, branch `c4/scaffolding-dimensions`. The V2 system, its databases and the existing Guidance Card checkpoint are preserved unchanged.

## 0. How to read this document

Each statement carries one of four labels:
- **[Implemented]** exists in the code today.
- **[Proposed]** a change I recommend.
- **[Changes research assumptions]** alters what an action or measurement means, so earlier results and learned state stop being comparable.
- **[Unsupported today]** cannot be supported by the verified procedure data as it stands.

Based on a read-only inspection of `service/app/v2/*`, the in-memory registry of all seven procedures, the prepared-demo wording, and the current frontend.

## 1. Research framing and weaknesses I recommend you address

### 1.1 The framing that holds up
- C4 studies which presentation mechanism helps which citizen in which procedure. The policy sees user context (per-procedure familiarity, confidence, soft preferences, accessibility) and seven structural measurements (step count, information volume, branch count, condition count, dependency count, dependency depth, parallel-group count), each with a completeness state. **[Implemented]**
- **Structural feasibility** (rule-based: is a scaffold meaningful, source-supported, accessible and implementable here?) is separate from **contextual selection** (Shared Gaussian LinTS over the feasible set). **[Implemented]** in `catalogue.evaluate` and `Runtime.create`.
- No frontend rule may choose a configuration from a profile label. No claim is made that the policy has learned an effective mapping before an evaluation shows it.

### 1.2 Weaknesses (updated)
1. **Numbering versus honest ordering.** Backend order is browsing order. Step numbers are only truthful where verified prerequisites support them (§3.1).
2. **Feasibility is not benefit.** Feasibility asks "is this meaningful and safe to show", never "will it help". Whether it helps is the experiment's question. Disclosure and Segmentation criteria therefore test *meaning and safety*, not predicted benefit (§3.3, §3.6).
3. **Mentions are not attribution.** A sentence that names several fees does not make each fee payable at that step (§2.2).
4. **Rendering is not reading.** A step in the document is not a step the citizen visited (§3.5).
5. **Feedback bias.** Learning only from positive answers would inflate every configuration. Negative answers must train (§8.3). Residual biases (who chooses to rate, what was visible when) are named and logged.
6. **The simulator is hand-built.** `v2/simulation.py:probability` is an authored curve. In the recorded run the fixed minimal baseline (about 0.66) beat every learned encoder (about 0.36 to 0.39). That negative result stays visible (§10).
7. **"Return to Overview" inside Guided is a configuration change** and must be recorded as such, or be a non-configuration peek (§8.2).
8. **Reducing feasible sets.** Requiring recorded review shrinks the adaptive space for the official procedures until content is reviewed. That is a research finding about content readiness, not a defect to hide (§6.4).

## 2. What is stored today (verified)

### 2.1 Per procedure [Implemented]
Per action: `title`, `concise`, `expanded` (equal to `concise` unless an overlay variant exists), `recap`, `fact_ids`, `conditions` (text), `branch`/`option`, `optional[]`, `unreviewed_supplement[]`, `actor` (practice only), `service_agency`, `wording_status`. Per document: `stages`, `stage_edges`, `edges`, `branches`, `parallel`, `joins`, `parallel_areas`, `facts`, `completeness`, `capabilities`, `sources`, `provenance`.

| Procedure | Source | Stages | Actions | Wording origin | Reviewed detailed text |
|---|---|---|---|---|---|
| Birth certificate copy | official snapshot | 1 | 2 | prepared-demo headings, source-preserving text | none |
| NIC amendment | official snapshot | 1 | 3 (XOR routes) | prepared-demo headings | none |
| Private company documents | official snapshot | 1 | 5 (4 preparations, 1 submission) | prepared-demo headings | none |
| Synthetic linear | fiction | 2 | 2 | source excerpt | none |
| Synthetic conditional | fiction | 2 | 3 (XOR) | source excerpt, titles cut at 115 characters | none |
| Synthetic parallel | fiction | 3 | 4 | source excerpt | none |
| Practice | fiction | 3 | 5 (XOR, join) | reviewed overlay (author-reviewed, not an official-source review) | yes |

### 2.2 Fee scope: what the data says and what the rule must be
**Root cause found.** An action's `fact_ids` are the facts referenced by its required content. The practice and synthetic-parallel registration actions contain one sentence naming three stage fees, so three fee facts attach to the first action. The Plan scopes each fee to a **stage** (`stage.fee_fact_id`).

**Rule [Proposed]: attribution must be explicit, never derived.**
- A fee is **action-level** only when the prepared contract records `scope: action` for that action (a reviewed attachment).
- **Route-level:** `scope: route`, with the condition IDs under which it applies.
- **Stage-level:** `scope: stage`; shown as a charge of that service or phase, not as a payment at any one step.
- **Service-level:** `scope: service`; shown once with the procedure.
- Belonging to a stage does **not** convert a stage fee into an action fee. A sentence that mentions a fee is a *mention*.
- Fees are never summed. Source qualifications (for example "excludes ATM and online payment") travel with the fee.

**Two defects, separated.**
- *Frontend (mine):* the Guidance Card lists every `fact_id` as that action's charge. Under the rule, until contracts carry scope, the card shows fees in a procedure-level "Charges recorded for this procedure" row, labelled by stage, and does **not** present them as per-step payments.
- *Content:* the synthetic text is rewritten (§6.3) so that fee facts have explicit scopes and no sentence implies a payment at the wrong step.

**What this means for the official procedures.** Birth certificate copy has one stage fee (LKR 120) whose source text sits in the payment action; it is shown with the procedure now and at the Pay step only after the prepared contract records `scope: action` through a source-fidelity review. NIC has one stage fee (LKR 500) reached by both routes: shown once at the route choice as "applies to both routes", never per route and never summed.

## 3. The six dimensions: exact meanings

Notation: `(D1, D2, D3, D4, D5, D6)`. All 96 combinations remain theoretical; feasibility removes combinations.

### 3.1 D1 Navigation: Overview / Guided
**Purpose:** find the relevant step and follow a longer procedure.

**Step numbers [Proposed].** Compute *layers* from verified prerequisite edges (`edges`, joins). Layer 1 holds actions with no prerequisite; layer n+1 holds actions whose latest prerequisite is in layer n.
- A one-action layer is "Step n".
- A multi-action layer is "Step n: all of these" with lettered items; the Plan states no order among them, so none is shown.
- Numbering is switched off when `completeness.prerequisites` is not `complete`.
- Alternative routes are never numbered as consecutive steps. A route group is a choice; steps are numbered **within** the chosen route.
- Phase membership (D6) never changes step numbers or implies an order.

**Overview:** all relevant steps together, titled and numbered as above, with essential facts. A route group shows the choice first (conditions in the source's words), then each route's steps; after a choice, the other route collapses to a "Change route" line.

**Guided:** one step with "Step 2 of 4" along the active route, Back, Next, a compact step list, and an obvious **Change route** when the active step is in a route group. Parallel siblings are "Step 1: item a of 4", not a sequence. A read-only **peek at overview** does not change the configuration (§8.2).

**Feasibility [Implemented]:** more than one action; removed when structure is incomplete; removed by the `no_guided` accessibility flag.

### 3.2 D2 Explanation depth: Concise / Detailed
The step title says *what* the action is; it is not the explanation.
- **Concise:** short, complete, actionable; names, where the source supports it, the actor, destination and essential requirements.
- **Detailed:** reviewed, source-supported clarification; must add meaning (`validate_overlay` already requires `concise != expanded`). **[Implemented]**
- **Rename [Proposed]:** `expanded` becomes `detailed`.
- **Feasibility [Implemented rule]:** Detailed requires reviewed detailed text for every action. Today only the practice procedure qualifies. **[Unsupported today]** for the rest.

### 3.3 D3 Progressive disclosure: OFF / ON [Changes research assumptions]
**Old meaning:** whether optional supplementary blocks start collapsed. **New meaning:** whether the selected explanation (Concise or Detailed) is collapsed behind a step-level control.

- **OFF:** the explanation chosen by D2 is shown normally. No show/hide control is added to represent OFF.
- **ON:** each step first shows its complete title and its **essential layer**; the remainder of the prepared explanation sits behind a small natural control ("More" / "Less").

| | OFF | ON |
|---|---|---|
| **Concise** | concise text visible | essential layer visible; concise remainder behind a control |
| **Detailed** | detailed text visible | essential layer visible; detailed remainder behind a control |

**Content model [Proposed].** Per action: `essential` (the minimum actionable instruction, with conditions), `concise_remainder`, and `detailed_remainder`. The essential layer always also shows the step's conditions, documents, correctly scoped fees and destination from the structured fields. Nothing required lives in a remainder.

**Meaningfulness criterion (evidence-based, no count threshold) [Proposed].** A disclosable remainder is feasible for a step when **all** of these hold:
1. **Coverage proof (automatic).** Every `required_content_id`, condition ID and attached fact ID of the step is expressed in the essential layer or its structured fields. The remainder contains no required claim. A failure makes disclosure infeasible for that step. Enforced by comparing the content graph's required IDs with the layer assignment recorded in the prepared contract.
2. **Adds information (reviewed).** The reviewer records `remainder_role` (`clarification`, `qualification` or `background`) with the evidence IDs it draws on, and attests it is non-duplicative of the essential layer.
3. **Source-grounded (reviewed).** The remainder carries evidence IDs and passes the same source-fidelity review as other wording.

At procedure level, D3 ON is feasible when **at least one step** satisfies 1 to 3. A single information-heavy action is enough. Steps without a remainder render plainly under ON, and the Support control says which steps can be disclosed. Because Concise and Detailed have different remainders, feasibility is evaluated **per (D2, D3) pair**; the capability schema needs combination constraints. The `no_collapsed` accessibility flag forces D3 OFF.

*Why not a count threshold:* a count says nothing about whether collapsing is safe or meaningful. The coverage proof is the safety condition; the reviewed role is the meaning condition. Whether disclosure *helps* is not a feasibility question.

**Supplementary information [your decision]:** stays separate from D3, useful only when reviewed and non-duplicative. It is an always-available "More information" item that never doubles the explanation; unreviewed supplements stay visible as labelled source notes **[Implemented]**.

**Events:** explanation open/close with action and view IDs; activity, never reward (§8).

### 3.4 D4 Relationship presentation: None / Inline / Map
- **None:** relationships are not drawn, but every necessary prerequisite, condition, route choice and parallel requirement is stated in natural language ("Do this first", "Only if", "These can be done in any order"). None never means deleting necessary relationships.
- **Inline:** short cues next to the step: **Before this**, **After**, **Also required**, **Can be done alongside**. Cues come only from verified edges, joins and parallel groups, never inferred.
- **Map:** compact numbered flowchart: small nodes, short labels (the prepared heading), thin connectors, accurate branches and joins; an embedded view, an expand icon, a spacious centred enlarged view, hide/show, and a text alternative. Numbers follow §3.1 layers. No giant text or clipped sentences.
- **Feasibility [Implemented]:** Map is removed when structure is incomplete or `parallel_groups` is not complete; all three official procedures declare parallel coverage unknown, so Map is infeasible for them. Inline stays available whenever relations exist. `no_map` removes Map.
- **Events:** map show/hide/expand/collapse are activity; they do not change the configuration or re-run selection.

### 3.5 D5 Earlier-step recap: OFF / ON
A **memory** aid, not a link list. OFF means no adaptive recap.

**Four distinct states [Proposed].**

| State | Meaning | Recorded? |
|---|---|---|
| **Rendered** | the step exists in the DOM | no (internal) |
| **Visible** | the essential layer was on screen (at least half in view) continuously for a declared dwell time | yes, `step_visible`, with the threshold and dwell in the event |
| **Visited** | the citizen did something explicit: navigated to it, opened it, or made it the active Guided step | yes, `navigate` / `step_open` |
| **Details opened** | the citizen opened the step's disclosure or "More information" | yes, `explanation_open` |

The dwell time is a declared, versioned instrumentation parameter stored with each event; it is not a reward and not a claim of reading. Rendering alone never counts.

**Recap rule.** A step enters the recap when it was **visited**, or **visible** by the definition above. Details-opened is a separate fact; the recap shows only the prepared `recap` line, so it never claims the citizen read details. "Earlier" means a lower layer in the verified order; routes not chosen are excluded.
- **Overview + Recap:** an "Earlier steps" reminder for steps viewed but now off-screen or collapsed. It does not appear when empty.
- **Guided + Recap:** a compact reminder of earlier viewed steps above the active step.
- Wording: "Viewed, not confirmed as done." It never shows links as its content; an optional "Go to" affordance may exist but is not the recap.
- **Content requirement:** a prepared, reviewed `recap` line per step, about 140 characters, written to remind (several current values are labels or copied sentences).
- **Feasibility:** more than one action and a reviewed recap line for every action.

### 3.6 D6 Procedural segmentation: OFF / ON [Changes research assumptions]
Replaces Preparation Summary. Groups actions into meaningful phases (for example Register, Prepare required items, Submit).

- **OFF:** no adaptive grouping. Mandatory routes and prerequisites still appear correctly.
- **ON, Overview:** phase headings organise the steps. **ON, Guided:** compact orientation beside the active step ("Prepare", and "2 of 3" **only if** phase order is verified).
- **Differs from other dimensions:** D1 chooses how many steps are visible at once; D4 shows relationships between steps; D6 chooses how steps are grouped. Phase membership creates **no** action-order dependency and never changes step numbers.

**Meaningfulness assessment (source-grounded, no rigid count) [Proposed].** A grouping is feasible when:
1. **Source of the grouping.** Verified Plan stages, or a reviewed phase overlay. A stage is a *candidate*, not a phase: its name is a service name, and a stage existing proves nothing.
2. **Recorded basis.** The reviewer records why actions belong together: `basis` ∈ {purpose, actor, location, timing, stage} with evidence IDs, plus a one-line `why_grouped`.
3. **Reviewed citizen label** per phase, written for readers and not identical to an action heading or a service name.
4. **"Adds orientation" attestation.** The reviewer records that the grouping clarifies the procedure beyond the step list. A grouping that gives each step its own phase and repeats its heading fails this attestation. This replaces a minimum-count rule.
5. **Integrity (automatic).** Every action belongs to exactly one phase; no phase is empty; at least two groups exist (one group is not a grouping); and a branch group is not silently split across phases without a reviewed note.
6. **Order honesty.** Phases are shown in a sequence, or numbered, only when verified `stage_edges` or a reviewed overlay states that order **and** no verified action edge points backwards across phases. Otherwise phases appear as unordered labelled groups.
7. A branch by itself does not establish segmentation.

## 4. Composition model

### 4.1 One layout, composed from decisions
The renderer derives layout decisions from the configuration and composes **one** interface. Six large independent sections are not allowed.

| Decision | Source |
|---|---|
| Container arrangement | D1 |
| Grouping | D6 |
| Step content | D2 chooses the text; D3 chooses visible versus behind a control |
| Cues and diagram | D4 |
| Memory aid | D5, only when something was viewed |

### 4.2 Composition rules
1. Essential facts are never inside a disclosure: title, conditions, route choice, the essential layer, documents, and correctly scoped fees.
2. A route group always renders as a choice before its steps.
3. D2/D3 are orthogonal to D1: in Guided the control sits on the active step; in Overview on each step.
4. Map in Guided is the orientation bar, not an extra panel.
5. Recap adds reminder text, not links, and only when viewed steps exist.
6. Segmentation provides headings or an orientation label and never renumbers.
7. Multiple scaffolds change organisation, not volume. A configuration is never made richer than selected.

### 4.3 Worked combinations
| Configuration | Result |
|---|---|
| Overview + Concise + OFF + None + Recap OFF + Seg OFF | Clean numbered list; concise text visible; relationships in words |
| Overview + Segmentation ON | The same list under phase headings |
| Guided + Recap ON | Active step with a short reminder of earlier viewed steps |
| Guided + Disclosure ON | Active step shows essentials; "More" reveals the explanation |
| Guided + Map | Compact map as orientation, current step highlighted |
| Detailed + Disclosure ON | Essentials visible; fuller approved explanation behind the control |
| Inline + Segmentation ON | Phase headings plus cues on the steps |

## 5. Standard, personalised and manually adjusted behaviour
- **Standard (guest, or profile with personalization off) [Implemented routing]:** baseline `(Overview, Concise, OFF, None, OFF, OFF)`; locks and accessibility still bind. **[Proposed UI]:** plain numbered natural-language steps; route choice explained first; documents and correctly scoped fees; essential source limits visible. **No Support panel, no feedback control, no research terms for ordinary guests.**
- **Personalised:** the backend-selected original view, labelled only "Selected for you". The frontend never alters it.
- **Manually adjusted:** a child view labelled "Adjusted by you", never policy-eligible. Support control exists only for personalised views and in research view.
- **Fairness:** the standard baseline must be complete and clear so the comparison is fair.

## 6. Prepared guidance content contract

### 6.1 Contract (`c4-guidance-content-3.0`) [Proposed]
Per procedure:
- `procedure_id`, `source_graph_fingerprint`, `version`, `review` (`reviewer`, `reviewed_at`, `scope_note`, `status`).
- `qualification`: short visible source limit plus full text. Official snapshots keep "not independently validated, not live, not an official application service".
- `phases[]` (optional): `id`, `label`, `action_ids`, `basis`, `why_grouped`, `adds_orientation`, `evidence_ids`, `order_source` (`stage_edges`, `overlay` or `none`), `review`.
- `actions[]`: `heading`, `essential`, `concise_remainder`, `detailed_remainder` (optional), `recap`, `actor`, `destination`, `route_condition`, `remainder_role`, `facts[]`, `evidence_ids`, `required_content_ids`, and `field_status` per field (`reviewed`, `draft`, `source_fallback`).
- `facts[]` entries: `fact_id`, `role` (document or fee), `scope` (`action`, `route`, `stage`, `service`), `action_id` or `condition_ids` as appropriate, and a qualification.
- `supplementary[]` (optional): reviewed, non-duplicative information with its own evidence IDs.

### 6.2 Rules
- Nothing is invented to fill a field; a missing field makes its dependent scaffold infeasible.
- An LLM may draft wording **offline** from the verified Plan using the existing preparation flow (`v2/preparation.py`: drafts are `PENDING REVIEW`; approval is explicit and bound to exact bytes). No provider call in a citizen request.
- **Official-source wording requires a recorded source-fidelity review** by a named reviewer, stating what was compared. Until then it is labelled prepared and unreviewed. Nothing implies government approval or independent validation.
- Fee scope is explicit (§2.2).

### 6.3 Synthetic data rewrite [Proposed], without false payment attribution
- Each fictional fee gets an explicit scope: for example registration fee `scope: action` on the Register action only when the fictional Plan says it is paid there; preparation and submission fees `scope: stage`, shown as "Charges recorded for this procedure" or in the phase, not at the Register step.
- No action sentence names another stage's fee as if payable now. If a sentence must mention fees, the fact scope stays `stage` and the sentence is not used to attach it.
- Add a **route-scoped** fictional fee (counter versus locker collection, different amounts) so route-level scope is testable without implying a combined payment.
- Add essential text, concise and detailed remainders, recap lines, and reviewed phase labels with a recorded basis, so each scaffold is exercisable.
- At least one fictional step is information-heavy so that a single-step disclosure is testable.
- All fiction is labelled; no official claims.

### 6.4 Content readiness: feasible now versus after reviewed content
**Now** means the current prepared records, applying the V3 rules (recorded review required). **After** means after the new wording, remainders, recap lines and phases are drafted offline and reviewed.

| Dimension | Official three, now | Official three, after review | Practice now | Synthetic fixtures now | Rewritten synthetic, after |
|---|---|---|---|---|---|
| D1 Overview/Guided | yes | yes | yes | yes | yes |
| D2 Detailed | no | yes if detailed text reviewed | yes (author-reviewed) | no | yes |
| D3 Disclosure ON | no (no essential layer, no coverage proof) | yes where a reviewed remainder exists | no until essential layer is recorded | no | yes |
| D4 Inline | yes | yes | yes | yes | yes |
| D4 Map | no (parallel coverage unknown) | no unless coverage becomes complete | yes | yes where complete | yes |
| D5 Recap | no (no reviewed reminders) | yes after review | no (copied sentences, need rewriting) | no (labels) | yes |
| D6 Segmentation | no (one stage, no reviewed overlay) | only with a reviewed overlay | no (labels not reviewed) | no | yes where grounded |

**Feasible-set size now (V3 rules):** official three about **4** configurations (navigation × inline); practice about **12** (navigation × detailed × none/inline/map). **After review:** up to the full 96 for the rewritten synthetic set; official procedures depend on what the source supports (still no Map until parallel coverage is complete).

**Consequence:** with today's records the adaptive space for the official procedures is small. Widening it needs offline drafting and your named source-fidelity review. That is reported as content readiness, not hidden.

## 7. Examples

### 7.1 Birth certificate copy (official snapshot, one stage, two actions)
- Edge: pay → submit. Standard: "Step 1 Pay for the certificate copy", "Step 2 Submit the form and receipt".
- Documents: Completed application and Payment receipt appear at the Submit step (the receipt is produced by Step 1: a verified edge).
- Fee: LKR 120 shown with the procedure's recorded charges, with the source qualification (the cited counter route excludes ATM and online payment); shown at Step 1 only after a reviewed `scope: action`.
- Feasible now: Overview or Guided, Inline or None. No Map, Detailed, Disclosure, Recap or Segmentation until content is reviewed.
- Visible limitation: bounded snapshot, not a current or verified service.

### 7.2 NIC amendment (official snapshot, XOR routes)
- Opening choice: "Which applies to you? Estate resident / Not an estate resident" in the source's words. No route is chosen for the citizen; choosing only focuses it.
- Estate route: Step 1 Apply through the Estate Superintendent. Non-estate route: Step 1 Apply through the Grama Niladhari, Step 2 Obtain the Divisional Secretary's countersignature (edge nic_gn → nic_ds).
- Guided: "Step 1 of 2" along the chosen route with an obvious **Change route**.
- Fee: the LKR 500 stage fee applies to both routes and is shown once at the route choice, never per route, never summed.
- No Map; Inline cues available; no Segmentation.

### 7.3 Synthetic parallel procedure
- Layers: Step 1 Register; Step 2 "all of these": a) prepare the supporting copy, b) prepare the form (no order stated); Step 3 Submit (needs both).
- Segmentation ON (after labels are reviewed): "Register", "Prepare the two items", "Submit", ordered only because verified stage edges and no backward edge support it.
- Map feasible and draws the join; Inline shows "Before this", "Can be done alongside", "Also required" on Submit.
- Fees follow §6.3.

## 8. Interactions, events and feedback

### 8.1 Event semantics
| Interaction | Recorded as | Reward? |
|---|---|---|
| Step visible (dwell and threshold stored) | `step_visible` | No |
| Step visited | `navigate` / `step_open` | No |
| Explanation open/close (D3) | `explanation_open/close` | No |
| Guided Back/Next | `navigate` with from/to | No |
| Route focus / change | `route_focus` | No |
| Map show/hide/expand/collapse | `map_*` | No |
| Recap open/close | `recap_open/close` | No |
| Overview peek | `overview_peek` | No |
| Manual presentation change | child view + `explicit_adjustment` | No; journey becomes permanently ineligible |
| Explicit rating | rating (+ optional diagnostic reasons) | Yes, only for an eligible view (§8.3) |

Implicit behaviour is never converted into reward. Duplicates are idempotent **[Implemented]**.

### 8.2 "Return to Overview" in Guided
Changing D1 is a configuration change. "Peek at overview" is a read-only list (an event, not an adjustment). A real switch to the Overview layout is a recorded manual adjustment ("Adjusted by you").

### 8.3 Feedback and the V3 support-fit reward

**Withdrawn:** my earlier "neutral thumbs-down that produces no reward". It would make learning positive-only.

**V3 mapping [Proposed].**
- **Thumbs-up** = `fits` → reward 1.
- **Thumbs-down** = `does_not_fit` → reward **0**, and it **updates the posterior** like any eligible rating. Negative evidence trains V3.
- This keeps the V2 convention (reward 1 only for a good fit; `need_more` and `too_much` already both give 0 and both update) while giving one honest binary question to the citizen.
- V2 reward behaviour is **unchanged**; V2 keeps its three values.

**Optional diagnostic reasons (after thumbs-down):** too much explanation, not enough explanation, navigation difficult, diagram confusing, requirements hard to find, other. They are recorded as diagnostics for analysis. **They never change the reward value** and are not used as a numeric signal in the first V3 experiment. Directional reasons may support a richer reward in a later, separately approved model.

**Eligibility (same discipline as V2):** the view is the original, unadjusted, personalised, unrevoked view; its essential layer was displayed; one rating per original view; no change after submission. Manual adjustments, comparison panes, guests and standard routing are recorded but ineligible.

**Effect on training:** each eligible journey contributes one (feature vector, reward) pair. A 0 lowers the posterior mean for that context-and-configuration vector and widens nothing artificially; a 1 raises it. Because only rated journeys train, the experiment records: exposure (which opportunities were displayed), rating rate by configuration, and reasons, to detect selection bias. These are reported, not corrected for in V3's first experiment.

**Known limits stated, not hidden:** a binary reward under a Gaussian linear model is a misspecification already present in V2; non-response and who-chooses-to-rate biases exist; reasons are self-reports. None is called validated.

## 9. Machine-learning implications

### 9.1 What changes meaning [Changes research assumptions]
The seven action indicators (`v2/features.py: ACTION_NAMES`) are `guided, explanation_expanded, disclosure_expanded, inline, map, recap, summary`. Under this specification: `guided, detailed, disclosure_on, inline, map, recap, segmentation`. Disclosure and Summary→Segmentation change meaning; Recap changes from links to reminders; Explanation is renamed. The 96-configuration count is unchanged but the actions are different actions.

### 9.2 Impact by component
| Component | Impact |
|---|---|
| 96 configurations | Same count; D3, D5 and D6 mean something else; feasibility changes |
| Encoder | Action-dependent blocks (context × action, the 55 three-way terms, the 9 scaffold pairs) were designed around the old actions. Interactions such as familiarity × information volume × summary no longer describe segmentation. They must be re-justified; the size may not stay 515. The seven structural measurements stay unchanged for the first V3 experiment (your decision) |
| Feasibility catalogue | New per-step disclosure rules, D2×D3 combination constraints, phase assessment |
| Content readiness | New required reviewed fields |
| Reward attribution | `fits`/`does_not_fit` with reward 1/0; same eligibility rules |
| Posterior | The V2 posterior cannot be reused |
| Historical journeys | Frozen V2 records stay as they are |
| Existing evaluation | Not evidence for V3 actions |

### 9.3 Versioned migration [Proposed]
- **V2 is not edited.** `v2/features.py` has no diff and stays that way. A new `service/app/v3/` package defines `c4-scaffolds-v3.0` and `c4-features-v3.0` (new fingerprint), reusing the unchanged posterior kernel.
- Separate storage (`service/.local/v3/...`, own table and manifest). V2 refuses mismatched manifests, so V2 data cannot be opened by V3 or vice versa.
- **Fresh posterior** (your decision). No V2 coefficient or reward is copied or replayed.
- V2 keeps running unchanged for reproducing earlier results.
- Interaction terms are listed with their hypotheses for your approval before any coding.

### 9.4 Profile and settings migration [Proposed]
V2 settings must **not** silently become V3 settings. V3 stores them under a versioned schema (`c4-settings-3.0`) in its own store; V2 profiles are read-only inputs to an explicit import adapter (a copy, never a move), following the existing legacy-review pattern in `v2/identity.py`.

| V2 item | V3 handling |
|---|---|
| Accessibility: `allow_guided_navigation = false` | Carried as `no_guided` (same meaning) |
| Accessibility: `allow_relationship_visuals = false` | Carried as `no_map` (same meaning) |
| Accessibility: `allow_collapsed_content = false` | Carried **conservatively** as "step disclosure not allowed" (forces D3 OFF). It restricts, never expands, and the reason is shown for confirmation |
| Hard lock on navigation or relationships | Offered as "carried over, please confirm"; **not applied until confirmed** |
| Hard lock on explanation `concise` | Offered for confirmation; `expanded` → `detailed` is shown as a proposed re-mapping, never applied silently |
| Hard locks on disclosure, recap, summary | **Dropped with a notice** (changed meaning) |
| Soft preferences on navigation or relationships | Imported as **unconfirmed**; excluded from model features until confirmed |
| Soft preferences on disclosure, recap, summary | **Dropped with a notice** (changed meaning) |
| Procedure-specific familiarity, navigation confidence | Carried (not scaffold-specific) |

**Safe defaults:** until the owner reviews the import, V3 uses accessibility constraints (conservative) and **no** soft preference or lock for changed dimensions. A profile never silently gains or loses a restriction that changes what it can see. Locks that cannot be satisfied produce the existing explicit error rather than being relaxed.

## 10. Synthetic scenarios and evaluation (design only)

### 10.1 Principles
Simulator performance is not real-user accuracy and is reported as such. The existing posterior is not trained on. Negative results are reported in full.

### 10.2 Scenario design
- **Contexts:** familiarity {1, 3, 5} × confidence {1, 3, 5} × soft-preference profiles × accessibility sets (none, no_map, no_guided, disclosure disallowed).
- **Procedures:** the rewritten synthetic set spanning the seven measurements, plus the three official procedures (small feasible set) as a content-readiness probe.
- **Labels:** each scenario has an expert-reviewed best-support judgement with provenance (author, date, rationale, status). Literature-informed assumptions are recorded separately from expert judgements, with references **you** verify; I will not assert findings from memory. Concepts to cite: cognitive load and expertise reversal, progressive disclosure, segmenting, advance organisers, step-by-step government patterns.
- **Reward model:** replace the single authored curve with a declared, versioned, parametrised response model derived from the scenario labels, with null and noise regimes, never visible to selection.

### 10.3 Protocol
1. Isolated warm-start in a V3 database; never the V2 posterior.
2. Held-out evaluation: whole procedures and whole context cells held out.
3. Many seeds (for example 20); schedule and scenario-file hashes recorded.
4. Baselines: fixed standard, fixed minimal, fixed maximal-feasible, uniform random over feasible, expert-label policy.
5. Metrics: mean simulated reward and regret (inside the simulator only), preference-match rate where labels exist, constraint violations (must be zero), selection diversity. No claim of calibrated probabilities.
6. Report all seeds, intervals and negative results, including that the V2 run found the minimal baseline above the learned selectors.

## 11. Citizen frontend, desktop and chat layouts
- **Desktop (about 1024 px and above):** restore the left workspace: Continue as guest and saved profiles, then procedure choices. The three bounded government-source procedures appear first as compact choices (Birth certificate copy, NIC amendment, Private-company documents); synthetic procedures sit under "Research examples". The guidance fills the main column.
- **Chat-sized (320 to 420 px):** the guidance component runs alone with no sidebar; identity and procedure come from compact selectors supplied by the host. The component takes `journey`, callbacks and `readOnly`, with no shell dependency.
- **Identity:** black, orange, white; light neutral background; strong type; subtle borders; orange as an accent only (never small text).
- Only procedure information dominates the citizen view. Research controls and technical explanation live in the researcher interface.

## 12. Comparison and research inspector

### 12.1 Comparison [Implemented core, Proposed presentation]
Keeps the consent step, isolated standard guest journey, constraint parity (accessibility and locks only), fingerprint checks and the unchanged-policy check. Compact side-by-side cards where space permits, tabs when narrow, a six-row difference matrix, and no events, adjustments or ratings from either pane.

### 12.2 Research inspector: only genuine backend data
An optional, collapsible, researcher-only panel (half-width side panel on desktop) with **two clearly separate parts**.

**Part A: completed-request record (a stored decision, reconstructed after the request).** Labelled "Record of the completed request", not a live process. From the stored decision (`decision.effective_context`, `measurements`, `evaluation`, `features`, `scores`, `selection_mode`, `policy_revision`):
1. Effective context with origins (identifiers masked).
2. The seven measurements and their completeness.
3. Feasibility: total versus feasible configurations, with reasons grouped.
4. Encoding: vector length and number of non-zero entries (computed from the stored vector).
5. Selection: the mode (`thompson`, `forced` or `standard`), policy revision at selection, number of candidates, and the selected configuration. It may state the verifiable fact that the chosen configuration has the highest **sampled** score among the candidates. It **does not** explain why the model favoured it, and does not attribute the choice to any user or procedure feature. For `forced` it states that only one configuration was feasible. For `standard` it states contextual selection was skipped.
6. The configuration applied for rendering and its attribution.

**Part B: interaction log (real recorded events).** The journey's event list with server timestamps and sequence numbers, labelled as client interaction events. It is not a pipeline trace.

**Not provided:** live processing milestones, timings or progress. The backend does not emit them; none are invented. If timings are wanted, a separate approved change would add explicit server-side timing fields.

## 13. Discrepancies between this specification and the current system
| Area | Current | Gap |
|---|---|---|
| D3 | Optional supplementary blocks collapsed or open | New meaning; needs essential layer, remainders and coverage proof |
| D6 | Preparation summary | New meaning; needs reviewed phases |
| D5 | Recap links to earlier steps; some `recap` values are labels | Reviewed reminder lines; viewed semantics |
| D2 | `expanded` | Rename; reviewed only for practice |
| Numbering | route markers only | Layer numbering |
| Fees | Card lists every `fact_id` as the action's charge | Explicit scope; synthetic data rewritten |
| Titles | Source-excerpt fallback cut at 115 characters | Prepared headings |
| Guests | Support and optional feedback exist | None for ordinary guests |
| Feedback | Three ratings; reasons limited to two | `fits`/`does_not_fit` (V3) and diagnostics |
| Sidebar | Top bar only | Restore left workspace |
| Inspector | Raw JSON page | Two-part panel, genuine data only |
| Events | `detail_open/close` tied to optional block IDs; `action_visible` has no dwell | New action-level events and recorded dwell |
| Profiles | V2 settings only | Versioned V3 settings with confirmation |

## 14. Files and contracts I propose to create or change (after approval)
- **Documentation:** `components/c4-presentation/docs/C4-RESEARCH-UX-SPECIFICATION.md`.
- **Backend (new package; V2 untouched):** `service/app/v3/` with `catalogue.py` (new dimensions, combination constraints), `features.py`, `content.py` and `registration.py` (new contract; coverage proof; phase assessment; fee scope), `runtime.py` and `api.py` (new events, `fits`/`does_not_fit`, separate storage), `identity.py` (settings import and confirmation), `preparation.py` (offline drafts with the new fields), `simulation.py`; prepared content under `research/data/v3/prepared/`; tests `service/tests/test_v3_*.py`.
- **Frontend:** a versioned renderer beside the current card (layer numbering, route choice, step-level disclosure, phases, compact map, reminder recap), restored sidebar shell, researcher inspector, updated comparison, and tests for each dimension and combination.
- **Frontend-only items valid under V2 that can start sooner if you wish:** fee display without false attribution (procedure-level charges row), layer numbering and route presentation, plain guest guidance with no Support or feedback, restored sidebar, the two-part inspector using existing data.

## 15. Implementation phases and tests
0. **Specification approval** (this step).
1. **Content preparation (offline, no model change):** rewrite synthetic data; draft essential, remainders, recap and phases for practice and synthetic; draft the official three for **your** source-fidelity review. Tests: schema validation, source-fingerprint binding, coverage proof, no invented field.
2. **Frontend-only corrections under V2:** fee display, numbering, route presentation, guest simplification, sidebar, inspector. Tests: numbering per procedure, no fee attribution by stage membership, guest has no Support or feedback.
3. **V3 backend** (new package, database): catalogue, features, runtime, events, rating values, settings import. Tests: disclosure coverage proof, segmentation assessment, combination constraints, encoder norm and fingerprint, eligibility parity with V2, negative rating updates the posterior, isolation from V2 storage, no history transfer, settings migration rules.
4. **V3 frontend renderer** for all six dimensions and feasible combinations. Tests: each dimension expressed and not expressed by others; the four D2×D3 cases; recap's four viewed states in both layouts; route change; event semantics; read-only comparison.
5. **Synthetic evaluation** in an isolated store. Tests: reproducibility, evaluation never trains, constraint violations zero.
6. **Browser verification:** 320, 390, 768 and 1280 widths; guest, personalised, manual, comparison; keyboard-only; 200% zoom; contrast.

## 16. Decisions that were open (resolved in §18)
1. **Dwell time and threshold for "visible":** I propose recording them as declared, versioned parameters and choosing the values with you before implementation (I will not hard-code a value silently).
2. **Reviewer identity and process:** who records the source-fidelity review of the official wording, and what the review record must state (what was compared, date).
3. **Import adapter:** confirm that V2 profiles may be read and copied (never modified) into V3, with the confirmation flow in §9.4.
4. **Interaction terms for the V3 encoder:** I will bring the proposed list with hypotheses for approval before any coding.

## 17. Implementation safeguards (approved)

1. **Detailed preserves Concise.** Every essential instruction and required fact present in the Concise guidance is also present in the Detailed guidance. Detailed adds reviewed, source-grounded clarification and never drops or weakens a required fact. This is checked automatically: the required content, condition and fact IDs of Concise must be a subset of those covered by Detailed, and a reviewer attests that no qualification was lost.
2. **Disclosure never collapses essentials.** Progressive Disclosure must never collapse an essential condition, fee qualification, document requirement, destination, or any instruction needed to perform the action safely and correctly. These items live in the always-visible layer; the coverage proof in §3.3 enforces it, and a step failing the proof does not offer disclosure.
3. **Numbering separates orientation from dependency.** Step numbers and "n of N" are *browsing orientation* unless a verified prerequisite supports an ordering. Verified execution dependencies are shown only from verified edges and joins (as "Before this" or "Do this first"). Alternative routes and parallel actions are never shown as falsely sequential, in any layout or in the map.

## 18. Resolved decisions

- **Dwell detection:** the visibility threshold and the dwell time are configurable, versioned and testable parameters stored with each `step_visible` event. I will propose concrete values (with the reasoning) **before** the event instrumentation is implemented, and no value is hard-coded silently.
- **Source review:** you act as the named internal source-fidelity reviewer for the official-source snapshots. The review record states exactly which sources (URLs, retrieval date, passages) and which drafted statements were compared, the result per statement, the reviewer and the date. Nothing implies independent government verification.
- **Profile import:** approved as read-only copying from V2 into a separate V3 settings store, with explicit confirmation and no silent reinterpretation of changed scaffold meanings (§9.4).
- **Encoder:** the revised interaction terms, their hypotheses and the proposed feature schema will be presented for your approval **before any coding**.
- Earlier decisions stand: supplementary information stays separate when useful, reviewed and non-duplicative; verified Plan stages or reviewed overlays may supply segmentation groups; ordinary guests get no personalised Support controls or feedback controls; V3 gets its own feature schema and a fresh posterior; the first V3 experiment keeps the seven structural measurements.

## 19. Handoff outline

**Codex: first, in the V3 backend, content and ML layer** (no frontend work, nothing run against V2 data):
1. Create `service/app/v3/` beside V2 (V2 and its databases untouched): action schema `c4-scaffolds-v3.0`, catalogue with the new dimension values, and feasibility with combination constraints.
2. The prepared-content contract `c4-guidance-content-3.0` as validated models, with the disclosure coverage proof, the Detailed-contains-Concise check, the segmentation assessment (basis, reviewed label, adds-orientation, order honesty) and explicit fee scope.
3. The V3 runtime and API: separate storage and manifest, fresh posterior, new events (`step_visible` with stored threshold and dwell, `step_open`, `explanation_open/close`, `map_*`, `overview_peek`, `recap_open/close`), `fits`/`does_not_fit` ratings with reward 1/0 and unchanged eligibility.
4. The read-only V2→V3 settings import with a confirmation record.
5. **Stop and present** the encoder's interaction terms, hypotheses and feature schema for approval before writing `features.py`; then the encoder, then the offline preparation extensions and the synthetic data rewrite, then the isolated simulation framework.
6. Tests for each of the above, including V2 untouched and isolation of storage.

**Claude: subsequently, in the citizen frontend** (after the V3 contract and sample content exist):
1. The V3 renderer for all six dimensions and feasible combinations: layer numbering, route choice and Change route, step-level disclosure, phase grouping, compact map, reminder recap.
2. Guest standard guidance with no Support or feedback controls; restored desktop sidebar; chat-sized standalone component.
3. The thumbs-up/thumbs-down feedback and optional reasons for eligible views only.
4. The two-part researcher inspector and the compact comparison.
5. Frontend tests for every dimension, the four D2×D3 cases, recap's visible/visited states and fee scope, then a browser verification.

**Preserved:** the V2 system and databases, and the existing Guidance Card checkpoint (`83d02ac` plus the uncommitted redesign).

---

## Appendix A. Revision history

Changes made between the first draft and revision 2 (all approved):

| # | Your point | Previous position | Revised position |
|---|---|---|---|
| 1 | Disclosure meaningfulness | "At least two steps and half the steps" | No count threshold. A step's disclosable body is feasible when a **reviewer attests** it adds source-supported clarification and an **automatic coverage check proves** every required condition, document, fee and instruction is already in the always-visible layer. One heavy step is enough (§3.3) |
| 2 | Segmentation | Plan stages as source, minimum counts | A grouping needs a **recorded basis** (purpose, actor, location, timing or stage), a **reviewed citizen label** and a reviewed **"adds orientation"** attestation. Phase membership never creates an ordering. Phase order is shown only when a verified edge or reviewed overlay states it (§3.6) |
| 3 | Fee scope | Fees filtered by the action's stage | A stage fee is **never** turned into an action fee by stage membership. Four explicit scopes (action, route, stage, service). A fee sentence that *mentions* several fees is not attribution. Synthetic example rewritten with explicit scopes (§2.2, §6) |
| 4 | Recap | "Viewed" = visible | Four separated states: rendered, visible with dwell, visited (explicit interaction), details opened. Recap uses only visible-with-dwell or visited steps (§3.5) |
| 5 | Feedback | A neutral thumbs-down | **Withdrawn.** Thumbs-down is an eligible rating with reward 0, so negative evidence trains V3. Reasons are diagnostics, not rewards. Mapping, bias risks and training effect are specified (§8.3). V2 reward untouched |
| 6 | Profile migration | Not covered | Versioned V3 settings; **no silent reinterpretation**. Accessibility constraints carry over conservatively; unchanged-meaning preferences come in as "unconfirmed"; changed-meaning ones are dropped with a notice (§9.4) |
| 7 | Inspector | Narrated pipeline | Two clearly separated parts: a **completed-request record** (stored decision) and the **interaction log**. No live milestones, no causal reasons for Thompson selections (§12.2) |
| 8 | Content readiness | One table | Feasible **now** under current prepared records versus feasible **after** reviewed content, with configuration counts (§6.4) |

**Your decisions, recorded:** supplementary information stays separate when useful, reviewed and non-duplicative; verified Plan stages or reviewed overlays may supply segmentation groups; ordinary guests get no personalised Support controls and no feedback controls; official-source wording needs an actual recorded source-fidelity review and nothing implies government or independent approval; V3 gets a separate feature schema and a fresh posterior while V2 is preserved; the first V3 experiment keeps the seven structural measurements.
