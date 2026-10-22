# Preferences, sidebar, earlier procedures and Inspector summary

Branch `c4/final-official-guidance`. The Shared LinTS policy, the 525-feature encoder and fingerprint, the 96 configurations, rewards, the checkpoint, the strict map rule and every v3 graph are unchanged.

## Audit findings
- **Preferences:** the encoder already supports soft preferences for all six dimensions (13 one-hot indicators, unset = all zeros, trained with such preferences in the synthetic study). Hard limits are accessibility flags and locks, enforced in `evaluate31`. A soft preference never removes a candidate (tested).
- **Defect fixed:** the profile field "Preferred guidance layout" (OVERVIEW/GUIDED) was saved in the legacy settings but never reached `effective_context.preferences` or the encoder (it only appeared under `legacy.preferences_not_imported`). It is now imported as a soft `navigation` preference (`GuidanceAPI.context`), until the citizen saves revised preferences explicitly, after which the revised set is authoritative (so "No preference" works). The other legacy meanings stay review items.
- **Other five dimensions:** supported by the existing `PATCH /workspace/guidance/context/{session}` but had no UI. Added an optional collapsed "Presentation preferences (optional)" section to "Edit saved settings"; blank = unknown. Accessibility is labelled "(always respected)".
- **Maps:** unchanged rule. Earlier official graphs have parallel coverage "unknown". The DRP page states no parallel work, no independence and no order between amendment steps, so NIC cannot legitimately qualify; no fixture was created and nothing was marked verified. The one-day service is not modelled as a branch because the page does not say whether it replaces the certifying-officer step. The retained fictional "Submit a prepared application" (4 verified actions, 4 prerequisites, 1 stated parallel group, coverage complete, all 96 configurations feasible) is the map demonstration.

## Changes
- Sidebar lists the official services, exactly three earlier versions, and only the fictional parallel example (`citizen/visibility.ts`). Nothing is removed from the registry.
- Earlier-version wording (`research/build_provisional_content.py`, content_version `demo-accepted-v3-2`): new headings, Concise, Detailed, supplements and recap lines; filler removed; NIC fee now sits on the two certification steps instead of the route question. The previous wording is copied unchanged to `research/data/guidance/provisional-v31/archive/`.
- Research Inspector: new "Decision summary" (`guidance/inspector_summary.py`, `summary` key in the inspector payload, `Research.tsx`). Values come from the stored journey; map availability separates accessibility, explicit lock, no relationship data, incomplete coverage and policy choice.

## Compatibility
- v3 graph fingerprints are unchanged (tested against both wording versions). The training schedule used the v3 graphs with no prepared content, so the demo wording files do not take part in training, replay or the checkpoint manifest.
- Demo content fingerprints for the three earlier procedures changed (new wording); frozen journeys keep their stored content.
- The preference import changes only the soft-preference input for profiles that set a layout preference.
