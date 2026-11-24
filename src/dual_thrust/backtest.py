"""The state machine: flat or fully invested, one position, close-price fills.

Daily order, exactly as the source module runs it:

1. **index stop** — if the benchmark fell more than ``index_stop`` today, go flat
2. **stock stop** — if the stock fell more than ``stop_2d`` over two sessions or
   ``stop_3d`` over three, go flat
3. **Dual Thrust sell** — if today's low broke the sell line, go flat
4. **Dual Thrust buy** — if today's high broke the buy line and we are flat, buy

Fills are at the close, which the source module states is a simplification: a
daily band can be breached intraday long before the close prints. The engine
keeps that assumption so the equity curve matches what the notebook produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .signals import Bar, Config, Levels, compute_levels

__all__ = ["TradeConfig", "Trade", "Result", "Stats", "backtest", "metrics"]


@dataclass(frozen=True)
class TradeConfig:
    signals: Config = Config()
    capital: float = 1_000_000.0
    stop_2d: float = -0.06
    stop_3d: float = -0.08
    index_stop: float = -0.03


@dataclass(frozen=True)
class Trade:
    date: str
    action: str            # BUY | SELL_INDEX_STOP | SELL_STOCK_STOP | SELL_DT
    price: float
    shares: float
    note: str = ""


@dataclass
class Result:
    dates: list[str] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    levels: list[Levels | None] = field(default_factory=list)
    config: TradeConfig = TradeConfig()

    @property
    def buys(self) -> list[Trade]:
        return [t for t in self.trades if t.action == "BUY"]

    @property
    def sells(self) -> list[Trade]:
        return [t for t in self.trades if t.action.startswith("SELL")]


@dataclass(frozen=True)
class Stats:
    total_return: float
    annual_return: float
    max_drawdown: float
    trades: int
    win_rate: float | None
    buy_and_hold: float


def _changes(closes: Sequence[float]) -> list[float]:
    out = [0.0] * len(closes)
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        out[i] = closes[i] / prev - 1.0 if prev else 0.0
    return out


def backtest(stock: Sequence[Bar], index: Sequence[Bar],
             config: TradeConfig = TradeConfig()) -> Result:
    if len(stock) != len(index):
        raise ValueError("stock and index must be aligned on the same sessions")

    levels = compute_levels(stock, config.signals)
    index_move = _changes([b.close for b in index])
    n = config.signals.n

    cash = config.capital
    shares = 0.0
    result = Result(levels=levels, config=config)

    for i, bar in enumerate(stock):
        result.dates.append(bar.date)

        if i < n or levels[i] is None:
            result.equity.append(cash + shares * bar.close)
            continue

        level = levels[i]

        if shares > 0 and index_move[i] < config.index_stop:
            result.trades.append(Trade(bar.date, "SELL_INDEX_STOP", bar.close, shares,
                                       f"index {index_move[i]:.2%}"))
            cash = shares * bar.close
            shares = 0.0

        if shares > 0:
            ret_2d = bar.close / stock[i - 2].close - 1.0 if i >= 2 else 0.0
            ret_3d = bar.close / stock[i - 3].close - 1.0 if i >= 3 else 0.0
            if ret_2d <= config.stop_2d or ret_3d <= config.stop_3d:
                result.trades.append(Trade(bar.date, "SELL_STOCK_STOP", bar.close, shares,
                                           f"2d {ret_2d:.2%} / 3d {ret_3d:.2%}"))
                cash = shares * bar.close
                shares = 0.0

        if shares > 0 and bar.low <= level.sell:
            result.trades.append(Trade(bar.date, "SELL_DT", bar.close, shares,
                                       f"sell line {level.sell:.2f}"))
            cash = shares * bar.close
            shares = 0.0

        if shares == 0 and bar.high >= level.buy:
            shares = cash / bar.close
            result.trades.append(Trade(bar.date, "BUY", bar.close, shares,
                                       f"buy line {level.buy:.2f}"))
            cash = 0.0

        result.equity.append(cash + shares * bar.close)

    return result


def metrics(result: Result, stock: Sequence[Bar]) -> Stats:
    equity = result.equity
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        max_dd = min(max_dd, value / peak - 1.0)

    total = equity[-1] / result.config.capital - 1.0
    annual = (1.0 + total) ** (252.0 / len(equity)) - 1.0 if equity else 0.0

    wins = 0
    pairs = 0
    entry = None
    for trade in result.trades:
        if trade.action == "BUY":
            entry = trade
        elif entry is not None:
            pairs += 1
            wins += trade.price > entry.price
            entry = None
    win_rate = wins / pairs if pairs else None

    bh = stock[-1].close / stock[0].close - 1.0 if stock else 0.0
    return Stats(total_return=total, annual_return=annual, max_drawdown=max_dd,
                 trades=len(result.buys), win_rate=win_rate, buy_and_hold=bh)
