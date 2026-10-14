# Open questions for C2 (service IDs for C1 intents)

From: C1 (Dabarera W. A. S.) · To: C2 (T. Malindu Pabasara) · 2026-10-14

C1 maps each citizen intent to a C2 `service_id`. The draft mapping is in
`components/c1-intent/research/data/kg_service_map.json`. It was built from C2's committed
files only (agency profiles, `crawl/tree.json`, `changes.jsonl`, `seed_urls.yaml`,
`drp_completion_log.md`), because the graph and the crawl archive were not available locally.
`contracts/naming.md` says C2 owns the service vocabulary, so these IDs need your confirmation
before C1 uses them.

## Current mapping

| C1 intent | Service ID | Status |
|---|---|---|
| `nic_new` | `svc:nic` (variant `first_issue`) | in graph |
| `nic_update` | `svc:nic` (variant `amended`) | in graph |
| `nic_replace_lost` | `svc:nic` (variant `lost`) | in graph |
| `passport_new` | `svc:passport` (variant `ordinary`) | in graph |
| `passport_renew` | `svc:passport` (variant `replacement`) | in graph |
| `birth_cert_copy` | `svc:birth_certificate` | ID exists, no facts yet |
| `marriage_registration` | `svc:marriage_registration` | **proposed** |
| `death_cert_copy` | `svc:death_certificate` | **proposed** |

## Questions

### 1. Service IDs for marriage and death
No ID exists yet for these two. Can you confirm or assign them?

- `svc:marriage_registration`: appears only in `tests/test_autoreview.py`.
- `svc:death_certificate`: proposed to match `svc:birth_certificate`. `vocabulary.py` has a
  `death_certificate` document key, but no service ID for it.

### 2. Registration vs certificate copy
`svc:birth_certificate` seems to cover the certificate only. New birth registration and
registration of an unregistered birth have their own RGD pages
(`birth/birth-registration`, `birth/registration-of-unregistered-birth`) but no ID.

- Is one ID for registration and copy intended?
- If you plan a separate `svc:birth_registration`, should death (`death/death-registration`)
  and marriage follow the same pattern?

C1 treats new birth registration as `unsupported_service` until this is decided.

### 3. Passport basis: normal / urgent
Passport facts use `normal` / `urgent` (e.g. `svc:passport:fee:ordinary_normal`,
`minor_urgent_3y`). C1's schema 1.1 now matches this: the passport `service_type` slot is
`[normal, urgent]`, and "one day service" in user text maps to `urgent`. NIC one-day
service (`oneday_branch.php`) stays separate, in C1's `urgency` slot.

- Are you happy with this?

### 4. NIC and passport variants
Please confirm that these cases are **variants of one service**, not separate services:

- NIC update → `svc:nic` / `amended`
- NIC lost or damaged → `svc:nic` / `lost` or `replacement`
- Passport renewal → `svc:passport` / `replacement`

Also, is passport amendment (`pages_e.php?id=10`) planned as its own service
(`svc:passport_alteration` appears in a test), or as a `svc:passport` variant?

### 5. Deceased person's NIC
Two IDs appear: `svc:surrender_nic_deceased` (`test_autoreview.py`, completion log) and
`svc:nic_deceased_card_handover` (`test_sections.py`). Which one is current?

### 6. Dual citizenship
The Immigration dual citizenship page (`pages_e.php?id=4`) is crawled, with fee, document
and prerequisite signals. Forms are linked at both Immigration (`DualCIT_Application.pdf`)
and DRP (`0007.pdf`, `104.pdf`, `dual.pdf`).

- Will it get a service ID (e.g. `svc:dual_citizenship`)?
- If yes, C1 will add a `dual_citizenship` intent and seed dialogues for it.

### 7. RGD extraction status
The RGD birth, marriage and death pages were crawled on 2026-10-11 (run `67a7606f9c7b`),
after the last entry in `drp_completion_log.md`. Have they been read by the model and
written to the graph, or are they still waiting? This decides whether C1 can promise
answers for `birth_cert_copy`, `marriage_registration` and `death_cert_copy`.

### 8. Service list export
Could you export the current Service nodes to a JSON file in git? For each service:

- `service_id`
- English name
- department
- which predicates have approved facts (fee, document, prerequisite, processing_time,
  eligibility)
- variants and basis qualifiers in use

C1 would check its IDs against this file in CI, instead of inferring them from logs.

### 9. Sinhala service names
Discovery drops the Sinhala and Tamil copies of pages, so the KG has no official Sinhala
service names. C1 needs them to match Sinhala user text.

- Do you plan to crawl the Sinhala menu pages (`immigration.gov.lk/*_s.php`,
  `drp.gov.lk/si/`, the RGD Sinhala menu)?
- If not, C1 will collect the names by hand. Should they be stored on C2's Service nodes
  (e.g. `name_si`) or kept on the C1 side?

## What C1 does after the answers

- Fill `kg_service_id` in `research/data/schema_v1.json` and close its open questions.
- Update `kg_service_map.json` (statuses, Sinhala names).
- Add or drop the `dual_citizenship` intent and adjust the `service_type` enum.
