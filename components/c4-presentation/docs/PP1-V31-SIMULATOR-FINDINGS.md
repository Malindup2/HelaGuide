# Why the 3.0 study could not show a learned advantage, and what the 3.1 study changes

Synthetic findings only. Nothing here is a real-citizen result, expert validation or measured comprehension. The 3.0 experiment, simulator (`synthetic.py`) and results (`PP1-SYNTHETIC-RESULTS.json`) are untouched.

## What the 3.0 results were
Held-out simulated expected reward: standard/minimal 0.7062, simulator oracle 0.7135, Shared LinTS 525 0.5374, random feasible 0.5077.

## What I measured on the 3.0 simulator before writing the 3.1 one
I re-scored 400 held-out-style 3.0 cases against every feasible configuration (read-only; `analyse30` run on the existing `synthetic.py` and its seven registered graphs).

| Finding | Number |
|---|---|
| Oracle versus standard (the most any selector could add) | 0.7140 versus 0.7021, a gap of 0.012 |
| Share of cases where standard is already the best feasible configuration | 55% |
| Minimal support equals standard (both give no scaffolds) | 0.7021 |
| Maximal support | 0.3812 |
| Largest oracle-minus-standard gap for any procedure | 0.029 (practice); under 0.01 for the three official procedures and linear |
| Families where the best support is none at all | S9 and S10 (0.00 and 0.03 scaffolds) |

Reading: the potential advantage of personalization in the 3.0 world was about one percentage point. The learner started from near-random selection among up to 96 configurations, so to beat standard it had to learn to pick the standard-like corner and ignore 95 others, from roughly 600 binary rewards in 525 dimensions. It improved from its start (0.51 to 0.54) but could not close a gap that large relative to the ceiling.

## Why the ceiling was so low (causes found)
1. **The seven registered graphs are all small.** Normalised structural demand is between 0 and 0.56 (two to five steps, at most one branch group, at most one parallel group). The 3.0 demand vector is `(1-confidence)*(0.35+length)` and similar, which stays low, so "no scaffold" fits almost every case.
2. **Support burden dominates through a squared mismatch around a low target.** With a demand near 0.3 and a support of 0 or 1, supporting more is penalised about as much as supporting less. Over-support (a map for a three-step task) is punished, but under-support is rarely punished hard because demand is small.
3. **Only four fictional graphs were used for training and one family of structures per scenario.** There was no long procedure, no multi-level dependency chain, no multi-stage procedure with real phases, and no high-information procedure where Detailed or Disclosure could matter.
4. **Three of the four held-out reward regimes (null, burden shift, preference shift) favour doing less**, which lowers the value of any learning even further.
5. **Official procedures are only fallback probes** (4 feasible configurations each), so they add cases where all selectors tie.

What the data do NOT say: that personalization cannot work, or that the 3.0 learner was defective. They say the 3.0 hypothetical world left almost nothing to gain.

## What 3.1 changes (all separately versioned, none edits 3.0)
- `synthetic31.py` (`c4-synthetic-response-pp1-1.1`): every scaffold has an explicit **need** between 0 and 1 for the citizen and procedure; under-support and over-support are penalised by separate, documented weights. Familiar, confident citizens on short procedures need almost nothing; unfamiliar or low-confidence citizens on long, branching, dependent or multi-phase procedures need a lot. Neither direction is favoured by construction.
- Five reward assumptions: `balanced` (primary), `under_heavy`, `over_heavy`, `preference_led`, `low_need` (a 3.0-like world where most citizens need little) and `flat` (no effect). All checkpoints are evaluated under all of them, and matched-assumption runs test whether the learner can adapt to a different world.
- Eight fictional **study procedures** (`procedures31.py`) with short, long, branching, multi-level, parallel-with-join, multi-phase, information-heavy and mixed structure. Templated wording, never shown to citizens, not registered in the application.
- 22 scenario families: S1 to S10 retained, N1 to N12 new, including counterexamples and no-benefit cases.
- Separate **training, development and final test** procedures and contexts. The final test is never used for any choice.
- Baselines: standard, minimal, maximal, random feasible, a hindsight **best constant** configuration, smaller encoders (416, 451, 516) and the simulator oracle.

## Assumption warning
The need formulas are author-defined and were set before any 3.1 training result was seen. They were not adjusted to favour the learner. Because the `balanced` world contains many high-need citizens, standard guidance performs poorly in it by construction; the `low_need` world exists to show the opposite situation, and the report states how conclusions change between them.
