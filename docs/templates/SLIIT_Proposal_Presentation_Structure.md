# SLIIT Proposal Presentation — Reverse-Engineered Structure Template

Derived from a full read of **25-26J-436, "Cross Platform Form Generator with Schema Driven Automation"** (23 slides, 4 members, Software Engineering). This is the house style the panel is used to seeing. Written so a deck for **J26-SE-354** can be generated from it without re-deriving the format.

---

## 1. The shape at a glance

```
GROUP SECTION (5 slides)
  1. Title + team
  2. Hero image (full bleed, no text)
  3. Previous Research & Shortcomings : Our Approach   <- 3-col table
  4. Constraints & Limitations                          <- plain bullets
  5. System Overview Diagram                            <- whole system, all components

PER-MEMBER BLOCK (x4 members, 4 slides each = 16 slides)
  A. Member divider          <- ID | NAME + component title + photo
  B. Existing Work, Gaps and Solution
  C. Application of Pillars & Technologies
  D. System Overview and Requirements
  (optional 5th: Performance Metrics & Data Source)

CLOSING (1 slide)
  23. Commercial Viability
```

Total ≈ 22–25 slides. The per-member block is the unit that repeats — build one perfectly, then clone it four times.

---

## 2. Group section — slide by slide

### Slide 1 — Title

- **PROJECT TITLE IN BOLD CAPS**, two lines, centred, largest text on the deck
- Project ID directly beneath (`25-26J-436` style → yours is `J26-SE-354`)
- **Supervisor row:** 2 photos side by side, centred. Name in bold, then `Lecturer` / `Senior Lecturer`, then `Faculty of Computing | Computer Science` (or Software Engineering) in small bold text beside the photo
- **Member row:** 4 photos in a row beneath, equal size. Under each: `Surname Initials.` then `(Leader)` on the leader only, then `IT-number`
- Footer: SLIIT logo bottom-left, project ID centre, date + slide number bottom-right

### Slide 2 — Hero image

One full-bleed contextual image, **no text at all**. In the reference deck it was an AI-generated image of a developer at a multi-monitor setup — i.e. a visual of the *pain*, not the solution. For J26-SE-354 the equivalent would be a citizen at a government counter, or a queue at a divisional secretariat.

Purpose is pacing, not information. Don't over-think it.

### Slide 3 — Previous Research & Shortcomings : Our Approach

A **3-column table, black header row, white bold header text**, alternating grey/white body rows:

| Existing Tools | Shortcomings | Our Approach |
|---|---|---|
| *Named product/system* | 3 bullets, each a concrete limitation | 3 bullets, each answering the shortcoming on the same row |

3 rows is what they used. **The discipline that makes this slide work: every "Our Approach" bullet must answer the shortcoming sitting directly to its left.** Don't list generic features.

For J26-SE-354 the rows would be Microsoft GraphRAG / HIT-Leiden / EraRAG (or GIC-1919 / manual portals, depending on whether the panel wants tools or research as the comparison).

### Slide 4 — Constraints & Limitations

Plain bullet list, 5–7 items, no boxes, no colour. Short declarative sentences. Reference deck examples:

- Dependent on *[external standard/ecosystem]*
- *[Third-party system]* must support *[version]* for integration
- AI-assisted *[X]* may cause inaccuracies
- Performance overhead with large or complex *[input]*
- Automated *[Y]* may miss domain-specific edge cases

**Note this slide is where honest limitations go — the panel expects it, and it costs nothing to be candid here.** Naming a limitation yourself is worth more than having it found.

### Slide 5 — System Overview Diagram

One large boxed diagram of the **whole system**, all components, with the project name as the diagram's internal title. Flow reads top-to-bottom: actors → shared artefact → the N component boxes side by side → their outputs → converged final output.

Small italic caption underneath: `System Overview Diagram – [Project Title]`.

---

## 3. Per-member block — the repeating unit

### Slide A — Member divider

Sparse and clean:

- Photo, top-right corner
- `IT-NUMBER | SURNAME INITIALS` in large bold caps, left-aligned, roughly vertically centred
- `Title of the Individual Component: ` in grey, followed by the **component title in bold** (some members used bold italic — pick one and keep it consistent)
- `Software Engineering` in grey, lower down
- Footer switches here to `IT-number | Name | Project-ID`

### Slide B — Existing Work, Gaps and Solution

Title in bold caps, **component title as an italic subtitle beneath it**. Then coloured bordered boxes:

| Box | Border | Content |
|---|---|---|
| **Gaps** | blue | 3–5 bullets. Each ends with a bracketed citation `[1][2]` |
| **Related work** | magenta | Grouped by category: `Category - Tool, Tool, Tool` |
| **Proposed Solution** | green or orange | 3–4 bullets, each mapping to a gap |
| *(optional)* comparison table | thin grey | Feature rows × competitor columns, with ❌ / ✅ marks and your column last |

**Footnote strip along the bottom:** IEEE-style numbered references in ~6pt text, with live hyperlinks. Format used:

> [1] F. Author, J. Author, and B. Author, "Title," arXiv preprint arXiv:XXXX.XXXXX, Aug. 2025. [Online]. Available: https://arxiv.org/abs/XXXX.XXXXX

The optional comparison table is the strongest element on this slide — it makes the gap visible in one glance. **Use it.** Rows are capabilities, columns are named competitors, your column is rightmost and is the only one with all ✅.

### Slide C — Application of Pillars & Technologies

Four boxes, quadrant-ish layout:

| Box | Border | Content |
|---|---|---|
| **Application of Key Pillars** | blue | `**Pillar Name** → what you do with it`. Pillars used: Software Engineering, Web Engineering, NLP, HCI, Software Quality Assurance, Backend Engineering |
| **Application of Technologies** | magenta | `**Layer (PILLAR-TAG)** → concrete named tools/versions` |
| **Evaluation Plan** | green | 3 bullets, `**Dimension:** how it is measured` |
| **Data Availability** | orange | Named datasets/sources with citation markers, plus a reference footnote strip |

The `(SE)` / `(WE)` / `(HCI)` / `(SQA)` tags after each technology line are how they show the pillar mapping without a separate slide. Keep them.

### Slide D — System Overview and Requirements

Two-column layout:

- **Left:** `System Overview Diagram` heading + the boxed **component-level** diagram (Inputs group → Core Processes group → Outputs), with small italic caption underneath
- **Right, top box:** `User / Functional Requirements` — 4–7 short bullets
- **Right, bottom box:** `Real world use case` — one short paragraph, a named concrete actor doing a concrete thing ("A university IT team defines fields in JSON Schema → system auto-generates a WCAG-compliant React form…")

The "Real world use case" paragraph is what makes the component feel real to a panel. Write it as a story with a named actor, not as a feature list.

### Optional Slide E — Performance Metrics & Data Source

Only one member used this, and **it was the strongest technical slide in the deck.** Two columns:

- **Left — Performance Metrics:** numbered metrics, each with a sub-bullet defining what is measured and a bold **Benchmark:** line giving the *numeric target from industry/literature* ("Success is generally recognized at 95% or higher"; "Industry benchmarks look for a 20–40% improvement")
- **Right — Data & Ethical Considerations:** `Training Data Sources: [Link]` then `Privacy & Ethics:` with 3 bullets

**For J26-SE-354 this slide should not be optional.** It is where your measured benchmark results belong, and you have real numbers where the reference deck only had targets.

---

## 4. Closing slide — Commercial Viability

Four quadrants in one outer box:

- **Top, full width — Target Market & Customer Profiles:** `Primary Market:` / `Secondary Market:` / `Market Size:` with the market-size figure as an underlined orange hyperlink
- **Bottom-left — Investment & Cost Analysis (monthly):** itemised cost lines (compute, load balancer, storage, AI usage) aligned in a monospace-ish column, ending in a bold `Estimated Cost: $X /month | $Y /yr`
- **Bottom-right — Revenue Recovery:** numbered models — Subscription (Free / Premium tiers), Enterprise Licensing, Pro Services
- **Bottom-left lower — Competitive Advantages:** 3 short bullets
- **Bottom-right lower:** the product logo/wordmark

---

## 5. Visual conventions to copy

| Element | Convention |
|---|---|
| Slide titles | Bold, ALL CAPS, left-aligned, large |
| Subtitles | Italic, caps or title case, directly beneath the title, smaller |
| Box borders | ~2pt coloured outline, white fill, square corners |
| Border colour code | blue = gaps/pillars · magenta = related work/technologies · green = proposed solution/evaluation · orange = data/requirements |
| Table headers | Black fill, white bold text |
| Comparison marks | ❌ red cross / ✅ green check |
| Body text | Plain, high contrast, no gradients, no shadows, no animation |
| Footer (group slides) | SLIIT logo left · project ID centre · date + slide number right |
| Footer (member slides) | SLIIT logo left · `IT-number \| Name \| Project-ID` centre · date + slide number right |
| References | 6pt IEEE format in a thin strip at the slide bottom, hyperlinked |

The aesthetic is deliberately plain — information density over design. Don't stylise it.

---

## 6. Mistakes in the reference deck — do not copy these

Worth listing, because they are the kind of thing a panel notices:

1. **Typos in slide titles** — "PERFORMACE METRICS", "SYSTEM OVERVIEW & REQUIRMENTS". Title typos read as carelessness. Proofread titles last.
2. **Inconsistent project ID** — the deck alternates between `25-26J-436` and `25-26H-436` in footers. Pick one, find-and-replace.
3. **Placeholder left in the final deck** — `Developer Cost : $ 0000.00`. If a number isn't known, write "not costed" rather than zeros.
4. **Box colours drift between members** — one member used green for Proposed Solution, another orange. Agree the colour code before anyone builds their block.
5. **Only one member did a Performance Metrics slide.** The other three had no numeric targets at all. If your team can, every member should have one — it is the difference between a plan and a measurable plan.
6. **"First-to-market solution"** as a competitive advantage with nothing backing it. Claims like this invite exactly the question you don't want. Say what you checked, or don't claim it.

---

## 7. Pre-mapped for J26-SE-354

So the next build starts from content, not structure.

**Group slides**

- Title: `AI-DRIVEN CITIZEN-SERVICE ORCHESTRATOR FOR URBAN SRI LANKA` / `J26-SE-354`
- Hero image: citizen queueing at a government office / navigating fragmented portals
- Slide 3 table rows: `Microsoft GraphRAG` · `HIT-Leiden` · `GIC-1919 / manual portals` — shortcomings then approach
- Constraints: dependence on `.gov.lk` availability and structure · LLM extraction may misread page content · modelled vs. real token cost · synthetic-graph benchmark until real graph is ported · escalation guard behaviour at large batch sizes
- System overview: 4 components → shared knowledge graph → orchestrated citizen answer

**Component 2 block (Thilakumara M.P., IT23391390)**

- Divider title: `Automated Graph-Based Knowledge Ontological Extraction Workflow for Dynamic Multi-Agency Service Orchestration`
- **Gaps box:** existing incremental GraphRAG triggers re-summarisation on membership change only [HIT-Leiden] · Microsoft's update path handles append-only, never edits or deletions [issue #741] · evaluation is free-text QA accuracy, requiring an LLM judge · no system combines live acquisition with incremental maintenance
- **Related work box:** `Incremental clustering — HIT-Leiden, Δ-screening, LD-Leiden` · `Incremental GraphRAG — Microsoft graphrag update, EraRAG, TagRAG` · `Hierarchy construction — Core-based Hierarchies (KDD'26)` · `Structured-output RAG — GRAG4PM`
- **Proposed Solution box:** content-change-aware re-summarisation triggering · type-differentiated escalation policy · structured-output fidelity evaluation without an LLM judge · continuous acquisition-to-maintenance pipeline
- **Comparison table rows:** `Handles edits/deletions` · `Re-evaluates existing nodes` · `Content-change triggering` · `Structured-output evaluation` — columns: MS GraphRAG, EraRAG, HIT-Leiden, TagRAG, **This System**
- **Pillars:** Software Engineering → incremental maintenance architecture · NLP → LLM fact extraction and community summarisation · Data Engineering → change-detected acquisition pipeline · SQA → ablation-based evaluation with a reproducibility control
- **Technologies:** `Graph store (SE) → Neo4j` · `Clustering (SE) → leidenalg / igraph` · `Acquisition (WE) → Crawlee / Crawl4AI + SHA-256 + SimHash change detection` · `LLM layer (NLP) → extraction + community report generation` · `Evaluation (SQA) → ARI/NMI vs Leiden reproducibility ceiling, token-cost ablation`
- **Performance Metrics slide — use the measured numbers:** token-cost reduction vs full rebuild (96.6% membership-only / 89.2% with content trigger) · stale facts served over 20 updates (49 → 0) · partition fidelity vs Leiden's own run-to-run ceiling · speedup 7.4×–28.9× widening with graph size. **Flag that token cost is currently modelled, with real-LLM validation as the named next step.**
- **Real world use case:** "A passport fee is revised on a government portal overnight. The system detects the content change, re-extracts the affected facts, re-clusters only the impacted region, and regenerates only the affected community summaries — so the next citizen asking about passport renewal is quoted the new fee, at a fraction of the cost of rebuilding the index."
