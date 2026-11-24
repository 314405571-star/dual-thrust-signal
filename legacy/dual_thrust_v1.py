import baostock as bs
import pandas as pd
import numpy as np

# ==================== 参数设置 ====================
STOCK_CODE   = "sh.600519"       # 标的股票代码
INDEX_CODE   = "sh.000300"       # 大盘指数（沪深300）
START_DATE   = "2022-01-01"
END_DATE     = "2025-12-31"
N            = 5                 # Dual Thrust 回溯天数
K1           = 0.5               # 上轨系数
K2           = 0.5               # 下轨系数
INIT_CAPITAL = 1_000_000

# 个股止损参数
STOP_2D_PCT  = -0.06             # 两天内下跌6%
STOP_3D_PCT  = -0.08             # 三天内下跌8%

# 大盘止损参数
INDEX_STOP_PCT = -0.03           # 大盘单日跌幅超过3%触发空仓

# ==================== 数据获取 ====================
def fetch_daily(code, start, end):
    """获取日线数据，前复权"""
    rs = bs.query_history_k_data_plus(
        code,
        "date,open,high,low,close,volume",
        start_date=start, end_date=end,
        frequency="d", adjustflag="2"   # 2=前复权
    )
    data = []
    while (rs.error_code == '0') & rs.next():
        data.append(rs.get_row_data())
    df = pd.DataFrame(data, columns=rs.fields)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


bs.login()

stock_df = fetch_daily(STOCK_CODE, START_DATE, END_DATE)
index_df = fetch_daily(INDEX_CODE, START_DATE, END_DATE)

bs.logout()

# 对齐交易日：以个股交易日为准
common_dates = stock_df.index.intersection(index_df.index)
stock_df = stock_df.loc[common_dates].copy()
index_df = index_df.loc[common_dates].copy()

# ==================== Dual Thrust 信号计算 ====================
def compute_dual_thrust(df, n, k1, k2):
    """
    基于前 N 日 OHLC 计算当日 BuyLine / SellLine。
    所有 rolling 结果均 shift(1)，严格避免未来函数。
    """
    out = df.copy()

    out["HH"] = out["high"].rolling(n).max().shift(1)
    out["LC"] = out["close"].rolling(n).min().shift(1)
    out["HC"] = out["close"].rolling(n).max().shift(1)
    out["LL"] = out["low"].rolling(n).min().shift(1)

    out["Range"] = np.maximum(out["HH"] - out["LC"], out["HC"] - out["LL"])
    out["BuyLine"] = out["open"] + k1 * out["Range"]
    out["SellLine"] = out["open"] - k2 * out["Range"]
    return out


stock_sig = compute_dual_thrust(stock_df, N, K1, K2)

# 大盘涨跌幅（用于大盘止损）
index_df["pct_chg"] = index_df["close"].pct_change()

# ==================== 回测引擎 ====================
def backtest(stock, index, init_cap):
    """
    逐日回测，持仓状态只有两种：空仓 / 满仓（以收盘价成交，简化处理）。
    卖出优先级：大盘止损 > 个股回撤止损 > Dual Thrust 下轨突破。
    """
    cash = init_cap
    shares = 0
    entry_price = 0.0
    equity_curve = []
    trades = []

    for i, date in enumerate(stock.index):
        if i < N:                       # 数据不足，跳过
            equity_curve.append(init_cap)
            continue

        row = stock.loc[date]
        idx_row = index.loc[date]

        open_p  = row["open"]
        high_p  = row["high"]
        low_p   = row["low"]
        close_p = row["close"]
        buy_line = row["BuyLine"]
        sell_line = row["SellLine"]

        # ---------- 1. 大盘止损（无条件清仓） ----------
        index_stop = idx_row["pct_chg"] < INDEX_STOP_PCT

        if shares > 0 and index_stop:
            cash = shares * close_p
            trades.append({
                "date": date, "action": "SELL_INDEX_STOP",
                "price": close_p, "shares": shares
            })
            shares = 0
            entry_price = 0.0

        # ---------- 2. 个股回撤止损 ----------
        if shares > 0:
            close_series = stock["close"].iloc[:i+1]
            ret_2d = close_series.iloc[-1] / close_series.iloc[-3] - 1 if len(close_series) >= 3 else 0
            ret_3d = close_series.iloc[-1] / close_series.iloc[-4] - 1 if len(close_series) >= 4 else 0

            stock_stop = (ret_2d <= STOP_2D_PCT) or (ret_3d <= STOP_3D_PCT)

            if stock_stop:
                cash = shares * close_p
                trades.append({
                    "date": date, "action": "SELL_STOCK_STOP",
                    "price": close_p, "shares": shares,
                    "ret_2d": round(ret_2d, 4), "ret_3d": round(ret_3d, 4)
                })
                shares = 0
                entry_price = 0.0

        # ---------- 3. Dual Thrust 下轨突破（已持仓时触发） ----------
        if shares > 0 and low_p <= sell_line:
            cash = shares * close_p
            trades.append({
                "date": date, "action": "SELL_DT",
                "price": close_p, "shares": shares
            })
            shares = 0
            entry_price = 0.0

        # ---------- 4. Dual Thrust 上轨突破（开仓） ----------
        if shares == 0 and high_p >= buy_line:
            shares = cash / close_p
            entry_price = close_p
            cash = 0.0
            trades.append({
                "date": date, "action": "BUY",
                "price": close_p, "shares": shares
            })

        # ---------- 记录当日权益 ----------
        equity = cash + shares * close_p
        equity_curve.append(equity)

    equity_curve = pd.Series(equity_curve, index=stock.index)
    trades_df = pd.DataFrame(trades)
    return equity_curve, trades_df


equity, trades = backtest(stock_sig, index_df, INIT_CAPITAL)

# ==================== 绩效统计 ====================
total_ret = equity.iloc[-1] / INIT_CAPITAL - 1
annual_ret = (1 + total_ret) ** (252 / len(equity)) - 1
max_dd = (equity / equity.cummax() - 1).min()

print("=" * 60)
print(f"标的: {STOCK_CODE}    区间: {START_DATE} ~ {END_DATE}")
print(f"总收益: {total_ret:.2%}")
print(f"年化收益: {annual_ret:.2%}")
print(f"最大回撤: {max_dd:.2%}")
print(f"交易次数: {len(trades[trades['action'] == 'BUY']) if not trades.empty else 0}")
print("=" * 60)
if not trades.empty:
    print(trades.to_string(index=False))