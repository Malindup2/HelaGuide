# c4-presentation · Context-Aware Adaptive Guidance Presentation Engine

**Owner:** Dias K. S. S.  ·  **Port:** 8004

Decides how to present a plan to this citizen: detail level, wording, voice, based on behavioural signals.

| | |
|---|---|
| **Inputs** | `plan` from C2; `trust` from C3; behavioural signals from the frontend |
| **Outputs** | `render` to the gateway and frontend; `feedback` to C3 |
| **Stores** | PostgreSQL schema `c4`: preferences, behavioural signals |
| **Stack** | Behavioural-signal detection, support-level classifier, PostgreSQL |

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/v1/render` | `plan` + `trust` → adapted `render` |

Interactive docs at <http://localhost:8004/docs> when running.

## Layout

```
c4-presentation/
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
uvicorn app.main:app --reload --port 8004
pytest
```

Run these from `components/c4-presentation/service/`.
