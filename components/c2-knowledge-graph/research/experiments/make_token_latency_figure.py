"""Regenerates research/docs/figures/pp2_token_latency_figure.png from the real numbers
in research/docs/token_cost_and_latency.md. Copied in by hand -- update here if a re-run
of the timing changes a result.

    python research/experiments/make_token_latency_figure.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({"font.size": 10.5, "axes.titlesize": 11.5})

fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))

# ---- panel 1: update latency, unchanged vs changed (log scale) ----
ax = axes[0]
labels = ["Unchanged page\n(no LLM call)", "Changed page\n(LLM extraction)"]
values = [22.8, 11800]
colors = ["#1d9e75", "#378add"]
bars = ax.bar(labels, values, color=colors, width=0.5)
ax.set_yscale("log")
ax.set_ylabel("wall-clock time (ms, log scale)")
ax.set_title("Update latency: unchanged vs changed\nreal timings, n=20 and n=128")
for b, v in zip(bars, values):
    label = f"{v:.1f} ms" if v < 1000 else f"{v/1000:.1f} s"
    ax.text(b.get_x() + b.get_width() / 2, v * 1.3, label, ha="center", fontsize=9.5)
ax.text(0.5, 0.92, "~500x apart", transform=ax.transAxes, ha="center", fontsize=9, color="#52514e")

# ---- panel 2: token cost, real repeat-crawl event ----
ax = axes[1]
labels = ["If every previously-seen\npage were re-extracted", "What this component\nactually spent"]
values = [134 * 3728 / 1000, 0]
colors = ["#b4b2a9", "#1d9e75"]
bars = ax.bar(labels, values, color=colors, width=0.5)
ax.set_ylabel("tokens (thousands)")
ax.set_title("Token cost on one real repeat-crawl\n134 of 236 pages (57%) were unchanged")
for b, v in zip(bars, values):
    ax.text(b.get_x() + b.get_width() / 2, v + 10, f"{v:.0f}k" if v else "0", ha="center", fontsize=9.5)

fig.suptitle("Real measurements from the project's actual logs — 18 October 2026, not modelled", fontsize=10, y=1.04)
fig.tight_layout()
out = Path(__file__).resolve().parents[1] / "docs" / "figures" / "pp2_token_latency_figure.png"
fig.savefig(out, dpi=200, bbox_inches="tight")
print("saved", out)
