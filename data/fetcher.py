"""股票数据获取 - akshare (国内源) + yfinance (备用) + 本地缓存"""

import json
import time
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import STOCK_POOL, INDEX_CODES, DATA_CACHE_DIR

# 国内访问 yfinance 可能很慢，统一超时 6 秒
_YF_TIMEOUT = 6


# ── akshare 国内数据源 ──────────────────────────────────────────

def _ak_code(yf_code: str) -> str:
    """yfinance 代码 → akshare Tencent 代码: 600519.SS → sh600519"""
    if yf_code.endswith(".SS"):
        return f"sh{yf_code[:-3]}"
    elif yf_code.endswith(".SZ"):
        return f"sz{yf_code[:-3]}"
    elif yf_code.endswith(".BJ"):
        return f"bj{yf_code[:-3]}"
    return yf_code


def _parse_date(date_str: str, default_year: str = "2024") -> str:
    """将 akshare 返回的 '01-02' 格式转为 'YYYY-MM-DD'"""
    parts = date_str.strip().split("-")
    if len(parts) == 3:
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    elif len(parts) == 2:
        return f"{default_year}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
    return date_str


def fetch_stock_history_ak(code: str, period: str = "1y") -> pd.DataFrame:
    """通过 akshare (腾讯源) 获取单只股票历史日线，快于 yfinance ~30%"""
    import akshare as ak

    cache = _read_cache(f"ak_hist_{code}_{period}")
    if cache:
        df = pd.DataFrame(cache["data"])
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        return df

    # 计算起止日期
    end_date = datetime.now().strftime("%Y%m%d")
    days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
    days = days_map.get(period, 365)
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    ak_symbol = _ak_code(code)

    for attempt in range(2):
        try:
            raw = ak.stock_zh_a_hist_tx(
                symbol=ak_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            if raw.empty:
                time.sleep(0.5)
                continue

            df = pd.DataFrame()
            df["open"] = raw["open"]
            df["high"] = raw["high"]
            df["low"] = raw["low"]
            df["close"] = raw["close"]
            df["volume"] = raw["amount"]  # akshare Tencent 的 amount 即为成交量(手)
            df["date"] = pd.to_datetime(raw["date"])
            df = df.set_index("date").sort_index()

            _write_cache(f"ak_hist_{code}_{period}", {"data": df.reset_index().to_dict(orient="records")})
            return df
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
            else:
                print(f"akshare 获取 {code} 失败: {e}")

    return pd.DataFrame()


def _with_timeout(fn, timeout=_YF_TIMEOUT):
    """在线程中执行，超时返回默认值避免阻塞整个页面"""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn)
            return future.result(timeout=timeout)
    except Exception:
        return None


def _get_ticker(code: str) -> yf.Ticker:
    """获取 Ticker，禁用自动重试减少等待"""
    ticker = yf.Ticker(code)
    return ticker


def _cache_path(code: str) -> Path:
    return DATA_CACHE_DIR / f"{code.replace('.', '_')}.json"


def _read_cache(code: str) -> dict | None:
    p = _cache_path(code)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        cached_time = datetime.fromisoformat(data["cached_at"])
        # 当天缓存有效
        if cached_time.date() == datetime.now().date():
            return data
        return None
    except (json.JSONDecodeError, KeyError, ValueError):
        # 缓存损坏则删除，下次重新获取
        p.unlink(missing_ok=True)
        return None


def _write_cache(code: str, data: dict) -> None:
    data["cached_at"] = datetime.now().isoformat()
    _cache_path(code).write_text(json.dumps(data, ensure_ascii=False, default=str))


def _yf_code(ticker: str) -> str:
    """将本地代码格式转为 yfinance 格式"""
    return ticker  # yfinance 直接支持 600519.SS / 000858.SZ


def fetch_stock_history(code: str, period: str = "6mo", timeout: int = _YF_TIMEOUT,
                      source: str = "akshare") -> pd.DataFrame:
    """获取单只股票历史日线数据 (akshare国内源优先，yfinance备用)"""
    cache = _read_cache(f"history_{code}_{period}")
    if cache:
        return pd.DataFrame(cache["data"])

    # ── akshare (国内源，更快更稳) ──
    if source == "akshare":
        df = fetch_stock_history_ak(code, period)
        if not df.empty:
            _write_cache(f"history_{code}_{period}", {"data": df.reset_index().to_dict(orient="records")})
            return df

    # ── yfinance 备用 ──
    def _fetch():
        ticker = yf.Ticker(_yf_code(code))
        df = ticker.history(period=period)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        df.columns = [c.lower() for c in df.columns]
        return df

    result = _with_timeout(_fetch, timeout=timeout)
    if result is None or (isinstance(result, pd.DataFrame) and result.empty):
        time.sleep(1)
        result = _with_timeout(_fetch, timeout=timeout)

    if result is None or (isinstance(result, pd.DataFrame) and result.empty):
        return pd.DataFrame()

    _write_cache(f"history_{code}", {"data": result.reset_index().to_dict(orient="records")})
    return result


def fetch_stock_info(code: str) -> dict:
    """获取股票基本信息（名称、行业、PE/PB等）"""
    cache = _read_cache(f"info_{code}")
    if cache:
        return cache["data"]

    try:
        ticker = yf.Ticker(_yf_code(code))
        info = ticker.info
        result = {
            "name": info.get("longName") or info.get("shortName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margin": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "beta": info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "fifty_day_avg": info.get("fiftyDayAverage"),
            "two_hundred_day_avg": info.get("twoHundredDayAverage"),
        }
        _write_cache(f"info_{code}", {"data": result})
        return result
    except Exception as e:
        print(f"获取 {code} 信息失败: {e}")
        return {}


def fetch_multiple_stocks(codes: list[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    """批量获取多只股票历史数据"""
    results = {}
    for i, code in enumerate(codes):
        df = fetch_stock_history(code, period)
        if not df.empty:
            results[code] = df
        if i > 0 and i % 10 == 0:
            time.sleep(0.5)  # 避免请求过快
    return results


def get_stock_pool_data(period: str = "6mo") -> pd.DataFrame:
    """获取股票池所有股票的最近数据"""
    rows = []
    for name, code in STOCK_POOL.items():
        try:
            df = fetch_stock_history(code, period)
            if df.empty:
                continue
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            change_pct = ((latest["close"] - prev["close"]) / prev["close"]) * 100 if len(df) > 1 else 0
            rows.append({
                "name": name,
                "code": code,
                "close": latest["close"],
                "volume": latest.get("volume", 0),
                "change_pct": round(change_pct, 2),
                "high": latest.get("high", 0),
                "low": latest.get("low", 0),
                "open": latest.get("open", 0),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


def fetch_index_data() -> dict[str, float]:
    """获取大盘指数 (并行 + 超时)"""
    result = {}

    def _fetch_one(name: str, code: str) -> tuple[str, float]:
        try:
            ticker = yf.Ticker(code)
            df = ticker.history(period="2d")
            if len(df) >= 2:
                change_pct = ((df.iloc[-1]["Close"] - df.iloc[-2]["Close"]) / df.iloc[-2]["Close"]) * 100
                return name, round(change_pct, 2)
            return name, 0.0
        except Exception:
            return name, 0.0

    # 并行获取所有指数
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(INDEX_CODES)) as executor:
        futures = {executor.submit(_fetch_one, name, code): name for name, code in INDEX_CODES.items()}
        for future in concurrent.futures.as_completed(futures, timeout=_YF_TIMEOUT + 2):
            try:
                name, val = future.result(timeout=1)
                result[name] = val
            except Exception:
                name = futures[future]
                result[name] = 0.0

    # 确保所有指数都有值
    for name in INDEX_CODES:
        if name not in result:
            result[name] = 0.0

    return result


def fetch_financial_data(code: str) -> dict:
    """获取财务数据用于多因子评分"""
    cache = _read_cache(f"financial_{code}")
    if cache:
        return cache["data"]

    try:
        ticker = yf.Ticker(_yf_code(code))

        # 利润表
        income = ticker.financials
        # 资产负债表
        balance = ticker.balance_sheet
        # 现金流量表
        cashflow = ticker.cashflow

        result = {
            "net_income": _safe_series(income, "Net Income"),
            "total_revenue": _safe_series(income, "Total Revenue"),
            "gross_profit": _safe_series(income, "Gross Profit"),
            "operating_expense": _safe_series(income, "Operating Expense"),
            "total_assets": _safe_series(balance, "Total Assets"),
            "total_equity": _safe_series(balance, "Stockholders Equity"),
            "total_inventory": _safe_series(balance, "Inventory"),
            "operating_cashflow": _safe_series(cashflow, "Operating Cash Flow"),
            "capital_expenditure": _safe_series(cashflow, "Capital Expenditure"),
        }
        _write_cache(f"financial_{code}", {"data": result})
        return result
    except Exception as e:
        print(f"获取 {code} 财务数据失败: {e}")
        return {}


def _safe_series(df: pd.DataFrame, field: str) -> list[float]:
    """安全获取财务字段"""
    if df is None or df.empty or field not in df.index:
        return []
    row = df.loc[field]
    return [float(v) for v in row.values if pd.notna(v)]


def fetch_news(code: str, count: int = 5) -> list[dict]:
    """获取股票相关新闻"""
    try:
        ticker = yf.Ticker(_yf_code(code))
        news = ticker.news[:count]
        return [{"title": n.get("title", ""), "publisher": n.get("publisher", ""),
                 "link": n.get("link", ""), "published": n.get("providerPublishTime", "")} for n in news]
    except Exception:
        return []
