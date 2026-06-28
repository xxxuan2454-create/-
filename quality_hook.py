"""AI质量检测Hook - 检测输出质量，不达标自动重试"""

import re

from config import QUALITY_MIN_LENGTH, QUALITY_MAX_RETRIES
from db.store import log_quality


def clean_response(response: str) -> str:
    """清理AI输出中的噪音标记和免责声明"""
    # 去掉 HTML 注释（如 <!-- _retry_count: N -->）
    response = re.sub(r"<!--.*?-->", "", response, flags=re.DOTALL)
    # 去掉括号内的技术备注（如 (注：...）、（注：...））
    response = re.sub(r"[（(]注[：:][^）)]{0,300}[）)]", "", response)
    # 去掉末尾多余空行
    response = response.strip()
    return response


def check_divination_quality(response: str) -> tuple[bool, str]:
    """检测六爻解卦输出质量"""
    issues = []

    if len(response) < QUALITY_MIN_LENGTH:
        issues.append(f"响应过短({len(response)}字 < {QUALITY_MIN_LENGTH}字)")

    # 必须包含卦名或卦象描述
    has_gua = any(kw in response for kw in ["卦", "爻", "动爻", "本卦", "变卦", "体用", "生克"])
    if not has_gua:
        issues.append("缺少卦象解读内容")

    # 必须包含涨跌结论
    has_conclusion = any(kw in response for kw in ["【预测结论】", "方向", "涨", "跌", "平", "看涨", "看跌"])
    if not has_conclusion:
        issues.append("缺少涨跌预测结论")

    # 不能出现推脱/免责用语
    refusal_patterns = [
        "作为AI", "无法预测", "我无法", "这超出了", "我不能",
        "as an AI", "I cannot predict", "I cannot provide",
        "没有参考函数", "没有实时", "无法获取实时", "没有相关工具",
        "没有工具", "缺乏参考", "无法查询实时", "不具备实时",
    ]
    for pattern in refusal_patterns:
        if pattern.lower() in response.lower():
            issues.append(f"检测到推脱用语: '{pattern}'")
            break

    return (len(issues) == 0, "; ".join(issues))


def check_analysis_quality(response: str) -> tuple[bool, str]:
    """检测多智能体分析输出质量"""
    issues = []

    if len(response) < QUALITY_MIN_LENGTH:
        issues.append(f"响应过短({len(response)}字 < {QUALITY_MIN_LENGTH}字)")

    # 应包含各角色分析
    roles = ["技术", "基本面", "情绪", "综合", "建议"]
    found_roles = sum(1 for r in roles if r in response)
    if found_roles < 2:
        issues.append(f"分析角色覆盖不足 ({found_roles}/{len(roles)})")

    has_conclusion = any(kw in response for kw in ["结论", "建议", "买入", "卖出", "持有", "buy", "sell", "hold"])
    if not has_conclusion:
        issues.append("缺少投资建议或结论")

    return (len(issues) == 0, "; ".join(issues))


def quality_check_and_retry(call_fn, input_text: str, call_type: str) -> tuple[str, int]:
    """
    包装AI调用，检测质量，不达标自动重试
    返回 (响应字符串, 重试次数)
    """
    check_fn = {
        "divination": check_divination_quality,
        "analysis": check_analysis_quality,
    }.get(call_type)

    last_response = ""
    last_error = ""

    for attempt in range(QUALITY_MAX_RETRIES + 1):
        try:
            response = call_fn()
            if not isinstance(response, str):
                response = str(response)

            response = clean_response(response)

            if check_fn is None:
                return response, attempt

            passed, reason = check_fn(response)

            log_quality(
                call_type=call_type,
                input_text=input_text,
                retry_count=attempt,
                quality_passed=passed,
                fail_reason=reason if not passed else "",
                response_length=len(response),
            )

            if passed:
                return response, attempt

            last_error = reason
            last_response = response

        except Exception as e:
            last_error = f"调用异常: {str(e)}"
            log_quality(
                call_type=call_type,
                input_text=input_text,
                retry_count=attempt,
                quality_passed=False,
                fail_reason=last_error,
                response_length=0,
            )

    # 所有重试都失败，返回最后一次响应（若有）或空提示
    log_quality(
        call_type=call_type,
        input_text=input_text,
        retry_count=QUALITY_MAX_RETRIES,
        quality_passed=False,
        fail_reason=f"最终失败: {last_error}",
        response_length=len(last_response),
    )

    if last_response:
        return last_response, QUALITY_MAX_RETRIES

    return "AI解卦服务暂时不可用，请稍后再试。", QUALITY_MAX_RETRIES
