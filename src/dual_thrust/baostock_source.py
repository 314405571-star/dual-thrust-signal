"""baostock adapter and CLI.

Fetches one stock and one benchmark over the same window, aligns them on the
stock's trading days, and runs the engine. Prices are forward-adjusted
(``adjustflag="2"``), so the band and the equity curve are on a rebased series
rather than the raw tape.

    python -m src.dual_thrust.baostock_source run --code sh.600519 --start 2022-01-01
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .backtest import TradeConfig, backtest, metrics
from .signals import Bar, Config

__all__ = ["fetch_daily", "run", "main"]

log = logging.getLogger("dual_thrust")


def fetch_daily(bs, code: str, start: str, end: str) -> list[Bar]:
    rs = bs.query_history_k_data_plus(
        code, "date,open,high,low,close,volume",
        start_date=start, end_date=end, frequency="d", adjustflag="2",
    )
    fields = list(rs.fields)
    bars = []
    while rs.error_code == "0" and rs.next():
        row = dict(zip(fields, rs.get_row_data()))
        try:
            bars.append(Bar(row["date"], float(row["open"]), float(row["high"]),
                            float(row["low"]), float(row["close"])))
        except (TypeError, ValueError):
            continue          # suspended / missing prices
    return bars


def run(*, code: str, index_code: str, start: str, end: str,
        config: TradeConfig = TradeConfig(),
        out_dir: str | Path = "output", bs=None) -> dict:
    close = False
    if bs is None:
        import baostock as _bs
        bs = _bs
        close = True
        res = bs.login()
        if res.error_code != "0":
            raise SystemExit(f"login failed: {res.error_msg}")

    try:
        stock = fetch_daily(bs, code, start, end)
        index = fetch_daily(bs, index_code, start, end)
    finally:
        if close:
            bs.logout()

    index_by_date = {b.date: b for b in index}
    aligned = [(b, index_by_date[b.date]) for b in stock if b.date in index_by_date]
    if len(aligned) < config.signals.n + 10:
        raise SystemExit("not enough aligned sessions")
    stock = [pair[0] for pair in aligned]
    index = [pair[1] for pair in aligned]

    result = backtest(stock, index, config)
    stats = metrics(result, stock)

    print(f"{code} vs {index_code}  {stock[0].date} → {stock[-1].date}")
    print(f"  total return   {stats.total_return:+.2%}")
    print(f"  annualised     {stats.annual_return:+.2%}")
    print(f"  max drawdown   {stats.max_drawdown:.2%}")
    print(f"  trades         {stats.trades}")
    if stats.win_rate is not None:
        print(f"  win rate       {stats.win_rate:.0%}")
    print(f"  buy and hold   {stats.buy_and_hold:+.2%}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stock[-1].date.replace("-", "")
    trades_path = out_dir / f"dual_thrust_trades_{stamp}.csv"
    with trades_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "action", "price", "shares", "note"])
        for trade in result.trades:
            writer.writerow([trade.date, trade.action, trade.price,
                             round(trade.shares, 2), trade.note])
    equity_path = out_dir / f"dual_thrust_equity_{stamp}.csv"
    with equity_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "equity"])
        writer.writerows(zip(result.dates, result.equity))
    print(f"  wrote {trades_path.name}, {equity_path.name}")

    return {
        "total_return": stats.total_return,
        "annual_return": stats.annual_return,
        "max_drawdown": stats.max_drawdown,
        "trades": stats.trades,
        "win_rate": stats.win_rate,
        "buy_and_hold": stats.buy_and_hold,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dual Thrust signal and backtest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--code", default="sh.600519")
    run_cmd.add_argument("--index", default="sh.000300")
    run_cmd.add_argument("--start", default="2022-01-01")
    run_cmd.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    run_cmd.add_argument("--n", type=int, default=5)
    run_cmd.add_argument("--k1", type=float, default=0.5)
    run_cmd.add_argument("--k2", type=float, default=0.5)
    run_cmd.add_argument("--capital", type=float, default=1_000_000)
    run_cmd.add_argument("--out", default="output")
    run_cmd.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if args.cmd != "run":
        return 1
    run(code=args.code, index_code=args.index, start=args.start, end=args.end,
        config=TradeConfig(signals=Config(n=args.n, k1=args.k1, k2=args.k2),
                           capital=args.capital),
        out_dir=args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
