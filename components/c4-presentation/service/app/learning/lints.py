"""PP1 shared Gaussian LinTS; reuses the tested Gaussian numerical kernel only.

No V2 snapshot, coefficient, action adapter, or history adjustment is reused.
"""
import hashlib
import io
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4
import numpy as np
from scipy.linalg import solve_triangular
from app.learning.posterior import GaussianPosterior
from app.models.policy import PolicyConfig
from app.guidance import features
from app.guidance.catalogue import ACTION_SCHEMA
from app.guidance.content import GuidanceContent
CONTENT_SCHEMA = GuidanceContent.model_fields["schema_version"].default
from app.guidance.sources import digest

MODEL_SCHEMA = "c4-shared-gaussian-pp1-1.0"
STORE_SCHEMA = "c4-pp1-policy-store-1.0"
C4_ROOT = Path(__file__).resolve().parents[3]


def manifest(variant="525", *, exploration=1.0):
    return {"model": MODEL_SCHEMA, "action": ACTION_SCHEMA, "features": features.SCHEMA,
            "feature_fingerprint": features.FINGERPRINT, "variant": variant, "dimension": features.VARIANTS[variant],
            "content": CONTENT_SCHEMA, "reward": "fits-1-does-not-fit-0-pp1", "prior_precision": 1.0,
            "noise": 1.0, "exploration": exploration, "reward_center": 0.5}


@dataclass(frozen=True)
class PolicyProfile:
    """Which meanings a policy is bound to. The default is the historical 3.0 profile; the 3.1 pipeline supplies its own."""
    name: str
    manifest: Callable
    action_schema: str
    encoder_schema: str
    feature_fingerprint: str
    config_key: Callable


PROFILE_30 = PolicyProfile("3.0", manifest, ACTION_SCHEMA, features.SCHEMA, features.FINGERPRINT, lambda c: c.key)


class Model:
    def __init__(self, variant="525", *, exploration=1.0, profile=PROFILE_30):
        self.profile = profile
        self.manifest = profile.manifest(variant, exploration=exploration)
        self.kernel = GaussianPosterior(features.VARIANTS[variant], PolicyConfig(exploration_scale=exploration))

    @property
    def revision(self): return self.kernel.revision

    def state(self):
        stream = io.BytesIO()
        np.savez(stream, precision=self.kernel._precision, b=self.kernel._b,
                 revision=np.array(self.revision), manifest=np.array(json.dumps(self.manifest, sort_keys=True)))
        return stream.getvalue()

    @classmethod
    def restore(cls, blob, expected=None, profile=PROFILE_30):
        with np.load(io.BytesIO(blob), allow_pickle=False) as data:
            meta = json.loads(str(data["manifest"]))
            model = cls(meta["variant"], exploration=meta["exploration"], profile=profile)
            if meta != model.manifest or expected is not None and meta != expected:
                raise ValueError("incompatible PP1 checkpoint manifest")
            a = np.array(data["precision"], dtype=float); b = np.array(data["b"], dtype=float)
            revision = int(data["revision"])
        d = meta["dimension"]
        if a.shape != (d, d) or b.shape != (d,) or revision < 0 or not np.isfinite(a).all() or not np.isfinite(b).all() or not np.allclose(a, a.T, rtol=0, atol=1e-12):
            raise ValueError("invalid PP1 checkpoint arrays")
        factor = np.linalg.cholesky(a)
        mean = solve_triangular(factor.T, solve_triangular(factor, b, lower=True, check_finite=False), lower=False, check_finite=False)
        if not np.isfinite(mean).all(): raise ValueError("invalid posterior mean")
        k = model.kernel
        k._precision, k._b, k._factor, k._mean, k.revision = a, b, factor, mean, revision
        return model

    def score(self, matrix, seed):
        sampled = 0.5 + self.kernel._matrix(matrix) @ self.kernel.sample(seed)
        means, std = self.kernel.moments(matrix)
        return int(np.argmax(sampled)), sampled, means, std

    def update(self, vector, reward): self.kernel.observe(vector, reward)

    def save(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(C4_ROOT): raise ValueError("checkpoint outside C4")
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = self.state()
        with path.open("xb") as file: file.write(blob)
        return hashlib.sha256(blob).hexdigest()


class PolicyStore:
    """Fresh isolated store attached to journey transactions for atomic ratings.

    SQLite rollback journals (never WAL) permit an atomic attached-database commit.
    Every operation reloads under BEGIN IMMEDIATE; no stale in-memory model writer.
    """
    def __init__(self, directory, *, seed=0, mode="simulation", checkpoint=None, profile=PROFILE_30, exploration=1.0):
        self.profile = profile
        directory = Path(directory).resolve()
        if not directory.is_relative_to(C4_ROOT) or "pp1-learning" not in directory.parts:
            raise ValueError("PP1 model needs isolated C4/pp1-learning storage")
        if mode not in ("simulation", "participant"): raise ValueError("invalid PP1 data mode")
        if type(seed) is not int or not 0 <= seed < 2**63: raise ValueError("invalid seed")
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "policy.sqlite3"
        self.expected = profile.manifest(exploration=exploration)
        self.seed, self.mode = seed, mode
        initial = Path(checkpoint).resolve() if checkpoint else None
        if initial and not initial.is_relative_to(C4_ROOT): raise ValueError("checkpoint outside C4")
        initial_blob = initial.read_bytes() if initial else None
        self.initial_digest = hashlib.sha256(initial_blob).hexdigest() if initial_blob else None
        with sqlite3.connect(self.path) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and "pp1_manifest" not in tables: raise ValueError("refusing unrelated policy database")
            db.execute("CREATE TABLE IF NOT EXISTS pp1_manifest(body TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS posterior(id INTEGER PRIMARY KEY CHECK(id=1),state BLOB NOT NULL,counter INTEGER NOT NULL,run TEXT NOT NULL,initial_revision INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS updates(journey_id TEXT PRIMARY KEY,event_id TEXT,reward INTEGER,revision INTEGER,state_digest TEXT)")
            expected = {"store": STORE_SCHEMA, "model": self.expected, "seed": seed, "mode": mode, "initial_checkpoint_digest": self.initial_digest}
            row = db.execute("SELECT body FROM pp1_manifest").fetchone()
            if row and json.loads(row[0]) != expected: raise ValueError("existing PP1 state manifest differs; choose a fresh directory")
            if not row:
                model = Model.restore(initial_blob, self.expected, profile) if initial_blob else Model(exploration=exploration, profile=profile)
                db.execute("INSERT INTO pp1_manifest VALUES (?)", (json.dumps(expected),))
                db.execute("INSERT INTO posterior VALUES (1,?,0,?,?)", (model.state(), "pp1-run:" + uuid4().hex, model.revision))
            Model.restore(db.execute("SELECT state FROM posterior").fetchone()[0], self.expected, profile)

    def attach(self, db):
        if "pp1" not in {r[1] for r in db.execute("PRAGMA database_list")}:
            db.execute("ATTACH DATABASE ? AS pp1", (str(self.path),))

    def _load(self, db):
        self.attach(db)
        row = db.execute("SELECT state,counter,run,initial_revision FROM pp1.posterior WHERE id=1").fetchone()
        return Model.restore(row[0], self.expected, self.profile), row

    def status(self):
        with sqlite3.connect(self.path) as db:
            blob, counter, run, initial_revision = db.execute("SELECT state,counter,run,initial_revision FROM posterior WHERE id=1").fetchone()
            model = Model.restore(blob, self.expected, self.profile)
            return {"manifest": self.expected, "manifest_fingerprint": digest(self.expected), "policy_run_id": run,
                    "posterior_revision": model.revision, "accepted_feedback_count": db.execute("SELECT count(*) FROM updates").fetchone()[0],
                    "initial_training_revision": initial_revision, "decision_count": counter,
                    "posterior_fingerprint": hashlib.sha256(blob).hexdigest(), "mode": self.mode,
                    "training_provenance": ("mixed_explicitly_versioned" if initial_revision and model.revision>initial_revision else "participant") if self.mode=="participant" and model.revision>initial_revision else ("synthetic" if model.revision else "fresh_prior")}

    def select(self, db, measurements, context, configs):
        model, row = self._load(db)
        counter = row[1]
        seed = int(np.random.SeedSequence([self.seed, counter]).generate_state(1, dtype=np.uint64)[0])
        matrix = np.array([features.encode(measurements, context, c, self.expected["variant"]) for c in configs])
        index, scores, means, std = model.score(matrix, seed)
        db.execute("UPDATE pp1.posterior SET counter=counter+1 WHERE id=1")
        provenance = "synthetic" if model.revision else "fresh_prior"
        if self.mode == "participant" and model.revision > row[3]:
            provenance = "mixed_explicitly_versioned" if row[3] else "participant"
        evidence = {"algorithm": "shared_gaussian_lints", "action_schema": self.profile.action_schema,
            "encoder_schema": self.profile.encoder_schema, "model_manifest_fingerprint": digest(model.manifest),
            "policy_run_id": row[2], "posterior_revision": model.revision, "decision_id": "decision:" + uuid4().hex,
            "training_provenance": provenance}
        record = {"policy": evidence, "seed": seed, "decision_number": counter, "feature_fingerprint": self.profile.feature_fingerprint,
            "selected_features": matrix[index].tolist(), "selected_feature_digest": digest(matrix[index].tolist()),
            "candidates": [{"configuration": c.model_dump(), "id": self.profile.config_key(c), "sampled_score": float(s), "posterior_mean": float(m), "posterior_std": float(v)}
                           for c, s, m, v in zip(configs, scores, means, std)],
            "manifest": model.manifest, "selected_id": self.profile.config_key(configs[index])}
        return configs[index], record

    def update(self, db, journey, event_id, reward):
        model, row = self._load(db)
        previous = db.execute("SELECT reward,revision,state_digest FROM pp1.updates WHERE journey_id=?", (journey["id"],)).fetchone()
        if previous: raise ValueError("journey already updated")
        record = journey["decision"]
        if record["policy"]["policy_run_id"] != row[2] or record["manifest"] != self.expected:
            raise ValueError("decision belongs to another model")
        before = model.revision
        model.update(record["selected_features"], reward)
        blob = model.state(); fingerprint = hashlib.sha256(blob).hexdigest()
        db.execute("UPDATE pp1.posterior SET state=? WHERE id=1", (blob,))
        db.execute("INSERT INTO pp1.updates VALUES (?,?,?,?,?)", (journey["id"], event_id, reward, model.revision, fingerprint))
        return {"revision_before": before, "revision_after": model.revision, "state_digest": fingerprint}
