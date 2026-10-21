> Active integrated PP1 application: see [UNIFIED-README.md](UNIFIED-README.md). The standalone paths below are historical baseline documentation.

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




## Independent C4 research backend

The original `app.main:app` service and `/v1/render` stub remain unchanged.
The research backend runs through `app.dev_main:app` on port 8016.

### Start C4 PostgreSQL

From `components/c4-presentation/`:

```powershell
docker compose -p helaguide-c4 -f .\docker-compose.c4.yml up -d
```

This uses C4's separate development database and Docker volume on
`127.0.0.1:5434`.

### Install and run

From `components/c4-presentation/service/`, using the existing Python 3.11
virtual environment:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -e "../../../shared"
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev,postgres]"

$env:C4_STORAGE_BACKEND = "postgresql"
$env:C4_DATABASE_URL = "postgresql://c4:c4_local_demo_password@127.0.0.1:5434/c4_pp1_simulation"
$env:C4_FEEDBACK_MODE = "simulation"
$env:C4_DEV_LLM_ENABLED = "false"

& ".\.venv\Scripts\python.exe" -m uvicorn app.dev_main:app --reload --host 127.0.0.1 --port 8016
```

The database credentials above are for local development only.

Open http://127.0.0.1:8016/docs.
The health endpoint should report `storage: postgresql`.

Explicitly using `.venv\Scripts\python.exe` does not require activation.

### Status and integration

- 182 tests passed locally with PostgreSQL integration tests enabled.
- Default procedures and evidence are explicitly synthetic.
- Live OpenAI generation, the React frontend and full-team integration remain pending.
- The existing team Docker configuration still starts `app.main:app`.
- Keep `STUB_MODE=true` for that shared stub; setting it to false does not activate this research backend.
- Do not commit `.env`, runtime databases or virtual environments.
