# C1 contract proposal: optional fields for `intent` v1.1 (or v2)

**From:** C1 (Dabarera W. A. S.) · **To:** C2, C3, C4 owners · **Date:** 18 Oct 2026 · **Status:** proposal, nothing changed

This is a proposal only. `contracts/` and `shared/` are unchanged. Per `CONTRIBUTING.md`, an accepted proposal
becomes its own PR touching only `contracts/` and `shared/helaguide_common/contracts.py`, approved by all four
owners.

## Why

C1 tracks 12 internal intents and up to 3 slots per intent. The v1 `intent` contract carries 4 intents and two
entities (`service_id`, `district`), so C1 projects its state onto it (table in `technicalWorkFlow.md` §7). The
projection loses information that the other components need. Until the contract changes, C1 exposes the full
state on a **C1-only** endpoint, `POST /v1/intent/details`, which the demo uses and C3 can call directly.

All fields below are **optional** with a `null` default. An older consumer that ignores them keeps working, and
C1 keeps sending everything v1 requires. Because `intent.schema.json` has `additionalProperties: false`, adding
them is still a schema change: it can be v1.1 if the team treats additive optional fields as non-breaking, or v2
otherwise.

| Field | Where | Type | Values |
|---|---|---|---|
| `route` | top level | string or null | `orchestration`, `trust_verification`, `fallback`, `none` |
| `entities.variant` | entities | string or null | `first_issue`, `amended`, `lost`, `ordinary`, `replacement` |
| `entities.service_type` | entities | string or null | `normal`, `urgent` (passport) |
| `entities.urgency` | entities | string or null | `normal`, `urgent` (NIC one-day) |
| `bot_text` | `UtteranceRequest` | string or null, ≤ 2000 chars | the bot's last question |

## `route`

Today `unsupported_service`, `feedback_complaint` and `out_of_scope` all arrive at the gateway as
`intent: unknown` with `service_id: null`, and the gateway answers 422 "Could not identify a service". The gateway
cannot tell a complaint, which should go to C3 trust verification, from a service HelaGuide does not cover yet
(the citizen should be told so) or from small talk. C1 already decides this per turn: core intents and general
questions go to `orchestration`, complaints to `trust_verification`, unsupported services to `fallback`, and
everything else to `none`. A `route` field would let the gateway send complaints to C3 and give a clear
"not supported yet" answer, without C1 abusing `intent` or `service_id` to signal it.

## `entities.variant`

C1 keeps `nic_new`, `nic_update` and `nic_replace_lost` apart, but all three project to `svc:nic`; both passport
intents project to `svc:passport`. In the knowledge graph these are variants of one service, and the fee and the
document list differ by variant (a lost NIC needs a police report; a passport replacement is not a first issue).
C2 needs the variant to choose the right facts. C1 already has it: `research/data/kg_service_map.json` gives the
KG variant for each internal intent (`first_issue`, `amended`, `lost`, `ordinary`, `replacement`). The values are
C2's vocabulary and should be confirmed by C2 (see `c2_open_questions.md`).

## `entities.service_type` / `entities.urgency`

Some slots change the plan. Passport `service_type` (`normal` / `urgent`) decides the fee, and NIC `urgency`
decides whether the one-day service applies. C1 already fills both, often over several turns ("Ikmanata onada?"
→ "ow"), but v1 has nowhere to put them, so C2 has to assume the normal service. Two optional enum fields would
let C2 return the right fee and office and let C4 show the faster option. Other slots (`applicant_for`,
`travel_date`, `purpose`) can follow later if C2 or C4 need them.

## `bot_text` in the request

C1 understands a short answer much better when it knows the question. "Matara" after "Koheda inne?" fills
`district`. "ow" after "Ikmanata onada?" sets urgency, and "ow" after "District eka Colombo neda?" confirms
Colombo. In Observation 9 (`notes.md`), on the human-written fresh set, adding the bot's question raised joint
goal accuracy from **0.86 to 0.88**; corrections and confirmations, which also read the question, take it to 0.92.
The frontend or gateway already has the bot's last message, so passing it costs one optional string. Without it,
`/v1/intent` calls the tracker with no question, as now.

## What does not change

- The 4 contract intents and their meaning.
- `service_id` and `district`.
- Stub mode: `contracts/examples/intent.example.json` stays valid, because every new field is optional.
