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
| Experiment tracking | Weights & Biases |
| Training compute | Google Colab GPU |
| Synthetic data | LLM API (Claude/GPT) |
| Local env | Miniconda, Python 3.10 (`nlp`, `label` envs) |

## 7. How success is measured

- Intent: accuracy, precision, recall, macro-F1, confusion matrix
- Entities: seqeval entity-level F1
- Multi-turn: joint goal accuracy
- Efficiency: tokens per turn, end-to-end latency
- **Main result:** accuracy vs tokens/latency trade-off curve across context strategies
- All results broken down by style (script / Singlish / code-mixed), never one blended number

## 8. Milestones

| Milestone | Date | Status |
|---|---|---|
| TAF (topic assessment) | Jul 2026 | ✅ Approved |
| Literature review (15+ papers) | Before TAF | ✅ / keep updating |
| Proposal presentation | Sep 2026 | ✅ |
| Environment + baseline tests | Oct 2026 | ✅ |
| **PP1** | **20 Oct 2026** | 🔄 |
| PP2 (context optimization + trade-off) | TBD | ⬜ |
| Final report & viva | TBD | ⬜ |

## 9. Planner board (bucket: Multilingual Intent Classification)

| Card | Status | Due |
|---|---|---|
| PP1 – Implementation of Multilingual Intent Classification Engine (milestone) | 🔄 | 10/20 |
| Dataset creation | 🔄 | |
| Annotation & data split | 🔄 | |
| Language segmentation layer | 🔄 | |
| Intent classifier | ⬜ | |
| Entity extractor + multi-turn tracking | ⬜ | |
| FastAPI endpoint + routing | ⬜ | |
| PP1 demo & slides | ⬜ | 10/20 |
| PP2 – Context optimization & evaluation | ⬜ | Later |

## 10. This week's priorities

1. ⬜ Send the 4 KG questions to Thilakumara and get his service IDs
2. ⬜ Write ~45 more dialogues for the 8 core intents
3. 🔄 Finish reviewing labels in Label Studio
4. ⬜ Export data and create the held-out test set
5. ⬜ Train first intent classifier baseline

## 11. Risks

| Risk | Mitigation |
|---|---|
| Not enough labelled data | Three sources: public seed queries, manual dialogues, synthetic LLM data |
| Class imbalance | New batch for core intents only; report macro-F1 |
| Singlish spelling is inconsistent | Include romanized variants; report it separately |
| Teammates' components not ready | Shared JSON schema + mocked services |
| Synthetic data unrealistic | Keep separate; test set uses manual data only |

## 12. Ethics & data

- Only public government information; no internal databases
- No personal data used for training; synthetic data seeded from public service descriptions only
- User testing goes through university ethics clearance with informed consent and data minimization

## 13. Weekly log

| Week | Done | Next |
|---|---|---|
| Early Oct | Env setup, fastText/XLM-R baselines, schema v0, 70 seed dialogues | Labelling |
| 12–13 Oct | Schema v1 (3 departments), migration, Label Studio project (142 tasks), Planner cards | KG questions, new dialogue batch |
| | | |
