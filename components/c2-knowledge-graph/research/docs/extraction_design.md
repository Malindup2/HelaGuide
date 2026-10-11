# Why a language model sits between the crawled page and the graph

Component 2, Stage 2. Written 10 October 2026.

## The decision

Crawl4AI fetches a page and converts it to Markdown. It does not decide what the text means.
A language model reads that Markdown and returns structured facts (fee, documents,
prerequisites, processing time). Those facts are staged, reviewed, and only then written to
Neo4j. The model is a reader, not an authority: nothing it returns reaches the graph without
passing the checks below.

## Why the page cannot go straight into the graph

The Markdown is text for people. The graph needs typed facts with stable identities. The
real passport page (`immigration.gov.lk/pages_e.php?id=8`, crawled 10 Oct 2026) shows the gap.

| What the page does | Example from the page | Why a fixed pattern struggles |
|---|---|---|
| States one kind of value in several formats | `LKR. 10,000.00`, `LKR.20,000.00`, `LKR 3500.00`, `Rs. 20,000` | Each format needs its own pattern, and the next agency's page brings another |
| Reuses one label across variants | "Normal Basis" and "Urgent Basis" repeat for ordinary, minor and replacement passports | Which fee belongs to which variant depends on the heading above it, not the line |
| Writes requirements as conditions | "If parents do not have passports submit the National Identity Card" | The requirement exists only for some applicants |
| Writes prerequisites as prose | "certified copy of the police report and a confirmation letter from the Grama Niladhari countersigned by the Divisional Secretary" | A chain of steps across agencies, with no list markup |
| Puts the facts of a service across layouts | The same service is a list on one agency's site and a table or PDF on another's | Rules are written per page layout |

The ordering edge the graph exists to hold (`svc:passport` requires `svc:nic` requires
`svc:birth_certificate`) is stated in sentences like these. It is the part pattern matching
reads least reliably, and it is the part that matters most for the product.

## Why not trust the model blindly

A model can invent a plausible fee. A wrong fee shown to a citizen is the worst failure this
system can have. So the model is constrained rather than trusted:

1. **Fixed schema.** It returns only the predicates in `contracts/naming.md` (fee, document,
   agency, prerequisite, processing_time, eligibility), as JSON that is validated.
2. **Quote or drop.** Every item must carry a verbatim quote from the page. An item whose
   quote is not found on the page is discarded and counted, never stored.
3. **No guessing.** Missing values are null or an empty list. Values are copied as written,
   not converted or rounded.
4. **Identity from position.** The model never chooses an id. `fact_id` is built from service,
   predicate and a short qualifier, so a changed fee keeps its id and the old version closes.
5. **Review gate.** Output is staged as `pending`. Nothing reaches Neo4j without approval, and
   each decision is audited.
6. **Only changed pages.** Change detection runs first. Unchanged pages never reach the model,
   so cost follows what changed, not what was crawled.
7. **Cost is recorded.** Prompt and completion tokens are stored per page from the provider's
   own report, so the cost of keeping the graph current is measured, not modelled.

## Why not rules alone

Rules are exact, free and repeatable, which is why they are not discarded (next section). On
their own they would read the regular parts of this one page and need rewriting for each new
layout, and they would silently mishandle variants and prose conditions. A rule that is wrong
fails quietly; a model answer must at least quote the page.

## The plan: rules where the text is regular, the model for the rest

The intended design is a hybrid. Patterns take what is stated regularly (a fee line such as
"Normal Basis - LKR amount", a duration, a numbered document list). The model takes what
remains: variants, conditions and prerequisites. This lowers tokens per page and keeps the
exact parts exact. It is stated here as a design intent, not a result.

## What is established and what is not

| Claim | Status |
|---|---|
| The page has several fee formats, shared labels across variants and prose prerequisites | Observed on the real page |
| Page text sent to the model is about 12,000 characters (about 3,000 tokens) after menus are removed | Measured on the passport page, 10 Oct |
| Quote-or-drop and fixed ids behave as designed | Covered by tests with a fake model |
| The model extracts facts correctly from real pages | **Not measured yet.** No live model call has been run |
| Rules plus model costs fewer tokens than the model alone | **Not measured yet** |
| Extraction precision and recall | **Not measured yet.** Needs hand-annotated pages |

## How it will be judged

Annotate a small set of real pages by hand, then score the model, the rules, and the hybrid
on the same pages: fact-level precision and recall, the number of facts dropped as
ungrounded, and tokens per page. The choice between them is then a measured one.

## Known risks

- The model may phrase a qualifier differently between runs (`normal` and `standard`), which
  would change a fact id. Qualifiers need a controlled vocabulary or a normalisation step.
- Pages in Sinhala or Tamil, and scanned PDFs, are not covered. Observed: the passport
  application PDF has a readable English layer and a garbled Sinhala and Tamil layer.
- A long page is truncated at 30,000 characters and flagged.
