# SO1: change classification accuracy

Real run: `python research/experiments/classification_scoring.py`, 18 October 2026.

## Result

| | Result | Target |
|---|---|---|
| Accuracy | **9/9 (100%)** | 95% |
| False positives on noise-only edits | **0** | 0 |

9 labelled cases: 1 real, 8 constructed. Real change events within a short crawl window
are scarce by construction, so most cases are constructed -- the same decision the
proposal already logs openly (Table 11, Sep 2026: *"Construct labelled controlled change
events and state this openly"*). The one real case is a genuine page, re-crawled on two
different dates, with a genuinely different HTML structure (777 tags vs. 749), not a
synthetic edit.

**A correction made during this run, worth stating:** the real case was first labelled
`CONTENT_CHANGED`, assumed without checking. The classifier returned
`STRUCTURE_CHANGED`. Rather than record that as a classifier error, the actual HTML was
diffed directly -- it genuinely gained 28 tags between crawls. The classifier was right;
the first label was a guess that turned out wrong. Fixed before reporting.

## What the constructed cases cover

- **C2, C6, C8** — a single fee edit, an added document requirement, and a fee change next
  to a real stated identifier (an NIC-format example). All three must register as
  `CONTENT_CHANGED` without the structural check or the identifier-preservation rule
  interfering.
- **C3** — the same wording, with an added wrapper `<div>`. Must register as
  `STRUCTURE_CHANGED` even though no word changed, since a rebuilt page breaks
  selector-based extraction regardless of wording.
- **C4** — the proposal's own named critical case: only a self-updating visit counter and
  a date stamp changed. Must register as `UNCHANGED`, or every page carrying a counter
  would burn tokens on every single run -- the exact failure this mechanism exists to
  prevent.
- **C7** — a bare clock time and a phone number present. Must NOT be stripped as noise:
  both are real information a citizen needs, and over-aggressive noise stripping would
  delete real facts, which is worse than letting a counter through.
- **C5** — a page never seen before, correctly `NEW`.

## What this honestly supports

The mechanism meets its target on this labelled set, including the specific adversarial
cases the proposal names by name (the counter, the identifier-near-a-fee). The sample is
small (9 cases) and mostly constructed rather than observed, which is a real limitation of
evaluating change detection inside a short project window -- stated plainly rather than
padded with more constructed cases to make the number look larger.
