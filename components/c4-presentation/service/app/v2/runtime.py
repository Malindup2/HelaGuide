"""Atomic, isolated V2 research runtime using the existing Shared LinTS kernel."""
import copy
import json
import sqlite3
import threading
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import numpy as np
from app.core.policy import _GaussianPosterior
from app.models.policy import PolicyConfig
from app.v2.catalogue import ACTION_SCHEMA, Configuration, Context, evaluate
from app.v2.content import digest, registry
from app.v2.features import SCHEMA, FINGERPRINT, NAMES, VARIANTS, encode

C4_ROOT = Path(__file__).resolve().parents[3]
EVENTS = {"action_visible", "opportunity_visible", "navigate", "detail_open", "detail_close", "recap_open", "source_open", "route_focus", "reason", "map_expand", "map_collapse"}

def now():
    return datetime.now(timezone.utc).isoformat()

def uid(kind):
    return f"{kind}:{uuid4().hex}"

class Conflict(ValueError):
    pass

class Runtime:
    TABLE = "c4_v2_state"
    def __init__(self, path=":memory:", *, mode="simulation", seed=0, variant="full", procedures=None):
        if mode not in ("simulation", "participant") or variant not in VARIANTS:
            raise ValueError("invalid V2 mode or encoder")
        if str(path) != ":memory:":
            path = Path(path).resolve()
            if not path.is_relative_to(C4_ROOT) or "v2" not in path.parts:
                raise ValueError("V2 storage must be inside C4 in a v2 directory")
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        existing = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if existing and existing != {self.TABLE}:
            self.db.close()
            raise ValueError("refusing a database with non-V2 tables")
        self.db.execute(f"CREATE TABLE IF NOT EXISTS {self.TABLE} (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)")
        self.db.commit()
        self.lock = threading.RLock()
        self.procedures = procedures if procedures is not None else registry()
        self.manifest = {"action": ACTION_SCHEMA, "features": SCHEMA, "fingerprint": FINGERPRINT,
                         "variant": variant, "dimension": VARIANTS[variant], "mode": mode, "seed": seed,
                         "prior_precision": 1.0, "noise": 1.0, "exploration": 1.0, "reward": "support-fit-1-0-0-v2"}
        row = self.db.execute(f"SELECT revision,payload,checksum FROM {self.TABLE} WHERE id=1").fetchone()
        if row:
            self.revision, payload, checksum = row
            self.state = json.loads(payload)
            if digest(self.state) != checksum or self.state["manifest"] != self.manifest:
                self.db.close()
                raise ValueError("incompatible or corrupt V2 state; never migrate V1 coefficients")
        else:
            self.revision = 0
            self.state = {"manifest": self.manifest, "run_id": uid("v2-run"), "journeys": {}, "decisions": {}, "updates": [], "rng": np.random.PCG64(seed).state}
            self.db.execute(f"INSERT INTO {self.TABLE} VALUES (1,0,?,?)", (json.dumps(self.state), digest(self.state)))
            self.db.commit()
        self._restore()

    def _restore(self):
        self.kernel = _GaussianPosterior(self.manifest["dimension"], PolicyConfig(cold_start_updates=0))
        for receipt in self.state["updates"]:
            decision = self.state["decisions"][receipt["decision_id"]]
            self.kernel.observe(decision["features"], receipt["reward"])
        self.rng = np.random.Generator(np.random.PCG64())
        self.rng.bit_generator.state = self.state["rng"]
        expected = self.state.get("posterior_fingerprint")
        if expected and expected != self.fingerprint():
            raise ValueError("posterior replay fingerprint mismatch")

    def fingerprint(self):
        import hashlib
        return hashlib.sha256(self.kernel._precision.tobytes() + self.kernel._b.tobytes()).hexdigest()

    def _write(self, function):
        with self.lock:
            previous = copy.deepcopy(self.state)
            try:
                self.db.execute("BEGIN IMMEDIATE")
                current = self.db.execute(f"SELECT revision FROM {self.TABLE} WHERE id=1").fetchone()[0]
                if current != self.revision:
                    raise Conflict("concurrent writer changed state; reopen this runtime")
                result = function()
                self.state["rng"] = self.rng.bit_generator.state
                self.state["posterior_fingerprint"] = self.fingerprint()
                self.db.execute(f"UPDATE {self.TABLE} SET revision=?,payload=?,checksum=? WHERE id=1", (self.revision + 1, json.dumps(self.state, allow_nan=False), digest(self.state)))
                self.db.commit()
                self.revision += 1
                return copy.deepcopy(result)
            except Exception:
                self.db.rollback()
                self.state = previous
                self._restore()
                raise

    def status(self):
        with self.lock:
            return {"manifest": self.manifest, "policy_run_id": self.state["run_id"], "posterior_revision": self.kernel.revision,
                    "accepted_feedback_count": len(self.state["updates"]), "posterior_fingerprint": self.fingerprint()}

    def create(self, procedure_id, context: Context, request_id, *, metadata=None, standard=False, capability_token=None):
        if procedure_id not in self.procedures:
            raise ValueError("unknown procedure")
        def change():
            # A new journey is an explicit request, never an Inspector side effect.
            for journey in self.state["journeys"].values():
                if journey["request_id"] == request_id:
                    if capability_token and secrets.compare_digest(journey["token_hash"], digest(capability_token)):
                        if (journey.get("identity") or {}).get("session_id") != (metadata or {}).get("session_id") or journey["document"]["id"] != procedure_id:
                            raise Conflict("request identity reused for another scope")
                        return {"token":capability_token, **self.public(journey)}
                    raise Conflict("request already created; resume with its capability token")
            p = self.procedures[procedure_id]
            evaluations = evaluate(p["document"]["capabilities"], context)
            candidates = [Configuration(**e["configuration"]) for e in evaluations if not e["reasons"]]
            if not candidates:
                raise ValueError("no feasible configuration; hard constraints were not relaxed")
            if standard:
                matrix=np.zeros((len(candidates),self.manifest["dimension"]))
                means,deviations=np.zeros(len(candidates)),np.zeros(len(candidates))
            else:
                matrix = np.stack([encode(p["measurements"], context, c, self.manifest["variant"]) for c in candidates])
                means, deviations = self.kernel.moments(matrix)
            seed = None if standard else int(self.rng.integers(0, 2**63 - 1))
            draw = np.zeros(self.manifest["dimension"]) if standard else self.kernel.sample(seed)
            scores = .5 + matrix @ draw
            if standard:
                # Standard routing does not sample, acknowledge a policy reward,
                # or reinterpret a user's characteristics as a selection rule.
                baseline = Configuration().model_copy(update={"disclosure": "expanded" if context.no_collapsed and p["document"]["capabilities"]["disclosure"]["applicable"] else "collapsed"})
                index = next((i for i,c in enumerate(candidates) if c == baseline), 0)
            else:
                index = int(np.argmax(scores))
            decision_id, journey_id, view_id = uid("decision"), uid("journey"), uid("view")
            token = capability_token or secrets.token_urlsafe(32)
            decision = {"id": decision_id, "journey_id": journey_id, "created_at": now(), "policy_revision": self.kernel.revision,
                "context": context.model_dump(), "configuration": candidates[index].model_dump(), "features": [] if standard else matrix[index].tolist(),
                "feature_names": [] if standard else list(NAMES[:self.manifest["dimension"]]), "evaluation": evaluations,
                "measurements": p["measurements"].model_dump(mode="json"), "draw_seed": str(seed), "sampled_parameters": [] if standard else draw.tolist(),
                "selection_mode": "standard" if standard else ("forced" if len(candidates) == 1 else "thompson"),
                "effective_context": copy.deepcopy(metadata), "learning_eligible": not standard,
                "scores": [] if standard else [{"id": c.key, "configuration": c.model_dump(), "mean": float(means[i]), "std": float(deviations[i]), "sampled": float(scores[i])} for i, c in enumerate(candidates)]}
            self.state["decisions"][decision_id] = decision
            journey = {"id": journey_id, "request_id": request_id, "token_hash": digest(token), "decision_id": decision_id,
                "document": copy.deepcopy(p["document"]), "current_view": view_id, "root_view": view_id,
                "views": {view_id: {"id": view_id, "parent": None, "configuration": candidates[index].model_dump(), "displayed": [], "rating": None}},
                "routing": "standard" if standard else "adaptive", "identity": copy.deepcopy(metadata), "events": [], "seen": [], "focus": None, "focused_routes": {}, "opportunities": {}, "created_at": now(), "adjustments": {}}
            self.add_opportunities(journey, view_id)
            self.state["journeys"][journey_id] = journey
            return {"token": token, **self.public(journey)}
        return self._write(change)

    def add_opportunities(self, j, view_id):
        for dimension, cap in j["document"]["capabilities"].items():
            key=f"{view_id}:{dimension}"
            j["opportunities"].setdefault(key, {"id":key,"dimension":dimension,"view_id":view_id,
                "available":cap["applicable"],"visible":False,"scope":"support_control", "created_at":now()})

    def authorized(self, journey_id, token):
        j = self.state["journeys"].get(journey_id)
        if j is None or not secrets.compare_digest(j["token_hash"], digest(token)):
            raise PermissionError("unknown journey or invalid capability")
        return j

    def public(self, j):
        result = {k: copy.deepcopy(v) for k, v in j.items() if k not in ("token_hash", "request_id", "adjustments")}
        result["available_configurations"] = [copy.deepcopy(e["configuration"]) for e in self.state["decisions"][j["decision_id"]]["evaluation"] if not e["reasons"]]
        return result

    def read(self, journey_id, token):
        with self.lock:
            return self.public(self.authorized(journey_id, token))

    def event(self, journey_id, token, payload):
        def change():
            j = self.authorized(journey_id, token)
            if j.get("constraints_revoked"):
                return self.public(j)  # Tell stale clients to retire incompatible UI.
            if payload["type"] not in EVENTS:
                raise ValueError("unknown event type")
            existing = next((e for e in j["events"] if e["event_id"] == payload["event_id"]), None)
            if existing:
                if existing["client_payload"] != payload:
                    raise Conflict("event id reused with different content")
                return self.public(j)
            if payload["view_id"] != j["current_view"]:
                raise Conflict("stale view event")
            action = payload.get("action_id")
            if action and action not in {a["id"] for a in j["document"]["actions"]}:
                raise ValueError("unknown action")
            view = j["views"][j["current_view"]]
            if payload["type"] == "action_visible":
                if not action:
                    raise ValueError("action display needs action")
                if action not in view["displayed"]:
                    view["displayed"].append(action)
                if action not in j["seen"]:
                    j["seen"].append(action)
                j["focus"] = action
                for dimension, cap in j["document"]["capabilities"].items():
                    key = f"{view['id']}:{dimension}"
                    j["opportunities"].setdefault(key, {"id": key, "dimension": dimension, "view_id": view["id"], "available": cap["applicable"], "visible": False})
            elif payload["type"] == "navigate":
                if not action:
                    raise ValueError("navigation needs an action")
                j["focus"] = action
            elif payload["type"] == "opportunity_visible":
                key = payload.get("opportunity_id")
                if key not in j["opportunities"] or j["opportunities"][key]["view_id"] != view["id"]:
                    raise ValueError("unknown opportunity")
                j["opportunities"][key]["visible"] = True
                j["opportunities"][key]["last_visible_at"] = now()
            if payload["type"] in ("map_expand", "map_collapse") and view["configuration"]["relationships"] != "map":
                raise ValueError("map size event requires an active map")
            if payload["type"] == "route_focus":
                matches = [b for b in j["document"]["branches"] if any(o["option_id"] == payload.get("value") for o in b["options"])]
                if not matches:
                    raise ValueError("unknown route focus")
                if matches[0]["selection"] != "XOR":
                    raise ValueError("exclusive route focus requires an XOR group")
                j["focused_routes"][matches[0]["group_id"]] = payload["value"]
            if payload["type"] == "reason" and payload.get("value") not in ("explanation", "other_or_unsure"):
                raise ValueError("unknown diagnostic code")
            if payload["type"] in ("detail_open", "detail_close"):
                supplied = next((a for a in j["document"]["actions"] if a["id"] == action), None)
                if not supplied or payload.get("value") not in {b["id"] for b in supplied["optional"]}:
                    raise ValueError("detail event must reference a supplied optional block")
            if payload["type"] == "recap_open" and (view["configuration"]["recap"] != "on" or not action):
                raise ValueError("recap is not active for this action")
            if payload["type"] in ("detail_open", "detail_close", "recap_open"):
                dimension = "recap" if payload["type"] == "recap_open" else "disclosure"
                key = f"{view['id']}:{dimension}"
                if key not in j["opportunities"] or not j["opportunities"][key]["available"]:
                    raise ValueError("no applicable support opportunity")
            j["events"].append({"event_id": payload["event_id"], "client_payload": copy.deepcopy(payload), "server_received_at": now(),
                "sequence": len(j["events"]) + 1, "journey_id": j["id"], "decision_id": j["decision_id"], "origin": self.manifest["mode"],
                "graph_fingerprint": j["document"]["graph_fingerprint"], "content_fingerprint": j["document"]["content_fingerprint"],
                "reward": None, "interpretation": "activity; not inferred preference or completion"})
            return self.public(j)
        return self._write(change)

    def adjust(self, journey_id, token, view_id, config: Configuration, event_id):
        def change():
            j = self.authorized(journey_id, token)
            if j.get("constraints_revoked"):
                raise Conflict("hard requirements changed; request fresh guidance")
            payload = {"from": view_id, "configuration": config.model_dump()}
            if event_id in j["adjustments"]:
                if j["adjustments"][event_id] != payload:
                    raise Conflict("adjustment id conflict")
                return self.public(j)
            if view_id != j["current_view"]:
                raise Conflict("stale adjustment")
            decision = self.state["decisions"][j["decision_id"]]
            valid = {e["id"] for e in decision["evaluation"] if not e["reasons"]}
            if config.key not in valid:
                raise ValueError("adjustment violates frozen hard feasibility")
            new_id = uid("view")
            j["views"][new_id] = {"id": new_id, "parent": view_id, "configuration": config.model_dump(), "displayed": [], "rating": None}
            j["current_view"] = new_id
            self.add_opportunities(j, new_id)
            j["adjustments"][event_id] = payload
            j["events"].append({"event_id": event_id, "type": "explicit_adjustment", "server_received_at": now(), "from": view_id, "to": new_id, "configuration": config.model_dump(), "reward": None, "sequence": len(j["events"]) + 1, "journey_id": j["id"], "decision_id": j["decision_id"], "origin": self.manifest["mode"], "graph_fingerprint": j["document"]["graph_fingerprint"], "content_fingerprint": j["document"]["content_fingerprint"], "interpretation": "explicit presentation request; not a reward"})
            return self.public(j)
        return self._write(change)

    def rate(self, journey_id, token, view_id, rating):
        if rating not in ("about_right", "need_more", "too_much"):
            raise ValueError("unknown support-fit rating")
        def change():
            j = self.authorized(journey_id, token)
            if view_id != j["current_view"]:
                raise Conflict("rate the current view")
            view = j["views"][view_id]
            if not view["displayed"]:
                raise ValueError("cannot rate an undisplayed view")
            if view["rating"]:
                if view["rating"]["rating"] != rating:
                    raise Conflict("view already rated")
                return view["rating"]
            eligible = view_id == j["root_view"] and len(j["views"]) == 1 and self.state["decisions"][j["decision_id"]].get("learning_eligible", True) and not j.get("learning_revoked", False)
            receipt = {"rating": rating, "reward": int(rating == "about_right") if eligible else None, "eligible": eligible,
                       "decision_id": j["decision_id"], "view_id": view_id, "origin": self.manifest["mode"], "at": now(),
                       "exclusion_reason": None if eligible else ("standard_guidance" if not self.state["decisions"][j["decision_id"]].get("learning_eligible",True) else ("constraints_changed" if j.get("constraints_revoked") else ("personalization_revoked" if j.get("learning_revoked") else "manual_adjustment")))}
            if eligible:
                self.kernel.observe(self.state["decisions"][j["decision_id"]]["features"], receipt["reward"])
                self.state["updates"].append(receipt)
            receipt["posterior_revision"] = self.kernel.revision
            view["rating"] = receipt
            return receipt
        return self._write(change)

    def inspect(self, journey_id, token):
        with self.lock:
            j = self.authorized(journey_id, token)
            return {"journey": self.public(j), "decision": copy.deepcopy(self.state["decisions"][j["decision_id"]]),
                    "policy": self.status(), "history_transfer": {"status": "abstain", "reason": "PP2 scoring is not implemented"}}

    def close(self):
        self.db.close()

