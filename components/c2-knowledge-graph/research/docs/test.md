# HelaGuide Research Ablations & Evaluation Benchmark Guide

This document contains the exact commands and explanations to run and demonstrate the research ablations, benchmarks, and evaluation metrics for **Component 2 (Knowledge Graph, Extraction, Review Gate & Traversal)**.

---

## 0. Environment & Setup

All experiment scripts run using the pre-configured Python virtual environment located in the C2 service:

- **Python Executable:**  
  `D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\service\.venv\Scripts\python.exe`
- **Experiments Directory:**  
  `D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\research\experiments`
- **Generated Figures:**  
  `D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\research\docs\figures`

> **Note for PowerShell:** Use `& "<path-to-python>" "<path-to-script>"` syntax to execute.

---

## 1. Ablation 1: Workflow Correctness (SO5 vs. Baseline B3)

### Purpose
Tests whether the Knowledge Graph can generate the correct, legally-mandated sequential workflow for multi-agency citizen journeys, and compares this directly against **Baseline B3 (Flat Lexical Text Search)** to prove why standard search fails.

### Run Command
```powershell
& "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\service\.venv\Scripts\python.exe" "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\research\experiments\workflow_scoring.py"
```

### Expected Output & Score
```text
======================================================================
Graph exact match:    10/10  (100%)   target: 85%
Graph set match:      10/10  (100%)   target: 95%
Baseline set match:   0/10  (0%)   (lexical search; cannot produce order at all)
Baseline exact match: 0/10  (0%)  -- structural: text search returns an unordered set, never a sequence
```

### What to Point Out to Examiners
1. **Transitive Dependency Resolution:** For J1 (*"I need a passport for the first time"*), HelaGuide correctly figures out that a passport requires an NIC, and an NIC requires a birth certificate:  
   `['svc:birth_certificate', 'svc:nic', 'svc:passport']`.
2. **Why Baseline B3 Fails (0/10):** Standard keyword search returns an unordered collection of search hits (e.g., `naval_crew_bond_sticker`, `passport_dispatch_approval`), completely failing to identify the required sequence or inter-agency prerequisites.

---

## 2. Ablation 2: Query-Side Traversal Latency & Scalability (Appendix B.3)

### Purpose
Evaluates how the query-side traversal algorithm (`build_plan` scoped DFS) scales as the graph grows from **100 nodes up to 50,000 nodes**, compared to an unconstrained whole-graph traversal.

### Run Command
```powershell
& "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\service\.venv\Scripts\python.exe" "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\research\experiments\traversal_cost.py"
```

### Expected Output
```text
 N nodes   scoped ms   whole-graph ms   scoped KB   whole-graph KB
     100      0.0027           0.0321        1.12             5.94
     500      0.0027           0.1654        1.12            22.34
    1000      0.0026           0.3310        0.94            44.34
    5000      0.0026           1.5759        0.94           174.98
   10000      0.0024           3.0779        0.94           350.45
   50000      0.0026          24.7532        0.94          3159.19

Scoped traversal cost stays within 1.1x across a 500x range of total graph size.
Whole-graph traversal grows 771.1x over the same range.
saved ...\research\docs\figures\pp2_b3_traversal_cost_figure.png
```

### What to Point Out to Examiners
1. **Bounded Latency:** Scoped DFS only explores ancestor prerequisites of the target service. Even when total graph nodes grow by 500× (from 100 to 50,000 nodes), query latency stays virtually flat (**1.1×** change).
2. **Exponential Penalty of Non-Scoped Traversal:** Whole-graph traversal grows **771×** in time and **531×** in memory overhead over the same range.
3. **Live Database Number:** The real `/v1/plan` endpoint over live Neo4j round-trips was measured at **153 ms** for a 3-step passport plan (`token_cost_and_latency.md`).

---

## 3. Ablation 3: Change Classification Accuracy (SO1)

### Purpose
Tests whether the acquisition fingerprinting engine can reliably distinguish meaningful content changes (e.g. fees, document rules) from structural redesigns and web noise (e.g. date stamps, hit counters).

### Run Command
```powershell
& "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\service\.venv\Scripts\python.exe" "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\research\experiments\classification_scoring.py"
```

### Expected Output
```text
9 labelled cases (1 real, 8 constructed)

R1   [real       ] expected=STRUCTURE_CHANGED got=STRUCTURE_CHANGED OK
C1   [constructed] expected=UNCHANGED         got=UNCHANGED         OK
C2   [constructed] expected=CONTENT_CHANGED   got=CONTENT_CHANGED   OK
C3   [constructed] expected=STRUCTURE_CHANGED got=STRUCTURE_CHANGED OK
C4   [constructed] expected=UNCHANGED         got=UNCHANGED         OK
C5   [constructed] expected=NEW               got=NEW               OK
C6   [constructed] expected=CONTENT_CHANGED   got=CONTENT_CHANGED   OK
C7   [constructed] expected=UNCHANGED         got=UNCHANGED         OK
C8   [constructed] expected=CONTENT_CHANGED   got=CONTENT_CHANGED   OK

======================================================================
Accuracy: 9/9  (100%)   target: 95%
False positives on noise-only edits: 0   target: 0
```

### What to Point Out to Examiners
1. **Zero Tokens on Noise (NFR4):** Case C4 tests a page where only a live visitor counter changed. HelaGuide correctly classifies it as `UNCHANGED`, burning **0 LLM tokens**.
2. **Real Diff (R1):** Case R1 is a genuine observed historical crawl diff from `immigration.gov.lk` between 11 Oct and 12 Oct 2026.

---

## 4. Regenerating Research Figures & Charts

To regenerate the high-resolution charts used in the report and slides:

### Generate Overall PP2 Results Dashboard Figure
```powershell
& "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\service\.venv\Scripts\python.exe" "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\research\experiments\make_results_figure.py"
```
*Output File:* `components/c2-knowledge-graph/research/docs/figures/pp2_results_figure.png`

### Generate Token Cost & Update Latency Figure
```powershell
& "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\service\.venv\Scripts\python.exe" "D:\SLIIT\Research\HelaGuide\components\c2-knowledge-graph\research\experiments\make_token_latency_figure.py"
```
*Output File:* `components/c2-knowledge-graph/research/docs/figures/pp2_token_latency_figure.png`

---

## 5. Summary Cheat Sheet for Examiners

| Specific Objective / Metric | Target | HelaGuide Measured Result | Baseline / Comparison |
|---|:---:|:---:|---|
| **SO1: Change Classification** | 95% | **100% (9/9)** | 0 false positives on noisy counters |
| **SO2: Fact Extraction Precision** | 90% | **99.2% (123/124 facts)** | Hand-verified against source HTML |
| **SO4: Entity Resolution** | 95% | **100% (3/3 agencies, TVRS merge)** | Canonical resolution without fuzzy drift |
| **SO5: Workflow Correctness** | 85% exact / 95% set | **100% exact (10/10) & 100% set** | Flat search baseline: **0% (0/10)** |
| **Metric 1: Token Cost per Update** | <4,500 / page | **0 tokens on unchanged (57% saved)** | 3,728 tokens average when changed |
| **Metric 2: Update Latency** | — | **22.8 ms** unchanged vs. **11.8 s** changed | **~500× faster** on unchanged pages |
| **Metric 6: Traversal Scaling** | Bound growth | **1.1× growth** from 100 to 50k nodes | Whole-graph traversal blows out **771×** |
