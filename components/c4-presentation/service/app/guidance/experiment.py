"""Reproducible PP1 synthetic bandit experiment. No live profiles or API state.

python -m app.guidance.experiment --output <new C4/pp1-learning directory>
"""
import argparse
import hashlib
import json
import math
import platform
from pathlib import Path
import numpy as np
import scipy
from app.guidance import features, synthetic
from app.guidance.policy import Model, C4_ROOT
from app.guidance.catalogue import Configuration, Constraints
from app.guidance.content import GuidanceContent, validate_content
from app.guidance.feasibility import evaluate
from app.guidance.sources import ProcedureSource, digest
from app.v2.registration import workspace_registry
from app.v2.measurements import measurements


def dataset():
    entries = workspace_registry(); result = {}
    for pid, entry in entries.items():
        source = ProcedureSource(graph=entry["graph"], relationships=entry.get("overlay")).validate()
        file = C4_ROOT / "research/data/guidance/fictional" / (pid + ".json")
        content = GuidanceContent.model_validate(json.loads(file.read_text(encoding="utf-8"))["content"]) if file.exists() else None
        if content: validate_content(source, content)
        result[pid] = {"source": source, "content": content, "measurements": measurements(source.graph, source.relationships)}
    return result


def candidates(item, case):
    return [c.configuration for c in evaluate(item["source"], item["content"], Constraints(**case["constraints"])) if c.feasible]


def heldout(data, count=60):
    rng = np.random.default_rng(80221)
    cases = []
    ids = sorted(data)
    for i in range(count):
        case = synthetic.scenario(rng, i, data, evaluation=True)
        case["procedure_id"] = ids[i % len(ids)]
        cases.append(case)
    return cases


def assess(model, cases, data, seed):
    before = hashlib.sha256(model.state()).hexdigest()
    values = []; dimensions = {d: {s: 0 for s in states} for d, states in __import__('app.guidance.catalogue',fromlist=['DIMENSIONS']).DIMENSIONS.items()}
    distribution = {}; comparisons = []
    for i, case in enumerate(cases):
        item = data[case["procedure_id"]]; allowed = candidates(item, case)
        matrix = np.array([features.encode(item["measurements"],case["context"],c,model.manifest["variant"]) for c in allowed])
        score_seed = int(np.random.SeedSequence([seed, 90001, i]).generate_state(1)[0])
        idx, scores, _, _ = model.score(matrix, score_seed)
        selected = allowed[idx]
        distribution[selected.key] = distribution.get(selected.key, 0) + 1
        for d, s in selected.model_dump().items(): dimensions[d][s] += 1
        # Only evaluator can enumerate counterfactual expected rewards.
        for regime in ("primary", "preference_shift", "burden_shift", "null"):
            regime = case["latent_regime"] if regime=="primary" else regime
            truth = np.array([synthetic.probability(c,case["context"],item["measurements"],regime) for c in allowed])
            minimal = min(range(len(allowed)),key=lambda k: (sum(features.action_values(allowed[k])[:-1]),allowed[k].key))
            maximal = max(range(len(allowed)),key=lambda k: (sum(features.action_values(allowed[k])[:-1]),allowed[k].key))
            standard = next((k for k,c in enumerate(allowed) if c==Configuration()),0)
            values.append({"case_id":case["id"],"procedure_id":case["procedure_id"],"regime":regime,
                "expected_reward":float(truth[idx]),"regret":float(max(truth)-truth[idx]),
                "standard":float(truth[standard]),"minimal":float(truth[minimal]),"maximal":float(truth[maximal]),
                "random":float(np.mean(truth)),"oracle":float(max(truth)),"violations":int(selected not in allowed)})
        comparisons.append({"case_id":case["id"],"configuration":selected.model_dump(),"seed":score_seed,
                            "sampled_winner_score":float(scores[idx]),"feasible_count":len(allowed)})
    assert hashlib.sha256(model.state()).hexdigest()==before, "evaluation changed posterior"
    # Primary values appear once per case; keep null/burden family metadata distinct.
    primary = values[::4]
    summary = {k:float(np.mean([v[k] for v in primary])) for k in ("expected_reward","regret","standard","minimal","maximal","random","oracle","violations")}
    sensitivity = {r:float(np.mean([values[4*i+j]["expected_reward"] for i in range(len(cases))])) for j,r in enumerate(("primary","preference_shift","burden_shift","null"))}
    return {"summary":summary,"sensitivity":sensitivity,"dimensions":dimensions,"distribution":distribution,
            "comparisons":comparisons,"cases":values,"state_digest":before}


def aggregate(records):
    result=[]
    # Student t 95% intervals across independent training seeds, not independent cases.
    from scipy.stats import t
    for variant in features.VARIANTS:
        for episode in sorted({r["episode"] for r in records}):
            rows=[r for r in records if r["variant"]==variant and r["episode"]==episode]
            metrics={}
            for key in rows[0]["evaluation"]["summary"]:
                x=np.array([r["evaluation"]["summary"][key] for r in rows]); n=len(x)
                half=float(t.ppf(.975,n-1)*np.std(x,ddof=1)/math.sqrt(n)) if n>1 else None
                metrics[key]={"mean":float(np.mean(x)),"ci95_half_width":half,"n_seeds":n}
            result.append({"variant":variant,"episode":episode,"metrics":metrics})
    return result


def run(output, *, seeds=(11,23,37), train=600, evaluation=60, checkpoints=None):
    output=Path(output).resolve()
    if not output.is_relative_to(C4_ROOT) or "pp1-learning" not in output.parts: raise ValueError("isolated C4/pp1-learning experiment required")
    if output.exists(): raise ValueError("refusing to overwrite experiment")
    if len(set(seeds))!=len(seeds) or not seeds or train<1 or evaluation<1: raise ValueError("invalid experiment schedule")
    output.mkdir(parents=True)
    data=dataset(); training={k:v for k,v in data.items() if v["source"].graph.synthetic and "conditional" not in k}
    tests=heldout(data,evaluation)
    checkpoints=sorted(set([0,train]+list(checkpoints or [min(50,train),min(200,train)])))
    if any(x<0 or x>train for x in checkpoints): raise ValueError("checkpoint outside training range")
    snapshots={pid:{"source":item["source"].model_dump(mode="json"),"content":item["content"].model_dump(mode="json") if item["content"] else None} for pid,item in data.items()}
    (output/"sources.json").write_text(json.dumps(snapshots,indent=2),encoding="utf-8")
    (output/"features.json").write_text(json.dumps(features.SPEC,indent=2),encoding="utf-8")
    (output/"heldout.json").write_text(json.dumps(tests,indent=2),encoding="utf-8")
    all_records=[]; runs=[]
    for seed in seeds:
        rng=np.random.default_rng(seed)
        schedule=[synthetic.scenario(rng,i,training) for i in range(train)]
        # One declared response uniform per observation, shared across encoder variants.
        uniforms=np.random.default_rng(np.random.SeedSequence([seed,771])).random(train)
        (output/f"schedule-{seed}.json").write_text(json.dumps(schedule,indent=2),encoding="utf-8")
        for variant in features.VARIANTS:
            model=Model(variant); chain=digest(model.manifest)
            name=f"seed-{seed}-{variant}"; trace=output/(name+".jsonl")
            eval_records=[]
            with trace.open("x",encoding="utf-8") as file:
                for episode in range(train+1):
                    if episode in checkpoints:
                        path=output/(name+f"-n{episode}.npz")
                        checkpoint_digest=model.save(path)
                        restored=Model.restore(path.read_bytes(),model.manifest)
                        assert restored.state()==model.state()
                        report=assess(restored,tests,data,seed)
                        record={"run":name,"variant":variant,"seed":seed,"episode":episode,"checkpoint":path.name,
                            "checkpoint_digest":checkpoint_digest,"update_chain":chain,"evaluation":report}
                        all_records.append(record);eval_records.append(record)
                        print(f"{name} n={episode} synthetic_reward={report['summary']['expected_reward']:.4f}",flush=True)
                    if episode==train: break
                    case=schedule[episode]; item=data[case["procedure_id"]]; allowed=candidates(item,case)
                    matrix=np.array([features.encode(item["measurements"],case["context"],c,variant) for c in allowed])
                    decision_seed=int(np.random.SeedSequence([seed,episode]).generate_state(1,dtype=np.uint64)[0])
                    selected,scores,means,std=model.score(matrix,decision_seed)
                    config=allowed[selected]
                    # The policy has completed selection before the simulator is called.
                    probability=synthetic.probability(config,case["context"],item["measurements"],case["latent_regime"])
                    reward=int(uniforms[episode]<probability); before=model.revision
                    model.update(matrix[selected],reward)
                    vector_digest=digest(matrix[selected].tolist())
                    chain=digest({"previous":chain,"features":vector_digest,"reward":reward})
                    observation={"run":name,"episode":episode+1,"scenario_id":case["id"],"family":case["family"],
                        "procedure_id":case["procedure_id"],"source_fingerprint":item["source"].graph_fingerprint,
                        "content_fingerprint":digest(snapshots[case['procedure_id']]["content"]),
                        "model":model.manifest,"context":case["context"],"constraints":case["constraints"],
                        "configuration":config.model_dump(),"feasible_count":len(allowed),"seed":decision_seed,
                        "sampled_scores":[{"id":c.key,"score":float(s)} for c,s in zip(allowed,scores)],
                        "selected_feature_digest":vector_digest,"reward":reward,"response_uniform":float(uniforms[episode]),
                        "simulated_selected_probability":probability,"revision_before":before,"revision_after":model.revision,
                        "update_chain":chain,"exposure":"synthetic_display_acknowledged","feedback_origin":"simulation"}
                    file.write(json.dumps(observation,separators=(",",":"))+"\n")
            runs.append({"run":name,"variant":variant,"seed":seed,"schedule_hash":digest(schedule),"trace":trace.name,"checkpoints":[r['checkpoint'] for r in eval_records]})
    report={"schema":"c4-pp1-experiment-1.0","label":"SYNTHETIC EVALUATION ONLY","seeds":list(seeds),"train":train,
        "evaluation_cases":evaluation,"checkpoints":checkpoints,"simulator":synthetic.SPEC,"simulator_fingerprint":synthetic.FINGERPRINT,
        "feature_fingerprint":features.FINGERPRINT,"data_fingerprint":digest(snapshots),"heldout_fingerprint":digest(tests),
        "heldout_protocol":"Conditional procedure excluded from training; all evaluation ratings are 2/4 versus training 1/3/5/unknown. Official procedures are fallback/content-readiness probes, not rich reviewed training data.",
        "runtime":{"python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__,"blas_threads":"set OPENBLAS_NUM_THREADS and OMP_NUM_THREADS=1"},
        "runs":runs,"aggregates":aggregate(all_records),"evaluations":all_records,
        "limitations":["Author-defined hypothetical response model; external expert review pending.","Same simulator assumptions do not establish real-citizen comprehension or benefit.","Only four existing fictional graphs; structural coverage and held-out procedure evidence are limited.","Binary rewards use a misspecified Gaussian surrogate; sampled scores are not calibrated probabilities.","Fixed minimal outperformed learned encoders in historical V2; that finding remains untouched.","525 is a provisional candidate; no architecture or hyperparameters selected by final held-out reward.","Standard/maximal/minimal baselines are fixed canonical feasible projections when hard constraints exclude the nominal configuration."]}
    (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True);parser.add_argument("--train",type=int,default=600)
    parser.add_argument("--evaluation",type=int,default=60);parser.add_argument("--seeds",type=int,nargs="+",default=[11,23,37])
    args=parser.parse_args();run(args.output,seeds=tuple(args.seeds),train=args.train,evaluation=args.evaluation)
