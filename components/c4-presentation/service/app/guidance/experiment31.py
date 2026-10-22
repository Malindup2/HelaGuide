"""PP1 v3.1 synthetic bandit study. SYNTHETIC EVALUATION ONLY; no live profiles, no API state, no v3.0 posterior.

  python -m app.guidance.experiment31 train  --output <new C4/.../pp1-learning/dir> --seed 11 --budget 5000
  python -m app.guidance.experiment31 report --output <same dir>
  python -m app.guidance.experiment31 replay --output <same dir> --run seed-11-525

The policy picks from the feasible 3.1 set with Shared Gaussian LinTS, THEN the hidden simulator draws a binary reward for the
selected configuration only, then the posterior is updated. The policy never sees the simulator, the hidden regime, or the
outcome of any unselected configuration. Training, development and final test cases are separate; nothing is tuned on test.
"""
import argparse
import hashlib
import json
import math
import platform
import time
from pathlib import Path
import numpy as np
import scipy
from app.guidance import features, procedures31, synthetic31 as syn
from app.guidance.catalogue import CATALOGUE, Configuration, Constraints, DIMENSIONS
from app.guidance.content_v31 import GuidanceContent31, evaluate31, validate_content31
from app.guidance.policy import C4_ROOT, Model
from app.guidance.sources import ProcedureSource, digest
from app.guidance.v31_pipeline import FIXTURES31, PROFILE_31, config_key31
from app.v2.measurements import measurements
from app.v2.registration import workspace_registry

TRAIN = ("study-short-linear", "study-long-linear", "study-branching", "study-parallel-join", "study-info-heavy", "synthetic-linear-v1", "synthetic-practice-v2",
         "synthetic-parallel-v1", "official-birth_copy-v3", "official-nic_amendment-v3", "official-company_pack-v3")
DEV = ("study-multilevel", "synthetic-conditional-v1")
TEST = procedures31.HELD_OUT
CHECKPOINTS = (0, 50, 200, 600, 2000, 5000)
VARIANTS = ("416", "451", "516", "525")
ASSUMPTION_NAMES = tuple(syn.ASSUMPTIONS)
SEEDS = (11, 23, 37, 51, 71)
DEV_CASES, TEST_CASES = 220, 440


def dataset():
    entries, result = workspace_registry(), {}
    for pid, entry in entries.items():
        source = ProcedureSource(graph=entry["graph"], relationships=entry.get("overlay")).validate()
        file = FIXTURES31 / (pid + ".json")
        content = GuidanceContent31.model_validate(json.loads(file.read_text(encoding="utf-8"))["content"]) if file.exists() else None
        if content:
            validate_content31(source, content)
        result[pid] = {"source": source, "content": content, "assume": False}
    for pid in procedures31.SPECS:
        source = procedures31.source(pid)
        result[pid] = {"source": source, "content": procedures31.content(source), "assume": True}
    for item in result.values():
        item["measurements"] = measurements(item["source"].graph, item["source"].relationships)
        item["stages"] = len(item["source"].graph.stages)
        item["cache"] = {}
    return result


def feasible(item, constraints):
    key = json.dumps(constraints, sort_keys=True)
    if key not in item["cache"]:
        item["cache"][key] = [c.configuration for c in evaluate31(item["source"], item["content"], Constraints(**constraints), assume_reviewed=item["assume"]) if c.feasible]
    return item["cache"][key]


def support_total(config):
    return float(features.action_values(config)[:-1].sum())


def make_cases(data, procs, count, seed, split):
    rng = np.random.default_rng(seed)
    pool = {p: data[p] for p in procs}
    return [syn.scenario(rng, i, pool, split=split) for i in range(count)]


class World:
    """Evaluator-only: truths for every feasible configuration. Built once per split; never reachable from the policy."""

    def __init__(self, data, cases, variant_matrices=None):
        self.cases, self.data, self.items = cases, data, []
        for case in cases:
            item = data[case["procedure_id"]]
            allowed = feasible(item, case["constraints"])
            truth = {a: np.array([syn.probability(c, case["context"], item["measurements"], item["stages"], a, case["latent_regime"]) for c in allowed]) for a in ASSUMPTION_NAMES}
            gaps = [syn.gaps(c, case["context"], item["measurements"], item["stages"]) for c in allowed]
            self.items.append({"allowed": allowed, "truth": truth, "under": np.array([g[0].sum() for g in gaps]), "over": np.array([g[1].sum() for g in gaps])})
        self.matrices = {}

    def matrix(self, variant, i):
        key = (variant, i)
        if key not in self.matrices:
            case, w = self.cases[i], self.items[i]
            self.matrices[key] = np.array([features.encode(self.data[case["procedure_id"]]["measurements"], case["context"], c, variant) for c in w["allowed"]])
        return self.matrices[key]


def fixed_best_ranking(data, seed=909):
    """Best CONSTANT configuration chosen with hindsight on a fresh training-distribution sample (balanced world); a strong non-personalised baseline."""
    cases = make_cases(data, TRAIN, 1500, seed, "train")
    totals, counts = {}, {}
    for case in cases:
        item = data[case["procedure_id"]]
        allowed = feasible(item, case["constraints"])
        for c in allowed:
            p = syn.probability(c, case["context"], item["measurements"], item["stages"], "balanced", case["latent_regime"])
            totals[c.key] = totals.get(c.key, 0) + p
            counts[c.key] = counts.get(c.key, 0) + 1
    return [k for k, _ in sorted(((k, totals[k] / counts[k]) for k in totals if counts[k] >= 30), key=lambda kv: -kv[1])]


def assess(model, world, seed, ranking, variant):
    before = hashlib.sha256(model.state()).hexdigest()
    rows = []
    for i, case in enumerate(world.cases):
        w = world.items[i]
        allowed = w["allowed"]
        score_seed = int(np.random.SeedSequence([seed, 90001, i]).generate_state(1)[0])
        idx, scores, means, _ = model.score(world.matrix(variant, i), score_seed)
        greedy = int(np.argmax(means))   # diagnostic only: pure posterior-mean exploitation, NOT what LinTS does
        sup = np.array([support_total(c) for c in allowed])
        std = next((k for k, c in enumerate(allowed) if c == Configuration()), 0)
        fixed = next((k for r in ranking for k, c in enumerate(allowed) if c.key == r), std)
        mn = min(range(len(allowed)), key=lambda k: (sup[k], allowed[k].key))
        mx = max(range(len(allowed)), key=lambda k: (sup[k], allowed[k].key))
        row = {"family": case["family"], "procedure_id": case["procedure_id"], "unseen": case["procedure_id"] in TEST, "config": config_key31(allowed[idx]),
               "support": float(sup[idx]), "support_minimal": float(sup[mn]), "support_best": float(sup[int(np.argmax(w["truth"]["balanced"]))]),
               "under": float(w["under"][idx]), "over": float(w["over"][idx]), "violation": int(allowed[idx] not in allowed), "n_feasible": len(allowed),
               "selected": allowed[idx].model_dump()}
        for a in ASSUMPTION_NAMES:
            t = w["truth"][a]
            row[a] = {"reward": float(t[idx]), "greedy": float(t[greedy]), "standard": float(t[std]), "minimal": float(t[mn]), "maximal": float(t[mx]), "fixed_best": float(t[fixed]),
                      "random": float(t.mean()), "oracle": float(t.max())}
        rows.append(row)
    assert hashlib.sha256(model.state()).hexdigest() == before, "evaluation changed the posterior"
    return rows


def summarise(rows):
    def mean(path):
        return float(np.mean([path(r) for r in rows]))
    out = {"n_cases": len(rows), "violations": int(sum(r["violation"] for r in rows)),
           "under_support": mean(lambda r: r["under"]), "over_support": mean(lambda r: r["over"]), "support_mean": mean(lambda r: r["support"]),
           "support_best_mean": mean(lambda r: r["support_best"]), "support_minimal_mean": mean(lambda r: r["support_minimal"]), "assumptions": {}}
    for a in ASSUMPTION_NAMES:
        block = {k: mean(lambda r, k=k: r[a][k]) for k in ("reward", "greedy", "standard", "minimal", "maximal", "fixed_best", "random", "oracle")}
        block["regret"] = block["oracle"] - block["reward"]
        out["assumptions"][a] = block
    families = {}
    for fam in sorted({r["family"] for r in rows}, key=lambda f: (f[0], int(f[1:]))):
        sub = [r for r in rows if r["family"] == fam]
        families[fam] = {k: float(np.mean([r["balanced"][k] for r in sub])) for k in ("reward", "standard", "oracle", "minimal", "maximal")} | {"n": len(sub), "support": float(np.mean([r["support"] for r in sub])), "support_best": float(np.mean([r["support_best"] for r in sub]))}
    out["by_family"] = families
    for name, flag in (("unseen_procedures", True), ("seen_procedures", False)):
        sub = [r for r in rows if r["unseen"] is flag]
        out[name] = ({k: float(np.mean([r["balanced"][k] for r in sub])) for k in ("reward", "standard", "oracle", "fixed_best")} | {"n": len(sub)}) if sub else None
    dist = {}
    for r in rows:
        dist[r["config"]] = dist.get(r["config"], 0) + 1
    out["distribution"] = dict(sorted(dist.items(), key=lambda kv: -kv[1])[:12])
    out["dimension_counts"] = {d: {s: sum(r["selected"][d] == s for r in rows) for s in states} for d, states in DIMENSIONS.items()}
    return out


def train(output, *, seed, budget, assumption="balanced", variants=VARIANTS, checkpoints=CHECKPOINTS, exploration=1.0):
    output = Path(output).resolve()
    if not output.is_relative_to(C4_ROOT) or "pp1-learning" not in output.parts:
        raise ValueError("isolated C4/pp1-learning experiment directory required")
    output.mkdir(parents=True, exist_ok=True)
    label = assumption if exploration == 1.0 else f"{assumption}@x{exploration}"
    tag = f"seed-{seed}" + ("" if assumption == "balanced" else "-" + assumption) + ("" if exploration == 1.0 else f"-x{exploration}")
    if (output / f"result-{tag}.json").exists():
        raise ValueError("refusing to overwrite " + tag)
    checkpoints = sorted({c for c in checkpoints if c <= budget} | {0, budget})
    data = dataset()
    training = {p: data[p] for p in TRAIN}
    rng = np.random.default_rng(seed)
    schedule = [syn.scenario(rng, i, training, split="train") for i in range(budget)]
    uniforms = np.random.default_rng(np.random.SeedSequence([seed, 771])).random(budget)
    dev = make_cases(data, DEV + TRAIN, DEV_CASES, 5101, "dev")
    test = make_cases(data, TEST + TRAIN, TEST_CASES, 80221, "test")
    ranking = fixed_best_ranking(data)
    worlds = {"dev": World(data, dev), "test": World(data, test)}
    if not (output / "cases.json").exists():
        (output / "cases.json").write_text(json.dumps({"dev": dev, "test": test, "fixed_best_ranking": ranking[:10]}), encoding="utf-8")
    (output / f"schedule-{tag}.json").write_text(json.dumps(schedule), encoding="utf-8")
    records, runs = [], []
    for variant in variants:
        model = Model(variant, exploration=exploration, profile=PROFILE_31)
        chain = digest(model.manifest)
        name = f"{tag}-{variant}"
        started = time.time()
        with (output / (name + ".jsonl")).open("x", encoding="utf-8") as trace:
            for episode in range(budget + 1):
                if episode in checkpoints:
                    path = output / (name + f"-n{episode}.npz")
                    digest_ = model.save(path)
                    restored = Model.restore(path.read_bytes(), model.manifest, PROFILE_31)
                    assert restored.state() == model.state()
                    record = {"run": name, "variant": variant, "seed": seed, "assumption": label, "exploration": exploration, "episode": episode, "checkpoint": path.name, "checkpoint_digest": digest_,
                              "update_chain": chain, "posterior_revision": restored.revision}
                    for split, world in worlds.items():
                        rows = assess(restored, world, seed, ranking, variant)
                        record[split] = summarise(rows)
                    records.append(record)
                    print(f"{name} n={episode} dev={record['dev']['assumptions']['balanced']['reward']:.4f} test={record['test']['assumptions']['balanced']['reward']:.4f} std={record['test']['assumptions']['balanced']['standard']:.4f} ({time.time() - started:.0f}s)", flush=True)
                if episode == budget:
                    break
                case = schedule[episode]
                item = data[case["procedure_id"]]
                allowed = feasible(item, case["constraints"])
                matrix = np.array([features.encode(item["measurements"], case["context"], c, variant) for c in allowed])
                decision_seed = int(np.random.SeedSequence([seed, episode]).generate_state(1, dtype=np.uint64)[0])
                chosen, scores, _, _ = model.score(matrix, decision_seed)
                config = allowed[chosen]
                # The policy has finished choosing; only now is the hidden world consulted, for the selected configuration alone.
                p = syn.probability(config, case["context"], item["measurements"], item["stages"], assumption, case["latent_regime"])
                reward = int(uniforms[episode] < p)
                before = model.revision
                model.update(matrix[chosen], reward)
                vector = digest(matrix[chosen].tolist())
                chain = digest({"previous": chain, "features": vector, "reward": reward})
                trace.write(json.dumps({"run": name, "episode": episode + 1, "scenario_id": case["id"], "family": case["family"], "procedure_id": case["procedure_id"],
                    "context": case["context"], "constraints": case["constraints"], "feasible_count": len(allowed), "seed": decision_seed, "selected_index": int(chosen),
                    "configuration": config.model_dump(), "selected_score": float(scores[chosen]), "scores_digest": digest([float(s) for s in scores]),
                    "selected_feature_digest": vector, "reward": reward, "response_uniform": float(uniforms[episode]), "simulated_selected_probability": p,
                    "revision_before": before, "revision_after": model.revision, "update_chain": chain, "feedback_origin": "simulation"}, separators=(",", ":")) + "\n")
        runs.append({"run": name, "variant": variant, "trace": name + ".jsonl", "schedule_hash": digest(schedule), "seconds": round(time.time() - started, 1)})
    (output / f"result-{tag}.json").write_text(json.dumps({"tag": tag, "seed": seed, "assumption": label, "exploration": exploration, "budget": budget, "records": records, "runs": runs}), encoding="utf-8")


def replay(output, run):
    """Exact selected-only replay: recompute every sampled-score vector and posterior update from the immutable trace."""
    output = Path(output).resolve()
    seed = int(run.split("-")[1])
    variant = run.rsplit("-", 1)[1]
    first = sorted(output.glob(run + "-n0.npz"))[0]
    with np.load(first, allow_pickle=False) as archive:
        exploration = json.loads(str(archive["manifest"]))["exploration"]
    data = dataset()
    model = Model(variant, exploration=exploration, profile=PROFILE_31)
    chain = digest(model.manifest)
    count = 0
    for line in (output / (run + ".jsonl")).read_text(encoding="utf-8").splitlines():
        obs = json.loads(line)
        item = data[obs["procedure_id"]]
        allowed = feasible(item, obs["constraints"])
        matrix = np.array([features.encode(item["measurements"], obs["context"], c, variant) for c in allowed])
        idx, scores, _, _ = model.score(matrix, obs["seed"])
        if idx != obs["selected_index"] or digest([float(s) for s in scores]) != obs["scores_digest"] or digest(matrix[idx].tolist()) != obs["selected_feature_digest"]:
            raise ValueError(f"decision replay mismatch at episode {obs['episode']}")
        if model.revision != obs["revision_before"]:
            raise ValueError("revision mismatch")
        model.update(matrix[idx], obs["reward"])
        chain = digest({"previous": chain, "features": obs["selected_feature_digest"], "reward": obs["reward"]})
        if chain != obs["update_chain"] or model.revision != obs["revision_after"]:
            raise ValueError("update chain mismatch")
        count += 1
        for path in sorted(output.glob(run + f"-n{count}.npz")):
            if Model.restore(path.read_bytes(), model.manifest, PROFILE_31).state() != model.state():
                raise ValueError("checkpoint mismatch at " + path.name)
    return {"run": run, "replayed_observations": count, "exact_scores": True, "exact_state": True, "update_chain": chain, "seed": seed}


def reassess(output, tag):
    """Re-evaluate saved checkpoints WITHOUT updating them, adding the greedy-mean diagnostic. Original result files are never rewritten;
    the sampled-selection numbers must reproduce exactly (an extra determinism check)."""
    output = Path(output).resolve()
    original = json.loads((output / f"result-{tag}.json").read_text(encoding="utf-8"))
    data = dataset()
    ranking = fixed_best_ranking(data)
    worlds = {"dev": World(data, make_cases(data, DEV + TRAIN, DEV_CASES, 5101, "dev")), "test": World(data, make_cases(data, TEST + TRAIN, TEST_CASES, 80221, "test"))}
    records = []
    for record in original["records"]:
        blob = (output / record["checkpoint"]).read_bytes()
        with np.load(__import__("io").BytesIO(blob), allow_pickle=False) as archive:
            exploration = json.loads(str(archive["manifest"]))["exploration"]
        model = Model.restore(blob, PROFILE_31.manifest(record["variant"], exploration=exploration), PROFILE_31)
        fresh = dict(record)
        for split, world in worlds.items():
            fresh[split] = summarise(assess(model, world, record["seed"], ranking, record["variant"]))
            if abs(fresh[split]["assumptions"]["balanced"]["reward"] - record[split]["assumptions"]["balanced"]["reward"]) > 1e-12:
                raise ValueError("re-assessment did not reproduce the original sampled result")
        records.append(fresh)
    (output / f"reassessed-{tag}.json").write_text(json.dumps({**original, "records": records}), encoding="utf-8")


def interval(values):
    from scipy.stats import t
    x = np.array(values, dtype=float)
    n = len(x)
    return {"mean": float(x.mean()), "ci95_half_width": float(t.ppf(0.975, n - 1) * x.std(ddof=1) / math.sqrt(n)) if n > 1 else None, "n_seeds": n, "min": float(x.min()), "max": float(x.max())}


def report(output):
    output = Path(output).resolve()
    results = []
    for p in sorted(output.glob("result-*.json")):
        again = output / p.name.replace("result-", "reassessed-")
        results.append(json.loads((again if again.exists() else p).read_text(encoding="utf-8")))
    if not results:
        raise ValueError("no results to report")
    records = [r for res in results for r in res["records"]]
    groups = {}
    for r in records:
        groups.setdefault((r["variant"], r["assumption"], r["episode"]), []).append(r)
    aggregate = []
    for (variant, assumption, episode), rows in sorted(groups.items()):
        entry = {"variant": variant, "training_assumption": assumption, "episode": episode, "n_seeds": len(rows)}
        for split in ("dev", "test"):
            block = {}
            for a in ASSUMPTION_NAMES:
                block[a] = {k: interval([r[split]["assumptions"][a][k] for r in rows]) for k in ("reward", "greedy", "regret", "standard", "minimal", "maximal", "fixed_best", "random", "oracle") if all(k in r[split]["assumptions"][a] for r in rows)}
            block["under_support"] = interval([r[split]["under_support"] for r in rows])
            block["over_support"] = interval([r[split]["over_support"] for r in rows])
            block["support_mean"] = interval([r[split]["support_mean"] for r in rows])
            block["violations"] = int(sum(r[split]["violations"] for r in rows))
            entry[split] = block
        aggregate.append(entry)
    out = {"schema": "c4-pp1-experiment-3.1", "label": "SYNTHETIC EVALUATION ONLY", "simulator": syn.SPEC, "simulator_fingerprint": syn.FINGERPRINT,
           "feature_schema": PROFILE_31.encoder_schema, "feature_fingerprint": PROFILE_31.feature_fingerprint, "manifest": PROFILE_31.manifest(),
           "splits": {"train_procedures": TRAIN, "dev_procedures": DEV, "test_unseen_procedures": TEST, "dev_cases": DEV_CASES, "test_cases": TEST_CASES},
           "budgets_per_independent_run": sorted({r["episode"] for r in records}), "seeds": sorted({res["seed"] for res in results}),
           "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
           "limitations": ["SYNTHETIC EVALUATION ONLY: the response model is author-defined, external expert review is pending, and nothing here measures real-citizen comprehension or benefit.",
                           "The primary 'balanced' world contains many high-need citizens, so standard guidance does poorly in it by construction; 'low_need' is the opposite world. Conclusions must be read across assumptions.",
                           "Study procedures are fictional with templated wording; official procedures are fallback probes with only four feasible configurations each.",
                           "Binary rewards under a Gaussian linear surrogate are misspecified; sampled scores are not calibrated probabilities.",
                           "Encoder variants and budgets are compared on development cases; the final test cases were not used for any choice."],
           "aggregates": aggregate, "runs": [run for res in results for run in res["runs"]]}
    (output / "report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def plots(output):
    """Genuine learning curves and baseline comparisons from the saved results. Nothing is smoothed, hidden or selected after the fact."""
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(C4_ROOT / "service" / ".local" / "pp1-learning" / "mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output = Path(output).resolve()
    rep = json.loads((output / "report.json").read_text(encoding="utf-8"))
    results = [json.loads((lambda q: q if q.exists() else p)(output / p.name.replace("result-", "reassessed-")).read_text(encoding="utf-8")) for p in sorted(output.glob("result-*.json"))]
    agg = [a for a in rep["aggregates"] if a["training_assumption"] == "balanced"]
    episodes = sorted({a["episode"] for a in agg})
    colour = {"416": "#8a8a8a", "451": "#b9b9b9", "516": "#5b7db1", "525": "#f5691a"}
    made = []
    for split in ("dev", "test"):
        fig, ax = plt.subplots(figsize=(8, 5))
        for v in VARIANTS:
            rows = sorted((a for a in agg if a["variant"] == v), key=lambda a: a["episode"])
            if not rows:
                continue
            x = [r["episode"] for r in rows]
            y = np.array([r[split]["balanced"]["reward"]["mean"] for r in rows])
            h = np.array([r[split]["balanced"]["reward"]["ci95_half_width"] or 0 for r in rows])
            ax.plot(range(len(x)), y, marker="o", color=colour[v], label=f"LinTS {v}")
            ax.fill_between(range(len(x)), y - h, y + h, color=colour[v], alpha=0.15)
        tuned = sorted((a for a in rep["aggregates"] if a["variant"] == "525" and a["training_assumption"] == "balanced@x0.25"), key=lambda a: a["episode"])
        if tuned:
            ax.plot([episodes.index(r["episode"]) for r in tuned], [r[split]["balanced"]["reward"]["mean"] for r in tuned], marker="s", linestyle="--", color="#a23d0a", label="LinTS 525, exploration 0.25 (chosen on development cases)")
        rows525 = sorted((a for a in agg if a["variant"] == "525" and "greedy" in a[split]["balanced"]), key=lambda a: a["episode"])
        if rows525:
            ax.plot(range(len(rows525)), [r[split]["balanced"]["greedy"]["mean"] for r in rows525], marker="^", linestyle=":", color="#2f6f4f", label="diagnostic: pure posterior mean, 525 (not LinTS)")
        ref = next(a for a in agg if a["variant"] == "525" and a["episode"] == 0)[split]["balanced"]
        for key, style in (("standard", "--"), ("minimal", ":"), ("maximal", "-."), ("fixed_best", "-"), ("random", ":"), ("oracle", "--")):
            ax.axhline(ref[key]["mean"], linestyle=style, color="#333", linewidth=1, alpha=0.7)
            ax.text(len(episodes) - 1 + 0.05, ref[key]["mean"], key.replace("_", " "), fontsize=8, va="center")
        ax.set_xticks(range(len(episodes)), [str(e) for e in episodes]); ax.set_xlabel("observations used for training (per independent run)")
        ax.set_ylabel("simulated expected reward (balanced world)"); ax.set_title(f"{split} cases: learning curves, mean and 95% interval over seeds (SYNTHETIC)")
        ax.legend(loc="upper left", bbox_to_anchor=(0.01, 0.9), fontsize=8); fig.tight_layout(); name = f"learning-curve-{split}.png"; fig.savefig(output / name, dpi=130); plt.close(fig); made.append(name)
    final = max(episodes)
    last = [a for a in agg if a["variant"] == "525" and a["episode"] == final][0]
    fig, ax = plt.subplots(figsize=(9, 5)); names = ["reward", "standard", "minimal", "maximal", "fixed_best", "random", "oracle"]
    width = 0.15
    for k, a in enumerate(ASSUMPTION_NAMES):
        ax.bar(np.arange(len(names)) + (k - 2.5) * width, [last["test"][a][n]["mean"] for n in names], width, label=a)
    ax.set_xticks(range(len(names)), ["LinTS 525" if n == "reward" else n.replace("_", " ") for n in names]); ax.set_ylabel("simulated expected reward (test)")
    ax.set_title(f"Sensitivity to the simulator assumption (LinTS 525 trained {final} observations under 'balanced')"); ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(output / "sensitivity-test.png", dpi=130); plt.close(fig); made.append("sensitivity-test.png")
    finals = [r for res in results for r in res["records"] if r["variant"] == "525" and r["assumption"] == "balanced" and r["episode"] == final]
    fams = sorted(finals[0]["test"]["by_family"], key=lambda f: (f[0], int(f[1:])))
    fig, ax = plt.subplots(figsize=(11, 5))
    for k, key in enumerate(("reward", "standard", "fixed_best_not_per_family", "oracle")):
        if key == "fixed_best_not_per_family":
            continue
        ax.bar(np.arange(len(fams)) + (k - 1.5) * 0.2, [np.mean([r["test"]["by_family"][f][key] for r in finals]) for f in fams], 0.2, label="LinTS 525" if key == "reward" else key)
    ax.set_xticks(range(len(fams)), fams); ax.set_ylabel("simulated expected reward (test)"); ax.set_title("Per scenario family (S = retained 3.0 hypotheses, N = new 3.1 situations)"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(output / "families-test.png", dpi=130); plt.close(fig); made.append("families-test.png")
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for key, label, col in (("under_support", "under-support (missing help)", "#5b7db1"), ("over_support", "over-support (surplus help)", "#f5691a")):
        rows = sorted((a for a in agg if a["variant"] == "525"), key=lambda a: a["episode"])
        ax[0].plot(range(len(rows)), [r["test"][key]["mean"] for r in rows], marker="o", color=col, label=label)
    ax[0].set_xticks(range(len(episodes)), [str(e) for e in episodes]); ax[0].set_title("Mismatch of the selected support (test)"); ax[0].legend(fontsize=8); ax[0].set_xlabel("observations")
    first = [r for res in results for r in res["records"] if r["variant"] == "525" and r["assumption"] == "balanced" and r["episode"] == 0]
    for label, group in (("n=0", first), (f"n={final}", finals)):
        shares = {d: np.mean([r["test"]["dimension_counts"][d][states[-1]] / r["test"]["n_cases"] for r in group]) for d, states in DIMENSIONS.items()}
        ax[1].plot(list(shares), list(shares.values()), marker="o", label=label)
    ax[1].set_ylim(0, 1); ax[1].set_title("Share of test cases where the last value of each scaffold is chosen"); ax[1].tick_params(axis="x", labelrotation=30); ax[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(output / "selection-mismatch.png", dpi=130); plt.close(fig); made.append("selection-mismatch.png")
    return made


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("train"); a.add_argument("--output", required=True); a.add_argument("--seed", type=int, required=True); a.add_argument("--budget", type=int, default=5000)
    a.add_argument("--assumption", default="balanced", choices=ASSUMPTION_NAMES); a.add_argument("--exploration", type=float, default=1.0); a.add_argument("--variants", nargs="+", default=list(VARIANTS))
    b = sub.add_parser("report"); b.add_argument("--output", required=True)
    c = sub.add_parser("replay"); c.add_argument("--output", required=True); c.add_argument("--run", required=True)
    d = sub.add_parser("plots"); d.add_argument("--output", required=True)
    e = sub.add_parser("reassess"); e.add_argument("--output", required=True); e.add_argument("--tag", required=True)
    args = parser.parse_args()
    if args.command == "train":
        train(args.output, seed=args.seed, budget=args.budget, assumption=args.assumption, variants=tuple(args.variants), exploration=args.exploration)
    elif args.command == "report":
        report(args.output)
    elif args.command == "reassess":
        reassess(args.output, args.tag)
    elif args.command == "plots":
        print(json.dumps(plots(args.output)))
    else:
        print(json.dumps(replay(args.output, args.run), indent=2))
