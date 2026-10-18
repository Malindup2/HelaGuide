"""Read every page of one agency that is waiting, and stage its facts.

    python scripts/read_agency.py ird.gov.lk
    C2_LLM_MODEL=gemini-flash-lite-latest python scripts/read_agency.py ird.gov.lk

Stops politely when the model's daily quota runs out; the rest stay 'to read' and the same
command resumes them later.
"""
import sys, time
from fastapi.testclient import TestClient
from app.admin_ui import app

host = sys.argv[1]
c = TestClient(app, raise_server_exceptions=False)
rows = [r for r in c.get("/api/files").json()
        if host in r["url"] and r["state"] in ("to_read", "changed") and r["gate_send"] and r.get("latest", True)]
rows.sort(key=lambda r: (not ("F" in r["signals"] or "P" in r["signals"]), r["url"]))
print(f"{len(rows)} page(s) to read for {host}", flush=True)
tin = tout = ok = 0
for r in rows:
    t0 = time.time()
    resp = c.post("/api/extract", json={"file": r["file"], "by_sections": True, "force": False})
    name = r["url"].rstrip("/").rsplit("/", 1)[-1][:40]
    if resp.status_code != 200:
        print(f"!! {name}: HTTP {resp.status_code} {resp.text[:140]}", flush=True)
        if "429" in resp.text or "quota" in resp.text.lower():
            print("quota exceeded: stopping, the rest stay 'to read' and can be resumed", flush=True)
            break
        continue
    d = resp.json()
    if d.get("skipped"):
        print(f"-- {name}: skipped: {d['reason']}", flush=True)
        continue
    ok += 1
    tin += d.get("tokens_in") or 0
    tout += d.get("tokens_out") or 0
    svcs = ", ".join(f"{s['service_id'].replace('svc:','')}({s['facts']})" for s in d.get("sections") or [] if s["facts"])
    print(f"== {name:40} {time.time()-t0:3.0f}s facts={d['facts']:3} new={d['new_pending']:3} dropped={len(d['dropped'])}  {svcs[:150]}", flush=True)
print(f"DONE read {ok} page(s); tokens in {tin}, out {tout}", flush=True)
