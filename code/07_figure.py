#!/usr/bin/env python3
"""07_figure.py — overview figure: stock and exit rates, stores vs locations.

Writes docs/figures/overview.png. Draft stamp unless --final.
Usage:  python code/07_figure.py [--final]
"""
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
FINAL = "--final" in sys.argv
OUTD = ROOT / "docs" / "figures"
OUTD.mkdir(parents=True, exist_ok=True)
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

nat = pd.read_csv(ROOT / "data" / "processed" / "national_year.csv")
t = nat[(nat["coverage"] == "all") & (nat["store_group"] == "All fixed-location")]
s = t[t["unit"] == "store"].sort_values("year")
l_ = t[t["unit"] == "location"].sort_values("year")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": INK2,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), dpi=200)
for ax in axes:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlim(2005.5, 2025.8)
    ax.set_xticks([2006, 2010, 2015, 2020, 2025])

ax = axes[0]
ax.plot(s["year"], s["stock_jan1"] / 1000, color=BLUE, lw=2, marker="o", ms=4, label="Stores (Record ID spells)")
ax.plot(l_["year"], l_["stock_jan1"] / 1000, color=ORANGE, lw=2, marker="o", ms=4, label="Locations (address spells)")
ax.set_ylim(140, 265)
ax.set_ylabel("Active on 1 January (thousands)")
ax.set_title("A. SNAP-authorized fixed-location retailers", loc="left", color=INK, fontsize=11)
ax.annotate(f"{s['stock_jan1'].iloc[-1] / 1000:.1f}k", (2025, s["stock_jan1"].iloc[-1] / 1000),
            xytext=(4, 6), textcoords="offset points", color=INK2, fontsize=9)
ax.legend(frameon=False, loc="lower right", labelcolor=INK2)

ax = axes[1]
s2, l2 = s[s["year"] <= 2024], l_[l_["year"] <= 2024]
ax.plot(s2["year"], 100 * s2["exit_rate"], color=BLUE, lw=2, marker="o", ms=4, label="Store exit")
ax.plot(l2["year"], 100 * l2["exit_rate"], color=ORANGE, lw=2, marker="o", ms=4, label="Location loss")
ax.set_ylim(0, 14)
ax.set_ylabel("Exits during year / stock on 1 January (%)")
ax.set_title("B. Annual exit rates (365-day continuity window)", loc="left", color=INK, fontsize=11)
ax.legend(frameon=False, loc="lower left", labelcolor=INK2)
ax.text(2024.4, 1.0, "2025 exits not\nyet observable", color=INK2, fontsize=8, ha="center")

fig.text(0.01, 0.01, "Source: USDA FNS SNAP Retailer Locator historical data 2005–2025 (current to 31 Dec 2025); "
         "all states and territories. The SNAP Retailer Spell Panel v1.0.0.", color=INK2, fontsize=8)
if not FINAL:
    fig.text(0.5, 0.5, "DRAFT", fontsize=70, color="#d0d0d0", alpha=0.45, ha="center", va="center", rotation=20)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(OUTD / "overview.png", facecolor="white")
print("wrote", OUTD / "overview.png")
