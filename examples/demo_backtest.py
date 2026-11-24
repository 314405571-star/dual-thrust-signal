"""Offline demo: a synthetic market, the Dual Thrust engine, and four figures.

No network, no baostock. The price paths come from a fixed seed, so the output
is identical on every machine.

    python examples/demo_backtest.py
"""

from __future__ import annotations

import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from src.dual_thrust.backtest import TradeConfig, backtest, metrics  # noqa: E402
from src.dual_thrust.signals import Bar, Config  # noqa: E402

FIG_DIR = Path(__file__).resolve().parent / "figures"
SESSIONS = 900
SEED = 5
START = date(2022, 1, 3)

SURFACE, INK, SECOND, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"

STYLE = {
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": SECOND,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": SECOND,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
}


# --------------------------------------------------------------------- data
def build_market(seed: int = SEED, sessions: int = SESSIONS):
    rng = random.Random(seed)
    days, day = [], START
    while len(days) < sessions:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)

    stock: list[Bar] = []
    index: list[Bar] = []
    stock_close = index_close = 100.0
    for i, day in enumerate(days):
        block = i // 80
        vol = 0.004 + 0.002 * ((block * 7) % 3)
        drift = [0.0018, 0.0005, -0.0004][(block * 5) % 3]
        index_drift = drift * 0.6

        def bar(prev: float, mu: float, sigma: float):
            gap = rng.gauss(0, sigma * 0.35)
            open_ = prev * (1 + gap)
            close = open_ * math.exp(mu + sigma * rng.gauss(0, 1))
            span = abs(rng.gauss(0, sigma * 0.7))
            high = max(open_, close) * (1 + span)
            low = min(open_, close) * (1 - span * 0.8)
            return open_, high, low, close

        o, h, l, c = bar(stock_close, drift, vol)
        stock_close = c
        stock.append(Bar(day.isoformat(), round(o, 2), round(h, 2), round(l, 2), round(c, 2)))

        shock = rng.gauss(0, vol * 0.5)
        o, h, l, c = bar(index_close, index_drift + shock, vol * 0.45)
        index_close = c
        index.append(Bar(day.isoformat(), round(o, 2), round(h, 2), round(l, 2), round(c, 2)))
    return stock, index


# ------------------------------------------------------------------ figures
def _fig(w, h):
    plt.rcParams.update(STYLE)
    return plt.figure(figsize=(w, h), dpi=170)


def _clean(ax, axis="y"):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if axis:
        ax.grid(True, axis=axis, color=GRID, linewidth=0.7)
        ax.set_axisbelow(True)


def _header(fig, title, subtitle, meta, x=0.065, y=0.955):
    fig.text(x, y, title, fontsize=17, fontweight="semibold", color=INK, ha="left", va="top")
    fig.text(x, y - 0.058, subtitle, fontsize=9.7, color=SECOND, ha="left", va="top")
    fig.text(0.985, y, meta, fontsize=8.2, color=MUTED, ha="right", va="top",
             family="DejaVu Sans Mono")


def _state_spans(result):
    """(start_index, end_index) blocks where the book was long."""
    spans, start = [], None
    for i, trade in enumerate(_by_date(result)):
        if trade == "long" and start is None:
            start = i
        elif trade != "long" and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(result.equity)))
    return spans


def _by_date(result):
    """One label per session: 'long' while holding."""
    labels = []
    holding = False
    trades = {t.date: t for t in result.trades if t.action == "BUY"}
    sells = {t.date: t for t in result.trades if t.action.startswith("SELL")}
    for day in result.dates:
        if day in trades:
            holding = True
        labels.append("long" if holding else "flat")
        if day in sells:
            holding = False
    return labels


def fig_price_signals(stock, result, path):
    x = list(range(len(stock)))
    fig = _fig(13.0, 5.6)
    ax = fig.add_axes([0.07, 0.13, 0.90, 0.62])

    for start, end in _state_spans(result):
        ax.axvspan(start, end, color=BLUE, alpha=0.07, linewidth=0)

    closes = [b.close for b in stock]
    ax.plot(x, closes, color=INK, linewidth=1.2, zorder=3)
    buys = [section for section in result.levels]
    buy_line = [lv.buy if lv else None for lv in buys]
    sell_line = [lv.sell if lv else None for lv in buys]
    ax.plot(x, buy_line, color=ORANGE, linewidth=0.8, alpha=0.8, zorder=2)
    ax.plot(x, sell_line, color=AQUA, linewidth=0.8, alpha=0.8, zorder=2)

    buy_days = {t.date for t in result.trades if t.action == "BUY"}
    sell_days = {t.date for t in result.trades if t.action.startswith("SELL")}
    buy_x = [i for i, b in enumerate(stock) if b.date in buy_days]
    sell_x = [i for i, b in enumerate(stock) if b.date in sell_days]
    ax.scatter(buy_x, [stock[i].low * 0.992 for i in buy_x], marker="^", s=44,
               color=ORANGE, edgecolor=SURFACE, linewidth=0.8, zorder=6)
    ax.scatter(sell_x, [stock[i].high * 1.008 for i in sell_x], marker="v", s=44,
               color=AQUA, edgecolor=SURFACE, linewidth=0.8, zorder=6)

    ax.set_xlim(0, len(stock))
    ax.set_ylabel("price", fontsize=8.8)
    _clean(ax)
    ticks = list(range(0, len(stock), 120))
    ax.set_xticks(ticks)
    ax.set_xticklabels([stock[i].date[2:7] for i in ticks], fontsize=7.8)

    ax.legend(handles=[
        Line2D([], [], color=INK, linewidth=1.2, label="close"),
        Line2D([], [], color=ORANGE, linewidth=0.9, label="buy line"),
        Line2D([], [], color=AQUA, linewidth=0.9, label="sell line"),
        Line2D([], [], marker="^", linestyle="none", color=ORANGE, markersize=6, label="buy"),
        Line2D([], [], marker="v", linestyle="none", color=AQUA, markersize=6, label="sell"),
        Patch(facecolor=BLUE, alpha=0.12, label="long"),
    ], loc="upper left", frameon=False, fontsize=7.8, ncol=6,
        handlelength=1.2, columnspacing=1.2)

    _header(fig, "Two lines, one position",
            "the band is rebuilt every morning from the previous five sessions",
            "synthetic · 900 sessions")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def fig_equity(stock, result, path):
    equity = [v / result.config.capital for v in result.equity]
    hold = [b.close / stock[0].close for b in stock]
    x = list(range(len(stock)))

    fig = _fig(11.0, 5.0)
    ax = fig.add_axes([0.08, 0.15, 0.88, 0.60])
    ax.plot(x, equity, color=BLUE, linewidth=1.6)
    ax.plot(x, hold, color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.axhline(1.0, color=BASELINE, linewidth=0.9)
    ax.set_xlim(0, len(stock))
    ax.set_ylabel("growth of 1.00", fontsize=8.8)
    _clean(ax)
    ticks = list(range(0, len(stock), 120))
    ax.set_xticks(ticks)
    ax.set_xticklabels([stock[i].date[2:7] for i in ticks], fontsize=7.8)
    ax.legend(handles=[Line2D([], [], color=BLUE, linewidth=1.6, label="Dual Thrust"),
                       Line2D([], [], color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)),
                              label="buy and hold")],
              loc="upper left", frameon=False, fontsize=8.0)

    _header(fig, "In the market or out of it",
            "the strategy is either fully invested or in cash; the switches are the band",
            "synthetic · 900 sessions")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def fig_drawdown(stock, result, path):
    equity = result.equity
    peak, curve = equity[0], []
    for value in equity:
        peak = max(peak, value)
        curve.append(value / peak - 1.0)
    hold_peak, hold_curve = stock[0].close, []
    for bar in stock:
        hold_peak = max(hold_peak, bar.close)
        hold_curve.append(bar.close / hold_peak - 1.0)

    x = list(range(len(stock)))
    fig = _fig(11.0, 4.2)
    ax = fig.add_axes([0.08, 0.16, 0.88, 0.55])
    ax.fill_between(x, curve, 0, color=BLUE, alpha=0.18, linewidth=0)
    ax.plot(x, curve, color=BLUE, linewidth=1.3)
    ax.plot(x, hold_curve, color=MUTED, linewidth=1.0, linestyle=(0, (4, 3)))
    ax.set_xlim(0, len(stock))
    ax.set_ylim(min(min(curve), min(hold_curve)) * 1.1, 0.02)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_ylabel("drawdown from peak", fontsize=8.8)
    _clean(ax)
    ticks = list(range(0, len(stock), 120))
    ax.set_xticks(ticks)
    ax.set_xticklabels([stock[i].date[2:7] for i in ticks], fontsize=7.8)

    _header(fig, "How deep, how long",
            "underwater curve; the dashed line is buy and hold",
            "synthetic · 900 sessions")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def fig_anatomy(stock, result, path, start=140, length=55):
    end = min(start + length, len(stock))
    fig = _fig(12.4, 5.4)
    ax = fig.add_axes([0.07, 0.15, 0.90, 0.60])

    for i in range(start, end):
        bar = stock[i]
        up = bar.close >= bar.open
        color = RED if up else AQUA
        ax.plot([i, i], [bar.low, bar.high], color=color, linewidth=0.9, zorder=2)
        ax.plot([i - 0.28, i + 0.28], [bar.open, bar.open], color=color, linewidth=0.9, zorder=2)
        ax.plot([i - 0.28, i + 0.28], [bar.close, bar.close], color=color, linewidth=1.4, zorder=3)

    levels = result.levels[start:end]
    xs = list(range(start, end))
    ax.plot(xs, [lv.buy if lv else None for lv in levels], color=ORANGE, linewidth=1.1,
            label="buy line")
    ax.plot(xs, [lv.sell if lv else None for lv in levels], color=AQUA, linewidth=1.1,
            label="sell line")
    ax.plot(xs, [stock[i].open for i in xs], color=MUTED, linewidth=0.9,
            linestyle=(0, (2, 2)), label="open")

    ax.set_xlim(start - 1, end)
    ax.set_ylabel("price", fontsize=8.8)
    _clean(ax)
    ax.legend(handles=[
        Line2D([], [], color=ORANGE, linewidth=1.1, label="buy line"),
        Line2D([], [], color=AQUA, linewidth=1.1, label="sell line"),
        Line2D([], [], color=MUTED, linewidth=0.9, linestyle=(0, (2, 2)), label="open"),
    ], loc="upper left", frameon=False, fontsize=7.8, ncol=3)

    _header(fig, "Anatomy of a band",
            "open ± 0.5 × the larger of (HH − LC) and (HC − LL) over the prior five sessions",
            "synthetic · 55 sessions")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# --------------------------------------------------------------------- main
def main() -> int:
    stock, index = build_market()
    config = TradeConfig(signals=Config(n=5, k1=0.5, k2=0.5))
    result = backtest(stock, index, config)
    stats = metrics(result, stock)

    print("Dual Thrust — offline demo")
    print(f"  sessions        {len(stock)}")
    print(f"  total return    {stats.total_return:+.2%}")
    print(f"  annualised      {stats.annual_return:+.2%}")
    print(f"  max drawdown    {stats.max_drawdown:.2%}")
    print(f"  buys            {stats.trades}")
    if stats.win_rate is not None:
        print(f"  win rate        {stats.win_rate:.0%}")
    print(f"  buy and hold    {stats.buy_and_hold:+.2%}")
    reasons: dict[str, int] = {}
    for trade in result.trades:
        if trade.action.startswith("SELL"):
            reasons[trade.action] = reasons.get(trade.action, 0) + 1
    print("  exits           " + ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())))

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig_price_signals(stock, result, FIG_DIR / "price_signals.png")
    fig_equity(stock, result, FIG_DIR / "equity.png")
    fig_drawdown(stock, result, FIG_DIR / "drawdown.png")
    fig_anatomy(stock, result, FIG_DIR / "anatomy.png")
    print(f"\n  four figures written to {FIG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
