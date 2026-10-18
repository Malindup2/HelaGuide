# Technical Workflow — Multilingual Intent & Entity Engine

**Component:** Multilingual Conversational Intent & Entity Understanding Engine
**Project:** AI-Driven Citizen-Service Orchestrator (J26-SE-354)
**Project folder:** `HelaGuide\components\c1-intent\research\` in the team repo (`data\`, `experiments\`, `docs\`, `results\`, two Colab notebooks; `models\` local only, trained models on Drive). Originally `D:\Research\cs-intent-engine`.
**Next milestone:** PP1 — due 20 Oct 2026
**Last updated:** 18 Oct 2026

Status key: ✅ done · 🔄 in progress · ⬜ not started · ⚠️ blocked

---

## 0. Quick status

| Phase | Status | Planner card |
|---|---|---|
| 1. Environment setup | ✅ | — |
| 2. Schema & dataset creation | ✅ for PP1 (gold, silver, fresh sets) | Dataset creation |
| 3. Annotation & data split | ✅ (guideline doc pending) | Annotation & data split |
| 4. Language segmentation layer | 🔄 XLM-R trained, 3 seeds (0.973 ± 0.005 on fresh set); module wrap pending | Language segmentation layer |
| 5. Intent classifier | 🔄 XLM-R and TF-IDF baselines, 3 seeds (XLM-R macro-F1 0.936 gold / 0.926 fresh; TF-IDF higher) | Intent classifier |
| 6. Entity extraction + multi-turn tracking | 🔄 Hybrid extractor + state tracker done: JGA 0.807 synthetic / 0.920 fresh (held-out), 0.88 fresh with predicted intent; Rasa pending | Entity extractor + multi-turn tracking |
| 7. FastAPI service + routing | 🔄 (skeleton + stub) | FastAPI endpoint + routing |
| 8. PP1 demo & slides | ⬜ | PP1 demo & slides |
| 9. Context optimization & trade-off evaluation | 🔄 first experiment done (Observation 8: XLM-R + window_3 recommended) | PP2 – Context optimization & evaluation |

**Headline results (mean ± std over 3 seeds, 16 Oct; `notes.md` Observations 7–8, `docs\c1_results_log.md`)**
- Language ID on the fresh, human-written test set: XLM-R **0.973 ± 0.005** vs fastText 0.595 vs heuristic 0.773 (SI/EN words). On Singlish: **0.955** vs 0.262 vs 0.829. At code-switch points: 0.973 vs fastText 0.507
- Intent macro-F1: XLM-R 0.936 ± 0.025 gold / 0.926 ± 0.021 fresh; a TF-IDF + LogReg baseline scores higher (0.972 / 0.953), because intents are keyword-driven
- Entities: span micro-F1 0.528 ± 0.054 gold / 0.394 ± 0.080 fresh, the weakest part (district and travel_date over-predicted)
- Context strategies (sessions of joined dialogues): XLM-R + window_3 matches full history on gold (0.896 vs 0.897) with a fixed input size; TF-IDF gets **worse** with more context (full history 0.683)

**Current blockers**
- ⚠️ C2 confirmation of the two proposed service IDs (`svc:marriage_registration`, `svc:death_certificate`) and the other questions in `docs\c2_open_questions.md` (ready to send)
- All 12 intents now have training data (18 Oct: 30 synthetic dialogues per support intent, §2.3), so all 142 gold turns can be scored once the models are retrained. The results above are from the 8-core-intent silver set

---

## 1. Environment setup ✅

### What was done
- ✅ Installed Miniconda with Python 3.10
- ✅ Created two separate conda environments
  - `nlp` — research, modelling, scripts
  - `label` — Label Studio only
- ✅ Installed core packages in `nlp`: `torch`, `transformers`, `fasttext-wheel`, `seqeval`, and supporting libraries
- ✅ Created project folder `D:\Research\cs-intent-engine` with `data\` and `src\` (since moved into the team repo; scripts now live in `research\experiments\`)

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

## 2. Schema & dataset creation ✅ (for PP1)

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
- ✅ `experiments\migrate_schema_v1.py` converted v0 labels to v1
  - Updated 54 user turns across 3 files
  - Backed up originals to `data\backup_v0\`
  - Kept old labels as `original_intent` / `original_slots` so they can be restored if the KG grows
  - Safe to run twice (idempotent)
- ✅ Schema 1.1 update (14 Oct): `service_type` `one_day` → `urgent` in `d002` and `d018` (3 state values; user text unchanged)
- ✅ Dataset stats (v1.1): 70 dialogues, 142 user turns, 788 tokens; 102 turns code-mixed, 40 pure Sinhala. Full breakdown in `data\README.md`

**Why three styles:** citizens type in Sinhala script, in romanized Sinhala, and in a mix. Results must be reportable per style, because the baseline already shows huge differences between them (see §4).

**To do**
- ✅ ~~Write ~45 more dialogues for the 8 core intents~~ — replaced by the synthetic batch (§2.3), about 35 dialogues per core intent
- ⬜ Use official Sinhala terms (ජාතික හැඳුනුම්පත, උප්පැන්න සහතිකය, etc.) once they are available. C2 has **not** scraped the Sinhala pages (see §2.1), so this waits on C2 crawling them or a manual pass over the agencies' Sinhala sites
- ⬜ Use the English pages C2 has crawled (`kg_service_map.json` → `source_pages`) for real required documents
- ✅ Generate a synthetic batch with an LLM — see §2.3
- ⬜ Log sources and provenance for every seed query (website, date accessed)

### 2.3 Synthetic training set (silver) ✅

- ✅ `experiments\generate_synthetic.py` writes prompts from the schema (intent, style, phenomenon, number of turns, domain hints from `kg_service_map.json`), validates every answer and keeps the accepted ones in `data\synthetic\synthetic_dialogues.json`
  - Validation: known intent and slots, district in the 25-district list, enum values, extractive slots (`date`, `purpose`, `new_value` …) must be exact substrings of the user's words, no dropped slots, no leaked field names, script matches the style, intent switches carry `previous_intent`
  - Rejected answers go to `rejected.jsonl` with the reason (19 so far: 15 duplicates, 4 slots not allowed)
  - Prompt versions: v2 (KG-grounded, 40 dialogues), v3 (literal examples, 193), v4 (five styles, 40), v5 (support intents, 120)
  - `--intents a,b,c` picks which intents to generate (default: the 8 core intents)
- ✅ **393 dialogues, 977 user turns**, `s0001`–`s0395`: Claude Code 347, Gemini 3.5 Flash Lite 46 (2 more removed by hand)
  - 8 core intents, 29–36 dialogues each, `s0001`–`s0275`
  - Styles: 177 code-mixed, 72 pure Sinhala (incl. 16 romanized Sinhala without English words), 24 English only; 163 romanized, 110 Sinhala script
  - Phenomena: 67 corrections, 41 several slots in one turn, 34 intent switches
- ✅ **Support intents (18 Oct, prompt v5)**: 120 dialogues `s0276`–`s0395`, 30 each for `unsupported_service`, `feedback_complaint`, `general_question` and `out_of_scope`; 251 user turns
  - 120/120 accepted, no rejections
  - Own spec mix: no phenomenon 68, intent switch 31 (to any other intent, e.g. question → apply, greeting → task), correction 21; 1–3 user turns (`out_of_scope` 1–2). No `multi_slot`, since these intents have at most two slots
  - Slots: `service_mentioned` (and `issue` for complaints) in the user's exact words; `out_of_scope` has none. The gold seeds for these intents use normalised values ("fee different"), so the prompt uses 1–2 core seeds for format plus one inline example per intent that follows the literal rule
  - Styles: Singlish 52, Sinhala script + EN 22, romanized Sinhala 20, pure Sinhala 18, English 8
  - Bot turns for unsupported services say the service isn't covered yet and ask at most one follow-up
- ✅ `experiments\tag_synthetic.py` adds word-level language tags
  - `--export` / `--ingest`: an LLM (Claude Code) tags every word; 897 turns tagged this way (251 of them for the support intents)
  - `--to-labelstudio` / `--compare`: 80 turns (418 words) hand-checked in a separate Label Studio project. LLM tags agreed **100%**; the heuristic 94.0% overall but only 88.7% on code-mixed text (`results\synthetic_tag_quality.json`)
  - `--build`: `data\synthetic\silver_tokens.jsonl`, 977 turns / 5,972 tokens in the gold format, all 12 intents. No turn falls back to heuristic tags. Language tags: hand correction > LLM tag > heuristic. Entity spans from slot values
- ✅ Fixes on 16 Oct
  - Two new dialogues had reused IDs `s0234` / `s0235` (IDs were numbered from the count, and 2 dialogues had been removed). Renumbered to `s0274` / `s0275`; the generator now numbers from the highest ID, and `--build` stops if any ID repeats
  - District spans now also match romanized names (Kolamba, Mahanuwara, Galla …) and Sinhala-script names for all 25 districts, with several spellings each (e.g. මොණරාගල / මොනරාගල). District spans: 165 → 222
- Silver stats: SI 3,522 · EN 1,890 · NE 380 · OTHER 165 · MIXED 15 words; entities: district 233 · service_mentioned 107 · purpose 83 · travel_date 67 · date 48 · date_of_birth 38 · issue 33 · new_value 23
- Turns per intent: death_cert_copy 106 · birth_cert_copy 105 · passport_new 98 · marriage_registration 93 · nic_update 93 · nic_replace_lost 91 · nic_new 83 · passport_renew 82 · unsupported_service 60 · general_question 60 · feedback_complaint 55 · out_of_scope 51

**Why synthetic data for training:** hand-writing enough dialogues for a balanced training set was not possible before PP1. LLM-written dialogues are cheap and balanced, and they are kept separate: they are only used for training, never for testing.

### 2.4 Fresh test set ✅

- ✅ 23 dialogues / 50 user turns / 403 words written by the author in `data\fresh_dialogues.txt` after the model design was fixed
- ✅ `experiments\prepare_fresh.py --to-labelstudio` → a new Label Studio project with **no pre-labels**; every word and entity labelled from scratch → `data\fresh_ls_export.json`
- ✅ `prepare_fresh.py --from-export` → `data\fresh_tokens.jsonl` and `results\fresh_baselines.json` (heuristic and fastText scores)

**Why:** the gold labels started from the heuristic's pre-labels, which inflates the heuristic's score on gold (~0.99) and could bias any comparison. A test set labelled from scratch gives a fair comparison (heuristic only 0.773 there).

---

## 3. Annotation & data split 🔄

### What was done
- ✅ Label Studio installed in the `label` env
- ✅ `experiments\prepare_labelstudio.py` — merges the dialogue files and pre-labels:
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
  - ⚠️ `MIXED` has only **1** example (`16i`), and `OTHER` only 11. A classifier cannot learn `MIXED` from one token, and per-class F1 for it is meaningless at this size

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
- ✅ Held-out test sets — done differently from the original plan: **train on synthetic (silver) only, test on all human-written data**
  - Gold set (142 turns) and fresh set (50 turns) are both test-only, so no split of the small manual set was needed
  - The silver set is split 90/10 into train / dev by the training notebook (655 / 71 turns in run 2)
- ✅ Token-classification format: gold, silver and fresh sets all use the same JSONL format (tokens, language tags, BIO entity tags, intent)
- ⬜ Rasa NLU YAML (only if Rasa is used; see §6)

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

### XLM-R language ID ✅ (run 2, 15 Oct)
- ✅ Colab GPU notebook `research\c1_xlmr_train.ipynb`; results saved to `results\xlmr_results_run_1.json`, `results\xlmr_results_run_2.json` and, for the 3-seed runs, `results\xlmr_results_seed{42,1,2}.json`
- ✅ Fine-tuned `xlm-roberta-base` for token classification (`SI` / `EN` / `MIXED` / `NE` / `OTHER`): 8 epochs, batch 16, lr 3e-5, seed 42; each word's label on its first subword
  - Why XLM-R: already pretrained on Sinhala and English; fine-tuning needs far less data than training from scratch
  - Why not fastText alone: it's sentence-level and fails on romanized Sinhala
- ✅ Results, SI/EN words:

  | Test set / style | Heuristic | fastText | XLM-R |
  |---|---|---|---|
  | Fresh, all (n=375) | 0.773 | 0.595 | **0.971** |
  | Fresh, Singlish (164) | 0.829 | 0.262 | **0.945** |
  | Fresh, English only (99) | 0.495 | 0.808 | **0.990** |
  | Fresh, Sinhala script + EN (80) | 0.913 | 0.888 | **0.988** |
  | Fresh, pure Sinhala (32) | 1.000 | 0.906 | **1.000** |
  | Gold, all (n=711) | ~0.99 (inflated by pre-labels) | 0.574 | **0.990** |

  - Run 1 (618 silver turns, no English-only style) scored 0.987 on gold; run 2 added English-only and romanized-Sinhala dialogues
  - Fresh-set errors: EN→SI 4, OTHER→SI 3, EN→NE 3

### To do
- ⬜ Weights & Biases (runs are currently logged only as `results\*.json`)
- ⬜ Decide on `MIXED`: 1 gold, 1 fresh and 7 silver examples. Either add dialogues with mixed words (`16i` / `16යි`, `NIC-eka`) or fold `MIXED` into `SI` for training and report it separately. Record the choice in the decision log
- ✅ 3 seeds (42, 1, 2): fresh SI/EN 0.973 ± 0.005, at code-switch points 0.973 ± 0.007 (`notes.md`, Observation 7)
- ✅ Accuracy at switch points (where the language changes mid-sentence): XLM-R 0.973 at switch points vs 0.974 inside single-language runs on the fresh set; fastText falls to 0.507 at switch points (Observation 7)
- ⬜ Report per-tag scores for SI / EN / NE / OTHER, and state that `MIXED` (1 example per test set) is too rare to evaluate. Seed 2 missed the one `MIXED` word, which alone dropped its gold macro-F1 to 0.78
- ⬜ Error analysis of individual switch-point errors
- ⬜ Wrap as a module: `segment(text) -> [(token, lang)]`, loading `MyDrive/c1_models/run_seed1`

---

## 5. Intent classifier 🔄

- ✅ Model: XLM-R fine-tune (sequence classification), input = full dialogue history up to the turn. Rasa DIET not tried yet
- ✅ Class balance: silver set has 29–36 dialogues per core intent and 30 per support intent
- ✅ Baseline trained (same settings as §4)
- ✅ Results:

  | Test set | n | Accuracy | Macro-F1 |
  |---|---|---|---|
  | Gold, 8 core intents | 70 | 0.943 | 0.944 |
  | Fresh | 50 | 0.900 | — |

  - Gold per style: Singlish 0.912 (34) · Sinhala script + EN 1.000 (14) · pure Sinhala 0.955 (22)
  - Gold errors: `nic_new`→`birth_cert_copy` 2, `passport_renew`→`passport_new` 1, `nic_replace_lost`→`nic_update` 1
  - Run 1 scored 0.957 on gold; the change is within single-seed noise at n=70
- ✅ 3 seeds (42, 1, 2), with a TF-IDF + LogReg baseline (Observation 7):

  | | Gold (n=70) | Fresh (n=50) |
  |---|---|---|
  | XLM-R accuracy | 0.933 ± 0.030 | 0.927 ± 0.023 |
  | XLM-R macro-F1 | 0.936 ± 0.025 | 0.926 ± 0.021 |
  | TF-IDF + LogReg macro-F1 | **0.972** | **0.953 ± 0.014** |

  - **TF-IDF beats XLM-R**: intents are signalled mainly by keywords (passport, NIC, *nathi una* = lost, renew), and with ~650 training turns the transformer gains nothing over keyword features. Reported as a finding, and it makes model cost a second axis of the trade-off in §9
  - **One systematic error:** in every seed, 2 gold `nic_new` turns are predicted as `birth_cert_copy`, most likely because the citizen mentions the birth certificate as a required document. The other errors change from seed to seed
  - The context experiment (§9) showed that switch turns are not the problem: they name the new service in the message. Same-intent follow-ups ("Matara", "ow urgent") are, and they need context
- ✅ Training data for the 4 non-core intents (18 Oct, §2.3), so all 142 gold turns can be scored. Not retrained yet: the results above are 8 core intents only
- ⬜ Tune hyperparameters
- ⬜ Confusion matrix figure for PP1
- ✅ Checkpoints on Drive, not git: `MyDrive/c1_models/run_seed1` is the deployment model (seed 42 models were lost)
- ⬜ Optional: Rasa DIET for comparison

---

## 6. Entity extraction + multi-turn tracking 🔄

- ✅ XLM-R token-classification baseline for entities (BIO tags), scored with **seqeval**:

  | Test set | Support | Precision | Recall | Micro-F1 |
  |---|---|---|---|---|
  | Gold, learnable types | 54 | 0.506 | 0.833 | 0.629 |
  | Gold, all types | 70 | 0.506 | 0.643 | 0.566 |
  | Fresh | 14 | 0.400 | 0.571 | 0.471 |

  - Over-prediction: `district` recall 0.95 but precision 0.61; `travel_date` recall 1.0, precision 0.36
  - `issue` and `service_mentioned` score 0: they only occur in the non-core intents, which have no training data
- ✅ 3 seeds (Observation 7): span micro-F1 **0.528 ± 0.054** gold (0.584 ± 0.063 on types seen in training), **0.394 ± 0.080** fresh. The weakest and least stable part of the engine (gold 0.47–0.57, fresh 0.31–0.47 across seeds)
- ✅ **Hybrid rule-based slot extractor** (`experiments\c1_dst.py`, Observation 9)
  - District gazetteer: all 25 districts in English, Sinhala script and romanized spellings
  - Date pattern matcher (English and Sinhala months, relative dates) → canonical form
  - Keyword rules for fixed-choice slots (`applicant_for`, `change_field`, `urgency`, `service_type`); lists for service, purpose and complaint type
  - Entity span F1 on extractive types: **0.750** gold (precision 1.00) / **0.727** fresh, vs XLM-R NER 0.655 / 0.481
  - ⬜ XLM-R NER + rules combination not yet reported (`dst_eval.py --xlmr-dir models/c1/run_seed1`)
  - ⬜ Synthetic data for the support intents, so `issue` and `service_mentioned` have training examples
- ⬜ Set up Rasa Open Source project inside `components\c1-intent\`
  - Why Rasa: ready-made intent/entity/slot tracking, so effort goes into the code-switching work, not dialogue plumbing
- ⬜ Generate `domain.yml` from `schema_v1.json` (intents, entities, slots)
- ⬜ Configure NLU pipeline (tokenizer, featurizer with XLM-R, DIET classifier)
- ⬜ Train NER and evaluate with **seqeval** (entity-level precision/recall/F1)
  - Why seqeval: scores whole entities, not individual tokens, which is the standard for NER
- ✅ Slot carryover across turns (e.g. turn 1 "NIC eka wenas karanna one", turn 2 "Colombo 7" → fills `district`), using the bot's last question for short answers, yes/no and confirmations
- ✅ Handle corrections ("ne, Gampaha") and intent switches mid-dialogue (after a switch, keep only the slots the new intent uses)
- ✅ Joint goal accuracy (`experiments\dst_eval.py`, gold intent, Observation 9). Gold is the development set for the rules; synthetic and fresh are held out:

  | Tracker setting | Gold (dev, 142) | Synthetic (726) | Fresh (50) |
  |---|---|---|---|
  | No memory | 0.528 | 0.477 | 0.720 |
  | + slot carryover | 0.838 | 0.718 | 0.860 |
  | + bot's question | 0.901 | 0.762 | 0.880 |
  | Full (corrections, switches, negation) | 0.979 | **0.807** | **0.920** |

  - With predicted intent (TF-IDF, window_3): fresh JGA **0.88** (intent accuracy 0.96)
  - Remaining errors: unusual date formats, `new_value` without a bot question (F1 0.56), corrections that give only the new value

---

## 7. FastAPI service + routing 🔄

### What already exists (team skeleton)
- ✅ Service in `components\c1-intent\service\` (FastAPI, port 8001), Dockerfile, CI job running `pytest` in stub mode
- ✅ `GET /health` and `POST /v1/intent` (`app\api\routes.py`, kept thin)
  - Input: `UtteranceRequest` — `session_id`, `text` (1–2000 chars)
  - Output: `Intent` — validated against `contracts\schema\v1\intent.schema.json` (Pydantic model in `shared\helaguide_common\contracts.py`)
- ✅ `app\core\pipeline.py` → `resolve(req)`: in stub mode returns `contracts\examples\intent.example.json`; otherwise raises `NotImplementedError`. **All C1 logic goes behind this function**
- ✅ Shared contract agreed by the team (`contracts\schema\v1\`); the gateway calls C1 → C2 → C3 → C4
- ✅ Tests: `tests\test_health.py`, `tests\test_routes.py` (stub returns `svc:passport`)

### The contract is narrower than our schema
`intent.schema.json` (v1, `additionalProperties: false`) allows only:

| Field | Allowed values |
|---|---|
| `intent` | `apply_service`, `service_info`, `check_requirements`, `unknown` |
| `entities` | `service_id` (`^svc:[a-z0-9_]+$` or null), `district` (or null) — nothing else |
| `language` | `si`, `en`, `ta`, `mixed` |
| `turn_id`, `confidence`, `session_id` | integer ≥ 0, 0–1, string |

So C1 keeps its full 12-intent state internally (PostgreSQL schema `c1`: sessions, turns) and **projects** it onto the contract:

| Our intent (schema 1.1) | Contract `intent` | `entities.service_id` | Gateway result |
|---|---|---|---|
| `nic_new`, `nic_update`, `nic_replace_lost` | `apply_service` | `svc:nic` | plan from C2 |
| `passport_new`, `passport_renew` | `apply_service` | `svc:passport` | plan from C2 |
| `birth_cert_copy` | `apply_service` | `svc:birth_certificate` | plan from C2 |
| `marriage_registration` | `apply_service` | `svc:marriage_registration` (proposed) | plan from C2 once the ID exists |
| `death_cert_copy` | `apply_service` | `svc:death_certificate` (proposed) | plan from C2 once the ID exists |
| `general_question` | `service_info` (or `check_requirements` when it asks about documents/fees) | the mentioned service's ID if it is one of the above, else null | plan if ID set, else 422 |
| `unsupported_service` | `unknown` | null | 422 "Could not identify a service" |
| `feedback_complaint` | `unknown` | null | 422 (see gaps) |
| `out_of_scope` | `unknown` | null | 422 |

- `language`: from the token tags of the turn — only `SI` → `si`, only `EN` → `en`, both → `mixed` (`NE`, `OTHER`, `MIXED` ignored; `MIXED` alone → `mixed`). `ta` is never produced (Tamil is future work).
- `district`: our `district` slot, carried across turns. All other slots stay internal.
- `turn_id`: counts the user's turns in the session (0, 1, 2 …), unlike the seed files, where `turn` counts bot turns too.

**What the contract loses (gaps to raise with the team)**
- **Variant:** `nic_new` / `nic_update` / `nic_replace_lost` all become `svc:nic`, and both passport intents become `svc:passport`. C2 needs `kg_variant` (`first_issue`, `amended`, `lost`, `ordinary`, `replacement`) to pick the right fee and documents, but the contract has no field for it
- **Slots:** `applicant_for`, `service_type`, `urgency`, `travel_date` etc. cannot be sent, although some decide the fee (passport normal/urgent)
- **Fallbacks:** `unsupported_service`, `out_of_scope` and `feedback_complaint` all arrive as `unknown` + null and the gateway answers 422. There is no way to tell the citizen "not supported yet" vs "send this to C3"
- Any fix (e.g. optional `entities.variant`, `entities.service_type`) is a contract change: a PR touching only `contracts\` + `shared\…\contracts.py`, approved by all four owners; breaking changes go in `schema\v2\` (CONTRIBUTING.md)

### To do
- ⬜ `app\core\`: language segmentation → intent + entity extraction → dialogue state → projection to `Intent` (table above), called from `pipeline.resolve()`
- ⬜ Keep stub mode working; the other components and CI test against it
- ⬜ Store sessions and turns in PostgreSQL schema `c1`
- ⬜ Unit tests for the projection: one per row of the table, validated against `intent.schema.json`
- ⬜ Propose the contract additions above (variant, service type, fallback reason) to the team
- ⬜ Log latency per request (needed later for the trade-off curve)
- ⬜ Heavy libraries go in the `research` extra in `pyproject.toml`, not the base dependencies (CI installs `.[dev]` only)

Why FastAPI: fast, async, auto-generates API docs, and the team already uses it as the common serving layer.

---

## 8. PP1 demo & slides ⬜ (due 20 Oct)

- ⬜ Pick demo dialogue (e.g. multi-turn NIC update with a correction)
- ⬜ Test full demo flow end to end
- ⬜ Record a backup demo video
- ⬜ Slides
  - Baseline findings (fastText on romanized Sinhala: 35.2% on gold, 26.2% on the fresh set; XLM-R tokenizer fragmentation)
  - Dataset: gold 70 dialogues / 142 turns, silver 273 / 726, fresh 23 / 50; 12 intents; schema 1.1 mapped to KG service IDs
  - Model results (3 seeds): language ID 0.973 on the fresh set (Singlish 0.955), intent macro-F1 0.936 gold / 0.926 fresh (TF-IDF baseline higher), entity F1 0.53 / 0.39, with the limitations (small test sets, 4 intents not covered)
  - Context strategies: window_3 matches full history with a fixed input size (Observation 8)
  - Progress vs TAF objectives
  - PP2 plan
- ⬜ Rehearse

---

## 9. PP2 — Context optimization & trade-off evaluation 🔄

This is the core research contribution. First experiment done early: `research\c1_context_experiment.ipynb`, 6 strategies × 3 seeds, XLM-R and TF-IDF (`notes.md`, Observation 8; results in `results\c1_context_results_e15.json`).

- ✅ Full-history baseline (control: whole conversation every turn)
- ✅ Sliding-window strategy (window_2, window_3)
- 🔄 Summarization strategy: only a keyword summary (EN/NE words from earlier turns), which scored lowest; LangChain summary / summary-buffer memory not tried
- ✅ Structured-state carryover (previous intent + slots). Uses gold tags (an oracle); repeat with predicted tags
- ✅ Token counting per turn (model tokenizer)
- 🔄 Measure per strategy: intent macro-F1, tokens per turn and GPU/CPU latency done; joint goal accuracy needs slot tracking (§6)
- ✅ Trade-off curve: `results\context_tradeoff_e15.png`, `results\context_token_growth_e15.png`
- 🔄 Error analysis: accuracy by turn type (switch vs same-intent) done; individual switch-turn errors not yet analysed
- **Result:** XLM-R + window_3 is the recommended default: within 0.001 of full history on gold and 0.037 on fresh, with a fixed input size. TF-IDF + structured state or window_2 is the CPU option (about 2 ms per turn)

Why: no existing work measures this trade-off for Sinhala-English code-switched multi-turn dialogue. The curve is the research result.

---

## Git

Team repo: `github.com/Malindup2/HelaGuide`. Rules from `CONTRIBUTING.md`:

- `main` is protected: no direct pushes. One branch per piece of work (`c1/<topic>`), merged by PR once CI passes
- Only change `components\c1-intent\` without approval (CODEOWNERS). `contracts\`, `shared\` and `docs\` are shared; a contract change is its own PR approved by all four owners
- Commit messages: short, present tense, prefixed `c1:` (e.g. `c1: add fastText baseline results`)
- Never commit `.env`, keys, model weights (`*.bin`, `*.safetensors`, `*.ckpt`) or datasets over a few MB; record their location in `research\data\README.md`
- PDFs, Office files and images go through Git LFS (`git lfs install` once per machine)
- No names, NIC numbers, phone numbers or addresses anywhere, including test data and logs
- No Claude co-author lines in commits or PRs

**Branches** (as of 17 Oct 2026). The team merges feature branches into `dev`, and `dev` into `main`.
- **`c1/context-experiment`** (current): branched from `c1/synthetic-data`, 5 commits on top of it. Fresh test set, `c1_xlmr_train.ipynb`, `c1_context_experiment.ipynb`, result files and charts, Observations 7–8. **Pushed**; no PR yet. Open its PR into `dev` after #22 is merged
- `c1/synthetic-data`: includes everything from `c1/seed-dataset`, plus the 16 Oct ID and district fixes. **PR #22 → `dev`**, open, not yet reviewed
- `c1/seed-dataset`: **PR #20 → `main`**, open. Its commits are all in `c1/synthetic-data`, so PR #22 supersedes it; close #20 or retarget it to `dev`
- `research\.gitignore` allows the reported result files and charts in `results\` (`baseline_fasttext.json`, `fresh_baselines.json`, `synthetic_tag_quality.json`, `xlmr_results_run_*.json`, `xlmr_results_seed*.json`, `c1_context_results_e*.json`, `context_*_e*.png`, `dst_results.json`, `run1\`); everything else there stays local

## Files in the project

Paths are relative to `components\c1-intent\`. Full data file descriptions are in `research\data\README.md`.

| File | Purpose | Status |
|---|---|---|
| `CLAUDE.md` | Working rules for Claude Code in this folder | ✅ |
| `research\.gitignore` | Keeps `models\`, unreported `results\` files, backups and regenerated files out of git | ✅ |
| `research\data\README.md` | What every data file is, formats, stats, labelling rules, how to regenerate | ✅ |
| `research\data\schema_v0.json` | First intent schema (kept as record) | ✅ |
| `research\data\schema_v1.json` | Current schema, version 1.1, 12 intents with KG service IDs | ✅ |
| `research\data\kg_service_map.json` | Intent → C2 service ID map, KG attributes, unmapped services | ✅ |
| `research\data\seed_dialogues_*.json` | 70 seed dialogues, 3 styles | ✅ |
| `research\data\labelstudio_config.xml` | Labelling interface | ✅ |
| `research\data\ls_export.json` | Label Studio export, 142 annotated tasks | ✅ |
| `research\data\gold_tokens.jsonl` | Token-level gold set (language + BIO entity tags) | ✅ |
| `research\data\synthetic\synthetic_dialogues.json` | 273 LLM-written training dialogues | ✅ |
| `research\data\synthetic\silver_tokens.jsonl` | Silver training set, 726 turns | ✅ |
| `research\data\synthetic\synthetic_lang_tags.json` | LLM language tags per turn | ✅ |
| `research\data\fresh_dialogues.txt`, `fresh_ls_export.json`, `fresh_tokens.jsonl` | Fresh test set, labelled from scratch | ✅ |
| `research\data\fresh_dialogues.json`, `fresh_ls_tasks.json` | Regenerated by `prepare_fresh.py` (local only) | — |
| `research\data\backup_v0\`, `backup_v1_0\` | Backups before the v1 migration and the 1.1 update (local only) | ✅ |
| `research\data\seed_all.json`, `ls_tasks.json` | Regenerated by `prepare_labelstudio.py` (local only) | — |
| `research\models\lid.176.bin` | fastText language-ID model (local only) | ✅ |
| `research\results\baseline_fasttext.json` | fastText baseline numbers (committed) | ✅ |
| `research\results\xlmr_results_run_1.json`, `_run_2.json` | XLM-R results: language ID, entities, intent (Observations 5, 6) | ✅ |
| `research\results\xlmr_results_seed{42,1,2}.json` | XLM-R and TF-IDF results over 3 seeds (Observation 7) | ✅ |
| `research\results\c1_context_results_e15.json`, `context_*_e15.png` | Context strategies, final run, and its charts (Observation 8) | ✅ |
| `research\results\run1\` | First, under-trained context run (6 epochs) | ✅ |
| `research\results\fresh_baselines.json` | Heuristic and fastText on the fresh set | ✅ |
| `research\results\synthetic_tag_quality.json` | LLM and heuristic tags vs the 80 hand-checked turns | ✅ |
| `research\experiments\migrate_schema_v1.py` | v0 → v1 label migration | ✅ |
| `research\experiments\prepare_labelstudio.py` | Merge + pre-label for Label Studio | ✅ |
| `research\experiments\baseline_fasttext.py` | Export → gold set + fastText baseline | ✅ |
| `research\experiments\check_fixes.py` | Spot-check language tags on English loanwords | ✅ |
| `research\experiments\generate_synthetic.py`, `tag_synthetic.py` | Synthetic data generation and tagging | ✅ |
| `research\experiments\prepare_fresh.py` | Fresh test set → Label Studio (no pre-labels) → tokens + baselines | ✅ |
| `research\c1_xlmr_train.ipynb` | Colab: XLM-R training and evaluation (language ID, intent, entities) | ✅ |
| `research\c1_context_experiment.ipynb` | Colab: context strategies, accuracy vs tokens and latency | ✅ |
| `research\docs\notes.md` | Research observations (1, 2, 4–8) | 🔄 |
| `research\docs\c1_results_log.md` | Results write-up for the report | 🔄 |
| `research\docs\TASKS.md` | Short PP1 task list | 🔄 |
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
| 15 Oct 2026 | Exception: `results\baseline_fasttext.json` is committed | It is small and holds the numbers reported in PP1, so they are traceable in git |
| 15 Oct 2026 | C1 keeps its 12-intent state internally and projects it onto the 4-intent `intent` contract | The shared contract v1 allows only `apply_service` / `service_info` / `check_requirements` / `unknown` and `service_id` + `district`; changing it needs all four owners |
| 15 Oct 2026 | Train on synthetic (silver) data only; all human-written data is test-only | The manual set is too small to split; keeping it out of training gives an honest test |
| 15 Oct 2026 | Silver language tags from an LLM, checked on an 80-turn sample | LLM tags agreed 100% with hand corrections; the heuristic only 88.7% on code-mixed text |
| 15 Oct 2026 | XLM-R (`xlm-roberta-base`) for all three tasks, not Rasa DIET yet | One model family, simple Colab training; Rasa can be compared later |
| 16 Oct 2026 | Fresh test set labelled from scratch, no pre-labels | Gold labels started from heuristic pre-labels, which inflates the heuristic's score (~0.99 on gold vs 0.773 fresh) |
| 16 Oct 2026 | Synthetic dialogue IDs numbered from the highest existing ID; `--build` stops on duplicate IDs | Numbering from the count reused `s0234` / `s0235` after 2 dialogues were removed, mixing up their tags |
| 16 Oct 2026 | District spans match English, romanized and Sinhala-script spellings (lists per district) | Romanized and Sinhala district names were missed; spans 165 → 222 |
| 16 Oct 2026 | Report results as mean ± std over 3 seeds (42, 1, 2) | A single run on small test sets cannot show whether a difference is real |
| 16 Oct 2026 | Add TF-IDF + LogReg as an intent baseline, and report that it beats XLM-R | Intents are keyword-driven; an honest baseline, and model cost becomes a second trade-off axis |
| 16 Oct 2026 | `MyDrive/c1_models/run_seed1` is the deployment model | Best overall (gold intent 0.957, fresh language ID 0.979); seed 42 models were lost from temporary Colab storage |
| 16 Oct 2026 | Context experiment at 15 epochs, best epoch on the dev set; the 6-epoch run is kept in `results\run1\` but not used for conclusions | At 6 epochs XLM-R was under-trained (structured state 0.700 ± 0.168 → 0.878 ± 0.046) |
| 16 Oct 2026 | Default context strategy: XLM-R + window_3; CPU option: TF-IDF + structured state or window_2; never TF-IDF + full history | window_3 is within 0.001 of full history on gold with a fixed input size; TF-IDF drops to 0.683 with full history |
| 16 Oct 2026 | Plan a hybrid entity extractor (gazetteer + date patterns + XLM-R for free text) | XLM-R entities are weak and unstable (gold F1 0.53 ± 0.05), with district and travel_date over-predicted |
| 17 Oct 2026 | Commit the reported result files and charts (`research\.gitignore` exceptions) | The numbers in the docs must be traceable in git |
| 18 Oct 2026 | Hybrid rule-based slot extractor + state tracker instead of XLM-R NER alone | Fresh entity F1 0.73 vs 0.48 |
| 18 Oct 2026 | Fresh-set states proposed by an LLM and checked by the author; gold is the development set for the rules | The rules were written while reading gold, so only synthetic and fresh are held out |
| 18 Oct 2026 | Synthetic data for the 4 support intents (prompt v5) | So all 142 gold turns can be scored and complaints can be routed to C3 |
