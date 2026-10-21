"""Exact selected-only replay from immutable experiment source snapshots/logs."""
import argparse
import json
from pathlib import Path
import numpy as np
from app.guidance.policy import C4_ROOT, Model
from app.guidance.sources import ProcedureSource, digest
from app.guidance.catalogue import Configuration
from app.guidance import features
from app.v2.measurements import measurements


def replay(directory, run):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(C4_ROOT) or "pp1-learning" not in directory.parts: raise ValueError("isolated C4 experiment required")
    report=json.loads((directory/"report.json").read_text(encoding="utf-8"))
    entry=next(r for r in report["runs"] if r["run"]==run)
    sources=json.loads((directory/"sources.json").read_text(encoding="utf-8"))
    if digest(sources)!=report["data_fingerprint"] or features.FINGERPRINT!=report["feature_fingerprint"]: raise ValueError("replay source/schema mismatch")
    model=Model(entry["variant"]);chain=digest(model.manifest)
    for line in (directory/entry["trace"]).read_text(encoding="utf-8").splitlines():
        obs=json.loads(line);source=ProcedureSource.model_validate_json(json.dumps(sources[obs["procedure_id"]]["source"]))
        m=measurements(source.graph,source.relationships)
        configs=[Configuration(**dict(zip(__import__('app.guidance.catalogue',fromlist=['DIMENSIONS']).DIMENSIONS,c['id'].split(':')[1:]))) for c in obs['sampled_scores']]
        matrix=np.array([features.encode(m,obs["context"],c,entry["variant"]) for c in configs])
        idx,scores,_,_=model.score(matrix,obs["seed"])
        if configs[idx].model_dump()!=obs["configuration"] or not np.array_equal(scores,np.array([c['score'] for c in obs['sampled_scores']])): raise ValueError("decision replay mismatch")
        if digest(matrix[idx].tolist())!=obs['selected_feature_digest'] or model.revision!=obs['revision_before']: raise ValueError("feature/revision replay mismatch")
        model.update(matrix[idx],obs["reward"])
        chain=digest({"previous":chain,"features":obs['selected_feature_digest'],"reward":obs['reward']})
        if chain!=obs['update_chain'] or model.revision!=obs['revision_after']: raise ValueError("update replay mismatch")
    checkpoint=Model.restore((directory/entry['checkpoints'][-1]).read_bytes(),model.manifest)
    if checkpoint.state()!=model.state(): raise ValueError("checkpoint replay mismatch")
    return {"run":run,"replayed_observations":model.revision,"exact_scores":True,"exact_state":True,"update_chain":chain}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--run',required=True)
    a=p.parse_args();print(json.dumps(replay(a.directory,a.run),indent=2))
