"""Enhanced technical indicators powered by akquant (TA-Lib compatible, 103 indicators)"""

import pandas as pd
import numpy as np

try:
    import akquant as aq
    _HAS_AKQUANT = True
except (ImportError, ModuleNotFoundError):
    aq = None
    _HAS_AKQUANT = False

from data.fetcher import fetch_stock_history


def compute_all_indicators(code: str, period: str = "6mo") -> dict:
    """Compute a comprehensive set of technical indicators for a stock"""
    if not _HAS_AKQUANT:
        return _empty_result()
    df = fetch_stock_history(code, period=period)
    if df.empty or len(df) < 30:
        return _empty_result()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    price = float(close.iloc[-1]) if not pd.isna(close.iloc[-1]) else 0.0

    def _last(s):
        return round(float(s.iloc[-1]), 4) if not pd.isna(s.iloc[-1]) else None

    result = {"price": price, "data_points": len(df)}

    # -- Momentum indicators --
    rsi = aq.talib.RSI(close, timeperiod=14, as_series=True)
    result["rsi_14"] = _last(rsi)

    macd_line, macd_signal, macd_hist = aq.talib.MACD(close, as_series=True)
    result["macd_line"] = _last(macd_line)
    result["macd_signal"] = _last(macd_signal)
    result["macd_hist"] = _last(macd_hist)

    result["mom_10"] = _last(aq.talib.MOM(close, timeperiod=10, as_series=True))
    result["roc_10"] = _last(aq.talib.ROC(close, timeperiod=10, as_series=True))

    # -- Trend indicators --
    result["sma_20"] = _last(aq.talib.SMA(close, timeperiod=20, as_series=True))
    result["sma_50"] = _last(aq.talib.SMA(close, timeperiod=50, as_series=True)) if len(df) >= 50 else None
    result["sma_200"] = _last(aq.talib.SMA(close, timeperiod=200, as_series=True)) if len(df) >= 200 else None
    result["ema_12"] = _last(aq.talib.EMA(close, timeperiod=12, as_series=True))
    result["ema_26"] = _last(aq.talib.EMA(close, timeperiod=26, as_series=True))

    adx = aq.talib.ADX(high, low, close, timeperiod=14, as_series=True)
    result["adx_14"] = _last(adx)

    # -- Volatility indicators --
    bb_upper, bb_mid, bb_lower = aq.talib.BBANDS(close, as_series=True)
    result["bb_upper"] = _last(bb_upper)
    result["bb_mid"] = _last(bb_mid)
    result["bb_lower"] = _last(bb_lower)

    atr = aq.talib.ATR(high, low, close, timeperiod=14, as_series=True)
    result["atr_14"] = _last(atr)

    # -- Volume indicators --
    result["obv"] = _last(aq.talib.OBV(close, volume, as_series=True))
    result["mfi_14"] = _last(aq.talib.MFI(high, low, close, volume, timeperiod=14, as_series=True))

    # -- Overbought/Oversold --
    result["cci_14"] = _last(aq.talib.CCI(high, low, close, timeperiod=14, as_series=True))
    result["willr_14"] = _last(aq.talib.WILLR(high, low, close, timeperiod=14, as_series=True))

    # -- Stochastic --
    stoch_k, stoch_d = aq.talib.STOCH(high, low, close, as_series=True)
    result["stoch_k"] = _last(stoch_k)
    result["stoch_d"] = _last(stoch_d)

    # -- Derived signals --
    result["trend"] = _classify_trend(result, close)
    result["momentum_signal"] = _momentum_signal(result)
    result["volatility_regime"] = _volatility_regime(result)

    return result


def compute_weekly_indicators(code: str) -> dict:
    """Compute weekly-scale indicators"""
    if not _HAS_AKQUANT:
        return {}
    df = fetch_stock_history(code, period="1y")
    if df.empty or len(df) < 50:
        return {}

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    weekly = df.resample("W").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    close_w = weekly["close"]
    result = {}

    sma10 = aq.talib.SMA(close_w, timeperiod=10, as_series=True)
    result["ma10w"] = round(float(sma10.iloc[-1]), 2) if not pd.isna(sma10.iloc[-1]) else None

    sma20 = aq.talib.SMA(close_w, timeperiod=20, as_series=True)
    result["ma20w"] = round(float(sma20.iloc[-1]), 2) if not pd.isna(sma20.iloc[-1]) else None

    rsi_w = aq.talib.RSI(close_w, timeperiod=14, as_series=True)
    result["rsi_14w"] = round(float(rsi_w.iloc[-1]), 2) if not pd.isna(rsi_w.iloc[-1]) else None

    return result


def _classify_trend(inds: dict, close: pd.Series) -> str:
    """Classify current trend regime"""
    sma20 = inds.get("sma_20")
    sma50 = inds.get("sma_50")
    price = inds.get("price", 0)
    adx = inds.get("adx_14") or 0

    if sma20 and sma50 and price > sma20 > sma50 and adx > 25:
        return "强势上涨"
    if sma20 and sma50 and price > sma20:
        return "温和上涨"
    if sma20 and sma50 and price < sma20 < sma50 and adx > 25:
        return "强势下跌"
    if sma20 and sma50 and price < sma20:
        return "温和下跌"
    return "震荡整理"


def _momentum_signal(inds: dict) -> str:
    """Derive momentum signal from indicators"""
    rsi = inds.get("rsi_14") or 50
    macd_hist = inds.get("macd_hist") or 0
    stoch_k = inds.get("stoch_k") or 50

    score = 0
    if rsi > 60: score += 1
    elif rsi < 40: score -= 1
    if macd_hist > 0: score += 1
    else: score -= 1
    if stoch_k > 60: score += 1
    elif stoch_k < 40: score -= 1

    if score >= 2: return "强势看多"
    if score == 1: return "偏多"
    if score == 0: return "中性"
    if score == -1: return "偏空"
    return "强势看空"


def _volatility_regime(inds: dict) -> str:
    """Classify volatility regime from BB width and ATR"""
    bb_upper = inds.get("bb_upper") or 0
    bb_lower = inds.get("bb_lower") or 0
    bb_mid = inds.get("bb_mid") or 1
    atr = inds.get("atr_14") or 0
    price = inds.get("price") or 1

    bb_width_pct = (bb_upper - bb_lower) / bb_mid * 100 if bb_mid else 0
    atr_pct = atr / price * 100 if price else 0

    if bb_width_pct > 15 or atr_pct > 3:
        return "高波动"
    if bb_width_pct > 8 or atr_pct > 1.5:
        return "中波动"
    return "低波动"


def indicator_summary_text(inds: dict) -> str:
    """Format indicators as readable text for AI prompt"""
    if not inds or inds.get("data_points", 0) < 30:
        return "技术数据不足"

    lines = [
        f"价格: ¥{inds.get('price', 0)}",
        f"趋势: {inds.get('trend', 'N/A')}",
        f"动量: {inds.get('momentum_signal', 'N/A')}",
        f"波动: {inds.get('volatility_regime', 'N/A')}",
        "",
        "【动量指标】",
        f"RSI(14): {inds.get('rsi_14', 'N/A')}",
        f"MACD: 线={inds.get('macd_line', 'N/A')} 柱={inds.get('macd_hist', 'N/A')}",
        f"MOM(10): {inds.get('mom_10', 'N/A')}  ROC(10): {inds.get('roc_10', 'N/A')}",
        "",
        "【趋势指标】",
        f"MA20: {inds.get('sma_20', 'N/A')}  MA50: {inds.get('sma_50', 'N/A')}  MA200: {inds.get('sma_200', 'N/A')}",
        f"ADX(14): {inds.get('adx_14', 'N/A')}",
        "",
        "【波动指标】",
        f"布林上轨: {inds.get('bb_upper', 'N/A')}  中轨: {inds.get('bb_mid', 'N/A')}  下轨: {inds.get('bb_lower', 'N/A')}",
        f"ATR(14): {inds.get('atr_14', 'N/A')}",
        "",
        "【量价指标】",
        f"MFI(14): {inds.get('mfi_14', 'N/A')}",
        f"CCI(14): {inds.get('cci_14', 'N/A')}   Williams%R: {inds.get('willr_14', 'N/A')}",
        f"Stoch K/D: {inds.get('stoch_k', 'N/A')}/{inds.get('stoch_d', 'N/A')}",
        f"OBV: {inds.get('obv', 'N/A')}",
    ]
    return "\n".join(lines)


def _empty_result() -> dict:
    return {"data_points": 0}
