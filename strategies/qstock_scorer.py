"""qstock 多因子评分: RPS + 10因子 + Mark Minervini趋势模板"""

import time
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.fetcher import fetch_stock_history, fetch_stock_info, fetch_financial_data
from config import STOCK_POOL


# ═══════════════════════════════════════════════════════════════
# RPS (Relative Price Strength) 多周期计算
# ═══════════════════════════════════════════════════════════════

def calc_single_rps(close: pd.Series, window: int) -> float:
    """计算单周期RPS: (当期收益 - min) / (max - min) -- 这里简化为收益率"""
    if len(close) < window:
        return 0.0
    ret = (close.iloc[-1] - close.iloc[-window]) / close.iloc[-window]
    return ret


def calc_rps_all_periods(code: str, df: pd.DataFrame | None = None) -> dict[str, float]:
    """计算多周期RPS (5, 20, 60, 120, 250日)"""
    if df is None:
        df = fetch_stock_history(code, period="1y")
    if df is None or df.empty:
        return {}
    close = df["close"]
    rps = {}
    for w in [5, 20, 60, 120]:
        rps[f"rps_{w}"] = round(calc_single_rps(close, w) * 100, 1)
    if len(close) >= 250:
        rps["rps_250"] = round(calc_single_rps(close, 250) * 100, 1)
    return rps


# ═══════════════════════════════════════════════════════════════
# 10因子评分系统 (基于 qstock 算法)
# ═══════════════════════════════════════════════════════════════

def _clamp_score(val: float, low: float = 0, high: float = 10) -> float:
    return max(low, min(high, val))


def cal_yoy(y: float, baseline: float) -> float:
    """同比增长率评分 (净利润增长/营收增长)
    y = 同比增长率(%), baseline = 基准线
    score = 5 + min(round(y - baseline), 5)  if y >= baseline
    score = 5 + max(round(y - baseline), -5) if y < baseline
    """
    diff = round(y - baseline)
    if diff > 5:
        diff = 5
    elif diff < -5:
        diff = -5
    return _clamp_score(5 + diff)


def cal_exp(y: float, a: float) -> float:
    """偏差评分 (毛利率/费用率/周转/现金流)
    y可正可负, a为除数
    """
    scaled = round(y) / a if a != 0 else 0
    if scaled > 5:
        scaled = 5
    elif scaled < -5:
        scaled = -5
    return _clamp_score(5 + scaled)


def cal_roa(roa: float) -> float:
    """ROA评分: (roa - 5) / 0.5, min 0, max 10"""
    score = round((roa - 5) / 0.5)
    return _clamp_score(score)


def cal_pepb(val: float, a: float, b: float) -> float:
    """估值评分 (PE: a=3, b=0.4; PEG: a=1, b=0.1)
    估值越低分数越高
    """
    diff = round((val - a) / b)
    if diff < -5:
        diff = -5
    elif diff > 5:
        diff = 5
    return _clamp_score(5 - diff)


def calc_indicator_scores(code: str) -> dict:
    """
    计算10因子评分 (基于yfinance可用数据)
    每项0-10分, 总分100
    """
    info = fetch_stock_info(code)
    if not info:
        return {"total_score": 0}

    scores = {}

    # 1. 净利润增长率 (yoy)
    earnings_growth = (info.get("earnings_growth") or 0) * 100
    scores["net_profit_growth"] = round(cal_yoy(earnings_growth, 10), 1)

    # 2. 营收增长率 (yoy)
    revenue_growth = (info.get("revenue_growth") or 0) * 100
    scores["revenue_growth"] = round(cal_yoy(revenue_growth, 20), 1)

    # 3. 毛利率 (用 profit_margin 近似)
    profit_margin = (info.get("profit_margin") or 0) * 100
    scores["gross_margin"] = round(cal_exp(profit_margin - 30, 5), 1)  # 基准30%

    # 4. ROE
    roe = (info.get("roe") or 0) * 100
    scores["roe"] = round(cal_yoy(roe, 15), 1)

    # 5. ROA (简化: ROE * equity/assets, 用ROE近似)
    roa = roe * 0.6  # 粗略估计
    scores["roa"] = round(cal_roa(roa), 1)

    # 6. PE评分 (a=3%即PE~33为中性, b=0.4)
    pe = info.get("pe_ratio") or 30
    # 转换为收益率: 1/PE
    if pe > 0:
        pe_val = (1 / pe) * 100  # 百分比
        scores["pe"] = round(cal_pepb(pe_val, 3, 0.4), 1)
    else:
        scores["pe"] = 5.0

    # 7. PEG估算 (PE/增长率)
    if pe > 0 and earnings_growth > 0:
        peg = pe / earnings_growth
        scores["peg"] = round(cal_pepb(peg, 1, 0.1), 1)
    elif earnings_growth > 0:
        scores["peg"] = round(cal_pepb(earnings_growth / 10, 1, 0.1), 1)
    else:
        scores["peg"] = 5.0

    # 8-10: 未从yfinance获取到的维度给中性分
    scores["expense_ratio"] = 5.0   # 费用率
    scores["inventory_turnover"] = 5.0  # 存货周转
    scores["operating_cashflow"] = 5.0  # 经营现金流

    scores["total_score"] = round(sum(scores[k] for k in scores if k != "total_score"), 1)
    scores["pe_ratio"] = pe
    scores["roe_pct"] = round(roe, 1)
    scores["earnings_growth_pct"] = round(earnings_growth, 1)

    return scores


# ═══════════════════════════════════════════════════════════════
# 综合评分
# ═══════════════════════════════════════════════════════════════

def comprehensive_score(code: str, name: str, hist_df: pd.DataFrame | None = None) -> dict:
    """
    综合评分: RPS(50%) + 因子评分(50%)
    """
    rps = calc_rps_all_periods(code, df=hist_df)
    indicators = calc_indicator_scores(code)

    # RPS综合: 多周期加权
    rps_composite = (
        rps.get("rps_5", 0) * 0.1 +
        rps.get("rps_20", 0) * 0.2 +
        rps.get("rps_60", 0) * 0.3 +
        rps.get("rps_120", 0) * 0.4
    )
    # RPS归一化到0-100
    rps_score = max(0, min(100, rps_composite + 50))  # 中值50

    factor_score = indicators.get("total_score", 50)

    total = rps_score * 0.5 + factor_score * 0.5

    return {
        "code": code,
        "name": name,
        "total_score": round(total, 1),
        "rps_score": round(rps_score, 1),
        "factor_score": round(factor_score, 1),
        "rps_details": rps,
        "indicator_details": indicators,
    }


def screen_by_comprehensive(limit: int = 30, stock_limit: int = 200,
                           progress_callback=None) -> list[dict]:
    """综合评分筛选topN，并行获取数据，stock_limit控制评分股票数"""
    stocks = list(STOCK_POOL.items())
    # 只取前 stock_limit 只股票进行评分
    stocks = stocks[:stock_limit]
    total = len(stocks)

    # ── 并行预取历史数据 + 基本面信息 ──
    data_cache: dict[str, dict] = {}

    def _fetch_one(name: str, code: str):
        try:
            hist = fetch_stock_history(code, period="1y", timeout=8)
            info = fetch_stock_info(code)
            return code, {"name": name, "hist": hist, "info": info}
        except Exception:
            return code, {"name": name, "hist": pd.DataFrame(), "info": {}}

    completed = 0
    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = {pool.submit(_fetch_one, name, code): code for name, code in stocks}
        for f in as_completed(futures):
            code, data = f.result()
            data_cache[code] = data
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    # ── 计算评分 ──
    results = []
    for code, data in data_cache.items():
        name = data["name"]
        hist_df = data["hist"]
        if hist_df is None or hist_df.empty:
            continue
        try:
            score = comprehensive_score(code, name, hist_df=hist_df)
            results.append(score)
        except Exception as e:
            print(f"评分 {code} 失败: {e}")

    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results[:limit]
