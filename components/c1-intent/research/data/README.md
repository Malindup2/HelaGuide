# Data

Small files only (under a few MB). Large datasets, raw crawls and model weights stay
**out of git**. Store them on the team drive and record the location here:

| Dataset | Location | Owner | Notes |
|---|---|---|---|
| fastText language-ID model `lid.176.bin` (~126 MB) | `research/models/lid.176.bin` on the local machine; not in git (`*.bin` is ignored) | Dabarera | Download from <https://fasttext.cc/docs/en/language-identification.html>. Needed only by `baseline_fasttext.py` |
| Label Studio project "CS-Intent Seed" (142 tasks) | Local Label Studio instance (conda env `label`) | Dabarera | `ls_export.json` below is the committed snapshot of it |
| Pre-migration dialogue backups | `research/data/backup_v0/` on the local machine; not in git | Dabarera | Written by `migrate_schema_v1.py` before it edits files in place |
| Schema 1.0 backups | `research/data/backup_v1_0/` on the local machine; not in git | Dabarera | `schema_v1.json` and `seed_dialogues_*.json` as they were before the 1.1 update (2026-10-14) |

## Files in this folder

| File | What it is | Produced by |
|---|---|---|
| `schema_v0.json` | First intent/slot draft: 17 intents, including six services outside the KG. Kept as a record | Hand-written |
| `schema_v1.json` | **Current schema, version 1.1.** 12 intents scoped to the three KG departments, each core intent with its C2 `kg_service_id` and `kg_variant`; slot types, routes, token language tags, open questions for C2 | Hand-written; KG ids from `kg_service_map.json` |
| `seed_dialogues_v0.json` | 10 dialogues `d001`–`d010` (8 romanized, 2 Sinhala script), 25 user turns | Hand-written, migrated to v1.1 |
| `seed_dialogues_v1.json` | 40 dialogues `d011`–`d050` (28 romanized, 12 Sinhala script), 77 user turns | Hand-written, migrated to v1.1 |
| `seed_dialogues_v2_pure_si.json` | 20 dialogues `d051`–`d070`, pure Sinhala script (`code_mix: "pure_si"`), 40 user turns | Hand-written against v1 |
| `labelstudio_config.xml` | Label Studio interface: one language tag per word, plus entity spans | Hand-written |
| `ls_export.json` | Label Studio JSON export, 142 tasks (one per user turn), all annotated | Label Studio → Export → JSON |
| `gold_tokens.jsonl` | Token-level gold set, one line per user turn: tokens, language tags, BIO entity tags | `baseline_fasttext.py` |
| `kg_service_map.json` | The 8 core intents mapped to C2 service ids (confirmed or proposed), which attributes the KG holds for each, source pages, and the KG services no intent covers | Hand-built from C2's committed files, 2026-10-14 |
| `synthetic/synthetic_dialogues.json` | 273 LLM-written training dialogues (`s0001`–`s0275`, 8 core intents, ~35 each), 726 user turns | `generate_synthetic.py` (Claude Code 227, Gemini 3.5 Flash Lite 46) |
| `synthetic/silver_tokens.jsonl` | Training set in the gold format: 726 turns, 4,368 tokens. Language tags from the LLM (646 turns) or hand-checked (80); entity spans from slot values | `tag_synthetic.py --build` |
| `fresh_dialogues.txt` / `.json` | Fresh test set: 23 dialogues written by the author after the model was designed, 50 user turns | Hand-written; `prepare_fresh.py` |
| `fresh_ls_export.json` | Label Studio export of the fresh set, labelled from scratch (no pre-labels) | Label Studio |
| `fresh_tokens.jsonl` | Fresh test set in the gold format: 50 turns, 403 tokens | `prepare_fresh.py --from-export` |

All files are UTF-8. Sinhala text is stored in Sinhala script, not escaped.

## Schema 1.1 and the KG

Schema 1.1 (2026-10-14) links each core intent to a C2 service using `kg_service_map.json`:

| Intent | `kg_service_id` | `kg_variant` | Status |
|---|---|---|---|
| `nic_new` · `nic_update` · `nic_replace_lost` | `svc:nic` | `first_issue` · `amended` · `lost` | confirmed |
| `passport_new` · `passport_renew` | `svc:passport` | `ordinary` · `replacement` | confirmed |
| `birth_cert_copy` | `svc:birth_certificate` | none | confirmed, no facts yet |
| `marriage_registration` | `svc:marriage_registration` | none | **proposed**, to agree with C2 |
| `death_cert_copy` | `svc:death_certificate` | none | **proposed**, to agree with C2 |

The passport `service_type` slot is now `normal` / `urgent`, matching C2's passport
vocabulary; "one day service" in user text maps to `urgent`. The two seed dialogues that
used `one_day` (`d002`, `d018`) were updated; only state values changed, never user text.
NIC speed stays in the separate `urgency` slot, since C2 keeps NIC `one_day` as its own
qualifier.

## Current dataset (schema v1.1)

70 dialogues, 142 user turns, 788 tokens.

| | |
|---|---|
| Style | 102 turns code-mixed (romanized or Sinhala script with English), 40 turns pure Sinhala |
| Language tags | SI 513 · EN 198 · NE 65 · OTHER 11 · MIXED 1 |
| Entities | district 37 · issue 10 · new_value 5 · service_mentioned 6 · travel_date 5 · purpose 4 · date 3 |
| Turns per intent | unsupported_service 54 · nic_update 16 · birth_cert_copy 11 · feedback_complaint 9 · passport_renew 9 · nic_replace_lost 8 · nic_new 8 · passport_new 7 · marriage_registration 6 · death_cert_copy 5 · general_question 5 · out_of_scope 4 |
| Phenomena tagged | correction 9 · intent_switch 5 · long_dialogue 2 · colloquial_term 1 · greeting_then_task 1 |

`unsupported_service` is over a third of all turns because v0 had six out-of-KG services.
The next dialogue batch is core intents only, to fix the imbalance.

## Formats

### Seed dialogues

```json
{
  "dialogue_id": "d001",
  "script": "romanized",            // or "sinhala"
  "code_mix": "pure_si",            // optional; missing means "mixed"
  "route": "fallback",              // optional; set when a turn is not plain orchestration
  "phenomena": ["correction"],      // optional
  "turns": [
    { "speaker": "user", "text": "...",
      "state": { "intent": "nic_update", "slots": { "change_field": "address" } } },
    { "speaker": "bot",  "text": "..." }
  ]
}
```

- `state` on a user turn is the **cumulative** dialogue state after that turn, not just what
  the turn added.
- `previous_intent` is set on the turn where the user switches intent.
- `original_intent` / `original_slots` hold the v0 label for turns that the v1 migration
  folded into `unsupported_service`, so the migration can be undone.

### `gold_tokens.jsonl`

```json
{"dialogue_id": "d001", "turn": 2, "intent": "nic_update", "code_mix": "mixed",
 "text": "No. 45, Galle Road, Colombo 3",
 "tokens": ["No", "45", "Galle", "Road", "Colombo", "3"],
 "lang_tags": ["SI", "OTHER", "NE", "EN", "NE", "OTHER"],
 "ner_tags": ["B-new_value", "I-new_value", "I-new_value", "I-new_value", "I-new_value", "I-new_value"]}
```

`turn` is the index in the dialogue's `turns` list, counting bot turns, so user turns are
0, 2, 4, … `intent` is taken from the current dialogue files, not from the Label Studio task,
so it always follows the latest schema.

## Labelling rules

- **Language tags, one per word:** `SI` Sinhala (either script, including Singlish), `EN`
  English, `MIXED` one word combining both (e.g. `16i`), `NE` names and places that are
  neither clearly Sinhala nor English, `OTHER` numbers and symbols.
- In Singlish, `one` is usually ඕනේ (need) and is tagged `SI`.
- **Entities** are labelled only where the value literally appears in that user turn.
  Enum slots (`applicant_for`, `urgency`, `service_type`, `change_field`) are turn-level
  labels in the dialogue JSON and are never highlighted.
- Intents are not labelled in Label Studio; they live in the dialogue JSON, so a schema
  change does not require relabelling.

## Language tagging guidelines

Decisions for cases the tag definitions above leave open. They were applied to the
synthetic tags in `synthetic/synthetic_lang_tags.json` (`prompt_version: "tag-v1"`,
2026-10-15).

| Case | Tag | Examples |
|---|---|---|
| Any word in Sinhala script, including English loanwords and month names | `SI` | විසා, ලේක්, ජූනි, දෙසැම්බර් |
| `one` meaning ඕනේ ("need") | `SI` | mata NIC eka ganna **one** |
| `one` in "one day (service)" | `EN` | **one** day service eken |
| Place names, in either script, also with a Sinhala case ending | `NE` | ගාල්ලේ, වවුනියාවේ, නුවරඑළියේදී, lankawe |
| People's names, including initials | `NE` | S M Nadeesha Perera, එච් එම් සඳමාලි කුමාරි |
| A number with a Sinhala suffix | `MIXED` | 16i, 17i, 16යි |
| Grama Niladhari (an official's title, not a name) | `SI` `SI` | |

English words written in Latin letters stay `EN`, including month names (`march`, `dec`)
and generic place words (`district`, `road`, `hospital`).

## Regenerating

Run from `components/c1-intent/research/`. The scripts use paths relative to that folder
(`data/`, `models/`, `results/`).

```bash
conda activate nlp
python experiments/migrate_schema_v1.py     # v0 -> v1 intents, edits seed_dialogues_* in place (already done)
python experiments/prepare_labelstudio.py   # -> data/seed_all.json, data/ls_tasks.json
# label in Label Studio, then Export -> JSON -> data/ls_export.json
python experiments/baseline_fasttext.py     # -> data/gold_tokens.jsonl, results/baseline_fasttext.json (needs seed_all.json)
python experiments/check_fixes.py           # spot-check language tags on known English loanwords
```

`seed_all.json` and `ls_tasks.json` are regenerated outputs and are not committed. In
`results/`, only `baseline_fasttext.json` is committed, so the reported baseline numbers
are in git; other result files stay local.
Import `ls_tasks.json` into Label Studio only when setting up a new project: the tasks carry
heuristic pre-labels, not the corrected labels, and importing them into "CS-Intent Seed"
would add 142 duplicate tasks. `baseline_fasttext.py` stops if `seed_all.json` is missing,
so the gold set cannot silently pick up the outdated intents in the export.

## Results so far

From `results/xlmr_results_run_2.json` (run 2, 2026-10-15) and `results/fresh_baselines.json`.
Result files by observation in `docs/notes.md`: `xlmr_results_run_1.json` = Observation 5 (first XLM-R run, 618-turn silver set) · `xlmr_results_run_2.json` = Observation 6 (seed 42, first fresh-set run) · `xlmr_results_seed{42,1,2}.json` = Observation 7 (3 seeds) · `c1_context_results_e15.json` = Observation 8 (`run1/…_e6.json` is its under-trained first run).
Model: `xlm-roberta-base`, 8 epochs, batch 16, lr 3e-5, seed 42; one model per task (language ID,
entities, intent). Trained on the silver set only (655 train / 71 dev turns); tested on the gold set
(142 turns) and the fresh set (50 turns), neither of which was used for training.

### Language ID on the fresh set (SI/EN words only)

The fresh set was labelled from scratch, without the heuristic pre-labels, so it is the fairest
test of all three methods.

| Style | n | Heuristic | fastText | XLM-R |
|---|---|---|---|---|
| **All** | 375 | 0.773 | 0.595 | **0.971** |
| Code-mixed, romanized (Singlish) | 164 | 0.829 | 0.262 | **0.945** |
| English only | 99 | 0.495 | 0.808 | **0.990** |
| Code-mixed, Sinhala script | 80 | 0.913 | 0.888 | **0.988** |
| Pure Sinhala | 32 | **1.000** | 0.906 | **1.000** |

XLM-R on all five tags (incl. `NE`, `OTHER`, `MIXED`): 0.963. Most common errors: EN→SI (4),
OTHER→SI (3), EN→NE (3).

### Gold set (142 turns)

| | XLM-R | Note |
|---|---|---|
| Language ID, SI/EN (n=711) | 0.990 | Singlish 0.986 · Sinhala script + EN 0.992 · pure Sinhala 1.000 |
| Language ID, all tags | 0.991 | |
| fastText, SI/EN (for comparison) | 0.574 | Singlish 0.352 (`results/baseline_fasttext.json`) |

The heuristic scores ~0.99 on the gold set but only 0.773 on the fresh set: the gold labels
started from its pre-labels, so that number is inflated.

### Intent (full dialogue history as input)

| Test set | n | Accuracy | Macro-F1 |
|---|---|---|---|
| Gold, 8 core intents | 70 | 0.943 | 0.944 |
| Fresh | 50 | 0.900 | — |

Gold errors: `nic_new`→`birth_cert_copy` (2), `passport_renew`→`passport_new` (1),
`nic_replace_lost`→`nic_update` (1). In run 1, 2 of 3 errors followed an intent switch
(birth certificate → NIC), where the earlier part of the conversation misleads a model that
reads the whole history (`docs/notes.md`, Observations 5–6).

### Entities (seqeval, entity level)

| Test set | Support | Precision | Recall | Micro-F1 |
|---|---|---|---|---|
| Gold, learnable types | 54 | 0.506 | 0.833 | 0.629 |
| Gold, all types | 70 | 0.506 | 0.643 | 0.566 |
| Fresh | 14 | 0.400 | 0.571 | 0.471 |

`district` is found almost always (gold recall 0.95) but also over-predicted (precision 0.61);
`travel_date` likewise (recall 1.0, precision 0.36). `issue` and `service_mentioned` score 0
because they never occur in the training data.

### Limitations

- This section is one run with one seed. Mean ± std over 3 seeds is in `docs/notes.md`, Observation 7.
- Small test sets. Rough 95% ranges: ±2 points for fresh language ID (375 words), about ±8 for
  fresh intent (50 turns), and entity F1 on 14 fresh entities is indicative only.
- 72 of 142 gold turns use intents with no training data (`unsupported_service` 54,
  `feedback_complaint` 9, `general_question` 5, `out_of_scope` 4), so they are not scored.
- `MIXED` has 1 gold, 1 fresh and 7 silver examples, so the model cannot really learn it.
- Training data is LLM-written; the fresh set is the check that results carry over to human text.
- Run 1 (`xlmr_results_run_1.json`, 618 silver turns) scored intent 0.957 on gold; the drop to
  0.943 in run 2 is within single-seed noise at n=70.
- The result files and charts named above are committed; other files in `results/` stay local
  (see `research/.gitignore`). Model checkpoints are on Google Drive, not in git.

## Known issues

- The Label Studio tasks were created before the v1 migration, so `ls_export.json` still
  carries v0 intents (54 tasks show one of the six retired services). This does not affect
  `gold_tokens.jsonl`, which takes intents from the dialogue files via `seed_all.json`.

## Privacy

All dialogues are written by hand. No real citizen data. Names, NIC numbers, phone
numbers and real addresses must not be added, including as slot values.
