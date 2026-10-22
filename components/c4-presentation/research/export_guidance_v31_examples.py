"""Capture real isolated TestClient responses from the 3.1 runtime (no model, no live provider, no policy). Never overwrites an export."""
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
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}
RICH = {'navigation': 'guided', 'explanation': 'detailed', 'disclosure': 'on', 'relationships': 'map', 'recap': 'on', 'segmentation': 'on'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    output = Path(parser.parse_args().output).resolve()
    if not output.is_relative_to(C4) or output.exists():
        raise ValueError('Choose a new output directory inside C4; never overwrite an export.')
    output.mkdir(parents=True)
    directory = C4 / 'service' / '.local' / 'prepared-content' / ('v31-export-' + uuid4().hex[:8]) / 'v31'
    runtime = WorkspaceRuntime(procedures=workspace_registry())
    options = {'directory': directory, 'demo_fixtures': True, 'flavour': FLAVOUR_31}
    try:
        with TestClient(create_app(runtime=runtime, workspace=True, prepared_content_options=options, guidance_api_options={'research_enabled': True, 'flavour': FLAVOUR_31})) as client:
            def save(name, method, path, body=None, token=False):
                response = client.request(method, path, json=body, headers={'X-C4-Token': TOKEN} if token else {})
                if response.status_code != 200:
                    raise RuntimeError(name + ': ' + response.text)
                (output / (name + '.json')).write_text(json.dumps({'method': method, 'path': path, 'request': body, 'status_code': 200, 'response': response.json()}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
                return response.json()
            save('status', 'GET', ROOT + '/status')
            sid = save('guest', 'POST', ROOT + '/guests')['session_id']
            def req(pid, config=None):
                body = {'request_id': str(uuid4()), 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN}
                if config is not None:
                    body.update(mode='research_preview', configuration=config)
                return ROOT + ('/research/previews' if config is not None else '/requests'), body
            for name, pid, config in [('standard-synthetic-practice-v2', 'synthetic-practice-v2', None), ('standard-official-nic_amendment-v3', 'official-nic_amendment-v3', None),
                                      ('standard-official-birth_copy-v3', 'official-birth_copy-v3', None), ('standard-synthetic-parallel-v1', 'synthetic-parallel-v1', None),
                                      ('preview-concise-off', 'synthetic-practice-v2', BASE), ('preview-concise-on', 'synthetic-practice-v2', {**BASE, 'disclosure': 'on'}),
                                      ('preview-detailed-off', 'synthetic-practice-v2', {**BASE, 'explanation': 'detailed'}),
                                      ('preview-detailed-on', 'synthetic-practice-v2', {**BASE, 'explanation': 'detailed', 'disclosure': 'on'}),
                                      ('preview-rich', 'synthetic-practice-v2', RICH),
                                      ('preview-parallel-guided', 'synthetic-parallel-v1', {**BASE, 'navigation': 'guided', 'relationships': 'map', 'segmentation': 'on'})]:
                path, body = req(pid, config)
                save(name, 'POST', path, body)
            save('procedures', 'GET', ROOT + '/procedures')
            save('availability-practice', 'GET', ROOT + '/procedures/synthetic-practice-v2/availability?session_id=' + sid)
            save('availability-nic', 'GET', ROOT + '/procedures/official-nic_amendment-v3/availability?session_id=' + sid)
        (output / 'README.md').write_text('Real responses from the isolated c4-guidance-content-3.1 runtime (research/export_guidance_v31_examples.py). Fictional content is internally author-reviewed by an AI-assisted reviewer, not human or external expert. No policy was used.\n', encoding='utf-8')
    finally:
        runtime.close()
        shutil.rmtree(directory.parent, ignore_errors=True)


if __name__ == '__main__':
    main()
