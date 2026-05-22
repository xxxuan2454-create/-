"""Momentum-X 动量趋势选股 — 6大趋势延续策略

与 Sequoia-X 互补:
- Sequoia-X: 捕捉极端事件（涨停震仓、趋势跌停、高紧旗形…）
- Momentum-X: 捕捉趋势延续（均线多头、平台突破、回调支撑…）

纯 pandas 实现，零 akquant 依赖，Streamlit Cloud 完全兼容。
"""

import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.fetcher import fetch_stock_history
from config import STOCK_POOL, MOMENTUM_PARAMS


# ═══════════════════════════════════════════
# 6 大动量趋势策略
# ═══════════════════════════════════════════

def strategy_bullish_alignment(df: pd.DataFrame, p: dict) -> bool:
    """均线多头排列: MA5 > MA20 > MA60，价格不远离MA20（未过度拉伸）"""
    close = df["close"]
    if len(close) < 60:
        return False

    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    if not (ma5.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1]):
        return False

    # 价格不远离MA20: 涨幅不超过 15%，避免追高
    pct_above_ma20 = (close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1]
    if pct_above_ma20 > p.get("ba_max_pct_above_ma20", 0.15):
        return False

    # 20日趋势确认向上
    if close.iloc[-1] <= close.iloc[-20]:
        return False

    return True


def strategy_volume_breakout(df: pd.DataFrame, p: dict) -> bool:
    """放量突破平台: 前20日窄幅整理(<20%)，今日放量突破平台上沿"""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    if len(close) < 60:
        return False

    window = p.get("vb_range_days", 20)

    prev_high = high.iloc[-(window + 1):-1].max()
    prev_low = low.iloc[-(window + 1):-1].min()
    if prev_low <= 0:
        return False

    # 前 window 日窄幅整理
    consolidation = (prev_high - prev_low) / prev_low
    if consolidation > p.get("vb_range_max", 0.20):
        return False

    # 今日突破平台上沿 (至少到 98% 位置)
    if close.iloc[-1] < prev_high * 0.98:
        return False

    # 放量确认 (>1.5x 20日均量)
    vol_ma20 = vol.rolling(20).mean()
    if vol.iloc[-1] < vol_ma20.iloc[-1] * p.get("vb_volume_ratio", 1.5):
        return False

    # 收阳
    if close.iloc[-1] <= close.iloc[-2]:
        return False

    return True


def strategy_trend_pullback(df: pd.DataFrame, p: dict) -> bool:
    """趋势回调支撑: 上升趋势中缩量回踩MA20获支撑"""
    close = df["close"]
    vol = df["volume"]
    if len(close) < 60:
        return False

    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    vol_ma20 = vol.rolling(20).mean()

    # 中期上升趋势: MA20 > MA60，且MA20仍在爬升
    if ma20.iloc[-1] <= ma60.iloc[-1]:
        return False
    if ma20.iloc[-1] <= ma20.iloc[-5]:
        return False

    # 短期回调: 价格在MA5之下
    if close.iloc[-1] >= ma5.iloc[-1]:
        return False

    # 守住MA20支撑 (允许1%容差)
    if close.iloc[-1] < ma20.iloc[-1] * 0.99:
        return False

    # 回调缩量: 当前量 < 70% 均量
    if vol.iloc[-1] > vol_ma20.iloc[-1] * p.get("tp_vol_shrink", 0.7):
        return False

    return True


def strategy_macd_zero_cross(df: pd.DataFrame, p: dict) -> bool:
    """MACD零轴上金叉: MACD柱刚翻红，MACD线在零轴上方"""
    close = df["close"]
    vol = df["volume"]
    if len(close) < 60:
        return False

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line

    # MACD柱刚由负转正
    if not (macd_hist.iloc[-2] < 0 and macd_hist.iloc[-1] > 0):
        return False

    # 零轴上方
    if macd_line.iloc[-1] <= 0 or signal_line.iloc[-1] <= 0:
        return False

    # 价格在 MA20 上方
    ma20 = close.rolling(20).mean()
    if close.iloc[-1] <= ma20.iloc[-1]:
        return False

    # 放量确认，ADX 过滤
    vol_ma20 = vol.rolling(20).mean()
    adx = _calc_adx(df, 14)
    if vol.iloc[-1] < vol_ma20.iloc[-1] or (adx is not None and adx < p.get("macd_adx_min", 18)):
        return False

    return True


def strategy_bb_squeeze_breakout(df: pd.DataFrame, p: dict) -> bool:
    """布林带收口突破: 波动率收缩后向上突破上轨"""
    close = df["close"]
    vol = df["volume"]
    if len(close) < 60:
        return False

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_width = (bb_upper - bb_lower) / bb_mid

    squeeze_window = p.get("bb_squeeze_days", 10)

    # 布林带收口: 近 squeeze_window 天宽度收窄 15%+
    w_old = bb_width.iloc[-squeeze_window]
    w_new = bb_width.iloc[-1]
    if pd.isna(w_old) or pd.isna(w_new) or w_old <= 0:
        return False
    if (w_old - w_new) / w_old < 0.15:
        return False

    # 今日突破上轨
    if close.iloc[-1] <= bb_upper.iloc[-1]:
        return False

    # 放量确认
    vol_ma20 = vol.rolling(20).mean()
    if vol.iloc[-1] < vol_ma20.iloc[-1] * p.get("bb_vol_ratio", 1.3):
        return False

    return True


def strategy_rsi_momentum(df: pd.DataFrame, p: dict) -> bool:
    """RSI强势动量: RSI在55-72强势区间，持续走高，MFI确认资金流入"""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    if len(close) < 30:
        return False

    rsi = _calc_rsi(close, 14)
    rsi_val = rsi.iloc[-1]
    if pd.isna(rsi_val):
        return False

    rsi_low = p.get("rsi_low", 55)
    rsi_high = p.get("rsi_high", 72)
    if not (rsi_low <= rsi_val <= rsi_high):
        return False

    # RSI 持续走高 (近3天)
    rising_days = p.get("rsi_rising_days", 3)
    if rsi.iloc[-1] <= rsi.iloc[-rising_days]:
        return False

    # 价格在 MA20 上方
    ma20 = close.rolling(20).mean()
    if close.iloc[-1] <= ma20.iloc[-1]:
        return False

    # MFI > 50 确认资金流入
    mfi = _calc_mfi(high, low, close, vol, 14)
    if mfi is None or mfi < p.get("mfi_min", 50):
        return False

    return True


# ═══════════════════════════════════════════
# 技术指标工具函数 (纯 pandas)
# ═══════════════════════════════════════════

def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def _calc_mfi(high: pd.Series, low: pd.Series, close: pd.Series,
              vol: pd.Series, period: int = 14) -> float | None:
    typical = (high + low + close) / 3
    raw_mf = typical * vol
    pos_flow = raw_mf.where(typical > typical.shift(1), 0)
    neg_flow = raw_mf.where(typical < typical.shift(1), 0)
    pos_sum = pos_flow.rolling(period).sum()
    neg_sum = neg_flow.rolling(period).sum()
    neg_sum = neg_sum.replace(0, 1e-9)
    mr = pos_sum / neg_sum
    mfi = 100 - (100 / (1 + mr))
    val = mfi.iloc[-1]
    return None if pd.isna(val) else float(val)


def _calc_adx(df: pd.DataFrame, period: int = 14) -> float | None:
    """简化 ADX 计算，返回当前值"""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    n = len(close)
    if n < period * 2:
        return None

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > 0) & (up_move > down_move), 0)
    minus_dm = down_move.where((down_move > 0) & (down_move > up_move), 0)

    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, 1e-9))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, 1e-9))

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-9)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    val = adx.iloc[-1]
    return None if pd.isna(val) else float(val)


# ═══════════════════════════════════════════
# 策略注册表
# ═══════════════════════════════════════════

STRATEGY_REGISTRY: dict[str, tuple[str, callable]] = {
    "BullishAlignment":  ("均线多头排列", strategy_bullish_alignment),
    "VolumeBreakout":    ("放量突破平台", strategy_volume_breakout),
    "TrendPullback":     ("趋势回调支撑", strategy_trend_pullback),
    "MACDZeroCross":     ("MACD零轴金叉", strategy_macd_zero_cross),
    "BBSqueezeBreakout": ("布林收口突破", strategy_bb_squeeze_breakout),
    "RSIStrength":       ("RSI强势动量", strategy_rsi_momentum),
}


# ═══════════════════════════════════════════
# 单只股票多策略运行
# ═══════════════════════════════════════════

def run_all_momentum_strategies(code: str,
                                strategy_names: list[str] | None = None) -> list[dict]:
    """对单只股票运行所有动量策略，返回命中列表"""
    df = fetch_stock_history(code, period="1y")
    if df.empty or len(df) < 60:
        return []

    if strategy_names is None:
        strategy_names = list(STRATEGY_REGISTRY.keys())

    last_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])
    change = (last_close - prev_close) / prev_close * 100 if prev_close else 0

    hits = []
    for name in strategy_names:
        if name not in STRATEGY_REGISTRY:
            continue
        _, func = STRATEGY_REGISTRY[name]
        try:
            if func(df, MOMENTUM_PARAMS):
                hits.append({
                    "strategy": name,
                    "code": code,
                    "price": round(last_close, 2),
                    "volume": int(df["volume"].iloc[-1]),
                    "score": round(change, 2),
                })
        except Exception:
            pass

    return hits


# ═══════════════════════════════════════════
# 并行全市场筛选
# ═══════════════════════════════════════════

def screen_stock_pool(strategy_names: list[str] | None = None,
                      progress_callback=None) -> pd.DataFrame:
    """并行筛选全市场股票池 (20线程)，返回命中 DataFrame"""
    stock_list = list(STOCK_POOL.items())
    total = len(stock_list)

    all_hits: list[dict] = []
    done = 0

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(run_all_momentum_strategies, code, strategy_names): name
            for name, code in stock_list
        }

        for future in as_completed(futures):
            done += 1
            if progress_callback:
                progress_callback(done, total)
            try:
                hits = future.result()
                stock_name = futures[future]
                for h in hits:
                    h["name"] = stock_name
                    all_hits.append(h)
            except Exception:
                pass

    if not all_hits:
        return pd.DataFrame()

    return pd.DataFrame(all_hits)
