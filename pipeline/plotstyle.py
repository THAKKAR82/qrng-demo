"""One matplotlib style for every chart in the notebook. See SPEC.md, Section 8.

Classical is always the same warm colour and quantum always the same cool colour. Sizes
are chosen to stay readable on a projector. Titles never repeat the axis labels, and any
chart drawn from synthetic data says so in its title (SPEC.md, Section 4.1).
"""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from typing import Any

import matplotlib as mpl
from matplotlib.axes import Axes
from matplotlib.colors import ListedColormap
from matplotlib.typing import RcKeyType

# Validated as a pair (dataviz palette checks): lightness band, chroma, colour-blind
# separation, and at least 3:1 contrast against the surface.
CLASSICAL = "#eb6834"  # warm orange
QUANTUM = "#2a78d6"  # cool blue
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
REFERENCE = "#8a8984"  # reference lines such as "a coin flip, 0.5"
FLAG = "#e34948"  # flagged qubits

SYNTHETIC_LABEL = "SYNTHETIC DATA: not from quantum hardware"

RC_PARAMS: dict[RcKeyType, Any] = {
    "figure.figsize": (12.0, 5.5),
    "figure.dpi": 110,
    "figure.facecolor": SURFACE,
    "figure.titlesize": 20,
    "figure.titleweight": "bold",
    "axes.facecolor": SURFACE,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "axes.labelsize": 16,
    "axes.titlesize": 18,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.titlepad": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 1.0,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.fontsize": 14,
    "legend.frameon": False,
    "lines.linewidth": 2.5,
    "font.size": 14,
    "text.color": INK,
    "savefig.facecolor": SURFACE,
    "savefig.bbox": "tight",
}


def apply() -> None:
    """Set the shared style for every chart drawn after this call."""
    mpl.rcParams.update(RC_PARAMS)


def label(text: str, *, synthetic: bool) -> str:
    """A chart title, marked as synthetic when the data is."""
    return f"SYNTHETIC · {text}" if synthetic else text


def title(ax: Axes, text: str, *, synthetic: bool) -> None:
    ax.set_title(label(text, synthetic=synthetic), color=FLAG if synthetic else INK)


def bitmap_cmap(color: str) -> ListedColormap:
    """Two colours: 0 is the surface and 1 is the stream's colour."""
    return ListedColormap([SURFACE, color])


def reference_line(ax: Axes, y: float = 0.5, text: str = "coin flip") -> None:
    """A dashed horizontal reference, labelled at the right-hand end."""
    ax.axhline(y, color=REFERENCE, linestyle="--", linewidth=1.5, zorder=1)
    ax.annotate(
        text,
        xy=(1.0, y),
        xycoords=("axes fraction", "data"),
        xytext=(4, 0),
        textcoords="offset points",
        va="center",
        color=MUTED,
        fontsize=13,
    )


def banner_html(text: str = SYNTHETIC_LABEL) -> str:
    """A large, high-contrast banner for notebook output."""
    return (
        '<div style="background:#e34948;color:#ffffff;font-size:26px;font-weight:700;'
        'padding:18px 24px;border-radius:6px;margin:8px 0;letter-spacing:0.02em">'
        f"{html.escape(text)}</div>"
    )


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """A Markdown table; cells are shown with ``str``."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def format_p(p: float) -> str:
    """``"= 0.018"`` or ``"< 1e-300"``: a p-value that underflowed is shown as a bound, not 0."""
    if math.isnan(p):
        return "= n/a"
    return f"= {p:.2g}" if p > 0.0 else "< 1e-300"
