"""Demo A to E against the isolated 3.1 runtime with a REAL trained 3.1 checkpoint. Nothing is forced or hard-coded.

Records what the model actually selected for declared test citizens. In-process TestClient, isolated directories,
the saved checkpoint is only read (the demo policy store is a fresh copy), nothing is committed.
  python research/verify_pp1_v31_demo.py --checkpoint <seed-51-525-n5000.npz> --output docs/PP1-V31-DEMO-DECISIONS.json
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

C4 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(C4 / 'service'))
from fastapi.testclient import TestClient  # noqa: E402
from app.guidance.flavours import FLAVOUR_31  # noqa: E402
from app.host.application import create_app  # noqa: E402
from app.host.identity import WorkspaceRuntime  # noqa: E402
from app.procedures.registration import workspace_registry  # noqa: E402

ROOT = '/workspace/guidance'
TOKEN = 'demo-sandbox-capability-not-a-production-secret-' + 'x' * 16
KEYS = ('navigation', 'explanation', 'disclosure', 'relationships', 'recap', 'segmentation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--exploration', type=float, default=1.0)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists() or not output.is_relative_to(C4):
        raise ValueError('choose a new output file inside C4')
    tag = uuid4().hex[:8]
    prepared = C4 / 'service' / '.local' / 'prepared-content' / ('v31-demo-' + tag) / 'v31'
    store = C4 / 'service' / '.local' / 'pp1-learning' / ('v31-demo-' + tag)
    runtime = WorkspaceRuntime(procedures=workspace_registry())
    options = {'directory': prepared, 'demo_fixtures': True, 'flavour': FLAVOUR_31}
    policy = {'directory': store, 'seed': 5, 'checkpoint': args.checkpoint, 'exploration': args.exploration}
    report = {'label': 'SYNTHETIC-TRAINED MODEL; decisions are genuine model selections, not previews', 'checkpoint': Path(args.checkpoint).name, 'exploration': args.exploration}
    try:
        with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options=options,
                                   guidance_api_options={'research_enabled': True, 'flavour': FLAVOUR_31, 'policy_options': policy})) as client:
            api = client.app.state.guidance_api
            services = {p['procedure_id']: p['service_id'] for p in client.get(ROOT + '/procedures').json()}
            report['policy_start'] = {k: api.policy.status()[k] for k in ('posterior_revision', 'training_provenance', 'accepted_feedback_count', 'manifest_fingerprint')}

            def profile(name, familiarity, confidence):
                body = {'profile_id': 'profile:' + uuid4().hex, 'display_name': name, 'personalization_enabled': True,
                        'initial_context': {'navigation_capability': confidence, 'familiarity': [{'service_id': services[p], 'score': s} for p, s in familiarity.items()]}}
                result = client.post(ROOT + '/profiles', json=body)
                assert result.status_code == 200, result.text
                return result.json()['session']['session_id']

            def ask(sid, pid, **extra):
                body = {'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, 'mode': 'personalized', **extra}
                result = client.post(ROOT + '/requests', json=body)
                assert result.status_code == 200, result.text
                return result.json()

            def summary(j):
                decision = client.get(ROOT + '/journeys/' + j['journey_id'] + '/inspector', headers={'X-C4-Token': TOKEN}).json().get('policy')
                out = {'kind': j['selection']['kind'], 'configuration': {k: j['document']['configuration'][k] for k in KEYS}, 'feasible': j['availability']['feasible_count'],
                       'context': {k: j['effective_context'][k] for k in ('familiarity', 'confidence', 'preferences')}, 'procedure': j['procedure_id'],
                       'learning_eligible': j['selection']['learning_eligible']}
                if decision:
                    ranked = sorted(decision['candidates'], key=lambda c: -c['sampled_score'])[:3]
                    out['top_sampled'] = [{'configuration': c['configuration'], 'sampled_score': round(c['sampled_score'], 4), 'posterior_mean': round(c['posterior_mean'], 4)} for c in ranked]
                    out['posterior_revision'] = decision['policy']['posterior_revision']
                    out['feasibility_fingerprint'] = decision['feasibility_fingerprint'][:16]
                return out

            guest = client.post(ROOT + '/guests').json()['session_id']
            g = ask(guest, 'synthetic-practice-v2')
            report['A_guest'] = {**summary(g), 'controls': g['controls'], 'note': 'standard guidance, no support control, no feedback'}

            experienced = profile('Demo experienced citizen', {'synthetic-linear-v1': 5, 'official-birth_copy-v3': 5}, 5)
            report['B_compact_candidate'] = {'profile': 'familiarity 5, confidence 5', 'linear': summary(ask(experienced, 'synthetic-linear-v1')), 'birth_copy_official': summary(ask(experienced, 'official-birth_copy-v3'))}

            novice = profile('Demo novice citizen', {'synthetic-practice-v2': 1, 'synthetic-linear-v1': 4}, 1)
            c = ask(novice, 'synthetic-practice-v2')
            report['C_rich_candidate'] = {'profile': 'familiarity 1, confidence 1', 'practice': summary(c)}
            report['D_same_citizen_other_procedure'] = {'profile': 'same citizen (confidence 1); familiarity 4 for the linear procedure, unset for the conditional one', 'linear_familiarity_4': summary(ask(novice, 'synthetic-linear-v1')),
                                                         'conditional_unset_familiarity': summary(ask(novice, 'synthetic-conditional-v1'))}

            # Demo E: feedback learning on a genuine model-selected original view.
            e = ask(novice, 'synthetic-practice-v2')
            shown = {'event_id': uuid4().hex, 'view_id': e['view_id'], 'type': 'view_displayed', 'action_ids': [e['document']['actions'][0]['id']]}
            client.post(ROOT + '/journeys/' + e['journey_id'] + '/events', headers={'X-C4-Token': TOKEN}, json=shown)
            rate = lambda view, r, ident=None: client.post(ROOT + '/journeys/' + e['journey_id'] + '/ratings', headers={'X-C4-Token': TOKEN}, json={'event_id': ident or uuid4().hex, 'view_id': view, 'rating': r})
            before = api.policy.status()['posterior_revision']
            ident = uuid4().hex
            first = rate(e['view_id'], 'fits', ident).json()
            again = rate(e['view_id'], 'fits', ident).json()
            second = rate(e['view_id'], 'does_not_fit')
            after = api.policy.status()['posterior_revision']
            child = client.post(ROOT + '/journeys/' + e['journey_id'] + '/views', headers={'X-C4-Token': TOKEN}, json={'request_id': uuid4().hex, 'parent_view_id': e['view_id'],
                                'configuration': {**e['document']['configuration'], 'recap': 'off'}}).json()
            manual = client.post(ROOT + '/journeys/' + e['journey_id'] + '/ratings', headers={'X-C4-Token': TOKEN}, json={'event_id': uuid4().hex, 'view_id': child['view_id'], 'rating': 'fits'}).json()
            report['E_feedback'] = {'selection': summary(e), 'revision_before': before, 'receipt': {k: first[k] for k in ('reward', 'policy_updated', 'learning_eligible')},
                                    'revision_after': after, 'idempotent_retry_same_receipt': again == first, 'second_rating_status': second.status_code,
                                    'manual_adjustment_kind': child['selection']['kind'], 'manual_rating_updated_policy': manual['policy_updated'],
                                    'revision_after_manual': api.policy.status()['posterior_revision']}
            report['policy_end'] = {k: api.policy.status()[k] for k in ('posterior_revision', 'accepted_feedback_count', 'training_provenance')}
    finally:
        runtime.close()
        shutil.rmtree(prepared.parent, ignore_errors=True)
        shutil.rmtree(store, ignore_errors=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
