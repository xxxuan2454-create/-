"""实时行情获取: 腾讯API / 新浪API / xtick API"""

import json
import re
import time
from datetime import datetime

import requests

from config import XTICK_API_TOKEN, XTICK_BASE_URL
from data.markets import is_cn_market, is_us_market


# ── 腾讯行情 API ──────────────────────────────────────────────
# 用法: qt.gtimg.cn/q=sh600519,sz000858
# 返回格式: v_sh600519="1~贵州茅台~600519~..." (GBK编码)

def _tencent_code(ticker: str) -> str:
    """将 600519.SS → sh600519, 000858.SZ → sz000858"""
    code_part = ticker.split(".")[0]
    if ticker.endswith(".SS"):
        return f"sh{code_part}"
    elif ticker.endswith(".SZ"):
        return f"sz{code_part}"
    return ticker


def fetch_realtime_tencent(codes: list[str]) -> dict[str, dict]:
    """通过腾讯API获取实时行情 (免费，无需API key)"""
    tc_codes = [_tencent_code(c) for c in codes if ".SS" in c or ".SZ" in c]
    if not tc_codes:
        return {}

    url = f"http://qt.gtimg.cn/q={','.join(tc_codes)}"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text
    except Exception:
        # Fallback to Sina
        return fetch_realtime_sina(codes)

    results = {}
    for line in text.strip().split("\n"):
        if "=" not in line or "v_" not in line:
            continue
        # 解析: v_sh600519="1~贵州茅台~600519~..."
        match = re.search(r'v_(\w+)="(.+)"', line)
        if not match:
            continue
        raw_code = match.group(1)  # sh600519
        data = match.group(2).split("~")

        # 恢复标准代码
        if raw_code.startswith("sh"):
            std_code = raw_code[2:] + ".SS"
        elif raw_code.startswith("sz"):
            std_code = raw_code[2:] + ".SZ"
        else:
            continue

        if len(data) < 40:
            continue

        results[std_code] = {
            "name": data[1],
            "code": data[2],
            "current_price": _safe_float(data[3]),
            "last_close": _safe_float(data[4]),
            "open": _safe_float(data[5]),
            "volume": _safe_int(data[6]),
            "high": _safe_float(data[33]),
            "low": _safe_float(data[34]),
            "change_pct": _safe_float(data[32]),
            "amount": _safe_float(data[37]),
            "turnover_rate": _safe_float(data[38]),
            "pe_ratio": _safe_float(data[39]),
            "update_time": data[30],
            "source": "tencent",
        }
    return results


# ── 新浪行情 API (备选) ──────────────────────────────────────

def _sina_code(ticker: str) -> str:
    code_part = ticker.split(".")[0]
    if ticker.endswith(".SS"):
        return f"sh{code_part}"
    elif ticker.endswith(".SZ"):
        return f"sz{code_part}"
    return ticker


def fetch_realtime_sina(codes: list[str]) -> dict[str, dict]:
    """通过新浪API获取实时行情"""
    sina_codes = [_sina_code(c) for c in codes if ".SS" in c or ".SZ" in c]
    if not sina_codes:
        return {}

    url = f"http://hq.sinajs.cn/list={','.join(sina_codes)}"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"
        text = resp.text
    except Exception:
        return {}

    results = {}
    for line in text.strip().split("\n"):
        if "hq_str_" not in line:
            continue
        match = re.search(r"hq_str_(\w+)=\"(.+)\"", line)
        if not match:
            continue
        raw_code = match.group(1)
        data = match.group(2).split(",")

        if raw_code.startswith("sh"):
            std_code = raw_code[2:] + ".SS"
        elif raw_code.startswith("sz"):
            std_code = raw_code[2:] + ".SZ"
        else:
            continue

        if len(data) < 30:
            continue

        results[std_code] = {
            "name": data[0],
            "open": _safe_float(data[1]),
            "last_close": _safe_float(data[2]),
            "current_price": _safe_float(data[3]),
            "high": _safe_float(data[4]),
            "low": _safe_float(data[5]),
            "volume": _safe_int(data[8]),
            "amount": _safe_float(data[9]),
            "change_pct": round((_safe_float(data[3]) - _safe_float(data[2])) / _safe_float(data[2]) * 100, 2) if _safe_float(data[2]) > 0 else 0,
            "update_time": f"{data[30]} {data[31]}",
            "source": "sina",
        }
    return results


# ── xtick API (用户提供token) ────────────────────────────────

def fetch_realtime_xtick(codes: list[str]) -> dict[str, dict]:
    """通过 xtick.top API 获取行情"""
    results = {}
    for code in codes:
        try:
            pure_code = code.split(".")[0]
            market = "sh" if code.endswith(".SS") else "sz"
            url = f"{XTICK_BASE_URL}/v1/stock/realtime"
            resp = requests.get(url, params={
                "token": XTICK_API_TOKEN,
                "code": f"{market}{pure_code}",
            }, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results[code] = _parse_xtick_response(data, code)
        except Exception as e:
            print(f"xtick 获取 {code} 失败: {e}")
    return results


def _parse_xtick_response(data: dict, code: str) -> dict:
    """解析xtick响应，适配常见字段名"""
    d = data.get("data", data)
    return {
        "name": d.get("name", ""),
        "code": code,
        "current_price": d.get("price") or d.get("current") or d.get("close", 0),
        "open": d.get("open", 0),
        "high": d.get("high", 0),
        "low": d.get("low", 0),
        "volume": d.get("volume", 0),
        "amount": d.get("amount", 0),
        "change_pct": d.get("change_pct") or d.get("pct_chg", 0),
        "pe_ratio": d.get("pe") or d.get("pe_ratio"),
        "source": "xtick",
    }


# ── yfinance 实时 (美股) ─────────────────────────────────────

def fetch_realtime_yfinance(codes: list[str]) -> dict[str, dict]:
    """通过 yfinance 获取美股最近行情 (基于最近交易日收盘价)"""
    import yfinance as yf

    results: dict[str, dict] = {}
    for code in codes:
        if not is_us_market(code):
            continue
        try:
            ticker = yf.Ticker(code)
            df = ticker.history(period="5d")
            if df.empty:
                continue
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            last_close = float(prev["Close"])
            current = float(latest["Close"])
            change_pct = round((current - last_close) / last_close * 100, 2) if last_close > 0 else 0.0
            vol = latest["Volume"]
            results[code] = {
                "name": code,
                "code": code,
                "current_price": current,
                "last_close": last_close,
                "open": float(latest["Open"]),
                "high": float(latest["High"]),
                "low": float(latest["Low"]),
                "volume": _safe_int(vol),
                "change_pct": change_pct,
                "source": "yfinance",
            }
        except Exception as e:
            print(f"yfinance 获取 {code} 失败: {e}")
    return results


# ── 统一接口 ──────────────────────────────────────────────────

def get_realtime_quotes(codes: list[str]) -> dict[str, dict]:
    """获取实时行情: A股 腾讯→新浪→xtick; 美股 yfinance"""
    cn_codes = [c for c in codes if is_cn_market(c)]
    us_codes = [c for c in codes if is_us_market(c)]

    results = fetch_realtime_tencent(cn_codes) if cn_codes else {}

    # A股: 腾讯未命中 → 新浪 → xtick
    missing_cn = [c for c in cn_codes if c not in results]
    if missing_cn:
        results.update(fetch_realtime_sina(missing_cn))
        missing_cn = [c for c in missing_cn if c not in results]
        if missing_cn and XTICK_API_TOKEN:
            results.update(fetch_realtime_xtick(missing_cn))

    # 美股: yfinance
    if us_codes:
        results.update(fetch_realtime_yfinance(us_codes))

    return results


def _safe_float(val) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0
