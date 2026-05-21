"""AI解卦 + 股价涨跌预测"""

import json
from datetime import datetime

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, AI_MODEL
from divination.liuyao import cast_full_hexagram, format_divination_result
from quality_hook import quality_check_and_retry


def build_prediction_prompt(
    stock_name: str,
    stock_code: str,
    current_price: float,
    change_pct: float,
    technical_summary: str,
    divination_text: str,
) -> str:
    """构建AI预测提示词"""
    return f"""你是一位精通六爻占卜和股票技术分析的资深分析师。请你根据以下信息，对该股票未来一个交易日的涨跌做出预测。

## 股票信息
- 名称: {stock_name}
- 代码: {stock_code}
- 当前价格: {current_price}
- 今日涨跌幅: {change_pct}%
- 近期技术面: {technical_summary}

{divination_text}

## 分析要求

请你按照以下步骤进行分析：

### 1. 卦象解读
- 本卦的含义、变卦的含义
- 体用生克关系解读
- 动爻的爻辞解读及其对走势的暗示
- 六亲在动爻中的体现

### 2. 卦象与股价关联分析
- 将卦象的吉凶与股票走势关联
- 结合当前技术面给出综合判断
- 分析体用生克对多空力量的影响

### 3. 涨跌预测
请在分析末尾，用以下固定格式给出结论:

【预测结论】
- 方向: [涨/跌/平] (三选一)
- 置信度: [0.0-1.0]
- 操作建议: [一句话建议]

请确保分析完整、有理有据，不要敷衍。回答长度不少于200字。"""


def predict_stock(
    stock_name: str,
    stock_code: str,
    current_price: float = 0.0,
    change_pct: float = 0.0,
    technical_summary: str = "暂无技术面数据",
) -> dict:
    """
    执行一次完整的六爻占卜 + AI预测
    返回预测结果字典
    """
    # 1. 起卦
    divination_result = cast_full_hexagram()
    divination_text = format_divination_result(divination_result)

    # 2. 构建提示词
    prompt = build_prediction_prompt(
        stock_name=stock_name,
        stock_code=stock_code,
        current_price=current_price,
        change_pct=change_pct,
        technical_summary=technical_summary,
        divination_text=divination_text,
    )

    # 3. 调用AI (带质量检测)
    ai_response, retry_count = _call_llm(prompt)

    # 4. 解析AI响应
    parsed = _parse_prediction_response(ai_response)

    return {
        "divination": divination_result,
        "divination_text": divination_text,
        "ai_full_response": ai_response,
        "prediction": parsed["direction"],
        "confidence": parsed["confidence"],
        "analysis": ai_response,
        "retry_count": retry_count,
    }


def _call_llm(prompt: str) -> tuple:
    """调用DeepSeek API (带质量检测)，返回 (response, retry_count)"""
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    def call_fn():
        response = client.chat.completions.create(
            model=AI_MODEL,
            max_tokens=2000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    return quality_check_and_retry(
        call_fn=call_fn,
        input_text=prompt,
        call_type="divination",
    )


def _parse_prediction_response(response: str) -> dict:
    """从AI响应中解析预测方向和置信度"""
    direction = "平"
    confidence = 0.5

    # 查找【预测结论】标记
    lines = response.split("\n")
    for line in lines:
        line = line.strip()
        if "方向" in line or "direction" in line.lower():
            if "涨" in line:
                direction = "涨"
            elif "跌" in line:
                direction = "跌"
            elif "平" in line:
                direction = "平"
        if "置信度" in line or "confidence" in line.lower():
            try:
                # 提取数字
                import re
                nums = re.findall(r"([\d.]+)", line)
                if nums:
                    confidence = float(nums[0])
                    if confidence > 1:
                        confidence = confidence / 100
                    confidence = min(max(confidence, 0.0), 1.0)
            except (ValueError, IndexError):
                pass

    # 如果在结论部分没找到，从全文判断
    if direction == "平" and ("看涨" in response or "上涨" in response):
        direction = "涨"
    elif direction == "平" and ("看跌" in response or "下跌" in response):
        direction = "跌"

    return {"direction": direction, "confidence": confidence}


def predict_multiple_stocks(
    stocks: list[dict],
    technical_data: dict = None,
) -> list[dict]:
    """批量预测多只股票"""
    results = []
    for stock in stocks:
        tech = (technical_data or {}).get(stock.get("code", ""), "暂无数据")
        result = predict_stock(
            stock_name=stock.get("name", ""),
            stock_code=stock.get("code", ""),
            current_price=stock.get("price", 0),
            change_pct=stock.get("change_pct", 0),
            technical_summary=str(tech),
        )
        results.append(result)
    return results
