// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { InspectorSheet } from '../Research';
import { guidanceApi } from '../api';
import { mainService } from './examples';
import type { InspectorRecord } from '../types';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function record(): InspectorRecord {
  const r = mainService('personalised-nic-novice-rich'), c = r.document.configuration;
  const names = ['step_count', 'information_volume', 'branch_count', 'condition_count', 'dependency_count', 'dependency_depth', 'parallel_group_count'];
  return {
    schema_version: 'x', record_kind: 'completed_request_and_client_events', journey_id: r.journey_id, created_at: r.created_at, source_graph_fingerprint: 'g', content_fingerprint: 'c',
    effective_context: r.effective_context, measurements: Object.fromEntries(names.map(n => [n, { observed: 1, completeness: 'complete', normalized_observed: 0.5 }])), availability: r.availability,
    views: [{ id: r.view_id, parent_view_id: null, created_at: r.created_at, selection: r.selection }], events: [], features: null, sampled_scores: null, policy: null, posterior_updates: 0,
    scoring_status: 'executed', pp2_history_adjustment: 'not_implemented', visibility_policy: null, note: 'n',
    summary: { kind: 'shared_gaussian_lints', personalized: true, label: r.selection.label, selected_configuration: c, selected_description: 'Guided navigation, Detailed explanation', displayed_configuration: c, adjusted_by_citizen: false,
      effective_context: { familiarity: 1, confidence: 1, personalization_enabled: true, soft_preferences: { navigation: 'guided' }, preference_origin: 'saved_layout_preference_and_explicit_revised_settings' },
      hard_restrictions: { no_guided: false, no_map: true, no_disclosure: false, locks: {} },
      structure: Object.fromEntries(names.map(n => [n, { observed: 3, completeness: n === 'parallel_group_count' ? 'unknown' : 'complete' }])), feasible_count: 64, nominal_count: 96, sampled_score: 0.5496, posterior_mean: 0.5146,
      policy: { algorithm: 'shared_gaussian_lints', action_schema: 'c4-scaffolds-v3.1', encoder_schema: 'c4-features-pp1-1.1-525', posterior_revision: 5000, decision_id: 'decision:abcdef0123456789', model_manifest_fingerprint: 'm', training_provenance: 'synthetic' },
      learning: { eligible: true, reason: 'A genuine, unadjusted personalized selection.' }, map: { status: 'accessibility_restriction', detail: 'The citizen\'s accessibility settings do not allow diagrams.', map_configurations_feasible: 0 },
      explanation: 'The model evaluated the 64 feasible presentation configurations. The selected configuration was Guided navigation, Detailed explanation.' },
  };
}

describe('Research Inspector decision summary', () => {
  it('shows the stored values in plain language, with the map reason and learning eligibility, and no invented cause', async () => {
    vi.spyOn(guidanceApi, 'inspector').mockResolvedValue(record());
    render(<InspectorSheet journeyId="j" token="t" onClose={vi.fn()} />);
    const box = await waitFor(() => screen.getByLabelText('Decision summary'));
    const text = box.textContent!;
    expect(text).toContain('The selected configuration was Guided navigation, Detailed explanation.');
    expect(text).toContain('Familiarity 1 · confidence 1');
    expect(text).toContain('navigation: guided');
    expect(text).toContain('diagrams off');
    expect(text).toContain('64 of 96');
    expect(text).toContain('0.5496');
    expect(text).toContain('decision …23456789');
    expect(text).toContain('Not offered: accessibility setting');
    expect(text).toContain('Eligible.');
    expect(text).not.toMatch(/because|chose Guided/i);
  });
});
