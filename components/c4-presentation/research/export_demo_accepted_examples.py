"""Capture real responses with the LOCAL RESEARCH DEMO acceptance mode and the trained 3.1 Shared LinTS checkpoint (a private copy; the original is never opened for writing).
  python research/export_demo_accepted_examples.py --output docs/examples/frontend-api-3.1-demo-accepted-2026-10-22
Never overwrites an export. Ordinary journeys use the accepted cached wording; the policy makes the selections."""
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
from app.v2.api import create_app  # noqa: E402
from app.v2.identity import WorkspaceRuntime  # noqa: E402
from app.v2.registration import workspace_registry  # noqa: E402

ROOT = '/workspace/guidance'
TOKEN = 'documentation-sandbox-only-not-a-production-capability'
CHECKPOINT = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-study-20261022-a' / 'seed-23-x0.25-525-n5000.npz'
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}
OFFICIAL = {'birth': 'official-birth_copy-v3', 'nic': 'official-nic_amendment-v3', 'company': 'official-company_pack-v3'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--draws', type=int, default=12)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to(C4) or output.exists():
        raise ValueError('Choose a new output directory inside C4; never overwrite an export.')
    output.mkdir(parents=True)
    tag = uuid4().hex[:8]
    prepared = C4 / 'service' / '.local' / 'prepared-content' / ('v31-accepted-export-' + tag) / 'v31'
    store = C4 / 'service' / '.local' / 'pp1-learning' / ('v31-accepted-export-' + tag)
    runtime = WorkspaceRuntime(procedures=workspace_registry())
    policy = {'directory': store, 'seed': 11, 'mode': 'simulation', 'checkpoint': str(CHECKPOINT), 'exploration': 0.25}
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, 'demo_accepted': True, 'demo_provisional': True, 'policy_options': policy}
    try:
        with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options={'directory': prepared, 'demo_fixtures': True, 'flavour': FLAVOUR_31}, guidance_api_options=options)) as client:
            summary = {'selections': []}

            def save(name, method, path, body=None):
                response = client.request(method, path, json=body, headers={'X-C4-Token': TOKEN} if method == 'POST' and body and 'capability_token' not in body else {})
                if response.status_code != 200:
                    raise RuntimeError(name + ': ' + response.text)
                (output / (name + '.json')).write_text(json.dumps({'method': method, 'path': path, 'request': body, 'status_code': 200, 'response': response.json()}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
                return response.json()

            def body(sid, pid, **extra):
                return {'request_id': str(uuid4()), 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, **extra}

            def profile(pid, familiarity, confidence):
                service = next(p['service_id'] for p in client.get(ROOT + '/procedures').json() if p['procedure_id'] == pid)
                r = client.post(ROOT + '/profiles', json={'profile_id': 'profile:' + uuid4().hex, 'display_name': 'Demo accepted example profile', 'personalization_enabled': True,
                                                          'initial_context': {'navigation_capability': confidence, 'familiarity': [{'service_id': service, 'score': familiarity}]}})
                assert r.status_code == 200, r.text
                return r.json()['session']['session_id']

            save('status', 'GET', ROOT + '/status')
            guest = client.post(ROOT + '/guests').json()['session_id']
            for key, pid in OFFICIAL.items():
                save('standard-' + key, 'POST', ROOT + '/requests', body(guest, pid, mode='standard'))
                save('availability-' + key, 'GET', ROOT + '/procedures/' + pid + '/availability?session_id=' + guest)
                for label, fam, conf in (('experienced', 5, 5), ('novice', 1, 1)):
                    # the policy is stochastic: record every draw, keep the first compact and the first richer selection for the examples
                    seen = {}
                    for _ in range(args.draws):
                        sid = profile(pid, fam, conf)
                        r = client.post(ROOT + '/requests', json=body(sid, pid, mode='personalized')).json()
                        c = r['selection']['configuration']
                        score = sum(v not in ('overview', 'concise', 'off', 'none') for v in c.values())
                        summary['selections'].append({'procedure': pid, 'citizen': label, 'configuration': c, 'support_elements': score})
                        seen.setdefault('rich' if score >= 3 else 'compact', r)
                    for kind, r in seen.items():
                        (output / f'personalised-{key}-{label}-{kind}.json').write_text(json.dumps({'method': 'POST', 'path': ROOT + '/requests', 'status_code': 200, 'response': r}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
                for e in ('concise', 'detailed'):
                    for d in ('off', 'on'):
                        save(f'preview-{key}-{e}-{d}', 'POST', ROOT + '/research/previews', body(guest, pid, mode='research_preview', configuration={**BASE, 'explanation': e, 'disclosure': d}, allow_provisional=False))
            save('preview-nic-map-relaxed', 'POST', ROOT + '/research/previews', body(guest, OFFICIAL['nic'], mode='research_preview', configuration={**BASE, 'relationships': 'map'}, allow_provisional=True))
            save('status-after', 'GET', ROOT + '/status')
            (output / 'selection-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        (output / 'README.md').write_text('Real responses from the isolated 3.1 runtime in LOCAL RESEARCH DEMO acceptance mode with a private copy of the trained Shared LinTS checkpoint (research/export_demo_accepted_examples.py). The wording is AI-assisted, source-grounded and accepted by the project owner for this demonstration; it has no external review. Capability token is a documentation sandbox value.\n', encoding='utf-8')
    finally:
        runtime.close()
        shutil.rmtree(prepared.parent, ignore_errors=True)
        shutil.rmtree(store, ignore_errors=True)


if __name__ == '__main__':
    main()
