"""Sequoia-X 7大技术面筛选策略"""

import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SEQUOIA_PARAMS
from data.fetcher import fetch_stock_history


def calc_rps(close_series: pd.Series, window: int = 120) -> float:
    """计算RPS (Relative Price Strength) 百分位值"""
    if len(close_series) < window:
        return 0
    ret = (close_series.iloc[-1] - close_series.iloc[-window]) / close_series.iloc[-window]
    return ret * 100


def ma_volume_strategy(df: pd.DataFrame) -> bool:
    """
    MA5金叉MA20 + 成交量放大1.5倍
    金叉: 前一日MA5<MA20, 当日MA5>MA20
    """
    if len(df) < 30:
        return False
    p = SEQUOIA_PARAMS
    close = df["close"]
    vol = df["volume"]

    ma5 = close.rolling(p["ma_short"]).mean()
    ma20 = close.rolling(p["ma_long"]).mean()
    vol_ma20 = vol.rolling(20).mean()

    golden_cross = (ma5.iloc[-2] < ma20.iloc[-2]) and (ma5.iloc[-1] > ma20.iloc[-1])
    volume_surge = vol.iloc[-1] > vol_ma20.iloc[-1] * p["volume_ratio"]

    return golden_cross and volume_surge


def turtle_trade_strategy(df: pd.DataFrame) -> bool:
    """
    海龟交易: 收盘价突破20日最高 + 成交额>1亿 + 阳线
    """
    if len(df) < 25:
        return False
    p = SEQUOIA_PARAMS
    close = df["close"]
    high = df["high"]
    vol = df["volume"]

    breakout = close.iloc[-1] > high.shift(1).rolling(p["turtle_window"]).max().iloc[-1]
    amount = vol.iloc[-1] * close.iloc[-1]
    bullish = close.iloc[-1] > close.iloc[-2]

    return breakout and amount > p["turtle_min_amount"] and bullish


def high_tight_flag_strategy(df: pd.DataFrame) -> bool:
    """
    High Tight Flag: 40日振幅>60% + 10日振幅<15% + 缩量
    特征: 前期大幅波动 + 近期窄幅整理 + 量缩
    """
    if len(df) < 45:
        return False
    p = SEQUOIA_PARAMS
    high = df["high"]
    low = df["low"]
    close = df["close"]
    vol = df["volume"]

    high_40 = high.iloc[-40:].max()
    low_40 = low.iloc[-40:].min()
    high_10 = high.iloc[-10:].max()
    low_10 = low.iloc[-10:].min()

    range_40 = (high_40 - low_40) / low_40  # > 0.6
    range_10 = (high_10 - low_10) / low_10  # < 0.15
    tight_low = low.iloc[-10:].min() >= high_40 * 0.8
    vol_ma20 = vol.rolling(20).mean()
    vol_shrink = vol.iloc[-1] < vol_ma20.iloc[-1] * p["htf_vol_ratio"]

    return (range_40 > p["htf_range_ratio"] and
            range_10 < p["htf_tight_ratio"] and
            tight_low and vol_shrink)


def limit_up_shakeout_strategy(df: pd.DataFrame) -> bool:
    """
    涨停震仓: 前日涨停(>=9.5%) + 今日阴线 + 放量2倍
    """
    if len(df) < 5:
        return False
    p = SEQUOIA_PARAMS
    close = df["close"]
    open_ = df["open"]
    vol = df["volume"]

    prev_chg = (close.iloc[-2] - close.iloc[-3]) / close.iloc[-3] * 100
    limit_up = prev_chg >= p["limit_up_pct"]
    bearish = close.iloc[-1] < open_.iloc[-1]
    vol_surge = vol.iloc[-1] > vol.iloc[-2] * 2

    return limit_up and bearish and vol_surge


def uptrend_limit_down_strategy(df: pd.DataFrame) -> bool:
    """
    上升趋势跌停: MA20>MA60 + 跌停(<=-9.5%) + 放量2倍
    """
    if len(df) < 65:
        return False
    p = SEQUOIA_PARAMS
    close = df["close"]
    vol = df["volume"]

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    uptrend = ma20.iloc[-1] > ma60.iloc[-1]
    chg = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
    limit_down = chg <= p["limit_down_pct"]
    vol_ma20 = vol.rolling(20).mean()
    vol_surge = vol.iloc[-1] > vol_ma20.iloc[-1] * 2

    return uptrend and limit_down and vol_surge


def rps_breakout_strategy(df: pd.DataFrame) -> bool:
    """
    RPS突破: RPS(120日) >= 90 + 收盘价在120日高点的90%以上
    """
    if len(df) < 125:
        return False
    p = SEQUOIA_PARAMS
    close = df["close"]
    high = df["high"]

    rps = calc_rps(close, p["rps_window"])
    high_120 = high.iloc[-120:].max()
    near_high = close.iloc[-1] >= high_120 * 0.9

    return rps >= p["rps_threshold"] and near_high


def run_all_sequoia_strategies(code: str, name: str) -> list[dict]:
    """
    对单只股票运行所有7个Sequoia-X策略
    返回匹配的策略列表
    """
    df = fetch_stock_history(code, period="1y")
    if df.empty:
        return []

    results = []
    strategies = [
        ("MaVolume", ma_volume_strategy),
        ("TurtleTrade", turtle_trade_strategy),
        ("HighTightFlag", high_tight_flag_strategy),
        ("LimitUpShakeout", limit_up_shakeout_strategy),
        ("UptrendLimitDown", uptrend_limit_down_strategy),
        ("RPSBreakout", rps_breakout_strategy),
    ]

    for strat_name, strat_fn in strategies:
        try:
            if strat_fn(df):
                close = df["close"].iloc[-1]
                change = ((close - df["close"].iloc[-2]) / df["close"].iloc[-2] * 100
                          if len(df) > 1 else 0)
                results.append({
                    "strategy": strat_name,
                    "code": code,
                    "name": name,
                    "score": round(change, 2),
                    "price": round(close, 2),
                    "volume": int(df["volume"].iloc[-1]) if "volume" in df.columns else 0,
                })
        except Exception as e:
            print(f"策略 {strat_name} 在 {code} 上出错: {e}")

    return results


def screen_stock_pool(strategy_names: list[str] = None,
                     progress_callback=None) -> pd.DataFrame:
    """
    对股票池运行策略筛选（并行化）
    返回筛选结果DataFrame
    """
    from config import STOCK_POOL

    if strategy_names is None:
        strategy_names = ["MaVolume", "TurtleTrade", "HighTightFlag",
                         "LimitUpShakeout", "UptrendLimitDown", "RPSBreakout"]

    stocks = list(STOCK_POOL.items())
    total = len(stocks)
    all_results: list[dict] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {
            pool.submit(run_all_sequoia_strategies, code, name): (name, code)
            for name, code in stocks
        }
        for f in as_completed(futures):
            name, code = futures[f]
            try:
                picks = f.result()
                for p in picks:
                    if p["strategy"] in strategy_names:
                        all_results.append(p)
            except Exception as e:
                print(f"筛选 {name}({code}) 出错: {e}")
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    return pd.DataFrame(all_results) if all_results else pd.DataFrame()
