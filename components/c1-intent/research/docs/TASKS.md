# C1 Task List

Short to-do list for C1. The reasons, commands and results are in `technicalWorkFlow.md`.
Tick items here as they finish, then update the Planner card.

**PP1: Tue 20 Oct 2026**

---

## Now: PP1 plan

### Thu 15 Oct: tidy up and unblock
- [x] Commit and push the latest work (schema 1.1, `kg_service_map.json`, data README, `CLAUDE.md`, `.gitignore`, synthetic scripts)
- [x] Open the pull request for `c1/seed-dataset` (#20 → `main`); later work is on `c1/synthetic-data` (#22 → `dev`)
- [ ] Merge: close #20 or retarget it to `dev` (#22 contains all its commits), and get #22 reviewed
- [ ] Send `docs/c2_open_questions.md` to Malindu (C2)
- [x] Finish the synthetic batch: 273 dialogues, LLM-tagged, 80 turns hand-checked → `silver_tokens.jsonl` (726 turns)
- [x] Test sets: train on silver only; gold (142 turns) and a new fresh set (50 turns, labelled from scratch) are test-only

### Fri 16 Oct: language segmentation
- [x] Colab GPU notebook
- [ ] W&B (results are saved as `results/*.json` for now)
- [x] Fine-tune XLM-R for token-level language ID (on silver, not gold)
- [x] Compare with fastText per style: Singlish 0.945 vs 0.262 on the fresh set (target of beating 35.2% met)
- [ ] Decide what to do with `MIXED` (1 gold, 1 fresh, 7 silver examples)
- [x] Commit the 16–17 Oct work (fresh set, XLM-R and context notebooks, results, docs) on a new branch `c1/context-experiment`
- [x] Push `c1/context-experiment`
- [ ] Open the `c1/context-experiment` PR into `dev` once #22 is merged

### Sat 17 Oct: intent classifier
- [x] Train an XLM-R intent baseline (synthetic training data): 0.943 gold, 0.90 fresh
- [x] Report macro-F1 (0.944) and results per style
- [ ] Confusion matrix figure for the slides
- [x] Save the checkpoint to Drive, not git (`MyDrive/c1_models/run_seed1` is the deployment model; seed 42 models were lost)
- [x] Second and third seed, to show variance (Observation 7: seeds 42, 1, 2)
- [x] Synthetic dialogues for the 4 intents with no training data (`unsupported_service`, `feedback_complaint`, `general_question`, `out_of_scope`): 30 each, `s0276`–`s0395`
- [x] TF-IDF + LogReg intent baseline: 0.972 gold / 0.953 fresh macro-F1, higher than XLM-R (Observation 7)
- [x] Context strategies, 6 × 3 seeds, XLM-R and TF-IDF: XLM-R + window_3 is the default (Observation 8)
- [ ] Tidy `notes.md`: fill the Observation 6 TODO (how the LLM key was used), fix the missing Observation 3, replace the old "Next steps" list

### Sun 18 Oct: plug into HelaGuide
- [x] Map the 12 internal intents to the contract (`intent` + `service_id`): `service/app/core/projection.py` (branch `c1/api`)
- [x] Implement `resolve()` in `service/app/core/pipeline.py` behind `POST /v1/intent`, keeping stub mode working (model: `run_v2_seed1` via `C1_MODEL_DIR`, window_3 context, `use_ner=True`; heavy libraries in the `research` extra)
- [x] C1-only `POST /v1/intent/details` with the route (orchestration / trust_verification / fallback / none) and the full state; in-memory sessions
- [x] Add tests in `service/tests/` (47, pass in stub mode without torch)
- [x] Run instructions for the `nlp` env and `service/scripts/demo_conversation.py` (`README.md`)
- [x] Contract additions written up: `docs/c1_contract_proposal.md`
- [ ] Run `docker compose up --build` and test one request through the gateway

### Mon 19 Oct: demo and slides
- [x] Pick the demo dialogue: `demo_conversation.py` sessions A (NIC lost, correction), B (complaint), C (driving licence), Sinhala script, English
- [ ] Record a backup demo video
- [ ] Slides: problem, baseline findings, dataset stats, model results (3-seed means), context trade-off chart (`results/context_tradeoff_e15.png`), integration, progress vs TAF, PP2 plan

### Tue 20 Oct
- [ ] Rehearse
- [ ] PP1

---

## Next: after PP1
- [ ] Record C2's answers and update the service IDs in `schema_v1.json` and `kg_service_map.json`
- [ ] Decide on a `dual_citizenship` intent
- [ ] Write `docs/annotation_guidelines.md` (start from the tagging guidelines in `data/README.md`)
- [x] Hybrid entity extractor (rules: district gazetteer + date patterns + keyword lists)
- [ ] Combine the hybrid extractor with XLM-R NER for free-text slots (dst_eval.py --xlmr-dir)
- [ ] Per-tag language-ID scores (SI / EN / NE / OTHER); state that `MIXED` is too rare to evaluate
- [ ] Add official Sinhala service names
- [ ] Log sources and provenance for the seed queries
- [x] Language ID at switch points (0.973, same as inside single-language runs; fastText 0.507)
- [ ] Error analysis of individual switch-point errors
- [ ] Wrap language ID as `segment(text)` in `service/app/core/`
- [ ] Set up the Rasa project: `domain.yml` from the schema, NER plus seqeval
- [x] Slot carryover, corrections and intent switches
- [ ] Retrain with support intents using c1_xlmr_train_v2.ipynb (seed 1)
- [ ] Run dst_eval.py --xlmr-dir models/c1/run_v2_seed1
- [ ] Fix DST errors found on held-out sets after PP1 (date formats, number-only corrections, applicant_for overwrite, new_value in first message), then retest on new data
- [x] Log latency per request (one log line per request, no message text)
- [ ] Raise a contract change with the team if C2 or C4 need more than `service_id` and `district`: send `docs/c1_contract_proposal.md`
- [ ] More training data for `feedback_complaint` and `general_question` (only 2 of 6 test complaints recognised; documents questions not recognised), measured on held-out data
- [ ] Store C1 sessions in PostgreSQL schema `c1` (in memory for now)
- [ ] Docker for the real engine (after PP1; the image runs in stub mode only today):
  1. Build arg in `service/Dockerfile` (`ARG C1_EXTRAS=""` → `pip install ".[${C1_EXTRAS}]"`); the default build stays as it is, so the shared compose file and CI are unaffected
  2. A `docker-compose.override.yml` example documented in `README.md`, not committed as a shared file: build with `C1_EXTRAS=research`, mount `research/models/c1/run_v2_seed1` read-only at `/models/c1`, set `STUB_MODE=false` and `C1_MODEL_DIR=/models/c1`
  3. Install torch from the CPU wheel index (`--extra-index-url https://download.pytorch.org/whl/cpu`) so the image is about 1 GB larger instead of 2–5 GB with CUDA; build it once to check

## PP2: context optimization
First experiment done early (Observation 8, `c1_context_experiment.ipynb`): recommended default is XLM-R + window_3.
- [x] Full-history baseline
- [x] Sliding window (window_2, window_3)
- [ ] Summarization (only a keyword summary so far; no LLM summary yet)
- [x] Structured-state carryover (uses gold tags; repeat with predicted tags)
- [x] Token counting per turn (model tokenizer)
- [ ] JGA per context strategy (JGA tool done in dst_eval.py; not yet run per strategy)
- [x] Trade-off curve (`results/context_tradeoff_e15.png`)
- [ ] Error analysis (accuracy by turn type done; switch-turn errors not yet analysed)
- [ ] Structured state and keyword summary with **predicted** tags instead of gold tags
- [ ] Real long conversations (5+ turns) instead of joined 2–3-turn dialogues

---

## Done
- [x] Environment: Miniconda, Python 3.10, `nlp` and `label` envs
- [x] Schema v0 (17 intents), then v1 (12 intents, 3 departments), then v1.1 (C2 service IDs and variants)
- [x] `kg_service_map.json` and `c2_open_questions.md` drafted
- [x] 70 seed dialogues in 3 styles; v0 to v1 migration; Singlish spelling fix
- [x] Label Studio project; all 142 tasks reviewed and exported
- [x] Gold set: 788 tokens, language and BIO entity tags; v0 intent bug fixed
- [x] fastText baseline on the full gold set (35.2% token accuracy on romanized Sinhala)
- [x] Data README, `CLAUDE.md`, `.gitignore`
- [x] Cloned the team repo; first push on `c1/seed-dataset`
- [x] Synthetic generator and LLM tagger; 273 dialogues; silver set (726 turns)
- [x] Fresh test set: 23 dialogues / 50 turns, labelled from scratch; heuristic and fastText baselines on it
- [x] XLM-R run 1 and run 2: language ID, intent, entities (results in `data/README.md` → Results so far)
- [x] Fixed duplicate synthetic IDs (`s0234`/`s0235` → `s0274`/`s0275`) and district spellings (spans 165 → 222)
- [x] Observations 4–6 in `notes.md`
- [x] XLM-R over 3 seeds with a TF-IDF intent baseline (Observation 7)
- [x] Context strategies, accuracy vs tokens and latency (Observation 8)
