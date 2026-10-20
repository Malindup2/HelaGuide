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
| POST | `/v1/intent` | Raw text → `intent` (team contract) |
| POST | `/v1/intent/details` | C1-only: same input plus optional `bot_text`; returns internal intent, route, slots, missing slots, language tags, latency and the projected `intent` |

Routes in `/v1/intent/details`: core intents and `general_question` → `orchestration`, `feedback_complaint` →
`trust_verification`, `unsupported_service` → `fallback`, `out_of_scope` / `unknown` → `none`.

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

## Run the real engine (laptop, `nlp` conda env)

Stub mode (`STUB_MODE=true`) is the default and needs no models. To run the trained models instead,
use the `nlp` env and the models in `research/models/c1/` (not in git; see `research/data/README.md`).

The Docker image and CI use Python 3.11. Python 3.10 is only for running locally in the `nlp` env.

**1. Install** (Windows cmd, from `components/c1-intent/`):

```bat
conda activate nlp
pip install -e "service[research]"
pip install --ignore-requires-python --no-deps -e ..\..\shared
```

`shared/` declares Python ≥ 3.11 but runs on 3.10; the flag goes on that package alone, with `--no-deps`,
because on a full install it would let pip pick packages that really need 3.11.
torch and transformers are already in `nlp`, so pip keeps them. Use `service[dev,research]` to run `pytest` too.

**2. Settings** (same cmd window):

```bat
set STUB_MODE=false
set C1_MODEL_DIR=research\models\c1\run_v2_seed1
set C1_MIN_CONFIDENCE=0.35
```

| Variable | Default | Meaning |
|---|---|---|
| `STUB_MODE` | `true` | `false` runs the real engine |
| `C1_MODEL_DIR` | `research/models/c1/run_v2_seed1` | Folder with `lid/`, `ner/`, `intent/`, `c1_config.json`. Absolute, or relative to the working directory or to `components/c1-intent/` |
| `C1_MIN_CONFIDENCE` | `0.35` | Below this the intent is not trusted: a mention of an unsupported service gives `unsupported_service`, otherwise the previous topic is kept (or `unknown` on the first turn) |

If the model folder is missing the service answers 503 with a message saying how to set `C1_MODEL_DIR`.
Sessions are kept in memory (30 minutes idle, at most 1,000) and are lost on restart.

**3. Start** (from `components/c1-intent/service/`):

```bat
cd service
uvicorn app.main:app --port 8001
```

The models load on the first request (a few seconds); later turns take about 50–150 ms on CPU.

**4. Try it.** PowerShell:

```powershell
$body = @{ session_id = "anon-demo1"; text = "mata ID eka nathi una, ikmanata aluth ekak one" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8001/v1/intent -Method Post -ContentType "application/json" -Body $body

$body = @{ session_id = "anon-demo1"; text = "Matara"; bot_text = "Koheda inne?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8001/v1/intent/details -Method Post -ContentType "application/json" -Body $body
```

cmd with `curl.exe`:

```bat
curl.exe -s -X POST http://127.0.0.1:8001/v1/intent -H "Content-Type: application/json" -d "{\"session_id\": \"anon-demo2\", \"text\": \"mata ID eka nathi una, ikmanata aluth ekak one\"}"
curl.exe -s -X POST http://127.0.0.1:8001/v1/intent/details -H "Content-Type: application/json" -d "{\"session_id\": \"anon-demo2\", \"text\": \"Matara\", \"bot_text\": \"Koheda inne?\"}"
```

Use `127.0.0.1` rather than `localhost` on Windows; `localhost` tries IPv6 first and adds about 2 s per request.

**5. Demo conversations** (second window, service running):

```bat
python scripts\demo_conversation.py
python scripts\demo_conversation.py --only A B C
```

Sessions: **A** NIC lost (district memory, correction Matara → Galle, urgency), **B** complaint →
`trust_verification`, **C** driving licence → `fallback`, **SI** Sinhala script (birth certificate copy),
**EN** English (new passport).

