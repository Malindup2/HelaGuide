# Technical Workflow — Multilingual Intent & Entity Engine

**Component:** Multilingual Conversational Intent & Entity Understanding Engine
**Project:** AI-Driven Citizen-Service Orchestrator (J26-SE-354)
**Project folder:** `D:\Research\cs-intent-engine`
**Next milestone:** PP1 — due 20 Oct 2026

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
- ⚠️ Service IDs and attributes from Thilakumara (needed to fill `kg_service_id`)
- ⚠️ Class imbalance: `unsupported_service` has 26 dialogues, core intents only 3–6 each

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
cd /d D:\Research\cs-intent-engine
```
```bash
conda activate label
label-studio
```

---

## 2. Schema & dataset creation 🔄

### 2.1 Intent schema

- ✅ `schema_v0.json` — first draft, 17 intents across many services
- ✅ `schema_v1.json` — narrowed to the three departments in the Knowledge Graph

**Why the change:** the Knowledge Graph component (Thilakumara) only scrapes three departments. If the engine predicts an intent the KG can't serve, orchestration fails. Intents must map one-to-one to KG services.

**Schema v1 — 12 intents**

| Intent | Department | Route | Slots |
|---|---|---|---|
| `nic_new` | Registration of Persons | orchestration | applicant_for, district, date_of_birth |
| `nic_update` | Registration of Persons | orchestration | change_field, new_value, district |
| `nic_replace_lost` | Registration of Persons | orchestration | district, urgency |
| `passport_new` | Immigration & Emigration | orchestration | applicant_for, service_type, travel_date |
| `passport_renew` | Immigration & Emigration | orchestration | service_type, travel_date |
| `birth_cert_copy` | Registrar General | orchestration | applicant_for, district, purpose |
| `marriage_registration` | Registrar General | orchestration | district, date |
| `death_cert_copy` | Registrar General | orchestration | district, purpose |
| `unsupported_service` | — | fallback | service_mentioned |
| `feedback_complaint` | — | Trust Verification | — |
| `general_question` | — | — | — |
| `out_of_scope` | — | — | — |

- `unsupported_service` covers real services the KG doesn't have yet (driving licence, police clearance, business registration, building permit, utilities, GN/residence certificate). The system says "not supported yet" instead of guessing.
- Slots dropped in v1 (only used by removed services): `address`, `vehicle_class`, `license_action`, `business_type`, `building_type`, `utility_type`.
- Every core intent has `kg_service_id: "TBD"`.

**To do**
- ⬜ Send the 4 `open_questions_for_kg` (in the schema) to Thilakumara:
  1. His exact service list and IDs (e.g. is NIC replacement its own service?)
  2. The attributes each service has (e.g. normal vs one-day passport) — slots should match these
  3. Whether he's scraping citizenship services (Immigration handles dual citizenship; no intent for it yet)
  4. Whether he can share scraped pages, especially the Sinhala versions
- ⬜ Fill every `kg_service_id`
- ⬜ Decide whether to add a citizenship intent

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

**Why three styles:** citizens type in Sinhala script, in romanized Sinhala, and in a mix. Results must be reportable per style, because the baseline already shows huge differences between them (see §4).

**To do**
- ⬜ Write ~45 more dialogues covering **only the 8 core intents** (target ~10 per intent)
  - Why: fixes the imbalance; otherwise the model learns to over-predict `unsupported_service`
- ⬜ Use scraped Sinhala pages for official terms (ජාතික හැඳුනුම්පත, උප්පැන්න සහතිකය, etc.) and real required documents
- ⬜ Generate a synthetic batch with an LLM (Claude/GPT)
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

### Why
- **Pre-labelling:** correcting labels is much faster than labelling from scratch.
- **Label Studio over Doccano:** supports custom configs for token-level tags plus spans in one task.
- **Intents are not labelled in Label Studio:** they already live in the dialogue JSON. Label Studio handles language and entity labels only, so schema changes don't affect labelling.

### Labelling rules decided so far
- Entity = a value that fills a slot (district, date, document type, etc.)
- `NE` = a name or proper noun that isn't clearly Sinhala or English (place names, department names)
- If information appears only in a bot question, the user's answer is labelled, not the bot turn

### To do
- 🔄 Review language tags on all 142 tasks
- 🔄 Review entity spans
- ⬜ Write a short annotation guideline doc (rules above + edge cases) — useful for the thesis and for consistency
- ⬜ Re-run `prepare_labelstudio.py` and re-import after the new dialogue batch
- ⬜ Export labelled data (JSON)
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

**Why this matters:** it's direct evidence that off-the-shelf language ID fails on how Sri Lankans actually type, which justifies fine-tuning a token-level model.

### To do
- ⬜ Build token-level LID training data from the Label Studio export
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

- ⬜ Set up Rasa Open Source project inside `cs-intent-engine`
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
  - Baseline findings (fastText 99.6% vs 21%; XLM-R fragmentation)
  - Dataset & schema stats (intents, dialogues, styles, tasks labelled)
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

| File | Purpose | Status |
|---|---|---|
| `data\schema_v0.json` | First intent schema (kept as record) | ✅ |
| `data\schema_v1.json` | Current schema, 12 intents | ✅ |
| `data\seed_dialogues_*.json` | 70 seed dialogues, 3 styles | ✅ |
| `data\backup_v0\` | Pre-migration backups | ✅ |
| `src\migrate_schema_v1.py` | v0 → v1 label migration | ✅ |
| `src\prepare_labelstudio.py` | Merge + pre-label for Label Studio | ✅ |
| `labelstudio_config.xml` | Labelling interface | ✅ |
| `notes.md` | Research observations | 🔄 |

## Decision log

| Date | Decision | Reason |
|---|---|---|
| Sep 2026 | Tamil moved to future work | Data and timeline; Sinhala-English has more resources |
| Oct 2026 | Two conda envs | Label Studio dependencies clash with ML stack |
| Oct 2026 | Scope intents to 3 KG departments | Intents must map to services the KG can serve |
| Oct 2026 | Out-of-scope services → `unsupported_service` | Honest fallback instead of guessing; originals preserved |
| Oct 2026 | Next dialogue batch: core intents only | Fix class imbalance |
