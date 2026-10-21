"""
Panel-ready figures from committed result files only (no training, no models). Run from research/:
    python experiments/make_figures.py                     # -> results/figures/
    python experiments/make_figures.py --out-dir <dir>

Each figure prints the file it reads. A figure whose source file (or field) is missing is skipped with a message.
  lid_comparison.png      language ID on the fresh set: XLM-R (3 seeds) vs fastText vs heuristic
                          (results/xlmr_results_seed{42,1,2}.json, Observation 7)
  dst_ablation.png        JGA by tracker setting, gold intent (results/dst_results.json, Observation 9)
  token_tax.png           cl100k vs XLM-R tokens per turn by language bucket (context_v2_final/context_jga_results.json)
  latency_vs_tokens.png   4-thread CPU latency per strategy vs tokens per turn (context_v2_final/deployment_benchmark.csv)
  memory_vs_budget.png    memory per worker vs the budget (context_v2_final/deployment_benchmark.json)
  seed_spread.png         held-out JGA per strategy over seeds, flagged runs marked (needs per-seed JGA in
                          context_jga_results.json and context_v2_final/convergence_check.csv)
  h3_calibration.png      false-positive rate of each H3 method on null data (context_v2_final/h3_calibration.csv)
Style: large fonts for a projector, colour-blind-safe palette (the validated reference categorical order), titles
that state what the chart shows.
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RESULTS = "results"
FINAL = os.path.join(RESULTS, "context_v2_final")
OUT = os.path.join(RESULTS, "figures")

# colour-blind-safe categorical order (blue, orange, aqua validate all-pairs) and an ordinal blue ramp
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]          # steps 250 / 400 / 550 / 700
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e5e5e5", "#fcfcfb"
STRATEGIES = ["current_only", "window_2", "window_3", "keyword_summary", "structured_state", "summary", "full_history"]
ORACLE = {"keyword_summary", "structured_state"}
LABEL = {s: s.replace("_", " ") + (" *" if s in ORACLE else "") for s in STRATEGIES}
ORACLE_NOTE = "* oracle: reads gold tags at test time (upper bound)"


def style(plt):
    plt.rcParams.update({
        "font.size": 15, "axes.titlesize": 18, "axes.labelsize": 15, "xtick.labelsize": 13, "ytick.labelsize": 13,
        "legend.fontsize": 13, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#888",
        "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.8, "axes.axisbelow": True, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "axes.titlelocation": "left", "axes.titleweight": "bold"})


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_csv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def title(ax, text, width=64):
    """Title that states what the chart shows, wrapped so it fits on a projector slide."""
    import textwrap
    ax.set_title(chr(10).join(textwrap.wrap(text, width)), fontsize=17, loc="left")


def need(*paths):
    """Returns the first missing path, or None."""
    return next((p for p in paths if not os.path.exists(p)), None)


def bar_labels(ax, bars, fmt="{:.2f}", pad=0.01, size=12):
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h + pad, fmt.format(h), ha="center", va="bottom", fontsize=size, color=INK)


def save(fig, out_dir, name):
    path = os.path.join(out_dir, name)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    return path


# ------------------------------------------------------------------ the figures
def lid_comparison(plt, out_dir):
    srcs = [os.path.join(RESULTS, f"xlmr_results_seed{s}.json") for s in (42, 1, 2)]
    if need(*srcs):
        return None, srcs, f"missing {need(*srcs)}"
    import numpy as np
    runs = [read_json(p)["fresh_test"] for p in srcs]
    groups = [("Overall (SI/EN words)", lambda f, s: f["language_id_si_en"][s]["ALL"]["acc"]),
              ("Singlish (romanised, mixed)", lambda f, s: f["language_id_si_en"][s]["mixed / romanized"]["acc"]),
              ("At code-switch points", lambda f, s: f["lang_switch_points"][s]["at_switch"]["acc"])]
    systems = [("XLM-R (3 seeds)", "XLM-R", BLUE), ("fastText", "fastText", ORANGE), ("Heuristic", "heuristic", AQUA)]
    fig, ax = plt.subplots(figsize=(12, 6.5))
    w = 0.26
    for j, (label, key, colour) in enumerate(systems):
        vals = [[get(f, key) for f in runs] for _, get in groups]
        means, sds = [np.mean(v) for v in vals], [np.std(v, ddof=1) for v in vals]
        xs = [i + (j - 1) * w for i in range(len(groups))]
        bars = ax.bar(xs, means, w * 0.92, color=colour, label=label,
                      yerr=sds if key == "XLM-R" else None, capsize=4, error_kw={"ecolor": INK2, "lw": 1.2})
        bar_labels(ax, bars)
    n = runs[0]["language_id_si_en"]["XLM-R"]
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([f"{g}\n(n={k})" for (g, _), k in zip(groups, (n["ALL"]["n"], n["mixed / romanized"]["n"],
                                                                         runs[0]["lang_switch_points"]["XLM-R"]["at_switch"]["n"]))])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Word-level accuracy (fresh test set)")
    title(ax, "XLM-R identifies Sinhala vs English per word far better than fastText, most of all in Singlish")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    ax.grid(axis="x", visible=False)
    return save(fig, out_dir, "lid_comparison.png"), srcs, None


def dst_ablation(plt, out_dir):
    src = os.path.join(RESULTS, "dst_results.json")
    if need(src):
        return None, [src], f"missing {src}"
    d = read_json(src)
    sets = [("Gold (dev set\nfor the rules)", d["dst_gold"]["oracle"]), ("Synthetic\n(held out, 977 turns)", d["dst_silver"]["oracle"])]
    if "dst_fresh" in d:
        sets.append(("Fresh\n(held out, 50 turns)", d["dst_fresh"]["oracle"]))
    settings = [("1_no_memory", "No memory"), ("2_carryover", "+ carry slots"), ("3_+bot_question", "+ bot question"),
                ("4_full", "Full tracker")]
    fig, ax = plt.subplots(figsize=(12, 6.5))
    w = 0.2
    for j, ((key, label), colour) in enumerate(zip(settings, RAMP)):
        xs = [i + (j - 1.5) * w for i in range(len(sets))]
        bars = ax.bar(xs, [t[key]["jga"] for _, t in sets], w * 0.92, color=colour, label=label)
        bar_labels(ax, bars)
    ax.set_xticks(range(len(sets)))
    ax.set_xticklabels([s for s, _ in sets])
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Joint goal accuracy (gold intent)")
    title(ax, "Remembering slots across turns gives the biggest gain in dialogue-state accuracy")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=4)
    ax.grid(axis="x", visible=False)
    return save(fig, out_dir, "dst_ablation.png"), [src], None


def token_tax(plt, out_dir):
    src = os.path.join(FINAL, "context_jga_results.json")
    if need(src):
        return None, [src], f"missing {src}"
    rows = {r["bucket"]: r for r in read_json(src).get("token_ratio", [])
            if r["test_set"] == "heldout" and r["strategy"] == "current_only"}
    buckets = [b for b in ("pure_si", "pure_en", "mixed") if b in rows]
    if not buckets:
        return None, [src], "no token_ratio rows for the held-out set in " + src
    names = {"pure_si": "Pure Sinhala", "pure_en": "Pure English", "mixed": "Code-mixed"}
    fig, ax = plt.subplots(figsize=(11, 6.5))
    w = 0.36
    xs = range(len(buckets))
    b1 = ax.bar([x - w / 2 for x in xs], [rows[b]["xlmr_text_tokens"] for b in buckets], w * 0.92, color=BLUE,
                label="XLM-R tokenizer")
    b2 = ax.bar([x + w / 2 for x in xs], [rows[b]["cl100k_tokens"] for b in buckets], w * 0.92, color=ORANGE,
                label="cl100k (GPT-4-class LLM tokenizer)")
    bar_labels(ax, b1, "{:.1f}", 0.3)
    bar_labels(ax, b2, "{:.1f}", 0.3)
    top = max(rows[b]["cl100k_tokens"] for b in buckets)
    for x, b in zip(xs, buckets):
        ax.text(x, top * 1.18, f"{rows[b]['ratio']:.2f}×", ha="center", fontsize=17, fontweight="bold", color=INK)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{names[b]}\n(n={rows[b]['n_turns']} turns)" for b in buckets])
    ax.set_ylim(0, top * 1.35)
    ax.set_ylabel("Tokens per message (held-out turns)")
    title(ax, "An LLM tokenizer needs about 3.5× more tokens for Sinhala; English costs about the same")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
    ax.grid(axis="x", visible=False)
    return save(fig, out_dir, "token_tax.png"), [src], None


def latency_vs_tokens(plt, out_dir):
    src, meta_src = os.path.join(FINAL, "deployment_benchmark.csv"), os.path.join(FINAL, "deployment_benchmark.json")
    if need(src):
        return None, [src], f"missing {src}"
    rows = read_csv(src)
    budget = read_json(meta_src)["budgets"]["latency_p95_ms"] if os.path.exists(meta_src) else 500.0
    pts = {r["strategy"]: r for r in rows if r["model"] == "xlmr" and r["threads"] == "4"}
    if not pts:
        return None, [src], "no 4-thread XLM-R rows in " + src
    eng = next((r for r in rows if r["model"] == "c1_engine" and r["threads"] == "4"), None)
    fig, ax = plt.subplots(figsize=(12, 6.5))
    sts = [s for s in STRATEGIES if s in pts]
    x = [float(pts[s]["tokens_per_turn"]) for s in sts]
    ax.plot(x, [float(pts[s]["latency_p95_ms"]) for s in sts], "o", ms=11, color=ORANGE, label="intent model, p95",
            markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.plot(x, [float(pts[s]["latency_p50_ms"]) for s in sts], "o", ms=11, color=BLUE, label="intent model, p50",
            markeredgecolor=SURFACE, markeredgewidth=1.5)
    last, level = None, 0
    for s, xi in sorted(zip(sts, x), key=lambda t: t[1]):       # stagger labels of strategies with similar inputs
        level = level + 1 if last is not None and xi - last < 3 else 0
        ax.annotate(LABEL[s], (xi, float(pts[s]["latency_p95_ms"])), textcoords="offset points",
                    xytext=(-4, 12 + 26 * level), fontsize=11, color=INK2, ha="left",
                    arrowprops={"arrowstyle": "-", "color": "#aaa", "lw": 0.8} if level else None)
        last = xi
    if eng:
        for k, mk in (("latency_p50_ms", "D"), ("latency_p95_ms", "s")):
            ax.plot([float(eng["tokens_per_turn"])], [float(eng[k])], mk, ms=12, color=AQUA, markeredgecolor=SURFACE,
                    label=f"deployed engine (window_3, full pipeline), {k.split('_')[1]}")
    ax.axhline(budget, color=INK2, lw=1.5, ls="--")
    ax.text(min(x), budget * 1.03, f"budget: p95 ≤ {budget:g} ms per turn", fontsize=13, color=INK2)
    ax.set_ylim(0, budget * 1.15)
    ax.set_xlabel("Input tokens per turn (XLM-R tokenizer)")
    ax.set_ylabel("Latency per turn on CPU, 4 threads (ms)")
    title(ax, "At 4 CPU threads, every context strategy and the full pipeline stay well under the latency budget")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, fontsize=12)
    fig.text(0.01, 0.01, ORACLE_NOTE + "." + chr(10) + "The budget is defined at 1 thread; the 1-thread timings on "
                         "this machine are unreliable (see summary.md), so the 4-thread measurements are shown.", fontsize=11,
             color=INK2)
    return save(fig, out_dir, "latency_vs_tokens.png"), [src, meta_src], None


def memory_vs_budget(plt, out_dir):
    src = os.path.join(FINAL, "deployment_benchmark.json")
    if need(src):
        return None, [src], f"missing {src}"
    meta = read_json(src)
    budget = meta["budgets"]["peak_memory_mb"]
    bars = [("Intent model only\n(1 XLM-R)", meta.get("memory_after_xlmr_load_mb"), BLUE),
            ("Deployed engine\n(3 XLM-R: language ID,\nNER, intent)", meta.get("engine_memory_after_load_mb"), ORANGE)]
    bars = [b for b in bars if b[1] is not None]
    fig, ax = plt.subplots(figsize=(10, 6.5))
    rects = ax.bar(range(len(bars)), [b[1] for b in bars], 0.55, color=[b[2] for b in bars])
    for r in rects:                                   # inside the bar, clear of the budget line
        ax.text(r.get_x() + r.get_width() / 2, r.get_height() - 120, f"{r.get_height():.0f} MB", ha="center",
                va="top", fontsize=16, fontweight="bold", color="white")
    ax.axhline(budget, color=INK2, lw=1.5, ls="--")
    ax.text(len(bars) - 0.62, budget + 70, f"budget: {budget:g} MB per worker", fontsize=13, color=INK2, ha="right")
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([b[0] for b in bars])
    ax.set_ylim(0, max(budget, max(b[1] for b in bars)) * 1.2)
    ax.set_ylabel("Peak memory per worker process (MB)")
    title(ax, "Three separate XLM-R models put the deployed engine over the memory budget", 56)
    ax.grid(axis="x", visible=False)
    fig.text(0.01, 0.01, "Process peak (Windows working set), including the Python and PyTorch runtime; "
                         "a per-model split was not measured.", fontsize=11, color=INK2)
    return save(fig, out_dir, "memory_vs_budget.png"), [src], None


def seed_spread(plt, out_dir):
    src, conv_src = os.path.join(FINAL, "context_jga_results.json"), os.path.join(FINAL, "convergence_check.csv")
    if need(src, conv_src):
        return None, [src, conv_src], f"missing {need(src, conv_src)}"
    metrics = read_json(src)["metrics"]
    per = {k: m.get("jga_per_seed") for k, m in metrics.items() if k.endswith("/heldout")}
    if not any(per.values()):
        return None, [src, conv_src], ("no per-seed JGA (`jga_per_seed`) in " + src +
                                       "; context_eval.py stores only mean, std and median")
    flagged = {(r["model"], r["strategy"], int(r["seed"])) for r in read_csv(conv_src) if r["flagged"] == "True"}
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), sharey=True)
    for ax, model, colour, title in ((axes[0], "xlmr", BLUE, "XLM-R"), (axes[1], "tfidf", ORANGE, "TF-IDF + LogReg")):
        sts = [s for s in STRATEGIES if per.get(f"{model}/{s}/heldout")]
        data = [[v for _, v in sorted(per[f"{model}/{s}/heldout"].items())] for s in sts]
        bp = ax.boxplot(data, positions=range(len(sts)), widths=0.55, patch_artist=True, showfliers=False)
        for b in bp["boxes"]:
            b.set(facecolor=colour, alpha=0.35, edgecolor=colour)
        for k in ("medians", "whiskers", "caps"):
            for line in bp[k]:
                line.set(color=colour, lw=1.6)
        for i, s in enumerate(sts):
            for seed, v in sorted(per[f"{model}/{s}/heldout"].items()):
                bad = (model, s, int(seed)) in flagged
                ax.plot(i, v, "X" if bad else "o", ms=13 if bad else 7, color=INK if bad else colour,
                        markeredgecolor=SURFACE, zorder=3, label="flagged (did not converge)" if bad else None)
        ax.set_xticks(range(len(sts)))
        ax.set_xticklabels([LABEL[s] for s in sts], rotation=30, ha="right")
        ax.set_title(title, fontsize=16)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("JGA on held-out turns (one point per seed)")
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        axes[0].legend(handles[:1], labels[:1], frameon=False, loc="lower right")
    fig.suptitle("Seed-to-seed spread: two XLM-R runs failed to converge; TF-IDF is stable", x=0.01, ha="left",
                 fontsize=18, fontweight="bold")
    fig.text(0.01, 0.01, ORACLE_NOTE, fontsize=11, color=INK2)
    return save(fig, out_dir, "seed_spread.png"), [src, conv_src], None


def h3_calibration(plt, out_dir):
    src = os.path.join(FINAL, "h3_calibration.csv")
    if need(src):
        return None, [src], f"missing {src}"
    rows = [r for r in read_csv(src) if r["test_set"] == "heldout"]
    methods = [("permutation", "Permutation test\n(headline)"), ("stratified", "Stratified\nbootstrap"),
               ("all_turns", "All turns\nbootstrap"), ("follow_up", "Follow-up only\nbootstrap*")]
    get = {(r["method"], r["metric"]): float(r["says_supported"]) for r in rows}
    fig, ax = plt.subplots(figsize=(12, 6.5))
    w = 0.36
    for j, (metric, label, colour) in enumerate((("intent_acc", "intent accuracy (exact null)", BLUE),
                                                 ("jga", "JGA (approximate null)", ORANGE))):
        xs = [i + (j - 0.5) * w for i in range(len(methods))]
        bars = ax.bar(xs, [100 * get.get((m, metric), 0) for m, _ in methods], w * 0.92, color=colour, label=label)
        bar_labels(ax, bars, "{:.1f}%", 1)
    ax.axhline(5, color=INK2, lw=1.5, ls="--")
    ax.text(len(methods) - 0.6, 6.2, "5% target", fontsize=13, color=INK2, ha="right")
    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels([l for _, l in methods])
    ax.set_ylim(0, 85)
    ax.set_ylabel("Says 'supported' with no real effect (%)")
    n = next((r["families"] for r in rows), "?")
    title(ax, "Only the permutation test keeps false positives near 5%")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="x", visible=False)
    fig.text(0.01, 0.01, f"200 null data sets, {n} model × data-set families. * follow-up only never says "
                         "'supported': its high-CMI bucket has < 30 turns.", fontsize=11, color=INK2)
    return save(fig, out_dir, "h3_calibration.png"), [src], None


FIGURES = [lid_comparison, dst_ablation, token_tax, latency_vs_tokens, memory_vs_budget, seed_spread, h3_calibration]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", default=OUT)
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    style(plt)
    made, skipped = [], []
    for fn in FIGURES:
        path, srcs, why = fn(plt, a.out_dir)
        plt.close("all")
        if path:
            made.append(path)
            print(f"{os.path.basename(path):24s} <- {', '.join(srcs)}")
        else:
            skipped.append((fn.__name__, why))
            print(f"{fn.__name__ + '.png':24s} SKIPPED: {why}")
    print(f"\n{len(made)} figures in {a.out_dir}" + (f"; {len(skipped)} skipped" if skipped else ""))
    return made, skipped


if __name__ == "__main__":
    main()
