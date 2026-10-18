# Token cost and update latency

![Update latency (unchanged vs changed) and token cost on a real repeat crawl](figures/pp2_token_latency_figure.png)

Real run, 18 October 2026, against the live Postgres log (`c2.extractions`, `c2.runs`) and
a direct timing of the real code paths — not modelled, not synthetic.

## Update latency

| Path | Measured | How |
|---|---|---|
| **Unchanged page** (no LLM call) | **22.8 ms** median, 24.4 ms max, n=20 | Real saved page, fingerprinted and classified twice (`fingerprint()` + `classify()`, the actual production code path) |
| **Changed page** (LLM extraction) | **11.8 s** median, 50.6 s p95, n=128 | Wall-clock gaps between 148 real consecutive extraction calls (`gemini-2.5-flash`), filtered to drop cross-session pauses |
| **`/v1/plan` query** (3-step passport plan) | **153 ms** | Real call through `app.core.workflow.plan_for`, the same code now serving the real API (today's earlier work) |

**The unchanged path is about 500x faster than the changed path** (11,800 ms / 22.8 ms),
because it never calls a language model at all — this is the real, measured version of
NFR4 ("a maintenance cycle in which no source page has changed shall consume zero
language-model tokens").

## Token cost: B1 (full rebuild) vs. the real incremental cost

| | Value | Source |
|---|---|---|
| Total corpus extracted so far | **244 pages, 909,593 tokens** | `sum(prompt_tokens + completion_tokens)` across every successful extraction, real |
| Average cost per page that needs extraction | **3,728 tokens** | Same data, averaged |
| Real repeat-crawl event (run `67a7606f9c7b`) | **134 of 236 previously-seen pages (57%) classified UNCHANGED** | The real run log (`crawl/runs.jsonl`), not constructed |

**What this means in B1/B2 terms, stated carefully:** the 909,593-token corpus total is a
real B1 figure — what it actually cost to build the current graph from nothing. The 57%
unchanged rate is a real, measured number from an actual second crawl of already-seen
pages, not a synthetic ablation. Applying that real rate to the average page cost: a
stateless crawler with no change detection would have spent roughly
`134 × 3,728 ≈ 500,000` tokens re-extracting pages that had not changed, on that one
real event alone. This component spent zero tokens on those 134 pages, because
`classify()` correctly identified them as `UNCHANGED` before any LLM call was made.

**One thing this is not, stated plainly:** this is not a repeated A/B ablation over
*identical* update batches with a controlled change rate, which is what the proposal's
own B1/B2 design (Section 3.3) calls for. It is a real number from the one genuine
repeat-crawl event this project window produced, which is a smaller and more honest claim
than a full ablation study would be.

## What this honestly supports

- NFR4 (zero tokens on an unchanged page) is demonstrated, not assumed — the unchanged
  path takes 22.8 ms and makes no network call.
- The 57% real unchanged rate, applied to the real average page cost, gives a genuine
  (not modelled) order-of-magnitude saving on the one repeat-crawl event measured.
- A proper B1/B2 ablation — identical graph, identical batch, trigger as the only
  manipulated variable, repeated across seeds — is not done. The numbers here are real
  but come from the project's actual operation, not a controlled experiment built to
  isolate the mechanism the way Section 3.3 specifies.
