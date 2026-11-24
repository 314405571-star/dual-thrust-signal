"""Dual Thrust: band construction, the flat/long state machine, and metrics."""

from .backtest import Result, Stats, TradeConfig, Trade, backtest, metrics
from .signals import Bar, Config, Levels, compute_levels

__all__ = [
    "Bar",
    "Config",
    "Levels",
    "Result",
    "Stats",
    "Trade",
    "TradeConfig",
    "backtest",
    "compute_levels",
    "metrics",
]
