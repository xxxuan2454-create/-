"""TradingAgents 多智能体分析 - 模拟多角色分析 + 辩论"""

import pandas as pd
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, AI_MODEL
from data.fetcher import fetch_stock_history, fetch_stock_info, fetch_news
from quality_hook import quality_check_and_retry


def _get_technical_data(code: str) -> dict:
    """获取技术分析所需数据 (powered by akquant TA-Lib)"""
    from data.technical import compute_all_indicators, compute_weekly_indicators, indicator_summary_text
    inds = compute_all_indicators(code, period="6mo")
    weekly = compute_weekly_indicators(code)

    if not inds or inds.get("data_points", 0) < 30:
        return {}

    return {
        **inds,
        **weekly,
        "summary": indicator_summary_text(inds),
    }


def _get_fundamental_data(code: str) -> dict:
    """获取基本面数据"""
    info = fetch_stock_info(code)
    if not info:
        return {}
    return {
        "sector": info.get("sector", "未知"),
        "industry": info.get("industry", "未知"),
        "market_cap": info.get("market_cap"),
        "pe": info.get("pe_ratio"),
        "pb": info.get("pb_ratio"),
        "roe": round((info.get("roe") or 0) * 100, 1),
        "profit_margin": round((info.get("profit_margin") or 0) * 100, 1),
        "revenue_growth": round((info.get("revenue_growth") or 0) * 100, 1),
        "earnings_growth": round((info.get("earnings_growth") or 0) * 100, 1),
        "debt_to_equity": info.get("debt_to_equity"),
        "beta": info.get("beta"),
        "dividend_yield": round((info.get("dividend_yield") or 0) * 100, 2),
    }


def build_multi_agent_prompt(stock_name: str, stock_code: str,
                             technical: dict, fundamental: dict) -> str:
    """构建多智能体分析提示词"""
    tech_summary = technical.get("summary", _format_dict(technical)) if technical else "暂无技术数据"

    return f"""你是一个由多位分析师组成的投资研究团队。请对以下A股进行多维度分析。

## 股票信息
- 名称: {stock_name}
- 代码: {stock_code}

## 技术面数据 (akquant TA-Lib 计算)
{tech_summary}

## 基本面数据
{_format_dict(fundamental)}

## 角色扮演要求

请依次以以下三位分析师的视角进行分析，每人不少于100字:

### 🔬 技术分析师
从RSI、MACD、ADX趋势强度、布林带位置、ATR波动率、成交量(OBV/MFI)、随机指标(StochKD)、CCI等角度全面分析该股的技术面走势和短期方向。

### 📊 基本面分析师
从PE/PB估值、ROE、利润率、增长率、行业地位等角度评估该股的投资价值。

### 📰 情绪分析师
从近期走势、技术指标多空信号、波动率环境角度分析市场情绪和多空力量。

### ⚔️ 辩论环节
看涨方与看跌方各给出核心论点。

### 🎯 综合结论
在分析末尾，用以下格式给出最终建议:

【最终建议】
- 操作: [买入/持有/卖出]
- 置信度: [0.0-1.0]
- 核心逻辑: [一句话总结]

请确保分析深入、观点明确，回答长度不少于400字。"""


def _format_dict(d: dict) -> str:
    if not d:
        return "暂无数据"
    return "\n".join(f"  {k}: {v}" for k, v in d.items())


def analyze_single_stock(stock_name: str, stock_code: str) -> dict:
    """
    对单只股票进行多智能体分析
    返回完整的分析结果
    """
    technical = _get_technical_data(stock_code)
    fundamental = _get_fundamental_data(stock_code)
    prompt = build_multi_agent_prompt(stock_name, stock_code, technical, fundamental)

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    def call_fn():
        response = client.chat.completions.create(
            model=AI_MODEL,
            max_tokens=3000,
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    response, _ = quality_check_and_retry(
        call_fn=call_fn,
        input_text=prompt,
        call_type="analysis",
    )

    # 解析结论
    action = "持有"
    confidence = 0.5
    for line in response.split("\n"):
        if "操作" in line or "action" in line.lower():
            if "买入" in line:
                action = "买入"
            elif "卖出" in line:
                action = "卖出"
            elif "持有" in line:
                action = "持有"
        if "置信度" in line or "confidence" in line.lower():
            import re
            nums = re.findall(r"([\d.]+)", line)
            if nums:
                confidence = min(max(float(nums[0]) / (100 if float(nums[0]) > 1 else 1), 0.0), 1.0)

    return {
        "code": stock_code,
        "name": stock_name,
        "technical": technical,
        "fundamental": fundamental,
        "analysis": response,
        "action": action,
        "confidence": confidence,
        "retry_count": 0,
    }
