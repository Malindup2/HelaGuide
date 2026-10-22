# Crawler-level ablation: fingerprint-gated extraction vs. always-extract

This is the other half of the component's novelty story, upstream of SO3. Where SO3 is
about *maintaining* the graph cheaply once a value changes, this is about *acquiring*
pages cheaply in the first place — the two together are the full claim: cheap to build,
cheap to keep correct.

Real run: `python research/experiments/crawler_ablation.py`, 19 October 2026.

## The traditional approach vs. this component's approach

| | Status quo (every reviewed graph-RAG system) | This component |
|---|---|---|
| Between crawls | Stateless — no memory of the last fetch | Keeps a fingerprint (content hash + structure hash) per page |
| On every refresh | Re-extracts every page with a language model, regardless of whether it changed | Classifies the page first, for free, locally — only sends it to the model if the classifier says `NEW`, `CONTENT_CHANGED` or `STRUCTURE_CHANGED` |
| Cost scales with | Crawl frequency | Change frequency |

## Result — real with-and-without, same real event

Real repeat-crawl event (`67a7606f9c7b`, 11 October 2026, from the actual crawl log,
`research/data/crawl/runs.jsonl` — not constructed for this comparison): 236 pages,
3 unreachable, 233 reachable, of which 134 classified `UNCHANGED` and 99 needed extraction.

| | Pages extracted | Tokens | 
|---|---|---|
| Status quo (always extract) | 233 | **1,164,479** |
| Proposed (fingerprint-gated) | 99 | **494,779** |

**Token savings on this real event: 57.5%.**

The per-page cost (4,998 tokens) is the real average across every extraction call made so
far (182 real calls, 909,593 tokens total, queried live from Postgres) — not a fixed
constant plugged in to make the arithmetic come out a certain way.

A live proof runs alongside the historical numbers: the real `fingerprint()`/`classify()`
functions, called on an actual saved page, right now — 17.21 ms, 0 tokens, result
`UNCHANGED`. The historical count and the live mechanism are the same code path, not two
different claims.

## What this honestly supports

- This is a real repeat-crawl event, not a synthetic batch built to hit a target
  percentage — the 57.5% is whatever the real data gave.
- The per-page token figure is a real, current average, re-queried each run, not a number
  frozen at one point in time.
- What this is *not*: a controlled sweep across multiple crawl frequencies or multiple
  change rates — it is one real event, honestly reported, the same scope as the other
  preliminary-evidence results in this project.

## How this relates to SO3

| | Crawler ablation (this doc) | SO3 (`so3_community_maintenance.md`) |
|---|---|---|
| Question | Should this page be re-read by a model at all? | Should this community's summary be regenerated? |
| Status quo | Always re-extract | Only regenerate on structural change |
| Proposed trigger | Fingerprint + classify, before extraction | Value-change detection, after extraction |
| Real result | 57.5% fewer tokens on one real repeat-crawl | 0/20 stale (vs 20/20), 2.9% of a full rebuild |

Together: acquisition only pays for pages that changed, and maintenance only pays for
communities a real change actually touched. Both are real, measured, and independently
verifiable with the scripts named above.
