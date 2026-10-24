"""Same synthetic generator, now through saved profiles and effective context.

The factory adapts the existing reproducible experiment to the citizen runtime.
It never injects configurations or passes outcome probabilities to selection.
"""
import argparse
import json
from app.models.demo_profiles import CreateDemoProfileRequest, InitialProfileContext
from app.models.user_context import FamiliarityReport
from app.host.identity import WorkspaceRuntime
from app.compat.v2_runtime import Runtime
from app.procedures.registration import workspace_registry
from app.studies.v2_simulation import run

class ProfileExperimentRuntime(WorkspaceRuntime):
    def create(self, procedure_id, context, request_id, **kwargs):
        if kwargs:
            return Runtime.create(self,procedure_id,context,request_id,**kwargs)
        # Stable profile per stated context; familiarity remains service-scoped.
        from hashlib import sha256
        key=sha256(json.dumps(context.model_dump(),sort_keys=True).encode()).hexdigest()[:32]
        profile_id="profile:"+key
        if profile_id not in self.profiles:
            services=sorted({p["graph"].requested_service_id for p in self.procedures.values()})
            self.create_profile(CreateDemoProfileRequest(profile_id=profile_id,display_name="Synthetic scenario "+key[:6],personalization_enabled=True,
                initial_context=InitialProfileContext(navigation_capability=context.confidence,
                    familiarity=[FamiliarityReport(service_id=s,score=context.familiarity) for s in services])))
        profile=self.profiles[profile_id]
        return self.guidance(profile.session_id,procedure_id,request_id,self.settings(profile.session_id)["settings_revision"])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True)
    parser.add_argument("--seed",type=int,default=17)
    parser.add_argument("--train",type=int,default=40)
    parser.add_argument("--evaluation",type=int,default=12)
    args=parser.parse_args()
    if args.train<1 or args.evaluation<1:parser.error("positive training and evaluation counts required")
    report=run(args.output,seed=args.seed,train=args.train,evaluation=args.evaluation,runtime_factory=ProfileExperimentRuntime,procedures=workspace_registry())
    print(json.dumps({"origin":report["origin"],"results":{k:{n:v[n] for n in ("reload_verified","expected_reward","minimal","rich","uniform")} for k,v in report["results"].items()}},indent=2))

if __name__=="__main__":main()
