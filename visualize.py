"""
Generates 4 PNG charts from a leads CSV.

Usage:
  python visualize.py                          # uses most recent CSV in output/
  python visualize.py output/leads_xyz.csv     # specific file

Outputs PNGs alongside the CSV in output/.
Requires: pip install matplotlib pandas
"""

import os
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

plt.rcParams.update({
    "font.family":        "DejaVu Sans",
    "font.size":          12,
    "axes.titlesize":     14,
    "axes.titleweight":   "bold",
    "axes.titlepad":      14,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.spines.left":   False,
    "axes.spines.bottom": True,
    "axes.grid":          True,
    "axes.grid.axis":     "x",
    "grid.color":         "#e0e0e0",
    "figure.facecolor":   "white",
    "axes.facecolor":     "white",
    "xtick.bottom":       False,
    "ytick.left":         False,
})

_PALETTE = {
    "success":        "#2ecc71",
    "llm_failed":     "#e74c3c",
    "no_website":     "#f39c12",
    "crawl_failed":   "#e67e22",
    "high":           "#2ecc71",
    "medium":         "#f39c12",
    "low":            "#e74c3c",
    "owner_personal": "#2ecc71",
    "owner_likely":   "#3498db",
    "generic":        "#9b59b6",
    "other":          "#1abc9c",
    "no_email":       "#bdc3c7",
    "found":          "#2ecc71",
    "not_found":      "#e74c3c",
}


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["owner_name"] = df["owner_name"].where(
        df["owner_name"].notna() & (df["owner_name"].str.strip() != ""), other=None
    )
    return df


def _bar_label(ax, bars, total: int) -> None:
    for bar in bars:
        v = bar.get_width()
        pct = v / total * 100
        ax.text(
            v + total * 0.008,
            bar.get_y() + bar.get_height() / 2,
            f"{int(v):,}  ({pct:.1f}%)",
            va="center", ha="left", fontsize=11, color="#333",
        )


def _style_ax(ax, title: str, xlabel: str = "Leads") -> None:
    ax.set_title(title, pad=12)
    ax.set_xlabel(xlabel)
    ax.invert_yaxis()
    ax.spines["bottom"].set_color("#cccccc")
    ax.tick_params(axis="both", length=0)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))


# ── Chart 1: Pipeline Status ──────────────────────────────────────────────────
def _draw_pipeline_status(df: pd.DataFrame, ax) -> None:
    order  = ["success", "llm_failed", "no_website", "crawl_failed"]
    labels = ["Success", "LLM Failed", "No Website", "Crawl Failed"]
    total  = len(df)
    counts = [df["status"].value_counts().get(s, 0) for s in order]
    colors = [_PALETTE[s] for s in order]

    bars = ax.barh(labels, counts, color=colors, height=0.5, edgecolor="none")
    _bar_label(ax, bars, total)
    ax.set_xlim(0, max(counts) * 1.38)
    _style_ax(ax, f"1 — Pipeline Status  ({total:,} total leads)")


# ── Chart 2: Owner Name Extraction ───────────────────────────────────────────
def _draw_owner_name(df: pd.DataFrame, ax) -> None:
    total     = len(df)
    n_found   = df["owner_name"].notna().sum()
    n_missing = total - n_found

    labels = ["Owner Found", "Not Found"]
    counts = [n_found, n_missing]
    colors = [_PALETTE["found"], _PALETTE["not_found"]]

    bars = ax.barh(labels, counts, color=colors, height=0.5, edgecolor="none")
    _bar_label(ax, bars, total)
    ax.set_xlim(0, max(counts) * 1.38)
    _style_ax(ax, f"2 — Owner Name Extraction  ({total:,} total leads)")


# ── Chart 3: Owner Confidence (success leads only) ───────────────────────────
def _draw_confidence(df: pd.DataFrame, ax) -> None:
    success_df = df[df["status"] == "success"]
    n_success  = len(success_df)
    order      = ["high", "medium", "low"]
    labels     = ["High", "Medium", "Low"]
    counts     = [success_df["llm_confidence"].str.lower().value_counts().get(c, 0) for c in order]
    colors     = [_PALETTE[c] for c in order]

    bars = ax.barh(labels, counts, color=colors, height=0.5, edgecolor="none")
    _bar_label(ax, bars, n_success)
    ax.set_xlim(0, max(counts) * 1.38)
    _style_ax(ax, f"3 — Owner Confidence  ({n_success:,} successful leads)")


# ── Chart 4: Email Coverage ───────────────────────────────────────────────────
def _draw_email_coverage(df: pd.DataFrame, ax) -> None:
    total   = len(df)
    vc      = df["recommended_email_type"].value_counts(dropna=False)
    n_personal = vc.get("owner_personal", 0)
    n_likely   = vc.get("owner_likely",   0)
    n_generic  = vc.get("generic",        0)
    n_other    = vc.get("other",          0)
    n_no_email = int(df["recommended_email_type"].isna().sum())

    labels = ["Owner Personal", "Owner Likely", "Generic Contact", "Other", "No Email"]
    counts = [n_personal, n_likely, n_generic, n_other, n_no_email]
    colors = [_PALETTE["owner_personal"], _PALETTE["owner_likely"], _PALETTE["generic"], _PALETTE["other"], _PALETTE["no_email"]]

    bars = ax.barh(labels, counts, color=colors, height=0.5, edgecolor="none")
    _bar_label(ax, bars, total)
    ax.set_xlim(0, max(counts) * 1.38)
    _style_ax(ax, f"4 — Email Coverage  ({total:,} total leads)")


# ── Chart 5: Pipeline Effectiveness (excl. no_website) ───────────────────────
def _draw_pipeline_effectiveness(df: pd.DataFrame, ax) -> None:
    actionable = df[df["status"] != "no_website"]
    total      = len(actionable)
    order      = ["success", "llm_failed", "crawl_failed"]
    labels     = ["Success", "LLM Failed", "Crawl Failed"]
    counts     = [actionable["status"].value_counts().get(s, 0) for s in order]
    colors     = [_PALETTE[s] for s in order]

    bars = ax.barh(labels, counts, color=colors, height=0.5, edgecolor="none")
    _bar_label(ax, bars, total)
    ax.set_xlim(0, max(counts) * 1.38)
    _style_ax(ax, f"5 — Pipeline Effectiveness  ({total:,} actionable leads, excl. no website)")


def main() -> None:
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        candidates = sorted(
            f for f in os.listdir(output_dir)
            if f.endswith(".csv") and "_summary" not in f
        )
        if not candidates:
            print("No CSV files found in output/. Pass a path explicitly.")
            sys.exit(1)
        csv_path = os.path.join(output_dir, candidates[-1])

    print(f"Loading {csv_path} ...")
    df = load(csv_path)
    print(f"{len(df):,} leads loaded\n")

    # Build all 5 axes in a single tall figure, one chart per row
    fig, axes = plt.subplots(nrows=5, ncols=1, figsize=(11, 27))
    fig.subplots_adjust(hspace=0.55)

    _draw_pipeline_status(df,            axes[0])
    _draw_owner_name(df,                 axes[1])
    _draw_confidence(df,                 axes[2])
    _draw_email_coverage(df,             axes[3])
    _draw_pipeline_effectiveness(df,     axes[4])

    out_path = csv_path.replace(".csv", "_charts.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
