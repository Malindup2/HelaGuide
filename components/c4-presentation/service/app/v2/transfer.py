"""Explicit copy tools. Source connections are read-only; targets never V1/V2 stores.

No command runs automatically at application startup. V1 coefficients are never
imported. Profile consent is reset off for an explicit local confirmation.
"""
import argparse
import copy
import hashlib
import json
import sqlite3
from pathlib import Path
from app.models.demo_profiles import CreateDemoProfileRequest, InitialProfileContext
from app.models.runtime_state import RuntimeState
from app.v2.content import digest
from app.v2.identity import WorkspaceRuntime, legacy_choices
from app.v2.registration import workspace_registry


def read_source(path):
    path=Path(path).resolve()
    if path.suffix.lower()==".json":
        return "v1", RuntimeState.model_validate_json(path.read_text(encoding="utf-8-sig"))
    connection=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)
    try:
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables in ({"c4_v2_state"}, {"c4_workspace_state"}):
            payload,checksum=connection.execute(f"SELECT payload,checksum FROM {next(iter(tables))} WHERE id=1").fetchone()
            state=json.loads(payload)
            if digest(state)!=checksum:raise ValueError("source checksum mismatch")
            return "v2",state
        if tables=={"c4_snapshot"}:
            payload,checksum=connection.execute("SELECT payload,checksum FROM c4_snapshot WHERE singleton=1").fetchone()
            if hashlib.sha256(payload.encode()).hexdigest()!=checksum:raise ValueError("source checksum mismatch")
            return "v1",RuntimeState.model_validate_json(payload)
        raise ValueError("unsupported source storage schema")
    finally:connection.close()


def preview_profiles(state):
    sessions={s.session.session_id:s for s in state.sessions}
    result=[]
    for profile in state.profiles:
        session=sessions[profile.session_id].session
        prefs,locks,review=legacy_choices(session.settings)
        result.append({"profile_id":profile.profile_id,"source_session_id":profile.session_id,"display_name":profile.display_name,
            "compatible_preferences":prefs,"compatible_locks":locks,"needs_review":review,
            "personalization_on_after_copy":False})
    return result


def copy_profiles(runtime,state):
    if state.policy.config.feedback_mode != runtime.manifest["mode"]:
        raise ValueError("profile evidence cannot cross simulation/participant storage modes")
    sessions={s.session.session_id:s for s in state.sessions}
    if any(p.profile_id in runtime.profiles for p in state.profiles):
        raise ValueError("target already contains a source profile; refusing duplicate copy")
    # One transaction: construct profiles using V1 services and retain raw source
    # evidence for later PP2 review without activating a history score adjustment.
    from types import SimpleNamespace
    from app.core.demo_profiles import create_profile
    def change():
        for p in state.profiles:
            old=sessions[p.session_id]
            settings=old.session.settings
            request=CreateDemoProfileRequest(profile_id=p.profile_id,display_name=p.display_name,personalization_enabled=False,
                initial_context=InitialProfileContext(familiarity=list(settings.familiarity),navigation_capability=settings.navigation_capability,
                    preferences=settings.preferences,locks=settings.locks,accessibility=settings.accessibility))
            proxy=SimpleNamespace(profiles=runtime.profiles,contexts=runtime.contexts,session=runtime.session,
                procedures={k:(v["graph"],None,None) for k,v in runtime.procedures.items()})
            create_profile(proxy,request)
        report=preview_profiles(state)
        for row in report:
            row["copied_session_id"]=runtime.profiles[row["profile_id"]].session_id
        owned={p.session_id for p in state.profiles}
        runtime._identity()["imports"].append({"source_schema":"v1","report":report,
            "source_context_evidence":[s.model_dump(mode="json") for s in state.sessions if s.session.session_id in owned],
            "policy_coefficients_imported":False})
        return report
    return runtime.identity_change(change)


def copy_policy(runtime,state):
    if runtime.state["journeys"] or runtime.state["updates"] or runtime.profiles:
        raise ValueError("V2 policy copy requires an empty workspace target")
    if state["manifest"] != runtime.manifest:
        raise ValueError("incompatible V2 encoder, mode, prior or seed")
    candidate=copy.deepcopy(state)
    # Verify exact numerical replay before changing the target transaction.
    verifier=WorkspaceRuntime(mode=runtime.manifest["mode"],seed=runtime.manifest["seed"],variant=runtime.manifest["variant"],procedures=runtime.procedures)
    try:
        verifier.state=candidate
        verifier._restore()
    finally:verifier.close()
    def change():
        runtime.state=candidate
        runtime._restore()
        runtime._identity()["imports"].append({"source_schema":"v2","posterior_fingerprint":runtime.fingerprint(),"mode":"explicit copy"})
        runtime._save_identity()
        return runtime.status()
    return runtime._write(change)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True)
    parser.add_argument("--target")
    parser.add_argument("--apply-copy",action="store_true")
    parser.add_argument("--mode",choices=["simulation","participant"],default="simulation")
    parser.add_argument("--seed",type=int,default=0)
    args=parser.parse_args()
    kind,state=read_source(args.source)
    print(json.dumps(preview_profiles(state) if kind=="v1" else {"manifest":state["manifest"],"updates":len(state["updates"])},indent=2))
    if args.apply_copy:
        if not args.target:raise ValueError("explicit separate target required")
        if Path(args.source).resolve()==Path(args.target).resolve():raise ValueError("source and target must differ")
        runtime=WorkspaceRuntime(args.target,mode=args.mode,seed=args.seed,procedures=workspace_registry())
        try:print(json.dumps(copy_profiles(runtime,state) if kind=="v1" else copy_policy(runtime,state),indent=2))
        finally:runtime.close()

if __name__=="__main__":main()
