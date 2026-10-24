"""Golden architecture baseline: fingerprints of observable backend behaviour.

The fixture was captured from the backend before the V3.1 consolidation refactor. Every structural
refactor must reproduce it exactly. Only isolated temporary directories are used; the live policy,
journeys, workspace and checkpoint files are never opened for writing (the checkpoint is copied).

Create the baseline (only before a refactor):  python -m tests.architecture_golden --write
Compare manually:                               python -m tests.architecture_golden
"""
import argparse
import gc
import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import numpy as np

SERVICE = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "architecture-golden.json"
CHECKPOINT = SERVICE / ".local" / "manual-v4-review" / "checkpoint" / "seed-23-x0.25-525-n5000.npz"
TOKEN = "golden-architecture-capability-" + "x" * 24
ROOT = "/workspace/guidance"
CONTEXTS = ({}, {"familiarity": 1, "confidence": 2}, {"familiarity": 5, "confidence": 5},
            {"familiarity": 3, "confidence": 1, "preferences": {"navigation": "guided", "explanation": "detailed"}},
            {"familiarity": 2, "preferences": {"relationships": "map", "recap": "on", "segmentation": "on", "disclosure": "on"}})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def arrays(*values):
    h = hashlib.sha256()
    for v in values:
        h.update(np.ascontiguousarray(np.asarray(v, dtype=np.float64)).tobytes())
    return h.hexdigest()


_HEX = re.compile(r"[0-9a-f]{32}|(?<=session:)[0-9a-f]{12}\b")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+00:00|Z)?")
_RANDOM_KEYS = {"token", "token_hash", "capability_token", "checksum"}


def canonical(value):
    """Replace random identifiers and wall-clock times by stable placeholders in first-seen order."""
    names = {}

    def name(token):
        return names.setdefault(token, f"<id{len(names)}>")

    def text(s):
        return _TIME.sub("<time>", _HEX.sub(lambda m: name(m.group(0)), s))

    def walk(v, key=None):
        if key in _RANDOM_KEYS and isinstance(v, str):
            return name(v)
        if isinstance(v, dict):
            return {text(k): walk(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            return text(v)
        return v
    return walk(value)


def scratch():
    tag = "golden-" + uuid4().hex[:10]
    dirs = {"policy": SERVICE / ".local" / "pp1-learning" / "golden-tmp" / tag,
            "prepared": SERVICE / ".local" / "prepared-content" / "golden-tmp" / tag / "v31",
            "workspace": SERVICE / ".local" / "golden-tmp" / tag / "v2" / "workspace" / "state.sqlite3"}
    return dirs


def cleanup(dirs):
    gc.collect()  # sqlite3 connections used as context managers stay open until collected (Windows file locks)
    shutil.rmtree(dirs["policy"], ignore_errors=True)
    shutil.rmtree(dirs["prepared"].parent, ignore_errors=True)
    shutil.rmtree(dirs["workspace"].parents[2], ignore_errors=True)
    for parent in (dirs["policy"].parent, dirs["prepared"].parents[1], dirs["workspace"].parents[3]):
        try:
            parent.rmdir()  # only when empty
        except OSError:
            pass


# ---------------------------------------------------------------- registry, feasibility, composition, encoder
def registry_part():
    from app.procedures.registration import workspace_registry
    from app.procedures.scaffolds import graph_fingerprint
    out = {}
    for pid, e in sorted(workspace_registry().items()):
        doc = e["document"]
        out[pid] = {"graph": graph_fingerprint(e["graph"]), "document": digest(doc), "structure": doc["structure_fingerprint"],
                    "content": doc["content_fingerprint"], "canonical": e["canonical"]["fingerprint"],
                    "measurements": digest(e["measurements"].model_dump(mode="json")), "preparation": digest(e["preparation"]),
                    "overlay": digest(e["overlay"].model_dump(mode="json")) if e.get("overlay") else None,
                    "title": doc["title"], "actions": [a["id"] for a in doc["actions"]]}
    return out


def guidance_part():
    from app.procedures.registration import workspace_registry
    from app.guidance import provisional, features
    from app.guidance.catalogue import CATALOGUE, Constraints
    from app.guidance.content_v31 import GuidanceContent31, evaluate31
    from app.guidance.sources import ProcedureSource
    from app.guidance.v31_pipeline import compose31, feasibility_fingerprint
    constraints = [None, Constraints(no_map=True), Constraints(no_guided=True, no_disclosure=True),
                   Constraints(locks={"explanation": "detailed", "recap": "on"})]
    out = {}
    for pid, e in sorted(workspace_registry().items()):
        source = ProcedureSource(graph=e["graph"], relationships=e.get("overlay")).validate()
        path = provisional.PROVISIONAL_DIR / (pid + ".json")
        content = GuidanceContent31.model_validate(json.loads(path.read_text(encoding="utf-8"))["content"]) if path.is_file() else None
        item = {"feasibility": [], "documents": {}, "encoder": None}
        for c in constraints:
            for reviewed in ((False, True) if content else (False,)):
                cands = evaluate31(source, content, c, assume_reviewed=reviewed)
                item["feasibility"].append({"constraints": c.model_dump() if c else None, "reviewed": reviewed,
                                            "fingerprint": feasibility_fingerprint(cands), "feasible": sum(x.feasible for x in cands),
                                            "detail": digest([[x.configuration.model_dump(), x.feasible, list(x.reasons)] for x in cands])})
        cands = evaluate31(source, content, None, assume_reviewed=True)
        for cand in cands:
            if cand.feasible:
                doc = compose31(source, content, cand.configuration, assume=True)
                item["documents"][":".join(cand.configuration.model_dump().values())] = digest(json.loads(json.dumps(doc, default=str)))
        m = e["measurements"]
        item["encoder"] = arrays(*[[features.encode(m, ctx, cfg, "525") for cfg in CATALOGUE] for ctx in CONTEXTS])
        out[pid] = item
    return out


# ---------------------------------------------------------------- numerical policy kernels
def matrices():
    from app.procedures.registration import workspace_registry
    from app.guidance import features
    from app.guidance.catalogue import CATALOGUE
    reg = workspace_registry()
    pids = sorted(reg)
    return [np.array([features.encode(reg[pid]["measurements"], ctx, cfg, "525") for cfg in CATALOGUE]) for pid in pids for ctx in CONTEXTS[:2]]


def kernel_part():
    from app.learning.lints import Model
    from app.guidance.v31_pipeline import PROFILE_31
    from app.models.policy import PolicyConfig
    from app.legacy.v1_policy import _GaussianPosterior, FEATURE_DIMENSION, FEATURE_NAMES_SHARED, FEATURE_SCALE
    from app.legacy.prior import load_prior
    out = {}
    mats = matrices()

    def exercise(model, seeds=40):
        scores = []
        for i, mat in enumerate(mats):
            for seed in range(seeds):
                idx, sampled, means, std = model.score(mat, 1000 * i + seed)
                scores.append(idx)
                scores.append(arrays(sampled, means, std))
        rng = np.random.Generator(np.random.PCG64(7))
        for step in range(120):
            mat = mats[step % len(mats)]
            model.update(mat[int(rng.integers(len(mat)))], int(step % 3 == 0))
        k = model.kernel
        return {"scores": digest(scores), "after_updates": arrays(k._precision, k._b, k._mean, k._factor), "revision": k.revision,
                "posterior_sample": arrays(k.sample(99))}

    out["fresh_31"] = exercise(Model("525", exploration=0.25, profile=PROFILE_31))
    if CHECKPOINT.is_file():
        blob = CHECKPOINT.read_bytes()
        out["checkpoint_sha256"] = hashlib.sha256(blob).hexdigest()
        restored = Model.restore(blob, profile=PROFILE_31)
        k = restored.kernel
        out["checkpoint_restore"] = {"arrays": arrays(k._precision, k._b, k._mean, k._factor), "revision": k.revision,
                                     "manifest": digest(restored.manifest)}
        out["checkpoint_31"] = exercise(restored)
    else:
        out["checkpoint_sha256"] = None

    # V2 and V1 users of the same kernel
    rng = np.random.Generator(np.random.PCG64(11))
    v2 = _GaussianPosterior(515, PolicyConfig(cold_start_updates=0))
    for step in range(60):
        x = rng.standard_normal(515)
        v2.observe(x / (2 * np.linalg.norm(x)), step % 2)
    means, std = v2.moments(rng.standard_normal((20, 515)) / 50)
    out["v2_kernel"] = arrays(v2._precision, v2._b, v2._mean, v2.sample(5), means, std)
    prior = load_prior(SERVICE / "priors" / "pp1-provisional-v1.json")
    v1 = _GaussianPosterior(FEATURE_DIMENSION, PolicyConfig(cold_start_updates=0, prior=prior))
    x = rng.standard_normal(FEATURE_DIMENSION)
    v1.observe(x / (2 * np.linalg.norm(x)), 1)
    out["v1_prior_kernel"] = arrays(v1._precision, v1._b, v1._mean, v1.sample(3), FEATURE_SCALE, len(FEATURE_NAMES_SHARED))
    return out


# ---------------------------------------------------------------- API contracts
def openapi_part():
    from app.main import app as team_app
    from app.dev_main import app as v1_app
    from app.guidance.flavours import FLAVOUR_31
    from app.host.application import create_app
    from app.host.identity import WorkspaceRuntime
    dirs = scratch()
    try:
        workspace = create_app(dirs["workspace"], workspace=True, runtime_class=WorkspaceRuntime,
                               prepared_content_options={"directory": dirs["prepared"], "flavour": FLAVOUR_31},
                               guidance_api_options={"research_enabled": True, "flavour": FLAVOUR_31,
                                                     "policy_options": {"directory": dirs["policy"], "seed": 23}})
        isolated_v2 = create_app(":memory:")
        return {"workspace": digest(workspace.openapi()), "isolated_v2": digest(isolated_v2.openapi()),
                "team_main": digest(team_app.openapi()), "dev_main": digest(v1_app.openapi()),
                "workspace_routes": sorted(f"{sorted(r.methods)} {r.path}" for r in workspace.routes if hasattr(r, "methods"))}
    finally:
        cleanup(dirs)


# ---------------------------------------------------------------- persistence and full request flows
def identity_part():
    """The integrated workspace record: identity, settings and legacy V2 journeys in one SQLite JSON record."""
    from app.models.demo_profiles import CreateDemoProfileRequest, PersonalizationRequest
    from app.compat.v2_catalogue import Configuration
    from app.host.identity import SettingsPatch, WorkspaceRuntime
    from app.procedures.registration import workspace_registry
    dirs = scratch()
    steps = []
    try:
        entries = workspace_registry()
        r = WorkspaceRuntime(dirs["workspace"], procedures=entries, seed=5)
        p = r.create_profile(CreateDemoProfileRequest(profile_id="profile:" + "1" * 32, display_name="Golden", personalization_enabled=True,
                             initial_context={"navigation_capability": 2, "preferences": {"presentation_mode": "GUIDED"},
                                              "familiarity": [{"service_id": "svc:nic_amendment", "score": 1}]}))
        steps.append(p)
        sid = p["session"]["session_id"]
        guest = r.create_session()
        steps.append(guest)
        revision = r.settings(sid)["settings_revision"]
        steps.append(r.update_settings(sid, SettingsPatch(request_id="golden-settings-1", expected_revision=revision,
                     preferences={"explanation": "expanded"}, locks={"recap": "on"})))
        profile_revision = r.profiles[p["profile"]["profile_id"]].revision
        steps.append(r.personalization(p["profile"]["profile_id"], PersonalizationRequest(request_id="event:" + "2" * 32,
                     expected_revision=profile_revision, enabled=True)))
        j = r.guidance(sid, "synthetic-practice-v2", "golden-request-1", r.settings(sid)["settings_revision"])
        steps.append(j)
        steps.append(r.event(j["id"], j["token"], {"event_id": "golden-event-1", "view_id": j["current_view"], "type": "action_visible",
                                                    "action_id": j["document"]["actions"][0]["id"]}))
        steps.append(r.rate(j["id"], j["token"], j["root_view"], "about_right"))
        m = r.guidance(sid, "synthetic-practice-v2", "golden-request-2", r.settings(sid)["settings_revision"])
        steps.append(r.adjust(m["id"], m["token"], m["current_view"], Configuration(**m["available_configurations"][0]), "golden-adjust-1"))
        steps.append(r.inspect(j["id"], j["token"]))
        steps.append(r.status())
        steps.append(r.settings(sid))
        r.close()
        with closing(sqlite3.connect(dirs["workspace"])) as db:
            tables = [t[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            revision, payload = db.execute("SELECT revision,payload FROM c4_workspace_state").fetchone()
        reopened = WorkspaceRuntime(dirs["workspace"], procedures=entries, seed=5)
        after = {"status": reopened.status(), "settings": reopened.settings(sid), "profiles": sorted(reopened.profiles)}
        reopened.close()
        record = json.loads(payload)
        # Sessions are exported in random-identifier order; order them by their identifier-free content.
        record["identity"]["sessions"].sort(key=lambda s: json.dumps(canonical(s), sort_keys=True))
        return {"steps": digest(canonical(steps)), "tables": tables, "record_revision": revision,
                "record_keys": list(record), "record": digest(canonical(record)), "reopened": digest(canonical(after)),
                "v2_manifest": digest(record["manifest"]), "posterior_fingerprint": record.get("posterior_fingerprint")}
    finally:
        cleanup(dirs)


def http_part():
    """End-to-end V3.1 flow through FastAPI with an isolated checkpoint copy and isolated stores."""
    from fastapi.testclient import TestClient
    from app.guidance.flavours import FLAVOUR_31
    from app.host.application import create_app
    from app.host.identity import WorkspaceRuntime
    from app.procedures.registration import workspace_registry
    if not CHECKPOINT.is_file():
        return None
    dirs = scratch()
    try:
        dirs["policy"].mkdir(parents=True, exist_ok=True)
        checkpoint = dirs["policy"].parent / (dirs["policy"].name + "-checkpoint.npz")
        shutil.copyfile(CHECKPOINT, checkpoint)
        entries = workspace_registry()
        options = {"research_enabled": True, "flavour": FLAVOUR_31, "demo_accepted": True, "demo_provisional": True,
                   "policy_options": {"directory": dirs["policy"] / "store", "seed": 23, "checkpoint": checkpoint, "exploration": 0.25}}
        app = create_app(dirs["workspace"], workspace=True, seed=0, runtime_class=lambda path, **kw: WorkspaceRuntime(path, procedures=entries, **kw),
                         prepared_content_options={"directory": dirs["prepared"], "demo_fixtures": True, "flavour": FLAVOUR_31},
                         guidance_api_options=options)
        log = []
        with TestClient(app) as client:
            log.append(client.get("/health").json())
            log.append(client.get(ROOT + "/status").json())
            procedures = client.get(ROOT + "/procedures").json()
            log.append(procedures)
            log.append(client.get("/dev/v1/procedures").json())
            log.append(client.get("/v2/policy").json())
            n = 0
            for proc in procedures:
                pid = proc["procedure_id"]
                n += 1
                body = {"profile_id": "profile:" + f"{n:032x}", "display_name": "Golden " + str(n), "personalization_enabled": True,
                        "initial_context": {"navigation_capability": 1 + n % 5, "preferences": {"presentation_mode": "GUIDED"},
                                            "familiarity": [{"service_id": proc["service_id"], "score": 1 + (n * 2) % 5}]}}
                created = client.post(ROOT + "/profiles", json=body)
                log.append([created.status_code, created.json()])
                sid = created.json()["session"]["session_id"]
                ctx = client.get(ROOT + "/context/" + sid, params={"procedure_id": pid}).json()
                log.append(ctx)
                if n % 2 == 0:
                    patched = client.patch(ROOT + "/context/" + sid, json={"request_id": f"golden-ctx-{n}", "expected_revision": ctx["revision"],
                                                                         "preferences": {"explanation": "detailed"}, "accessibility": {"no_map": n % 4 == 0}})
                    log.append([patched.status_code, patched.json()])
                log.append(client.get(ROOT + "/procedures/" + pid + "/availability", params={"session_id": sid}).json())
                j = client.post(ROOT + "/requests", json={"request_id": f"golden-req-{n}", "session_id": sid, "procedure_id": pid,
                                                          "capability_token": TOKEN, "mode": "personalized"})
                log.append([j.status_code, j.json()])
                if j.status_code != 200:
                    continue
                j = j.json()
                headers = {"X-C4-Token": TOKEN}
                ev = client.post(ROOT + "/journeys/" + j["journey_id"] + "/events", headers=headers,
                                 json={"event_id": f"golden-ev-{n}", "view_id": j["view_id"], "type": "view_displayed", "action_ids": [j["document"]["actions"][0]["id"]]})
                log.append([ev.status_code, ev.json()])
                if n % 3 == 0:
                    child = client.post(ROOT + "/journeys/" + j["journey_id"] + "/views", headers=headers,
                                        json={"request_id": f"golden-view-{n}", "parent_view_id": j["view_id"], "configuration": j["selection"]["configuration"]})
                    log.append([child.status_code, child.json()])
                rating = client.post(ROOT + "/journeys/" + j["journey_id"] + "/ratings", headers=headers,
                                     json={"event_id": f"golden-rate-{n}", "view_id": j["view_id"], "rating": "fits" if n % 2 else "does_not_fit"})
                log.append([rating.status_code, rating.json()])
                log.append(client.get(ROOT + "/journeys/" + j["journey_id"] + "/inspector", headers=headers).json())
            guest = client.post(ROOT + "/guests").json()
            log.append(guest)
            g = client.post(ROOT + "/requests", json={"request_id": "golden-guest", "session_id": guest["session_id"], "procedure_id": procedures[0]["procedure_id"],
                                                      "capability_token": TOKEN, "mode": "standard"})
            log.append([g.status_code, g.json()])
            log.append(client.get(ROOT + "/status").json())
            log.append(client.get("/v2/policy").json())
        with closing(sqlite3.connect(dirs["policy"] / "store" / "policy.sqlite3")) as db:
            updates = db.execute("SELECT reward,revision,state_digest FROM updates ORDER BY revision").fetchall()
        return {"log": digest(canonical(log)), "entries": len(log), "policy_updates": [[u[0], u[1]] for u in updates],
                "selected": [x[1]["selection"]["configuration"] for x in log if isinstance(x, list) and len(x) == 2 and isinstance(x[1], dict) and "selection" in x[1] and x[1]["selection"].get("kind") == "shared_gaussian_lints"]}
    finally:
        cleanup(dirs)
        for leftover in (SERVICE / ".local" / "pp1-learning" / "golden-tmp").glob("*-checkpoint.npz"):
            leftover.unlink(missing_ok=True)


PARTS = {"registry": registry_part, "guidance": guidance_part, "kernels": kernel_part, "openapi": openapi_part,
         "identity": identity_part, "http": http_part}


def capture(parts=None):
    return {name: PARTS[name]() for name in (parts or PARTS)}


def differences(expected, actual, path=""):
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for k in sorted(set(expected) | set(actual)):
            if k not in expected or k not in actual:
                out.append(f"{path}/{k}: missing on one side")
            else:
                out.extend(differences(expected[k], actual[k], f"{path}/{k}"))
        return out
    return [] if expected == actual else [f"{path}: expected {str(expected)[:120]} got {str(actual)[:120]}"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = capture()
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    if args.write:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("baseline written:", FIXTURE)
    else:
        diff = differences(json.loads(FIXTURE.read_text(encoding="utf-8")), json.loads(json.dumps(result)))
        print("IDENTICAL" if not diff else "\n".join(diff))
