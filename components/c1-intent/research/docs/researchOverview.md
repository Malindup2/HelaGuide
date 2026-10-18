# Research Overview & Task Tracker

**Student:** Dabarera W.A.S. (IT23175648)
**Project ID:** J26-SE-354 · IT4010 Research Project (2026 Jul batch)
**Group project:** AI-Driven Citizen-Service Orchestrator for Urban Sri Lanka
**My component:** Multilingual Conversational Intent & Entity Understanding Engine
**Supervisor:** Mr. Jeewaka Perera · **Co-supervisor:** Ms. Poojani Gunathilake
**Research group:** CoEAI (Centre of Excellence for AI) · **Specialization:** SE

Detailed technical steps live in `technicalWorkFlow.md`.

---

## 1. The research in one paragraph

Sri Lankan citizens mix Sinhala and English in the same sentence, often typing Sinhala in English letters (Singlish), and they give information across several messages. Current government channels like GIC-1919 (1.8M calls a year) treat each message in isolation. My engine takes a citizen's code-switched, multi-turn conversation and turns it into a structured request (intent + entities + dialogue state) for the rest of the system, while keeping token usage and latency low enough to run at national scale.

## 2. The gap

| Area | What exists | What's missing |
|---|---|---|
| Code-switching NLP | Single-message tasks (classification, keyword extraction) | Multi-turn intent/entity tracking |
| Dialogue state tracking | Mature, but English-only (MultiWOZ, SGD) | Code-switched, low-resource languages |
| Multi-turn efficiency | KV-cache work (CachedAttention, SwiftCache, LoopServe) | Any test on code-switched input |
| SinLlama | Sinhala-specific LLM beats general models | Single-turn, no code-switching, no entities |

**Novelty:** no work evaluates Sinhala-English code-switched, multi-turn intent/entity tracking together with a measured accuracy-vs-efficiency trade-off.

## 3. Objectives

**Main:** build a multilingual engine that understands multi-turn Sinhala-English citizen requests, with token usage and latency treated as design constraints alongside accuracy.

1. Language segmentation layer (token-level Sinhala-English identification)
2. Intent classification + entity extraction across turns
3. Context/token optimization (compare strategies, measure the trade-off)
4. Routing to Orchestration and Trust Verification engines

## 4. Scope

- **In:** Sinhala-English, in Sinhala script, Singlish, and mixed; text input; three departments (Registration of Persons, Immigration & Emigration, Registrar General)
- **Out (future work):** Tamil, voice input, services outside the three departments (handled as `unsupported_service`)

## 5. Team & dependencies

| Member | Component | How it connects to mine |
|---|---|---|
| Thilakumara M.P. | Knowledge Graph & service orchestration | My intents must map to his service IDs; I send structured requests to his engine |
| J.D. Minuli Pabasara | Civic Trust & Knowledge Verification | I route `feedback_complaint` messages to her engine |
| Dias K.S.S. | Adaptive Accessibility & Presentation | Presents the results to the citizen |

Shared: one JSON schema across all four engines, FastAPI serving, Docker deployment.

## 6. Tech stack (summary)

| Purpose | Tool |
|---|---|
| Language ID baseline | fastText lid.176 |
| Language segmentation | XLM-RoBERTa (fine-tuned), IndicNLP |
| Dialogue scaffold | Rasa Open Source |
| Intent & entities | HuggingFace Transformers, spaCy, seqeval |
| Context strategies | LangChain memory, tiktoken |
| Serving | FastAPI, Docker |
| Annotation | Label Studio |
| Experiment tracking | Results JSON files in `results\` (Weights & Biases planned) |
| Training compute | Google Colab GPU |
| Synthetic data | Claude Code and Gemini 3.5 Flash Lite, validated by script |
| Local env | Miniconda, Python 3.10 (`nlp`, `label` envs) |

## 7. How success is measured

- Intent: accuracy, precision, recall, macro-F1, confusion matrix
- Entities: seqeval entity-level F1
- Multi-turn: joint goal accuracy
- Efficiency: tokens per turn, end-to-end latency
- **Main result:** accuracy vs tokens/latency trade-off curve across context strategies
- All results broken down by style (script / Singlish / code-mixed), never one blended number

### Where things stand (18 Oct 2026)

XLM-R values are mean ± std over 3 seeds (42, 1, 2).

| | Result | Test set |
|---|---|---|
| Language ID (SI/EN words) | XLM-R **0.973 ± 0.005** vs fastText 0.595 vs heuristic 0.773 | Fresh, 375 words |
| Language ID on Singlish | XLM-R **0.955 ± 0.009** vs fastText 0.262 | Fresh, 164 words |
| Language ID at code-switch points | XLM-R **0.973 ± 0.007** vs fastText 0.507 | Fresh |
| Intent macro-F1 (8 core intents) | XLM-R 0.936 ± 0.025; TF-IDF + LogReg **0.972** | Gold, 70 turns |
| Intent macro-F1 | XLM-R 0.926 ± 0.021; TF-IDF + LogReg **0.953 ± 0.014** | Fresh, 50 turns |
| Entities (span micro-F1, all types) | XLM-R 0.528 ± 0.054 gold; 0.394 ± 0.080 fresh; hybrid: 0.75 gold / 0.73 fresh (extractive types) | Gold / fresh |
| JGA (full tracker, gold intent) | synthetic 0.807, fresh 0.920 (held out); fresh with predicted intent 0.88; gold 0.979 is the development set | Synthetic 726 / fresh 50 / gold 142 turns |
| Context strategy (sessions) | XLM-R + window_3: 0.896 gold, 0.898 fresh macro-F1 at ~30 tokens/turn (full history 42–55 tokens/turn) | Gold / fresh sessions |

Data: 70 hand-written gold dialogues (142 turns), 273 synthetic training dialogues (726 turns),
23 fresh hand-written test dialogues (50 turns). Full tables in `notes.md` (Observations 7–9)
and `research\data\README.md` → Results so far.

## 8. Milestones

| Milestone | Date | Status |
|---|---|---|
| TAF (topic assessment) | Jul 2026 | ✅ Approved |
| Literature review (15+ papers) | Before TAF | ✅ / keep updating |
| Proposal presentation | Sep 2026 | ✅ |
| Environment + baseline tests | Oct 2026 | ✅ |
| Datasets (gold, silver, fresh) | 14–16 Oct 2026 | ✅ |
| First XLM-R models (language ID, intent, entities) | 15 Oct 2026 | ✅ |
| **PP1** | **20 Oct 2026** | 🔄 |
| PP2 (context optimization + trade-off) | TBD | ⬜ |
| Final report & viva | TBD | ⬜ |

## 9. Planner board (bucket: Multilingual Intent Classification)

| Card | Status | Due |
|---|---|---|
| PP1 – Implementation of Multilingual Intent Classification Engine (milestone) | 🔄 | 10/20 |
| Dataset creation | ✅ | |
| Annotation & data split | ✅ | |
| Language segmentation layer | 🔄 (model trained and evaluated over 3 seeds; `segment(text)` module pending) | |
| Intent classifier | 🔄 (XLM-R over 3 seeds + TF-IDF baseline; 4 support intents have no training data) | |
| Entity extractor + multi-turn tracking | 🔄 (hybrid extractor done: entity F1 0.75 gold / 0.73 fresh vs XLM-R 0.655 / 0.481) | |
| FastAPI endpoint + routing | 🔄 (skeleton + stub; `resolve()` not implemented) | 10/18 |
| PP1 demo & slides | ⬜ | 10/20 |
| PP2 – Context optimization & evaluation | 🔄 (6 strategies × 3 seeds, tokens, latency, trade-off curve done; JGA, LLM summary, predicted tags, long conversations pending) | Later |

## 10. This week's priorities

1. ⬜ Send `c2_open_questions.md` to Malindu (C2) and get the service IDs confirmed
2. ✅ ~~Write ~45 more dialogues for the 8 core intents~~ — 273 synthetic dialogues instead
3. ✅ Finish reviewing labels in Label Studio
4. ✅ Export data and create test sets (gold + fresh, both test-only)
5. ✅ Train first intent classifier baseline; 3 seeds and a TF-IDF baseline (Observation 7)
6. ✅ Context strategies experiment: window_3 chosen as the default (Observation 8)
7. ⬜ Plug the models into `POST /v1/intent` behind `pipeline.resolve()`
8. ⬜ PP1 demo dialogue, backup video and slides

## 11. Risks

| Risk | Mitigation |
|---|---|
| Not enough labelled data | Three sources: manual gold dialogues, synthetic LLM data (silver), a fresh hand-labelled test set |
| Class imbalance | Synthetic batch balanced across the 8 core intents (29–36 dialogues each); report macro-F1 |
| 4 intents have no training data | Next synthetic batch: `unsupported_service`, `feedback_complaint`, `general_question`, `out_of_scope` |
| Singlish spelling is inconsistent | Include romanized variants; report it separately |
| Teammates' components not ready | Shared JSON schema + mocked services |
| Synthetic data unrealistic | Train on synthetic only, test only on human-written data (gold + fresh) |
| Small test sets | Results now reported as mean ± std over 3 seeds; test sets are still small (about ±2 pts language ID, ±8 pts fresh intent) |
| Entity extraction was weak with XLM-R alone (0.53 / 0.39) | Hybrid extractor built: 0.75 / 0.73 on extractive types (Observation 9) |

## 12. Ethics & data

- Only public government information; no internal databases
- No personal data used for training; synthetic data seeded from public service descriptions only
- User testing goes through university ethics clearance with informed consent and data minimization

## 13. Weekly log

| Week | Done | Next |
|---|---|---|
| Early Oct | Env setup, fastText/XLM-R baselines, schema v0, 70 seed dialogues | Labelling |
| 12–13 Oct | Schema v1 (3 departments), migration, Label Studio project (142 tasks), Planner cards | KG questions, new dialogue batch |
| 14 Oct | Gold set final (788 tokens); fastText baseline (35.2% on Singlish); schema 1.1 mapped to C2 service IDs; C2 questions drafted; work moved into the team repo | Synthetic data |
| 15 Oct | 273 synthetic dialogues, LLM language tags (100% on an 80-turn check), silver set; first XLM-R models (run 1) | Fresh test set |
| 16 Oct | Fresh test set (50 turns, labelled from scratch); run 2: language ID 0.971, intent 0.943 gold / 0.90 fresh; synthetic ID and district fixes | Service integration, PP1 slides |
| 17 Oct | XLM-R over 3 seeds + TF-IDF intent baseline (Observation 7); context strategies, 6 × 3 seeds, window_3 chosen as default (Observation 8); `c1/context-experiment` pushed | Service integration, PP1 slides |
| 18 Oct | Hybrid slot extractor + dialogue state tracker, JGA evaluation, fresh states labelled (Observation 9) | Retrain with support intents (v2 notebook), service integration, PP1 slides |
