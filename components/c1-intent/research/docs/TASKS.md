# C1 Task List

Short to-do list for C1. The reasons, commands and results are in `technicalWorkFlow.md`.
Tick items here as they finish, then update the Planner card.

**PP1: Tue 20 Oct 2026**

---

## Now: PP1 plan

### Thu 15 Oct: tidy up and unblock
- [ ] Commit and push the latest work (schema 1.1, `kg_service_map.json`, data README, `CLAUDE.md`, `.gitignore`, synthetic scripts)
- [ ] Open the pull request for `c1/seed-dataset` and merge it once CI passes
- [ ] Send `docs/c2_open_questions.md` to Malindu (C2)
- [ ] Finish the synthetic batch: generate, tag, filter by hand
- [ ] Create the held-out test set (manual data only, split by dialogue, stratified by intent and style)

### Fri 16 Oct: language segmentation
- [ ] Set up Colab GPU and W&B
- [ ] Fine-tune XLM-R for token-level language ID on `gold_tokens.jsonl`
- [ ] Compare with fastText on the same test split, per style (target: beat 35.2% on romanized Sinhala)
- [ ] Decide what to do with `MIXED`, which has only 1 example

### Sat 17 Oct: intent classifier
- [ ] Train an XLM-R intent baseline (manual and synthetic training data)
- [ ] Report macro-F1, a confusion matrix, and results per style
- [ ] Save the checkpoint to the team drive, not git

### Sun 18 Oct: plug into HelaGuide
- [ ] Map the 12 internal intents to the contract (`intent` + `service_id`)
- [ ] Implement `resolve()` in `service/app/core/pipeline.py` behind `POST /v1/intent`, keeping stub mode working
- [ ] Add tests in `service/tests/`
- [ ] Run `docker compose up --build` and test one request through the gateway

### Mon 19 Oct: demo and slides
- [ ] Pick the demo dialogue (NIC or passport, since `svc:birth_certificate` has no facts yet)
- [ ] Record a backup demo video
- [ ] Slides: problem, baseline findings, dataset stats, model results, integration, progress vs TAF, PP2 plan

### Tue 20 Oct
- [ ] Rehearse
- [ ] PP1

---

## Next: after PP1
- [ ] Record C2's answers and update the service IDs in `schema_v1.json` and `kg_service_map.json`
- [ ] Decide on a `dual_citizenship` intent
- [ ] Write about 45 more dialogues for the 8 core intents
- [ ] Write `docs/annotation_guidelines.md`
- [ ] Add official Sinhala service names
- [ ] Log sources and provenance for the seed queries
- [ ] Error analysis at switch points
- [ ] Wrap language ID as `segment(text)` in `service/app/core/`
- [ ] Set up the Rasa project: `domain.yml` from the schema, NER plus seqeval
- [ ] Slot carryover, corrections and intent switches
- [ ] Log latency per request
- [ ] Raise a contract change with the team if C2 or C4 need more than `service_id` and `district`

## PP2: context optimization
- [ ] Full-history baseline
- [ ] Sliding window
- [ ] Summarization
- [ ] Structured-state carryover
- [ ] Token counting per turn
- [ ] Joint goal accuracy, tokens and latency per strategy
- [ ] Trade-off curve
- [ ] Error analysis

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
