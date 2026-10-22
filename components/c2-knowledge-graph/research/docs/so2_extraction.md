# SO2: typed extraction precision and recall

Manual check, 18 October 2026, against a random sample of 10 real approved pages (124
facts total) across all 4 departments. `random.seed(7)` — the sample is reproducible, not
cherry-picked.

## Precision: 123/124 (99.2%) — target 90%

Every one of the 124 facts was read against its quote and its full source context, not
just checked for a quote's presence. One genuine error found:

**`title/transactions` (RGD)** derived `prerequisite: svc:passport` from the document
*"A certified copy of the National Identity Card, Passport, **or** Driving Licence"* —
three alternatives, any one of which suffices. The extraction (correctly) listed the
document, but the prerequisite-derivation step wrongly treated "passport" as a mandatory
requirement rather than one option among three. This would make the plan tool wrongly
insist a citizen already holds a passport before this service, when an NIC or driving
licence would do.

Two things checked and found correct on close reading, not assumed:
- A multi-column fee table (`title/charges`) where the extracted value was the *last*
  column (the total) of a 4-number row — correct, not an error, confirmed against the full
  quote rather than the truncated display.
- A real HTML structural change between two crawl dates of the same page (used for SO1)
  was initially mislabelled in that check's ground truth, not here — noted for
  transparency since it's the same discipline applied twice this session.

## Recall: partial check, 1 genuine miss found

A full fact-by-fact recall audit of 10 pages (checking every sentence of raw text against
what was extracted) was not completed in this pass — it is a materially larger task than
precision, and is named honestly as incomplete rather than padded with an unchecked
number.

**2 of the 10 pages were checked in depth** against their raw saved text:

- `translate-certificate-of-marriage` (RGD): **one real miss**. The page states *"If
  receiving by post, in addition to the above requirements, a stamped envelope bearing the
  recipient's address"* — a genuine, in-schema `document` fact (conditional, but a real
  requirement) that was not extracted at all. 2 of 3 extractable document-type facts on
  this page were captured.
- Nation Building Tax (IRD): no miss found in the content reviewed.

**One pattern worth naming, not a miss:** this same page also states office hours for
*accepting applications* ("9.00 a.m. to 2.30 p.m. on working days"). This is real,
useful information, but it does not fit any of the six predicate types the ontology
defines (`fee`, `document`, `agency`, `prerequisite`, `processing_time`,
`eligibility`) — `processing_time` is how long the service *takes*, not when you may
*submit* it. This is the same schema boundary already discussed earlier this session
(location/submission-hours questions fall outside the structured graph by design, into
search instead) — not a recall failure of the extractor, a scope decision of the ontology.

## What this honestly supports

Precision clears its target comfortably (99% vs. 90%), on a full, not partial, check.
Recall cannot be honestly reported as a single number yet — the one real finding (a
conditional document silently dropped) is a specific, useful signal that conditional
requirements are a weak spot, consistent with the conditional-fact handling gap already
known from the review process earlier this session, but a defensible recall percentage
needs the remaining 8 pages checked the same way.
