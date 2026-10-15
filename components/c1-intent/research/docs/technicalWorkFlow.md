# Technical Workflow — Multilingual Intent & Entity Engine

**Component:** Multilingual Conversational Intent & Entity Understanding Engine
**Project:** AI-Driven Citizen-Service Orchestrator (J26-SE-354)
**Project folder:** `HelaGuide\components\c1-intent\research\` in the team repo (`data\`, `experiments\`, `docs\`; local-only `models\` and `results\`). Originally `D:\Research\cs-intent-engine`.
**Next milestone:** PP1 — due 20 Oct 2026
**Last updated:** 15 Oct 2026

Status key: ✅ done · 🔄 in progress · ⬜ not started · ⚠️ blocked

---

## 0. Quick status

| Phase | Status | Planner card |
|---|---|---|
| 1. Environment setup | ✅ | — |
| 2. Schema & dataset creation | 🔄 | Dataset creation |
| 3. Annotation & data split | 🔄 | Annotation & data split |
| 4. Language segmentation layer | 🔄 | Language segmentation layer |
| 5. Intent classifier | ⬜ | Intent classifier |
| 6. Entity extraction + multi-turn tracking | ⬜ | Entity extractor + multi-turn tracking |
| 7. FastAPI service + routing | ⬜ | FastAPI endpoint + routing |
| 8. PP1 demo & slides | ⬜ | PP1 demo & slides |
| 9. Context optimization & trade-off evaluation | ⬜ (PP2) | PP2 – Context optimization & evaluation |

**Current blockers**
- ⚠️ C2 confirmation of the two proposed service IDs (`svc:marriage_registration`, `svc:death_certificate`) and the other questions in `docs\c2_open_questions.md` (ready to send)
- ⚠️ Class imbalance: `unsupported_service` has 26 dialogues (54 of 142 user turns), core intents only 3–6 each

---

## 1. Environment setup ✅

### What was done
- ✅ Installed Miniconda with Python 3.10
- ✅ Created two separate conda environments
  - `nlp` — research, modelling, scripts
  - `label` — Label Studio only
- ✅ Installed core packages in `nlp`: `torch`, `transformers`, `fasttext-wheel`, `seqeval`, and supporting libraries
- ✅ Created project folder `D:\Research\cs-intent-engine` with `data\` and `src\`

### Why
- **Python 3.10:** the most compatible version across Rasa, transformers, and fastText; newer versions break some of these packages.
- **Two environments:** Label Studio pins its own dependency versions, which clash with the ML stack. Keeping them apart stops one from breaking the other.
- **`fasttext-wheel` instead of `fasttext`:** the original package needs a C++ compiler on Windows; the wheel installs pre-built.

### Problems hit and fixes (keep for the thesis "challenges" section)
| Problem | Fix |
|---|---|
| Anaconda Terms of Service blocked env creation | Accepted the ToS for the default channels |
| Windows Application Control blocked a DLL | Resolved the blocked library (see setup chat) |
| fastText crashes with NumPy 2 | Downgraded NumPy below 2 (`numpy<2`) in `nlp` |

### Daily commands
```bash
conda activate nlp
cd /d D:\ResearchRepo\HelaGuide\components\c1-intent\research
```
Scripts use paths relative to `research\` (`data\`, `models\`, `results\`), so always run them from there: `python experiments\<script>.py`.
```bash
conda activate label
label-studio
```

---

## 2. Schema & dataset creation 🔄

### 2.1 Intent schema

- ✅ `schema_v0.json` — first draft, 17 intents across many services
- ✅ `schema_v1.json` — narrowed to the three departments in the Knowledge Graph
- ✅ `kg_service_map.json` (14 Oct) — maps the 8 core intents to C2 service IDs, built from C2's committed files (agency profiles, crawl tree and logs, vocabulary, completion log). Also lists which attributes the KG holds per service, source pages, KG services no intent covers, and Sinhala coverage
- ✅ `schema_v1.json` updated to **version 1.1** (14 Oct) from the map: `kg_service_id` + `kg_variant` filled, `service_type` enum changed, `open_questions_for_kg` replaced by `open_questions_for_c2`. Pre-1.1 files backed up to `data\backup_v1_0\`
- ✅ `docs\c2_open_questions.md` — 9 questions for C2 (IDs, registration vs copy, passport basis, variants, deceased NIC, dual citizenship, RGD extraction status, service list export, Sinhala names)

**Why the change:** the Knowledge Graph component (Thilakumara) only scrapes three departments. If the engine predicts an intent the KG can't serve, orchestration fails. Intents must map one-to-one to KG services.

**Schema v1.1 — 12 intents**

| Intent | Department | Route | KG service (variant) | Slots |
|---|---|---|---|---|
| `nic_new` | Registration of Persons | orchestration | `svc:nic` (`first_issue`) | applicant_for, district, date_of_birth |
| `nic_update` | Registration of Persons | orchestration | `svc:nic` (`amended`) | change_field, new_value, district |
| `nic_replace_lost` | Registration of Persons | orchestration | `svc:nic` (`lost`) | district, urgency |
| `passport_new` | Immigration & Emigration | orchestration | `svc:passport` (`ordinary`) | applicant_for, service_type, travel_date |
| `passport_renew` | Immigration & Emigration | orchestration | `svc:passport` (`replacement`) | service_type, travel_date |
| `birth_cert_copy` | Registrar General | orchestration | `svc:birth_certificate` (ID exists, no facts yet) | applicant_for, district, purpose |
| `marriage_registration` | Registrar General | orchestration | `svc:marriage_registration` (**proposed**) | district, date |
| `death_cert_copy` | Registrar General | orchestration | `svc:death_certificate` (**proposed**) | district, purpose |
| `unsupported_service` | — | fallback | — | service_mentioned |
| `feedback_complaint` | — | Trust Verification | — | — |
| `general_question` | — | — | — | — |
| `out_of_scope` | — | — | — | — |

- `unsupported_service` covers real services the KG doesn't have yet (driving licence, police clearance, business registration, building permit, utilities, GN/residence certificate). The system says "not supported yet" instead of guessing.
- Slots dropped in v1 (only used by removed services): `address`, `vehicle_class`, `license_action`, `business_type`, `building_type`, `utility_type`.
- **Answers found in C2's files** (closing the old `open_questions_for_kg`):
  - NIC update and NIC replacement are **not** separate KG services; they are variants of `svc:nic`. Passport renewal is a variant of `svc:passport`.
  - Passports use `normal` / `urgent` in the KG, so the `service_type` slot is now `[normal, urgent]`; "one day service" in user text maps to `urgent`. NIC one-day stays in the separate `urgency` slot, because C2 keeps NIC `one_day` as its own qualifier.
  - Dual citizenship **is** crawled (fee, documents, prerequisites) but has no service ID yet.
  - No official Sinhala service names were scraped: discovery drops the Sinhala and Tamil pages by design.

**To do**
- ⬜ Send `docs\c2_open_questions.md` to C2 and record the answers
- ⬜ Change the two proposed IDs if C2 assigns different ones; update `kg_service_map.json` statuses
- ⬜ Decide whether to add a `dual_citizenship` intent (depends on C2 giving it an ID)
- ⬜ Collect official Sinhala service names (C2 crawl of Sinhala pages, or by hand)

### 2.2 Seed dialogues

- ✅ 70 multi-turn seed dialogues in `data\seed_dialogues_*.json`, split into three styles:
  - Standard code-mixed (Sinhala + English)
  - Pure Sinhala
  - Mixed Singlish (romanized Sinhala)
- ✅ Dialogues include corrections, missing-slot follow-ups, and intent switches, each tagged
- ✅ Fixed Singlish spelling across bot turns ("kohenda" → "koheda")
- ✅ `src\migrate_schema_v1.py` converted v0 labels to v1
  - Updated 54 user turns across 3 files
  - Backed up originals to `data\backup_v0\`
  - Kept old labels as `original_intent` / `original_slots` so they can be restored if the KG grows
  - Safe to run twice (idempotent)
- ✅ Schema 1.1 update (14 Oct): `service_type` `one_day` → `urgent` in `d002` and `d018` (3 state values; user text unchanged)
- ✅ Dataset stats (v1.1): 70 dialogues, 142 user turns, 788 tokens; 102 turns code-mixed, 40 pure Sinhala. Full breakdown in `data\README.md`

**Why three styles:** citizens type in Sinhala script, in romanized Sinhala, and in a mix. Results must be reportable per style, because the baseline already shows huge differences between them (see §4).

**To do**
- ⬜ Write ~45 more dialogues covering **only the 8 core intents** (target ~10 per intent)
  - Why: fixes the imbalance; otherwise the model learns to over-predict `unsupported_service`
- ⬜ Use scraped Sinhala pages for official terms (ජාතික හැඳුනුම්පත, උප්පැන්න සහතිකය, etc.) and real required documents
- 🔄 Generate a synthetic batch with an LLM (Claude/GPT) — started: `data\synthetic\`, `experiments\generate_synthetic.py`, `experiments\tag_synthetic.py`
  - Seed only with public service descriptions, never real citizen data
  - Filter out unnatural or wrongly labelled samples by hand
  - Keep synthetic data in a separate file so it can be evaluated separately from manual data
- ⬜ Log sources and provenance for every seed query (website, date accessed)

---

## 3. Annotation & data split 🔄

### What was done
- ✅ Label Studio installed in the `label` env
- ✅ `src\prepare_labelstudio.py` — merges the dialogue files and pre-labels:
  - Word-level language tags: `SI`, `EN`, `MIXED`, `NE` (named entity), `OTHER`
  - Entity spans from the slot values
- ✅ `labelstudio_config.xml` — labelling interface config
- ✅ Project **"CS-Intent Seed"** created with 142 tasks
- ✅ All 142 tasks reviewed and submitted; exported to `data\ls_export.json`
  - Pre-labels were 98.9% right: 9 of 788 language tags corrected by hand
- ✅ `experiments\baseline_fasttext.py` converts the export into the token-level gold set `data\gold_tokens.jsonl` (one line per user turn: tokens, language tags, BIO entity tags, intent)
  - Fixed: `d001` turn 0 `change karanna` was wrongly tagged `new_value`
  - Fixed: the gold set had silently taken **v0 intents** from the Label Studio export because `seed_all.json` was missing. Regenerated with v1 intents; only the `intent` field changed (54 turns). The script now **stops** if `seed_all.json` is missing and warns if any turn is not found in it
- ✅ Gold set final: 788 tokens — SI 513 · EN 198 · NE 65 · OTHER 11 · MIXED 1; entities: district 37 · issue 10 · service_mentioned 6 · new_value 5 · travel_date 5 · purpose 4 · date 3

### Why
- **Pre-labelling:** correcting labels is much faster than labelling from scratch.
- **Label Studio over Doccano:** supports custom configs for token-level tags plus spans in one task.
- **Intents are not labelled in Label Studio:** they already live in the dialogue JSON. Label Studio handles language and entity labels only, so schema changes don't affect labelling.

### Labelling rules decided so far
- Entity = a value that fills a slot (district, date, document type, etc.)
- `NE` = a name or proper noun that isn't clearly Sinhala or English (place names, department names)
- If information appears only in a bot question, the user's answer is labelled, not the bot turn
- Entities are labelled only where the value literally appears in the user turn. Enum slots (`applicant_for`, `urgency`, `service_type`, `change_field`) are turn-level labels in the dialogue JSON, never spans
- In Singlish, `one` usually means ඕනේ (need) → `SI`
- `MIXED` = one word combining both languages (e.g. `16i`); `OTHER` = numbers and symbols

### To do
- ✅ Review language tags on all 142 tasks
- ✅ Review entity spans
- ⬜ Write a short annotation guideline doc (rules above + edge cases) — useful for the thesis and for consistency
- ⬜ After the new dialogue batch: run `prepare_labelstudio.py` and import `ls_tasks.json` into a **new** Label Studio project, or only the new tasks. Re-importing everything into "CS-Intent Seed" would duplicate 142 tasks without the corrections
- ✅ Export labelled data (JSON)
- ⬜ Create held-out test set
  - Manual data only, never synthetic
  - Split by **dialogue**, not by turn, so turns from one conversation don't leak across train and test
  - Stratify by intent and by style (script / Singlish / code-mixed)
- ⬜ Convert to training formats: Rasa NLU YAML and HuggingFace token-classification format

---

## 4. Language segmentation layer 🔄

### What was done — baseline findings (use in PP1)
- ✅ **fastText lid.176:**
  - Sinhala script → 99.6% confidence, correct
  - Romanized Sinhala → 21% confidence, misclassified as English
- ✅ **XLM-RoBERTa tokenizer:** fragments Singlish words into many meaningless subword pieces
- ✅ Findings recorded in `notes.md`
- ✅ **fastText baseline on the full gold set** (`experiments\baseline_fasttext.py` → `results\baseline_fasttext.json`)

  | Token level (SI/EN gold tokens) | Accuracy | n |
  |---|---|---|
  | All | 57.4% | 711 |
  | Gold EN | 86.9% | 198 |
  | Gold SI | 46.0% | 513 |
  | Code-mixed, romanized | **35.2%** | 421 |
  | Code-mixed, Sinhala script | 90.4% | 125 |
  | Pure Sinhala, Sinhala script | 89.1% | 165 |

  | Sentence level (vs majority tag) | Accuracy | n |
  |---|---|---|
  | All | 60.2% | 113 |
  | Code-mixed, romanized | **27.4%** | 62 |
  | Code-mixed, Sinhala script | 100% | 21 |
  | Pure Sinhala, Sinhala script | 100% | 30 |

  - 69 of 142 turns contain both SI and EN words, so a single sentence label is wrong for part of every one of them.

**Why this matters:** it's direct evidence that off-the-shelf language ID fails on how Sri Lankans actually type, which justifies fine-tuning a token-level model. Romanized Sinhala is the failure case: on a two-way SI/EN choice, fastText is worse than a coin flip at both token and sentence level.

### To do
- ✅ Build token-level LID training data from the Label Studio export (`data\gold_tokens.jsonl`)
- ⬜ Set up Colab GPU + Weights & Biases (log every run: config, metrics, model version)
- ⬜ Fine-tune XLM-RoBERTa for token classification (`SI` / `EN` / `MIXED` / `NE` / `OTHER`)
  - Why XLM-R: already pretrained on Sinhala and English; fine-tuning needs far less data than training from scratch
  - Why not fastText alone: it's sentence-level and fails on romanized Sinhala
- ⬜ Evaluate token-level F1 vs the fastText baseline, broken down by style
- ⬜ Error analysis at switch points (where the language changes mid-sentence)
- ⬜ Wrap as a module: `segment(text) -> [(token, lang)]`

---

## 5. Intent classifier ⬜

- ⬜ Choose model
  - **XLM-R fine-tune:** stronger multilingual representation; more control
  - **Rasa DIET:** joint intent + entity model; fits straight into the Rasa pipeline
  - Option: try both, report both
- ⬜ Check class balance before training (after the new batch)
- ⬜ Train baseline
- ⬜ Tune hyperparameters (learning rate, epochs, batch size) — log in W&B
- ⬜ Evaluate: accuracy, precision, recall, macro-F1
  - Why macro-F1: it treats small intents equally, so imbalance can't hide behind a high accuracy number
- ⬜ Confusion matrix (look especially at NIC intents confusing each other)
- ⬜ Report per style: Sinhala script vs Singlish vs code-mixed
- ⬜ Save best checkpoint with version name

---

## 6. Entity extraction + multi-turn tracking ⬜

- ⬜ Set up Rasa Open Source project inside `components\c1-intent\`
  - Why Rasa: ready-made intent/entity/slot tracking, so effort goes into the code-switching work, not dialogue plumbing
- ⬜ Generate `domain.yml` from `schema_v1.json` (intents, entities, slots)
- ⬜ Configure NLU pipeline (tokenizer, featurizer with XLM-R, DIET classifier)
- ⬜ Train NER and evaluate with **seqeval** (entity-level precision/recall/F1)
  - Why seqeval: scores whole entities, not individual tokens, which is the standard for NER
- ⬜ Slot carryover across turns (e.g. turn 1 "NIC eka wenas karanna one", turn 2 "Colombo 7" → fills `district`)
- ⬜ Handle corrections ("ne, Gampaha") and intent switches mid-dialogue
- ⬜ Test on the tagged multi-turn seed dialogues

---

## 7. FastAPI service + routing ⬜

- ⬜ Agree on the shared JSON schema with the whole team (interface contract for all four engines)
- ⬜ Build `POST /parse`
  - Input: `session_id`, `message`
  - Output: `intent`, `confidence`, `entities`, `dialogue_state`, `language_tags`, `route`
- ⬜ Routing logic
  - Core intents → Orchestration engine
  - `unsupported_service` → fallback message
  - `feedback_complaint` → Trust Verification engine
- ⬜ Mock downstream services so testing doesn't wait on teammates
- ⬜ Log latency per request (needed later for the trade-off curve)
- ⬜ Basic API tests
- ⬜ Dockerize (shared team infrastructure)

Why FastAPI: fast, async, auto-generates API docs, and the team already uses it as the common serving layer.

---

## 8. PP1 demo & slides ⬜ (due 20 Oct)

- ⬜ Pick demo dialogue (e.g. multi-turn NIC update with a correction)
- ⬜ Test full demo flow end to end
- ⬜ Record a backup demo video
- ⬜ Slides
  - Baseline findings (fastText 99.6% vs 21% on single sentences; on the gold set, 35.2% token / 27.4% sentence accuracy on romanized Sinhala; XLM-R fragmentation)
  - Dataset & schema stats (70 dialogues, 142 labelled turns, 788 tokens, 12 intents, 3 styles; schema 1.1 mapped to KG service IDs)
  - Model results (metrics, confusion matrix)
  - Progress vs TAF objectives
  - PP2 plan
- ⬜ Rehearse

---

## 9. PP2 — Context optimization & trade-off evaluation ⬜

This is the core research contribution.

- ⬜ Full-history baseline (control: whole conversation every turn)
- ⬜ Sliding-window strategy (last N turns)
- ⬜ Summarization strategy (LangChain summary / summary-buffer memory)
- ⬜ Structured-state carryover (pass only the tracked slots, not raw text)
- ⬜ Token counting per turn (tiktoken or the model tokenizer)
- ⬜ Measure per strategy on the same test set: joint goal accuracy, tokens per turn, latency
- ⬜ Plot the accuracy vs tokens/latency trade-off curve
- ⬜ Error analysis

Why: no existing work measures this trade-off for Sinhala-English code-switched multi-turn dialogue. The curve is the research result.

---

## Files in the project

Paths are relative to `components\c1-intent\`. Full data file descriptions are in `research\data\README.md`.

| File | Purpose | Status |
|---|---|---|
| `CLAUDE.md` | Working rules for Claude Code in this folder | ✅ |
| `research\.gitignore` | Keeps `models\`, `results\`, backups and regenerated files out of git | ✅ |
| `research\data\README.md` | What every data file is, formats, stats, labelling rules, how to regenerate | ✅ |
| `research\data\schema_v0.json` | First intent schema (kept as record) | ✅ |
| `research\data\schema_v1.json` | Current schema, version 1.1, 12 intents with KG service IDs | ✅ |
| `research\data\kg_service_map.json` | Intent → C2 service ID map, KG attributes, unmapped services | ✅ |
| `research\data\seed_dialogues_*.json` | 70 seed dialogues, 3 styles | ✅ |
| `research\data\labelstudio_config.xml` | Labelling interface | ✅ |
| `research\data\ls_export.json` | Label Studio export, 142 annotated tasks | ✅ |
| `research\data\gold_tokens.jsonl` | Token-level gold set (language + BIO entity tags) | ✅ |
| `research\data\synthetic\` | Synthetic dialogue batch | 🔄 |
| `research\data\backup_v0\`, `backup_v1_0\` | Backups before the v1 migration and the 1.1 update (local only) | ✅ |
| `research\data\seed_all.json`, `ls_tasks.json` | Regenerated by `prepare_labelstudio.py` (local only) | — |
| `research\models\lid.176.bin` | fastText language-ID model (local only) | ✅ |
| `research\results\baseline_fasttext.json` | fastText baseline numbers (local only) | ✅ |
| `research\experiments\migrate_schema_v1.py` | v0 → v1 label migration | ✅ |
| `research\experiments\prepare_labelstudio.py` | Merge + pre-label for Label Studio | ✅ |
| `research\experiments\baseline_fasttext.py` | Export → gold set + fastText baseline | ✅ |
| `research\experiments\check_fixes.py` | Spot-check language tags on English loanwords | ✅ |
| `research\experiments\generate_synthetic.py`, `tag_synthetic.py` | Synthetic data generation and tagging | 🔄 |
| `research\docs\notes.md` | Research observations | 🔄 |
| `research\docs\c2_open_questions.md` | Questions for C2 on service IDs | ✅ ready to send |

## Decision log

| Date | Decision | Reason |
|---|---|---|
| Sep 2026 | Tamil moved to future work | Data and timeline; Sinhala-English has more resources |
| Oct 2026 | Two conda envs | Label Studio dependencies clash with ML stack |
| Oct 2026 | Scope intents to 3 KG departments | Intents must map to services the KG can serve |
| Oct 2026 | Out-of-scope services → `unsupported_service` | Honest fallback instead of guessing; originals preserved |
| Oct 2026 | Next dialogue batch: core intents only | Fix class imbalance |
| 14 Oct 2026 | Gold-set intents always come from the dialogue files (`seed_all.json`), never the Label Studio export; the script stops without it | The export predates schema v1, and the gold set had silently picked up v0 intents |
| 14 Oct 2026 | Service IDs taken from C2's committed files (`kg_service_map.json`); two IDs proposed | Graph and crawl archive not available locally; C2 owns the vocabulary, so proposals go to C2 for confirmation |
| 14 Oct 2026 | NIC update / replacement and passport renewal stay separate intents but map to **variants** of one KG service | The KG has one service per document (`svc:nic`, `svc:passport`) with variants |
| 14 Oct 2026 | Passport `service_type` = `normal` / `urgent` (was `normal` / `one_day`) | Match C2's passport vocabulary; NIC one-day stays in the `urgency` slot |
| 14 Oct 2026 | Models, results, backups and regenerated files kept out of git (`research\.gitignore`) | Size, and they can be rebuilt from the scripts |
