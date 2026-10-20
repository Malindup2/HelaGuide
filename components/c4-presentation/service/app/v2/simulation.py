"""Reproducible synthetic experiment, not evidence of human benefit.

Runs the same select -> visible exposure -> explicit rating -> update mechanism
as the API. Conditional fixture is held out from training; practice user ratings
2 and 4 are also held out. No configuration is injected into the policy.
"""
import argparse
import json
import math
from pathlib import Path
from uuid import uuid4
import numpy as np
from app.v2.runtime import Runtime, C4_ROOT
from app.v2.catalogue import Configuration, Context, evaluate
from app.v2.content import registry, digest

GENERATOR = "c4-synthetic-fit-v2.1"

def probability(config, context, measurements, regime="interaction"):
    f=(context.familiarity or 3)/5
    n=(context.confidence or 3)/5
    length=measurements.step_count.normalized_observed
    volume=measurements.information_volume.normalized_observed
    dependency=measurements.dependency_count.normalized_observed
    # Independent declared outcome generator, never used inside selection.
    demand=np.array([(1-n)*(.5+length), (1-f)*(.5+volume), .3*(1-f),
                     (1-n)*(.5+dependency), (1-f)*(.3+length), (1-f)*(.4+volume)])
    support=np.array([config.navigation=="guided",config.explanation=="expanded",config.disclosure=="expanded",
                      {"none":0,"inline":.45,"map":1}[config.relationships],config.recap=="on",config.summary=="on"],dtype=float)
    if regime=="null":
        return .65
    if regime=="burden":
        demand=demand*.45
    mismatch=np.square(support-demand).sum()
    redundancy=.3*support[1]*support[2] + .2*support[3]*support[5]
    # Nonlinear misspecification: the model is not handed this response function.
    return 1/(1+math.exp(-(2.0-1.6*mismatch-redundancy)))

def run(output, *, seed=17, train=40, evaluation=12):
    output=Path(output).resolve()
    if not output.is_relative_to(C4_ROOT) or "v2" not in output.parts:
        raise ValueError("experiment outputs must remain inside C4/v2 storage")
    if output.exists():
        raise ValueError("refusing to overwrite an experiment; choose a new output directory")
    output.mkdir(parents=True)
    procedures=registry()
    synthetic={k:v for k,v in procedures.items() if v["document"]["synthetic"]}
    heldout=next(k for k in synthetic if "conditional" in k)
    training=[k for k in synthetic if k!=heldout]
    rng=np.random.default_rng(seed)
    schedule=[(training[int(rng.integers(len(training)))],int(rng.choice([1,3,5])),int(rng.choice([1,3,5])),float(rng.random())) for _ in range(train)]
    tests=[(heldout if i%2==0 else "synthetic-practice-v2",2 if i%3 else 4,2 if i%2 else 4, "null" if i%5==0 else ("burden" if i%3==0 else "interaction")) for i in range(evaluation)]
    report={"generator":GENERATOR,"seed":seed,"origin":"simulation","train":train,"evaluation":evaluation,
            "heldout_procedure":heldout,"heldout_ratings":[2,4],"schedule_hash":digest(schedule),"results":{},
            "limitations":"Synthetic outcomes only. No participant validation. Parameter uncertainty is not calibrated support-fit probability."}
    for variant in ("pairwise","threeway","full"):
        path=output/f"{variant}.sqlite3"
        runtime=Runtime(path,seed=seed,variant=variant,procedures=procedures)
        trace=[]
        for index,(pid,f,n,uniform) in enumerate(schedule):
            context=Context(familiarity=f,confidence=n)
            j=runtime.create(pid,context,f"training-{index:06d}-{variant}")
            config=Configuration(**j["views"][j["current_view"]]["configuration"])
            p=probability(config,context,procedures[pid]["measurements"])
            rating="about_right" if uniform<p else ("need_more" if f<3 else "too_much")
            runtime.event(j["id"],j["token"],{"event_id":f"display-{index:06d}","type":"action_visible","view_id":j["current_view"],"action_id":j["document"]["actions"][0]["id"]})
            receipt=runtime.rate(j["id"],j["token"],j["current_view"],rating)
            trace.append({"trial":index,"procedure":pid,"context":context.model_dump(),"configuration":config.model_dump(),"p_synthetic":p,"uniform":uniform,"receipt":receipt})
        before=runtime.status();runtime.close()
        runtime=Runtime(path,seed=seed,variant=variant,procedures=procedures)
        assert runtime.status()==before
        values=[]
        for index,(pid,f,n,regime) in enumerate(tests):
            context=Context(familiarity=f,confidence=n)
            j=runtime.create(pid,context,f"evaluation-{index:06d}-{variant}")
            config=Configuration(**j["views"][j["current_view"]]["configuration"])
            p=procedures[pid]
            feasible=[Configuration(**e["configuration"]) for e in evaluate(p["document"]["capabilities"],context) if not e["reasons"]]
            truth=[probability(c,context,p["measurements"],regime) for c in feasible]
            chosen=probability(config,context,p["measurements"],regime)
            # Baselines only, not the adaptive selector: first/last canonical feasible arm.
            values.append({"expected_reward":chosen,"oracle":max(truth),"regret":max(truth)-chosen,
                           "uniform":float(np.mean(truth)),"minimal":truth[0],"rich":truth[-1],"regime":regime,"procedure":pid})
        assert runtime.status()["posterior_revision"]==train # evaluation never trains
        report["results"][variant]={"reload_verified":True,"posterior":runtime.status(),
            **{key:float(np.mean([v[key] for v in values])) for key in ("expected_reward","regret","minimal","rich","uniform")},"trials":values}
        runtime.close()
        (output/f"{variant}-training.json").write_text(json.dumps(trace,indent=2),encoding="utf-8")
    (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--seed",type=int,default=17)
    parser.add_argument("--train",type=int,default=40)
    parser.add_argument("--evaluation",type=int,default=12)
    args=parser.parse_args()
    if args.train<1 or args.evaluation<1:parser.error("positive training/evaluation counts required")
    result=run(args.output,seed=args.seed,train=args.train,evaluation=args.evaluation)
    print(json.dumps({"output":args.output,"origin":result["origin"],"results":{k:{n:v[n] for n in ("reload_verified","expected_reward","regret")} for k,v in result["results"].items()}},indent=2))
