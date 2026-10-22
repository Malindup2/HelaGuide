"""Live HTTP check of the running 3.1 application (trained checkpoint): guest, compact and rich personalised guidance,
the four D2 x D3 combinations, step facts, manual adjustment and feedback eligibility. Only reads genuine responses.
  python research/verify_functional_review_live.py --base http://127.0.0.1:8021 --output docs/C4-FUNCTIONAL-REVIEW-LIVE.json
"""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

TOKEN = 'functional-review-capability-' + 'x' * 20
KEYS = ('navigation', 'explanation', 'disclosure', 'relationships', 'recap', 'segmentation')
BASE_CONFIG = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}


class Api:
    def __init__(self, base):
        self.base = base + '/workspace/guidance'

    def call(self, method, path, body=None, token=False):
        req = urllib.request.Request(self.base + path, method=method, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json', **({'X-C4-Token': TOKEN} if token else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b'null')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'null')


def step(j, aid):
    a = next(x for x in j['document']['actions'] if x['id'] == aid)
    return {'heading': a['heading'], 'primary': a['essential'], 'supplement_visible': a['explanation_visible'], 'supplement_hidden': a['explanation_hidden'],
            'documents_at_step': sorted(f['fact']['name'] for f in a['facts']), 'destination': a['destination'], 'has_source_wording': bool(a['source_wording'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise ValueError('choose a new output file')
    api = Api(args.base)
    procs = {p['procedure_id']: p['service_id'] for p in api.call('GET', '/procedures')[1]}
    status = api.call('GET', '/status')[1]
    report = {'status': {k: status[k] for k in ('action_schema', 'content_schema', 'encoder_status', 'personalized_selection_available')}, 'policy_revision_at_start': status['policy']['posterior_revision']}

    def profile(name, fam, conf):
        s, r = api.call('POST', '/profiles', {'profile_id': 'profile:' + uuid4().hex, 'display_name': name, 'personalization_enabled': True,
                                              'initial_context': {'navigation_capability': conf, 'familiarity': [{'service_id': procs[p], 'score': v} for p, v in fam.items()]}})
        assert s == 200, r
        return r['session']['session_id']

    def ask(sid, pid, mode=None, config=None):
        body = {'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN}
        if config:
            body.update(mode='research_preview', configuration=config)
        elif mode:
            body['mode'] = mode
        s, r = api.call('POST', '/research/previews' if config else '/requests', body)
        assert s == 200, r
        return r

    summary = lambda j: {'kind': j['selection']['kind'], 'configuration': {k: j['document']['configuration'][k] for k in KEYS}, 'controls': {k: j['controls'][k] for k in ('feedback', 'configuration_adjustment')}}
    guest = api.call('POST', '/guests')[1]['session_id']
    g = ask(guest, 'synthetic-practice-v2')
    report['guest_standard'] = {**summary(g), 'submit_step': step(g, 'action:submit_application')}
    experienced = profile('Review experienced', {'synthetic-practice-v2': 5, 'synthetic-linear-v1': 5}, 5)
    novice = profile('Review novice', {'synthetic-practice-v2': 1}, 1)
    c = ask(experienced, 'synthetic-practice-v2', 'personalized')
    r = ask(novice, 'synthetic-practice-v2', 'personalized')
    report['compact_candidate_experienced'] = {**summary(c), 'submit_step': step(c, 'action:submit_application')}
    report['rich_novice'] = {**summary(r), 'submit_step': step(r, 'action:submit_application'), 'register_step': step(r, 'action:register_application')}
    report['four_combinations'] = {}
    for explanation in ('concise', 'detailed'):
        for disclosure in ('off', 'on'):
            j = ask(guest, 'synthetic-practice-v2', config={**BASE_CONFIG, 'explanation': explanation, 'disclosure': disclosure})
            report['four_combinations'][f'{explanation}+{disclosure}'] = {'register': step(j, 'action:register_application'), 'submit': step(j, 'action:submit_application')}
    # manual adjustment and feedback eligibility on a genuine model selection
    shown = {'event_id': uuid4().hex, 'view_id': r['view_id'], 'type': 'view_displayed', 'action_ids': [r['document']['actions'][0]['id']]}
    api.call('POST', f"/journeys/{r['journey_id']}/events", shown, True)
    before = api.call('GET', '/status')[1]['policy']['posterior_revision']
    original = api.call('POST', f"/journeys/{r['journey_id']}/ratings", {'event_id': uuid4().hex, 'view_id': r['view_id'], 'rating': 'fits'}, True)[1]
    after = api.call('GET', '/status')[1]['policy']['posterior_revision']
    second_jid = ask(novice, 'synthetic-practice-v2', 'personalized')
    api.call('POST', f"/journeys/{second_jid['journey_id']}/events", {'event_id': uuid4().hex, 'view_id': second_jid['view_id'], 'type': 'view_displayed', 'action_ids': [second_jid['document']['actions'][0]['id']]}, True)
    child = api.call('POST', f"/journeys/{second_jid['journey_id']}/views", {'request_id': uuid4().hex, 'parent_view_id': second_jid['view_id'], 'configuration': {**second_jid['document']['configuration'], 'recap': 'off'}}, True)[1]
    manual = api.call('POST', f"/journeys/{second_jid['journey_id']}/ratings", {'event_id': uuid4().hex, 'view_id': child['view_id'], 'rating': 'fits'}, True)[1]
    parent_after_adjust = api.call('POST', f"/journeys/{second_jid['journey_id']}/ratings", {'event_id': uuid4().hex, 'view_id': second_jid['view_id'], 'rating': 'fits'}, True)[0]
    guest_rating = api.call('POST', f"/journeys/{g['journey_id']}/ratings", {'event_id': uuid4().hex, 'view_id': g['view_id'], 'rating': 'fits'}, True)[0]
    final = api.call('GET', '/status')[1]['policy']['posterior_revision']
    report['feedback'] = {'original_view_update': {k: original.get(k) for k in ('reward', 'policy_updated', 'learning_eligible')}, 'revision_before': before, 'revision_after_original_rating': after,
                          'manual_view_kind': child['selection']['kind'], 'manual_rating_updated_policy': manual['policy_updated'], 'parent_rating_after_adjusting_http_status': parent_after_adjust,
                          'guest_rating_http_status': guest_rating, 'revision_after_manual_and_guest': final}
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
