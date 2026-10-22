"""Regenerates research/docs/figures/pp2_results_figure.png from the real numbers in
research/docs/so1_classification.md, so2_extraction.md, so4_entity_resolution.md and
so5_workflow.md. The numbers are copied in by hand, not read live from those scores --
update them here if a re-run of the scoring scripts changes a result.

    python research/experiments/make_results_figure.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({"font.size": 10.5, "axes.titlesize": 11.5})

fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))

# ---- panel 1: SO5 workflow correctness, graph vs text-search baseline ----
ax = axes[0]
labels = ["Exact\nmatch", "Set\nmatch"]
x = range(len(labels))
w = 0.32
graph = [100, 100]
baseline = [0, 0]
target = [85, 95]
ax.bar([i - w / 2 for i in x], graph, width=w, label="graph (this component)", color="#1d9e75")
ax.bar([i + w / 2 for i in x], baseline, width=w, label="lexical text search", color="#b4b2a9")
ax.scatter(x, target, marker="_", s=900, linewidths=2.2, color="#993c1d", label="proposal target", zorder=5)
ax.set_xticks(list(x))
ax.set_xticklabels(labels)
ax.set_ylim(0, 100)
ax.set_ylabel("% of 10 journeys")
ax.set_title("Workflow correctness (SO5)\n10 real journeys, no LLM judge")
ax.legend(fontsize=8, loc="upper right")

# ---- panel 2: five objectives, measured vs target ----
ax = axes[1]
labels = ["SO1\nchange\nclass.", "SO2\nextraction\nprecision", "SO3\nstaleness\ncaught", "SO4\nentity\nresolution", "SO5\nexact\nmatch"]
measured = [100, 99.2, 100, 100, 100]  # SO3: 0/20 stale with the trigger = 100% caught
target = [95, 90, 100, 95, 85]
x = range(len(labels))
w = 0.32
ax.bar([i - w / 2 for i in x], measured, width=w, label="measured", color="#378add")
ax.bar([i + w / 2 for i in x], target, width=w, label="target", color="#b4b2a9")
ax.set_xticks(list(x))
ax.set_xticklabels(labels, fontsize=9)
ax.set_ylim(0, 110)
ax.set_ylabel("%")
ax.set_title("Specific objectives measured\nagainst the real graph, 18 Oct 2026")
ax.legend(fontsize=8, loc="lower right")

# ---- panel 3: where the facts come from, and what's deferred ----
ax = axes[2]
cats = ["SO1", "SO2\n(precision)", "SO2\n(recall)", "SO4\n(agency)", "SO4\n(service)", "SO5", "SO3"]
status = [2, 2, 1, 2, 2, 2, 2]  # 2=measured & passes, 1=partial, 0=gap found, -1=deferred
colors = {2: "#1d9e75", 1: "#ef9f27", 0: "#d85a30", -1: "#888780"}
bar_colors = [colors[s] for s in status]
ax.barh(range(len(cats)), [1] * len(cats), color=bar_colors)
ax.set_yticks(range(len(cats)))
ax.set_yticklabels(cats, fontsize=9)
ax.set_xticks([])
ax.invert_yaxis()
ax.set_title("Coverage at a glance\nacross all five objectives")
from matplotlib.patches import Patch
handles = [
    Patch(color="#1d9e75", label="measured, passes target"),
    Patch(color="#ef9f27", label="partially measured"),
    Patch(color="#d85a30", label="measured, gap found"),
    Patch(color="#888780", label="deferred (not in PP2 scope)"),
]
ax.legend(handles=handles, fontsize=7.3, loc="lower right", framealpha=0.95)

fig.suptitle("Real measurements against the live graph (2,532 nodes, incl. 142 real SO3 communities), not synthetic data — 19 October 2026", fontsize=10, y=1.03)
fig.tight_layout()
out = Path(__file__).resolve().parents[1] / "docs" / "figures" / "pp2_results_figure.png"
fig.savefig(out, dpi=200, bbox_inches="tight")
print("saved", out)
