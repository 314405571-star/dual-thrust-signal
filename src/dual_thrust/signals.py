"""Dual Thrust levels — pure, standard library only.

For each session, using the previous ``n`` bars:

    HH = max(high)      LC = min(close)
    HC = max(close)     LL = min(low)
    range = max(HH − LC, HC − LL)

    buy  = today's open + k1 × range
    sell = today's open − k2 × range

The range measures how far the market travelled in the last ``n`` days — the
wider the recent swing, the wider today's band. The two multipliers let the
band be asymmetric; 0.5 / 0.5 is the classic setting.

Every window ends **before** the session it is applied to, so the level is
known at the open and no future bar enters the calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

__all__ = ["Bar", "Levels", "Config", "compute_levels"]


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Levels:
    hh: float
    lc: float
    hc: float
    ll: float
    range_: float
    buy: float
    sell: float


@dataclass(frozen=True)
class Config:
    n: int = 5
    k1: float = 0.5
    k2: float = 0.5


def compute_levels(bars: Sequence[Bar], config: Config = Config()) -> list[Levels | None]:
    """One entry per bar; ``None`` during the first ``n`` sessions."""
    n = config.n
    out: list[Levels | None] = [None] * len(bars)
    for i in range(n, len(bars)):
        window = bars[i - n: i]
        hh = max(b.high for b in window)
        lc = min(b.close for b in window)
        hc = max(b.close for b in window)
        ll = min(b.low for b in window)
        span = max(hh - lc, hc - ll)
        out[i] = Levels(
            hh=hh, lc=lc, hc=hc, ll=ll, range_=span,
            buy=bars[i].open + config.k1 * span,
            sell=bars[i].open - config.k2 * span,
        )
    return out
