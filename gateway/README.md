# gateway

The only backend the frontend calls. It composes the four components; it holds no
research logic of its own.

| Method | Path | Does |
|---|---|---|
| GET | `/health` | Gateway liveness |
| GET | `/health/all` | Liveness of every component |
| POST | `/v1/guidance` | Citizen text → C1 → C2 → C3 → C4 → adapted plan |
| POST | `/v1/feedback` | Citizen report → C3 |

Docs at <http://localhost:8000/docs>.

```bash
pip install -e ../shared
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
pytest
```
