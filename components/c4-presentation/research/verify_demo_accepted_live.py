"""Black-box check of the RUNNING backend in LOCAL RESEARCH DEMO acceptance mode with the trained Shared LinTS checkpoint (a copy in a fresh policy folder).
  python research/verify_demo_accepted_live.py --base http://127.0.0.1:8021 --output docs/C4-DEMO-ACCEPTED-LIVE.json
No mocks: every number comes from the live server. It trains only the live policy copy, never the original checkpoint."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import httpx

C4 = Path(__file__).resolve().parents[1]
CHECKPOINT = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-study-20261022-a' / 'seed-23-x0.25-525-n5000.npz'
ROOT = '/workspace/guidance'
TOKEN = 'live-demo-accepted-capability-' + 'x' * 16
H = {'X-C4-Token': TOKEN}
OFFICIAL = ('official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3')
BASE = {'navigation': 'overview', 'explanation': 'concise', 'disclosure': 'off', 'relationships': 'none', 'recap': 'off', 'segmentation': 'off'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8021')
    ap.add_argument('--output', required=True)
    ap.add_argument('--draws', type=int, default=20)
    args = ap.parse_args()
    out = Path(args.output).resolve()
    if out.exists():
        raise SystemExit('refusing to overwrite ' + str(out))
    sha_before = hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
    c = httpx.Client(base_url=args.base, timeout=60)
    report = {'checkpoint_sha256_before': sha_before, 'status': c.get(ROOT + '/status').json()}
    report['status'] = {k: report['status'][k] for k in ('content_schema', 'action_schema', 'encoder_status', 'personalized_selection_available', 'demo_accepted_content', 'demo_provisional_content')} | {'policy': {k: report['status']['policy'][k] for k in ('training_provenance', 'posterior_revision', 'manifest_fingerprint', 'accepted_feedback_count') if k in report['status']['policy']}}

    def profile(pid, fam, conf):
        service = next(p['service_id'] for p in c.get(ROOT + '/procedures').json() if p['procedure_id'] == pid)
        r = c.post(ROOT + '/profiles', json={'profile_id': 'profile:' + uuid4().hex, 'display_name': 'live demo-accepted check', 'personalization_enabled': True,
                                             'initial_context': {'navigation_capability': conf, 'familiarity': [{'service_id': service, 'score': fam}]}})
        r.raise_for_status()
        return r.json()['session']['session_id']

    def request(pid, sid, **extra):
        return c.post(ROOT + ('/research/previews' if 'configuration' in extra else '/requests'), json={'request_id': uuid4().hex, 'session_id': sid, 'procedure_id': pid, 'capability_token': TOKEN, **extra})

    guest = c.post(ROOT + '/guests').json()['session_id']
    counts, standard, selections = {}, {}, collections.defaultdict(collections.Counter)
    for pid in OFFICIAL:
        av = c.get(ROOT + '/procedures/' + pid + '/availability', params={'session_id': guest}).json()
        counts[pid] = {'feasible_after_demo_acceptance': av['feasible_count'], 'content_state': av['preparation']['content_state'], 'nominal': av['nominal_count'],
                       'maps_feasible': any(x['feasible'] and x['configuration']['relationships'] == 'map' for x in av['candidates']),
                       'segmentation_feasible': any(x['feasible'] and x['configuration']['segmentation'] == 'on' for x in av['candidates']),
                       'detailed_feasible': any(x['feasible'] and x['configuration']['explanation'] == 'detailed' for x in av['candidates']),
                       'disclosure_on_feasible': any(x['feasible'] and x['configuration']['disclosure'] == 'on' for x in av['candidates'])}
        j = request(pid, guest, mode='standard').json()
        standard[pid] = {'kind': j['selection']['kind'], 'learning_eligible': j['selection']['learning_eligible'], 'content_state': j['preparation']['content_state'], 'configuration': j['selection']['configuration']}
        for label, fam, conf in (('experienced', 5, 5), ('novice', 1, 1)):
            for _ in range(args.draws):
                r = request(pid, profile(pid, fam, conf), mode='personalized').json()
                selections[pid + '/' + label][json.dumps(r['selection']['configuration'], sort_keys=True)] += 1
    report['feasible_counts'] = counts
    report['guest_standard'] = standard
    report['lints_selection_frequencies'] = {k: dict(v) for k, v in selections.items()}

    pid = 'official-nic_amendment-v3'
    sid = profile(pid, 3, 3)
    j = request(pid, sid, mode='personalized').json()
    ins = c.get(ROOT + '/journeys/' + j['journey_id'] + '/inspector', headers=H).json()
    report['inspection_sample'] = {'selection_kind': j['selection']['kind'], 'scoring_status': j['selection']['scoring_status'], 'candidates_scored': len(ins['sampled_scores']), 'feasible_count': j['availability']['feasible_count'],
                                   'feature_count': len(ins['features']['names']), 'feature_fingerprint': ins['features']['fingerprint'], 'decision_content_state': ins['policy'].get('content_state'),
                                   'manifest_fingerprint': ins['policy']['policy']['model_manifest_fingerprint'] if 'policy' in ins['policy'] else None}
    before = c.get(ROOT + '/status').json()['policy']['posterior_revision']
    ev = c.post(ROOT + '/journeys/' + j['journey_id'] + '/events', headers=H, json={'event_id': uuid4().hex, 'view_id': j['view_id'], 'type': 'view_displayed', 'action_ids': [j['document']['actions'][0]['id']]})
    rate = {'event_id': uuid4().hex, 'view_id': j['view_id'], 'rating': 'fits'}
    first = c.post(ROOT + '/journeys/' + j['journey_id'] + '/ratings', headers=H, json=rate)
    replay = c.post(ROOT + '/journeys/' + j['journey_id'] + '/ratings', headers=H, json=rate)
    second = c.post(ROOT + '/journeys/' + j['journey_id'] + '/ratings', headers=H, json={**rate, 'event_id': uuid4().hex})
    after = c.get(ROOT + '/status').json()['policy']['posterior_revision']
    j2 = request(pid, profile(pid, 3, 3), mode='personalized').json()
    c.post(ROOT + '/journeys/' + j2['journey_id'] + '/events', headers=H, json={'event_id': uuid4().hex, 'view_id': j2['view_id'], 'type': 'view_displayed', 'action_ids': [j2['document']['actions'][0]['id']]})
    other = {**j2['selection']['configuration'], 'disclosure': 'off' if j2['selection']['configuration']['disclosure'] == 'on' else 'on'}
    adj = c.post(ROOT + '/journeys/' + j2['journey_id'] + '/views', headers=H, json={'request_id': uuid4().hex, 'parent_view_id': j2['view_id'], 'configuration': other})
    adj_rate = c.post(ROOT + '/journeys/' + j2['journey_id'] + '/ratings', headers=H, json={'event_id': uuid4().hex, 'view_id': adj.json()['view_id'], 'rating': 'fits'}) if adj.status_code == 200 else None
    orig_after_adjust = c.post(ROOT + '/journeys/' + j2['journey_id'] + '/ratings', headers=H, json={'event_id': uuid4().hex, 'view_id': j2['view_id'], 'rating': 'fits'})
    gj = request(pid, guest, mode='standard').json()
    guest_rate = c.post(ROOT + '/journeys/' + gj['journey_id'] + '/ratings', headers=H, json={'event_id': uuid4().hex, 'view_id': gj['view_id'], 'rating': 'fits'})
    final = c.get(ROOT + '/status').json()['policy']['posterior_revision']
    report['feedback'] = {'revision_before': before, 'revision_after_first_rating': after, 'first_status': first.status_code, 'replay_status': replay.status_code, 'replay_identical': replay.json() == first.json(),
                          'second_distinct_rating_status': second.status_code, 'manual_adjustment_status': adj.status_code, 'manual_view_rating_status': adj_rate.status_code if adj_rate else None,
                          'original_view_rating_after_adjusting_status': orig_after_adjust.status_code, 'guest_rating_status': guest_rate.status_code, 'revision_after_all': final,
                          'updates_from_this_check': final - before, 'event_ack_status': ev.status_code}
    report['checkpoint_sha256_after'] = hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
    report['original_checkpoint_unchanged'] = report['checkpoint_sha256_after'] == sha_before
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('feasible_counts', 'feedback', 'original_checkpoint_unchanged')}, indent=1))


if __name__ == '__main__':
    main()
