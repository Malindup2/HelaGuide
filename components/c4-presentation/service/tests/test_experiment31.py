"""3.1 synthetic study: procedures, both-direction simulator, leak-free training, exact replay. SYNTHETIC only."""
import json
import shutil
from pathlib import Path
from uuid import uuid4
import numpy as np
import pytest
from app.guidance import features
from app.studies import procedures31
from app.studies import synthetic31 as syn
from app.guidance.catalogue import CATALOGUE, Configuration
from app.guidance.content_v31 import evaluate31, validate_content31
from app.studies.experiment31 import DEV, TEST, TRAIN, dataset, feasible, make_cases, reassess, replay, report, train
from app.learning.lints import Model
from app.guidance.v31_pipeline import PROFILE_31
from app.procedures.measurements import measurements

C4 = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def data():
    return dataset()


def best(config_list, context, item, assumption='balanced'):
    return max(config_list, key=lambda c: syn.probability(c, context, item['measurements'], item['stages'], assumption))


def test_study_procedures_are_valid_varied_and_never_official(data):
    assert set(procedures31.SPECS) <= set(data) and all(data[p]['source'].graph.synthetic for p in procedures31.SPECS)
    for pid in procedures31.SPECS:
        source = procedures31.source(pid)
        validate_content31(source, procedures31.content(source))
    steps = {p: data[p]['measurements'].step_count.normalized_observed for p in procedures31.SPECS}
    volume = {p: data[p]['measurements'].information_volume.normalized_observed for p in procedures31.SPECS}
    assert max(steps.values()) > 2 * min(steps.values()) and max(volume.values()) > 4 * min(volume.values())
    assert data['study-branching']['measurements'].branch_count.normalized_observed > 0 and data['study-parallel-join']['measurements'].parallel_group_count.normalized_observed > 0
    assert len(data['study-multiphase']['source'].graph.stages) >= 3 and len(data['study-short-linear']['source'].graph.stages) == 1


def test_splits_do_not_overlap_and_official_procedures_stay_fallback(data):
    assert not set(TRAIN) & set(DEV) and not set(TRAIN) & set(TEST) and not set(DEV) & set(TEST)
    for pid in ('official-birth_copy-v3', 'official-nic_amendment-v3', 'official-company_pack-v3'):
        assert data[pid]['content'] is None and len(feasible(data[pid], {})) == 4


def test_every_scaffold_stays_feasible_somewhere_in_the_study(data):
    seen = {d: set() for d in ('navigation', 'explanation', 'disclosure', 'relationships', 'recap', 'segmentation')}
    for pid, item in data.items():
        for c in feasible(item, {}):
            for d in seen:
                seen[d].add(getattr(c, d))
    assert seen == {'navigation': {'overview', 'guided'}, 'explanation': {'concise', 'detailed'}, 'disclosure': {'off', 'on'}, 'relationships': {'none', 'inline', 'map'}, 'recap': {'off', 'on'}, 'segmentation': {'off', 'on'}}


def test_simulator_penalises_both_under_and_over_support(data):
    easy = {'familiarity': 5, 'confidence': 5, 'preferences': {}}
    hard = {'familiarity': 1, 'confidence': 1, 'preferences': {}}
    short, rich = data['study-short-linear'], data['study-mixed']
    nothing, everything = Configuration(), Configuration(navigation='guided', explanation='detailed', disclosure='on', relationships='map', recap='on', segmentation='on')
    p = lambda c, ctx, item, a='balanced': syn.probability(c, ctx, item['measurements'], item['stages'], a)
    assert p(nothing, easy, short) > p(everything, easy, short) + 0.3          # over-support hurts
    assert p(everything, hard, rich) > p(nothing, hard, rich) + 0.3            # under-support hurts
    assert best(feasible(short, {}), easy, short).navigation == 'overview'
    assert support_total(best(feasible(rich, {}), hard, rich)) > support_total(best(feasible(short, {}), easy, short))


def support_total(c):
    return float(features.action_values(c)[:-1].sum())


def test_assumptions_change_the_weights_and_the_flat_world_has_no_effect(data):
    ctx, item = {'familiarity': 3, 'confidence': 3, 'preferences': {}}, data['study-multilevel']
    a, b = Configuration(), Configuration(navigation='guided', relationships='map')
    gap = lambda name: syn.probability(a, ctx, item['measurements'], item['stages'], name) - syn.probability(b, ctx, item['measurements'], item['stages'], name)
    assert gap('under_heavy') != gap('over_heavy')
    assert all(syn.probability(c, ctx, item['measurements'], item['stages'], 'flat') == 0.6 for c in CATALOGUE[:6])
    assert all(syn.probability(c, ctx, item['measurements'], item['stages'], 'balanced', 'flat') == 0.6 for c in CATALOGUE[:6])
    assert len(syn.FAMILIES) == 22 and sum(v[1] == 'retained' for v in syn.FAMILIES.values()) == 10


def test_scenarios_use_only_their_split_procedures_and_hard_constraints_are_respected(data):
    cases = make_cases(data, TEST + TRAIN, 66, 5, 'test')
    assert {c['procedure_id'] for c in cases} <= set(TEST + TRAIN) and any(c['procedure_id'] in TEST for c in cases)
    n12 = next(c for c in cases if c['family'] == 'N12')
    assert all(c.relationships != 'map' and c.navigation == 'overview' and c.disclosure == 'off' for c in feasible(data[n12['procedure_id']], n12['constraints']))


def test_policy_and_encoder_never_import_the_simulator_or_study_code():
    app = C4 / 'service' / 'app'
    for name in ('learning/lints.py', 'learning/posterior.py', 'guidance/features.py', 'guidance/catalogue.py', 'guidance/frontend_runtime.py', 'guidance/v31_pipeline.py'):
        text = (app / name).read_text(encoding='utf-8')
        assert 'synthetic31' not in text and 'experiment31' not in text and 'procedures31' not in text, name


def test_short_training_run_is_leak_free_exactly_replayable_and_never_changes_the_posterior_when_evaluated():
    out = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / uuid4().hex[:8]
    try:
        train(out, seed=5, budget=30, variants=('416',), checkpoints=(0, 10, 30))
        result = json.loads((out / 'result-seed-5.json').read_text(encoding='utf-8'))
        assert [r['episode'] for r in result['records']] == [0, 10, 30] and result['records'][0]['posterior_revision'] == 0 and result['records'][-1]['posterior_revision'] == 30
        assert result['records'][-1]['dev']['violations'] == 0 and result['records'][-1]['test']['violations'] == 0
        assert replay(out, 'seed-5-416')['replayed_observations'] == 30
        lines = [json.loads(x) for x in (out / 'seed-5-416.jsonl').read_text(encoding='utf-8').splitlines()]
        assert [x['revision_after'] for x in lines] == list(range(1, 31)) and all(x['reward'] in (0, 1) for x in lines)
        assert all(x['configuration'] and x['feedback_origin'] == 'simulation' for x in lines)
        restored = Model.restore((out / 'seed-5-416-n30.npz').read_bytes(), PROFILE_31.manifest('416'), PROFILE_31)
        assert restored.revision == 30 and restored.manifest['action'] == 'c4-scaffolds-v3.1'
        with pytest.raises(ValueError, match='incompatible PP1 checkpoint manifest'):
            Model.restore((out / 'seed-5-416-n30.npz').read_bytes(), Model('416').manifest)
        reassess(out, 'seed-5')   # raises unless the sampled-selection numbers reproduce exactly
        again = json.loads((out / 'reassessed-seed-5.json').read_text(encoding='utf-8'))
        assert all('greedy' in r['test']['assumptions']['balanced'] for r in again['records'])
        assert all(a['reward'] == b['reward'] for a, b in zip((r['test']['assumptions']['balanced'] for r in result['records']), (r['test']['assumptions']['balanced'] for r in again['records'])))
        summary = report(out)
        assert summary['aggregates'] and summary['budgets_per_independent_run'] == [0, 10, 30]
        with pytest.raises(ValueError, match='refusing to overwrite'):
            train(out, seed=5, budget=30, variants=('416',), checkpoints=(0, 30))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_first_decision_does_not_depend_on_the_hidden_reward_world():
    out = C4 / 'service' / '.local' / 'pp1-learning' / 'v31-tests' / uuid4().hex[:8]
    try:
        train(out, seed=7, budget=6, variants=('416',), checkpoints=(0, 6))
        train(out, seed=7, budget=6, variants=('416',), assumption='over_heavy', checkpoints=(0, 6))
        a = [json.loads(x) for x in (out / 'seed-7-416.jsonl').read_text(encoding='utf-8').splitlines()]
        b = [json.loads(x) for x in (out / 'seed-7-over_heavy-416.jsonl').read_text(encoding='utf-8').splitlines()]
        assert a[0]['configuration'] == b[0]['configuration'] and a[0]['scores_digest'] == b[0]['scores_digest']
    finally:
        shutil.rmtree(out, ignore_errors=True)
