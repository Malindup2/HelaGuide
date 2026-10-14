# c3-trust · Civic Trust and Knowledge Verification Engine

**Owner:** J. D. Minuli Pabasara  ·  **Port:** 8003

Uses what citizens report after visiting an office to keep a confidence score for every published fact, and tells the
rest of the system how far each fact can currently be trusted.

| | |
|---|---|
| **Inputs** | `feedback` from C4 (names the fact); free-text feedback as C1 would forward it (C3-private proposal); `fact` lookups from C2 |
| **Outputs** | `trust` to C4 (confidence + warning status) |
| **Stores** | PostgreSQL schema `c3` (its own tables). C3 **owns every fact's confidence and status**; C2's graph holds none. |
| **Stack** | FastAPI, SQLAlchemy + PostgreSQL, sentence-transformers (all-mpnet-base-v2), Gemini (translation, cached) |

## PP1 scope

Implemented: fact registry with version-aware confidence · fact grounding (two input paths) · translation to English ·
explainable trust score (MSRT) · duplicate-aware evidence · confidence update with a decay rate derived from a policy
(calibration-by-design) · confidence exposure with a warning that appears only after repeated drops.

Not yet (planned for PP2): reviewer workflow and verified corrections to C2, pending claims, attack defence.
Not planned: multi-source conflict handling.

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/v1/feedback` | Accept the contract `feedback` message (names the fact) |
| GET | `/v1/trust/{fact_id}` | Current `trust` for one fact |
| POST | `/internal/freetext-feedback` | *C3-private.* Free text, as C1 would forward it |
| GET | `/internal/explain/{fact_id}` | *C3-private.* Percentage, internal status, warning code, reasons |
| POST | `/internal/sync` | *C3-private.* Re-read facts, register new versions |

`/internal/*` only works with `STUB_MODE=false`. With `STUB_MODE=true` (the default) every route answers with the canned
samples in `contracts/examples/`, which is what the other components test against.

## Run locally (from `components/c3-trust/service/`)

```powershell
py -3.13 -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -e ..\..\..\shared
pip install -e ".[dev,research,demo]"
pytest -q                                  # no database, model or key needed
```

The demo needs C3's own database and the model:

```powershell
cd ..                                      # components/c3-trust
docker compose -f docker-compose.c3.yml up -d
cd service
copy .env.example .env                     # then edit .env
python -m app.cli.check_model              # downloads the model once
python -m app.cli.demo --pause             # the PP1 demonstration
```

No Docker? `python -m app.cli.demo --sqlite` runs the same demo on an in-memory database.

The real HTTP service: `$env:STUB_MODE="false" ; uvicorn app.main:app --reload --port 8003`, then open
<http://localhost:8003/docs>.

## Command-line tools (`python -m app.cli.<name>`)

| Tool | What it does |
|---|---|
| `demo` | The PP1 demonstration in seven parts (`--pause`, `--part`, `--path freetext\|structured\|both`) |
| `reset` | Back to the clean starting state |
| `check_model` | Checks the embedding model loads and ranks related text higher |
| `check_gemini` | Checks the Gemini key and translates three samples (`--models` lists usable models) |
| `translate_cache` | Refreshes the translation cache with Gemini. Resumable and paced under the free-tier limit (`--overwrite`, `--limit N`, `--pause S`, `--dry-run`, `--compare`) |
| `tune_grounding` | Finds grounding thresholds for your model from the labelled messages |
| `show` | Read-only view of what C3 stores right now: table sizes, every fact whose confidence moved, and one fact in detail (`--fact`). Use `reset` then `show` for BEFORE, `demo` then `show` for AFTER |
| `export_ddl` | Prints the PostgreSQL table definitions (for `infra/postgres` at integration) |

## Layout

```
c3-trust/
├── docker-compose.c3.yml   C3's own PostgreSQL (port 5433), independent of the team stack
├── db/init/                one-line schema bootstrap
├── service/                FastAPI app
│   ├── .env.example        copy to .env (git ignores .env)
│   ├── app/api/            routes (kept thin)
│   ├── app/core/           the research logic (see the module docstrings)
│   ├── app/cli/            the demo and tools
│   ├── app/models/         component-internal models
│   └── tests/
├── stub/                   how stub mode works
└── research/
    ├── data/mock/          the PP1 mock data (see research/data/README.md)
    └── experiments/        the demo notebook; out/ holds generated charts (not committed)
```

`app/core` modules: `config` (every parameter) · `db`, `repo` (storage) · `factsource` (file now, C2's HTTP route at
integration) · `registry` (Module R) · `grounding` (Module A) · `normaliser` (translation) · `trust` (Algorithm 1) ·
`dedup` (Algorithm 3a) · `confidence` (Algorithm 2) · `exposure` (Algorithm 6) · `pipeline` (the whole flow).
