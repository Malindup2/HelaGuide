# c1-intent · Multilingual Conversational Intent and Entity Understanding Engine

**Owner:** Dabarera W. A. S.  ·  **Port:** 8001

Turns a citizen's raw text (Sinhala, English or code-switched, multi-turn) into an identified service and entities.

| | |
|---|---|
| **Inputs** | Raw citizen text from the gateway |
| **Outputs** | `intent` to C2 (via the gateway) |
| **Stores** | PostgreSQL schema `c1`: sessions, conversation turns |
| **Stack** | XLM-RoBERTa (fine-tuned), Rasa, PostgreSQL tracker store |

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/v1/intent` | Raw text → `intent` |

Interactive docs at <http://localhost:8001/docs> when running.

## Layout

```
c1-intent/
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
uvicorn app.main:app --reload --port 8001
pytest
```

Run these from `components/c1-intent/service/`.
