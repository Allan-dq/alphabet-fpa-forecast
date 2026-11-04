"""Static charts (PNG) for the README and the executive summary.

Palette and mark specs follow one validated light palette:
series blue #2a78d6, its sequential ramp for interval bands, the blue<->red
diverging pair for favorable/unfavorable variances, neutral gray for totals.
"""
from __future__ import annotations

import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402

from .forecasting import q_to_ds  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"
BAND_80 = "#9ec5f4"
BAND_95 = "#cde2fb"
RED = "#e34948"
TOTAL = "#a8a7a0"

plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def _money(v, _=None) -> str:
    """USD millions -> compact tick label ($12B, $2.5B, $400M)."""
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v == 0:
        return "$0"
    if v >= 1000:
        b = v / 1000
        return f"{sign}${b:,.0f}B" if abs(b - round(b)) < 1e-9 else f"{sign}${b:,.1f}B"
    return f"{sign}${v:,.0f}M"


def _billions(ax):
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_money))


def _titles(fig, title: str, subtitle: str) -> None:
    fig.text(0.012, 0.975, title, ha="left", va="top", fontsize=12, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.012, 0.915, subtitle, ha="left", va="top", fontsize=9, color=INK_2)


def _grid(ax):
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def forecast_chart(actual: pd.Series, fc: pd.DataFrame, title: str, subtitle: str, path, ax=None, small=False):
    """actual: index fiscal_quarter -> value. fc: rows with fiscal_quarter, forecast, lo/hi 80/95."""
    own = ax is None
    if own:
        fig, ax = plt.subplots(figsize=(9, 4.6))
    x_a = [q_to_ds(q) for q in actual.index]
    x_f = [q_to_ds(q) for q in fc["fiscal_quarter"]]
    # connect the forecast to the last actual point
    x_fc = [x_a[-1]] + x_f
    join = actual.iloc[-1]
    ax.fill_between(x_fc, [join] + list(fc["lo_95"]), [join] + list(fc["hi_95"]), color=BAND_95, linewidth=0,
                    label="95% interval")
    ax.fill_between(x_fc, [join] + list(fc["lo_80"]), [join] + list(fc["hi_80"]), color=BAND_80, linewidth=0,
                    label="80% interval")
    ax.plot(x_a, actual.values, color=BLUE, linewidth=2, solid_capstyle="round", label="Actual")
    ax.plot(x_fc, [join] + list(fc["forecast"]), color=BLUE, linewidth=2, linestyle=(0, (4, 3)), label="Forecast")
    ax.plot([x_a[-1]], [join], "o", color=BLUE, markersize=6, markeredgecolor=SURFACE, markeredgewidth=2)
    _billions(ax)
    _grid(ax)
    if small:
        ax.set_title(title, fontsize=10)
        ax.tick_params(labelsize=8)
    else:
        _titles(ax.figure, title, subtitle)
        end = fc.iloc[-1]
        ax.annotate(f"{end['fiscal_quarter']}: ${end['forecast'] / 1000:,.0f}B", (x_f[-1], end["forecast"]),
                    xytext=(6, 0), textcoords="offset points", color=INK, fontsize=9, va="center")
        ax.annotate(f"{actual.index[-1]}: ${join / 1000:,.0f}B", (x_a[-1], join), xytext=(-8, 10),
                    textcoords="offset points", color=INK, fontsize=9, ha="right")
        leg = ax.legend(loc="upper left", frameon=False, fontsize=9, ncol=4, bbox_to_anchor=(0, 1.0))
        for t in leg.get_texts():
            t.set_color(INK_2)
        ax.set_xlim(x_a[0], x_f[-1] + pd.Timedelta(days=200))
    if own:
        fig.tight_layout(rect=(0, 0, 1, 0.88))
        fig.savefig(path, dpi=160)
        plt.close(fig)


def small_multiples(actuals: dict[str, pd.Series], fcs: dict[str, pd.DataFrame], titles: dict[str, str], path,
                    suptitle: str):
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.8))
    for ax, (key, title) in zip(axes.flat, titles.items()):
        forecast_chart(actuals[key], fcs[key], title, "", path=None, ax=ax, small=True)
        ax.xaxis.set_major_locator(matplotlib.dates.YearLocator(2))
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    fig.suptitle(suptitle, x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.01, 0.925, "Actual (solid) and forecast (dashed); bands are 80% and 95% intervals. Each panel has its own scale.",
             color=INK_2, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def waterfall(steps: pd.DataFrame, title: str, subtitle: str, path, favorable_up: bool = True):
    """steps: columns step, value, kind ('total' | 'delta'). Totals are absolute levels."""
    fig, ax = plt.subplots(figsize=(10, 5.0))
    running = 0.0
    bottoms, heights, colors = [], [], []
    for _, r in steps.iterrows():
        if r.kind == "total":
            bottoms.append(0)
            heights.append(r.value)
            colors.append(TOTAL)
            running = r.value
        else:
            good = (r.value >= 0) == favorable_up
            bottoms.append(running if r.value >= 0 else running + r.value)
            heights.append(abs(r.value))
            colors.append(BLUE if good else RED)
            running += r.value
    x = range(len(steps))
    totals = steps.loc[steps.kind == "total", "value"]
    deltas = steps.loc[steps.kind == "delta", "value"].abs()
    # zoom the y-axis so deltas are visible; totals are cut and the cut is labeled
    lo = min(totals.min(), min(b for b, k in zip(bottoms, steps.kind) if k == "delta")) - max(deltas.max() * 1.5, 1)
    hi = max(b + h for b, h in zip(bottoms, heights)) + max(deltas.max() * 0.6, 1)
    vis_bottoms = [max(b, lo) for b in bottoms]
    vis_heights = [h - (max(b, lo) - b) for b, h in zip(bottoms, heights)]
    ax.bar(x, vis_heights, bottom=vis_bottoms, color=colors, width=0.6, edgecolor=SURFACE, linewidth=2)
    for i, (r, b, h) in enumerate(zip(steps.itertuples(), bottoms, heights)):
        label = f"${r.value / 1000:,.2f}B" if r.kind == "total" else f"{r.value:+,.0f}M"
        ax.text(i, b + h + (hi - lo) * 0.012, label, ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylim(lo, hi)
    ax.set_xticks(list(x))
    ax.set_xticklabels([textwrap.fill(s, 14) for s in steps.step], fontsize=8.5, color=INK_2)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v / 1000:,.1f}B"))
    _grid(ax)
    _titles(fig, title, subtitle)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (TOTAL, BLUE, RED)]
    leg = ax.legend(handles, ["Forecast / actual level", "Favorable", "Unfavorable"], frameon=False, fontsize=9,
                    loc="upper right", ncol=3)
    for t in leg.get_texts():
        t.set_color(INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, dpi=160)
    plt.close(fig)
