# c2-knowledge-graph · Knowledge Graph and Service Orchestration Engine

**Owner:** T. Malindu Pabasara  ·  **Port:** 8002

Acquires government service pages, detects what changed, maintains a versioned knowledge graph, and turns a service into a dependency-ordered plan.

| | |
|---|---|
| **Inputs** | `intent` from C1; `correction` from C3; public government pages on a schedule |
| **Outputs** | `plan` to C4; `fact` to C3 |
| **Stores** | Neo4j (sole writer). No personal data. |
| **Stack** | Crawl4AI, Pydantic extraction, Neo4j, igraph + leidenalg |

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/v1/plan?service_id=` | Service → ordered `plan` |
| GET | `/v1/facts/{fact_id}` | A `fact` and its history |
| POST | `/v1/corrections` | Accept a verified `correction` from C3 |

Interactive docs at <http://localhost:8002/docs> when running.

## Layout

```
c2-knowledge-graph/
├── service/          FastAPI app
│   └── app/
│       ├── api/      routes (keep thin)
│       ├── core/     the research logic; structure it however you like
│       └── models/   component-internal models
├── stub/             how stub mode works
└── research/
    ├── docs/         proposal report, notes
    ├── diagrams/     sources (.svg, .drawio, .py) and exports (.png)
    ├── data/         small data + pointers to large data
    └── experiments/  notebooks, ablations, results
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ../../../shared
pip install -e ".[dev]"            # add ,research when you need the heavy libraries
uvicorn app.main:app --reload --port 8002
pytest
```

Run these from `components/c2-knowledge-graph/service/`.
