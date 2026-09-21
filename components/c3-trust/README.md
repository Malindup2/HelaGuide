# c3-trust · Civic Trust and Knowledge Verification Engine

**Owner:** J. D. Minuli Pabasara  ·  **Port:** 8003

Scores citizen feedback, detects duplicate and coordinated reports, and emits verified corrections.

| | |
|---|---|
| **Inputs** | `feedback` from C4; `fact` lookups from C2 |
| **Outputs** | `trust` to C4; `correction` to C2 |
| **Stores** | PostgreSQL schema `c3`: feedback, trust scores. Reads Neo4j. |
| **Stack** | Sentence embeddings, clustering, confidence scoring, PostgreSQL |

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/v1/feedback` | Accept citizen `feedback` |
| GET | `/v1/trust/{fact_id}` | Current `trust` score for one fact |

Interactive docs at <http://localhost:8003/docs> when running.

## Layout

```
c3-trust/
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
uvicorn app.main:app --reload --port 8003
pytest
```

Run these from `components/c3-trust/service/`.
