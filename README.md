# HelaGuide

**AI-Driven Citizen-Service Orchestrator for Urban Sri Lanka**  ·  Project J26-SE-354
Faculty of Computing, Sri Lanka Institute of Information Technology

A citizen asks, in Sinhala, English or a mix of both, how to get something done. HelaGuide
works out which government services are involved, puts them in the order they have to be
completed, and presents the steps in a way that suits that person, while keeping every
fee and requirement current with the agencies' own published pages.

## Team

| Component | Engine | Member |
|---|---|---|
| **C1** | Multilingual Conversational Intent and Entity Understanding | Dabarera W. A. S. |
| **C2** | Knowledge Graph and Service Orchestration | T. Malindu Pabasara |
| **C3** | Civic Trust and Knowledge Verification | J. D. Minuli Pabasara |
| **C4** | Context-Aware Adaptive Guidance Presentation | Dias K. S. S. |

Supervisor: Mr. Jeewaka Perera  ·  Co-supervisor: Ms. Poojani Gunathilake

## How the system works

```
                 citizen text
                      │
   frontend ──► gateway ──► C1 intent ──► C2 plan ──► C3 trust ──► C4 render ──► frontend
                                            ▲                                        │
                                            │                                   feedback
                  government pages ─────────┤                                        │
                  (scheduled crawl)         │                                        ▼
                                            └──────── verified correction ◄────── C3
```

| Component | Takes in | Gives out |
|---|---|---|
| **C1** | Raw citizen text | `intent`: the identified service and entities |
| **C2** | `intent`; government pages; `correction` | `plan`: ordered steps with agency, fee, documents; `fact` lookups |
| **C3** | `feedback` | `trust` score per fact; `correction` when verified |
| **C4** | `plan` + `trust` + behavioural signals | `render`: the plan adapted for this citizen |

Every payload is defined in [`contracts/`](contracts/). Every fact carries a stable
`fact_id`, its `source_url` and `retrieved_at`.

## Repository layout

```
HelaGuide/
├── docs/            team-level material: proposal, templates, architecture
├── contracts/       the shared interface: JSON schemas, examples, naming rules
├── components/
│   ├── c1-intent/           each component holds its own
│   ├── c2-knowledge-graph/    service/   FastAPI app
│   ├── c3-trust/              stub/      how stub mode works
│   └── c4-presentation/       research/  docs, diagrams, data, experiments
├── gateway/         the only backend the frontend calls
├── frontend/        citizen-facing app
├── shared/          helaguide_common: config, logging, contract models
├── infra/           Neo4j constraints, PostgreSQL schema
└── scripts/         contract validation, dev setup
```

## Quick start

Requires Docker.

```bash
cp .env.example .env
docker compose up --build
```

| | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Gateway health, all components | <http://localhost:8000/health/all> |
| Gateway API docs | <http://localhost:8000/docs> |
| C1 · C2 · C3 · C4 docs | <http://localhost:8001/docs> · `8002` · `8003` · `8004` |
| Neo4j browser | <http://localhost:7474> |

Everything starts in **stub mode**: each component answers with the samples in
`contracts/examples/`, so the whole path works before any research logic exists.
Try it:

```bash
curl -X POST localhost:8000/v1/guidance \
  -H "Content-Type: application/json" \
  -d '{"session_id": "anon-demo", "text": "mata passport ekak ganna one"}'
```

## Working on one component

You don't need the whole stack to work on your own part:

```bash
scripts/dev-setup.sh c2-knowledge-graph
cd components/c2-knowledge-graph/service
source .venv/bin/activate
uvicorn app.main:app --reload --port 8002
pytest
```

Put your research logic in `app/core/`. Keep stub mode working: it's what the other
components test against.

## Data stores

| Store | Holds | Written by |
|---|---|---|
| Neo4j | Public service knowledge | C2 only |
| PostgreSQL | Anonymous sessions, feedback, trust scores, preferences | C1, C3, C4 |

The two are separate on purpose; see
[`docs/architecture/decisions/0002-two-stores.md`](docs/architecture/decisions/0002-two-stores.md).

## Ports

| Service | Port |
|---|---|
| frontend | 5173 |
| gateway | 8000 |
| c1-intent | 8001 |
| c2-knowledge-graph | 8002 |
| c3-trust | 8003 |
| c4-presentation | 8004 |
| Neo4j | 7474, 7687 |
| PostgreSQL | 5432 |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md): ownership, branches, how to change the contract,
and what must never be committed.
