"""Regression for the HTTP 409 on PATCH /workspace/guidance/profile-context/{session}.

Root cause: the editor sent the identity session's own `revision` as `expected_identity_revision`, but the backend compares the
*settings* revision (session revision + the native settings revision that every saved edit increments). After the first save the two
numbers differ, so every later save was rejected as a stale write. The backend check stays strict; clients must send the revision
reported by GET /context (or the PATCH response)."""
import shutil
from pathlib import Path
from uuid import uuid4
import numpy as np
from fastapi.testclient import TestClient
from app.guidance.flavours import FLAVOUR_31
from app.v2.api import create_app
from app.v2.identity import WorkspaceRuntime
from app.v2.registration import workspace_registry

C4 = Path(__file__).resolve().parents[2]
ROOT = '/workspace/guidance'
PID = 'official-nic_amendment-v3'
TOKEN = 'ctx-revision-test-capability-' + 'x' * 20


def build(tmp: Path):
    entries = workspace_registry()
    options = {'research_enabled': True, 'flavour': FLAVOUR_31, 'policy_options': {'directory': C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / ('ctx-' + uuid4().hex[:8]), 'seed': 4}}
    kwargs = {'path': tmp / 'v2' / 'workspace' / 'api.sqlite3', 'workspace': True, 'runtime_class': lambda path, **kw: WorkspaceRuntime(path, procedures=entries, **kw),
              'prepared_content_options': {'directory': tmp / 'prepared-content' / 'v31', 'demo_fixtures': True, 'flavour': FLAVOUR_31}, 'guidance_api_options': options}
    return kwargs


def profile(client, name='ctx test'):
    service = next(p['service_id'] for p in client.get(ROOT + '/procedures').json() if p['procedure_id'] == PID)
    r = client.post(ROOT + '/profiles', json={'profile_id': 'profile:' + uuid4().hex, 'display_name': name, 'personalization_enabled': True,
                                              'initial_context': {'navigation_capability': 3, 'familiarity': [{'service_id': service, 'score': 1}]}})
    assert r.status_code == 200, r.text
    return r.json()['session']['session_id'], service


def patch(client, sid, service, revision, score, confidence=None):
    body = {'request_id': uuid4().hex, 'expected_identity_revision': revision, 'familiarity': [{'service_id': service, 'score': score, 'source': 'self_reported'}]}
    if confidence is not None:
        body['confidence'] = confidence
    return client.patch(ROOT + '/profile-context/' + sid, json=body)


def identity_revision(client, sid):
    return client.get(ROOT + '/context/' + sid, params={'procedure_id': PID}).json()['revision']['identity']


def test_the_session_revision_is_not_the_revision_the_backend_checks(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        sid, service = profile(client)
        first = patch(client, sid, service, identity_revision(client, sid), 2)
        assert first.status_code == 200, first.text
        session_revision = first.json()['session']['revision']
        assert identity_revision(client, sid) == first.json()['settings_revision'] != session_revision     # the two numbers really differ after one save
        stale = patch(client, sid, service, session_revision, 3)                                              # what the old editor sent
        assert stale.status_code == 409 and 'revision changed' in stale.text
        assert patch(client, sid, service, identity_revision(client, sid), 3).status_code == 200            # the strict check still accepts a correct revision


def test_a_genuinely_stale_write_is_still_refused(tmp_path):
    with TestClient(create_app(**build(tmp_path))) as client:
        sid, service = profile(client)
        old = identity_revision(client, sid)
        assert patch(client, sid, service, old, 2).status_code == 200
        assert patch(client, sid, service, old, 4).status_code == 409


def test_repeated_changes_across_profiles_persist_and_reach_the_encoder(tmp_path):
    kwargs = build(tmp_path)
    saved = {}
    with TestClient(create_app(**kwargs)) as client:
        profiles = [profile(client, 'ctx profile %d' % i) for i in range(3)]
        for sid, service in profiles:
            for score in (4, 1, 4, 2, 4):                                      # includes the reported 1 -> 4 change, repeated
                r = patch(client, sid, service, identity_revision(client, sid), score, confidence=score)
                assert r.status_code == 200, r.text
            ctx = client.get(ROOT + '/context/' + sid, params={'procedure_id': PID}).json()
            assert ctx['familiarity'] == 4 and ctx['confidence'] == 4
            saved[sid] = ctx['revision']['identity']
        sid = profiles[0][0]
        j = client.post(ROOT + '/requests', json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': PID, 'capability_token': TOKEN, 'mode': 'personalized'}).json()
        assert j['effective_context']['familiarity'] == 4 and j['effective_context']['confidence'] == 4
        features = client.get(ROOT + '/journeys/' + j['journey_id'] + '/inspector', headers={'X-C4-Token': TOKEN}).json()['features']
        names, vector = features['names'], features['selected']
        active = {n.split('*')[0] for n, v in zip(names, vector) if n.startswith('familiarity.') and v}
        assert active <= {'familiarity.4'} and active                       # the saved value, not the old 1, is what the encoder was given
        low = profiles[1][0]
        assert patch(client, low, profiles[1][1], identity_revision(client, low), 1).status_code == 200
        saved[low] = identity_revision(client, low)
        j2 = client.post(ROOT + '/requests', json={'request_id': uuid4().hex, 'session_id': low, 'procedure_id': PID, 'capability_token': TOKEN, 'mode': 'personalized'}).json()
        f2 = client.get(ROOT + '/journeys/' + j2['journey_id'] + '/inspector', headers={'X-C4-Token': TOKEN}).json()['features']
        assert {n.split('*')[0] for n, v in zip(f2['names'], f2['selected']) if n.startswith('familiarity.') and v} <= {'familiarity.1'}
    with TestClient(create_app(**kwargs)) as client:                         # a restart keeps the saved values
        for sid, revision in saved.items():
            ctx = client.get(ROOT + '/context/' + sid, params={'procedure_id': PID}).json()
            assert ctx['revision']['identity'] == revision
        assert client.get(ROOT + '/context/' + profiles[0][0], params={'procedure_id': PID}).json()['familiarity'] == 4
