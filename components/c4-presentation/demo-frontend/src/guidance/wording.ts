import type { Document, Navigation, Spec } from "./types";

export function preparedText(doc: Document, kind: string, subjectKind: string, id: string): string | undefined {
  const slot = doc.prepared_wording?.items.find((item) => item.slot_id === `${kind}/${subjectKind}/${id}`);
  return slot && slot.origin !== "source_fallback" ? slot.text : undefined;
}

/** Actual previous displayed visit in this episode, never a completion claim. */
export function previousViewedAction(spec: Spec, navigation: Navigation | null, focus: string | null): string | null {
  if (spec.configuration.presentation_mode !== "GUIDED" || !navigation?.acknowledged || !focus) return null;
  const visits = [spec.initial_action_id, ...[...navigation.events].sort((a, b) => a.sequence - b.sequence).map((event) => event.action_id)]
    .filter((id): id is string => id !== null);
  let index = visits.length - 1;
  if (visits[index] === focus) index -= 1;
  for (; index >= 0; index -= 1) {
    const id = visits[index];
    if (id !== focus && spec.pages.some((page) => page.action_id === id)) return id;
  }
  return null;
}
