# CLAUDE.md · c1-intent

Guidance for Claude Code when working in `components/c1-intent/` of the HelaGuide monorepo.

C1 is the Multilingual Conversational Intent and Entity Understanding Engine: Sinhala,
English and code-switched (including romanized "Singlish") citizen text in, multi-turn
intent and entities out. Owner: Dabarera W. A. S. Port 8001.

## Boundaries

- Edit only inside `components/c1-intent/` unless asked. Other components, `gateway/`,
  `frontend/` and `infra/neo4j/` belong to other team members (see `.github/CODEOWNERS`).
- `contracts/` and `shared/` are shared by all four components. Never edit a released
  schema in `contracts/schema/v1/`; a contract change is its own PR with every owner's
  approval and a matching update to `shared/helaguide_common/contracts.py`.
- C1's output is the `intent` contract (`contracts/schema/v1/intent.schema.json`).

## Commits and PRs

- Do **not** add Claude as a co-author. No `Co-Authored-By: Claude` trailer, no
  "Generated with Claude Code" line, in commits or PR descriptions.
- Prefix commit messages with the area, short and present tense: `c1: add token-level LID dataset`.
- Branch per piece of work (`c1/<topic>`); `main` is protected and merged by PR once CI passes.

## Layout

```
c1-intent/
├── service/              FastAPI app (CI runs pytest here)
│   ├── app/api/routes.py   POST /v1/intent; keep routes thin
│   ├── app/core/           research logic; pipeline.py is the entry point
│   └── tests/
├── stub/                 how stub mode works
└── research/
    ├── data/             schemas, seed dialogues, Label Studio files, gold set (see its README)
    ├── docs/             notes.md, researchOverview.md, technicalWorkFlow.md
    ├── experiments/      data-prep and baseline scripts
    └── diagrams/
```

## Service

Run from `components/c1-intent/service/`:

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e ../../../shared
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8001
pytest
```

- Stub mode (`STUB_MODE=true`) returns `contracts/examples/intent.example.json`. Keep it
  working: the other components and CI (`STUB_MODE=true`) test against it.
- Real logic goes in `app/core/`, behind `pipeline.resolve()`. Planned order: token-level
  language segmentation, then intent classification and entity extraction, then
  multi-turn context handling.
- Heavy libraries (torch, transformers, rasa) go in the `research` extra, never in the
  base dependencies; CI installs only `.[dev]`.

## Research workflow

- Scripts in `research/experiments/` use paths relative to `research/` (`data/`, `models/`,
  `results/`). Run them from `components/c1-intent/research/` in the conda env `nlp`
  (Python 3.10). Label Studio runs in a separate env, `label`. Model training runs on Colab.
- Pipeline: `migrate_schema_v1.py` (done) → `prepare_labelstudio.py` → label in Label
  Studio → export to `data/ls_export.json` → `baseline_fasttext.py` → `data/gold_tokens.jsonl`.
- `research/data/schema_v1.json` is the current intent/slot schema. `schema_v0.json` is a
  record only.
- Update `research/data/README.md` when data files are added or changed, and
  `research/docs/technicalWorkFlow.md` when a task's status or a decision changes.

## Data rules

- Seed dialogue `state` is cumulative per user turn. `turn` indices count bot turns too.
- Tokenisation for labels must match `prepare_labelstudio.words_with_offsets`; one
  language tag per word (`SI`, `EN`, `MIXED`, `NE`, `OTHER`). In Singlish `one` = ඕනේ → `SI`.
- Entities are labelled only where the value appears literally in the user turn; enum
  slots are turn-level labels, not spans.
- Test sets: manual data only, never synthetic; split by dialogue, not by turn; stratify
  by intent and style.
- Token counts for the efficiency study use the tokenizer of the model that processes the
  context, not word counts.
- Keep JSON UTF-8 with Sinhala in script (`ensure_ascii=False`).
- Do not commit model weights (`*.bin`, `*.safetensors`, `*.ckpt`), files over a few MB,
  or regenerated outputs (`seed_all.json`, `ls_tasks.json`, `results/`, `backup_v0/`).
  Record large-file locations in `research/data/README.md`.

## Privacy

Sessions are anonymous (`anon-xxxx`). No real names, NIC numbers, phone numbers or
addresses anywhere: seed data, tests, logs or fixtures. No personal data is used for
training.
