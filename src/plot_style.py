"""Ortak matplotlib stili (doğrulanmış referans paleti, açık tema)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
# Kategorik slotlar sabit sırayla kullanılır
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQ_CMAP = matplotlib.colors.LinearSegmentedColormap.from_list(
    "ww_blue", ["#f0efec", "#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"])
STATUS = {"Normal": "#0ca30c", "Şüpheli": "#fab219", "Anormal": "#d03b3b"}


def apply() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelsize": 10,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "font.size": 9.5,
        "legend.frameon": False,
        "legend.labelcolor": INK_2,
        "lines.linewidth": 2.0,
        "axes.prop_cycle": matplotlib.cycler(color=SERIES),
        "figure.dpi": 110,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
    })


def save(fig, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
