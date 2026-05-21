"""CrewAI 多智能体分析 - 每个角色独立 Agent + 任务编排"""

import re
from crewai import Agent, Task, Crew, Process, LLM
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, AI_MODEL
from quality_hook import quality_check_and_retry

from strategies.trading_agents import _get_technical_data, _get_fundamental_data, _format_dict


def _build_llm() -> LLM:
    return LLM(
        model=f"openai/{AI_MODEL}",
        base_url=DEEPSEEK_BASE_URL,
        api_key=DEEPSEEK_API_KEY,
        temperature=0.5,
        max_tokens=3000,
    )


def _build_agents() -> tuple[Agent, Agent, Agent, Agent, Agent]:
    """构建五个独立 Agent：技术/基本面/情绪/辩论主持/综合策略"""
    llm = _build_llm()

    technical_analyst = Agent(
        role="技术分析师",
        goal="从技术指标角度全面分析股票走势，给出多空判断和关键价位",
        backstory=(
            "你是一位拥有15年经验的A股技术分析师，精通RSI、MACD、ADX、布林带、"
            "ATR、CCI、随机指标(StochKD)、OBV/MFI量价指标、均线系统等技术工具。"
            "你擅长识别趋势转换点、背离信号和关键支撑阻力位。"
        ),
        llm=llm,
        verbose=True,
    )

    fundamental_analyst = Agent(
        role="基本面分析师",
        goal="从估值、盈利能力、成长性和行业地位角度评估股票的内在价值",
        backstory=(
            "你是一位资深价值投资者，曾在顶级公募基金担任研究员10年。"
            "你擅长解读PE/PB估值分位、ROE杜邦分析、利润率和增速质量、行业竞争格局。"
            "你注重安全边际和长期持有价值，但也理解成长股的合理溢价。"
        ),
        llm=llm,
        verbose=True,
    )

    sentiment_analyst = Agent(
        role="情绪分析师",
        goal="解读市场情绪和多空力量对比，判断当前是否处于极端情绪区域",
        backstory=(
            "你是一位量化情绪分析专家，专注于从技术指标的信号共振、"
            "波动率环境、成交量变化中捕捉市场情绪拐点。"
            "你相信贪婪与恐惧的轮回，擅长识别超买超卖的极端区域。"
        ),
        llm=llm,
        verbose=True,
    )

    debate_moderator = Agent(
        role="辩论主持人",
        goal="组织看涨方与看跌方的辩论，提炼双方最有力的核心论点",
        backstory=(
            "你是一位经验丰富的投资委员会主席，主持过上千场投资决策辩论。"
            "你要求双方用事实和数据说话，拒绝空洞的口号。"
            "你能敏锐识别逻辑漏洞和认知偏差，确保辩论结论经得起推敲。"
        ),
        llm=llm,
        verbose=True,
    )

    strategist = Agent(
        role="首席策略官",
        goal="综合各方分析，做出最终投资决策：买入/持有/卖出，并给出置信度",
        backstory=(
            "你是一位顶级对冲基金的首席投资官，管理百亿规模组合。"
            "你的决策风格冷静理性，绝不情绪化，严格基于概率思维。"
            "你会综合技术、基本面、情绪三方意见，权衡风险收益比后给出明确判断。"
        ),
        llm=llm,
        verbose=True,
    )

    return technical_analyst, fundamental_analyst, sentiment_analyst, debate_moderator, strategist


def _build_tasks(
    stock_name: str,
    stock_code: str,
    technical_data: dict,
    fundamental_data: dict,
    agents: tuple[Agent, Agent, Agent, Agent, Agent],
) -> list[Task]:
    """构建任务链：技术分析 → 基本面 → 情绪 → 辩论 → 综合结论"""
    tech_agent, fund_agent, sent_agent, debate_agent, strat_agent = agents

    tech_summary = technical_data.get("summary", _format_dict(technical_data)) if technical_data else "暂无技术数据"
    fund_summary = _format_dict(fundamental_data) if fundamental_data else "暂无基本面数据"

    task_technical = Task(
        description=f"""
对股票 **{stock_name}**（{stock_code}）进行技术分析。

以下是 akquant TA-Lib 计算的技术指标数据：
{tech_summary}

请从以下维度分析：
1. 趋势判断：多/空/震荡，依据均线排列和ADX
2. 动量信号：RSI、MACD、随机指标的共振方向
3. 波动率环境：布林带和ATR给出的波动区间
4. 成交量：MFI/OBV的多空含义
5. 关键支撑/阻力位
6. 短期（1-2周）技术面展望

输出结构化分析，不少于200字。
""",
        expected_output="技术分析报告，包含趋势判断、动量信号、关键价位和短期展望",
        agent=tech_agent,
    )

    task_fundamental = Task(
        description=f"""
对股票 **{stock_name}**（{stock_code}）进行基本面分析。

基本面数据：
{fund_summary}

请从以下维度分析：
1. 估值水平：PE/PB是否合理，与行业均值对比
2. 盈利能力：ROE和利润率反映的竞争优势
3. 成长性：营收和利润增速的质量与可持续性
4. 财务健康度：负债率、现金流情况
5. 行业地位和护城河评估

输出结构化分析，不少于200字。
""",
        expected_output="基本面分析报告，包含估值判断、盈利质量、成长性评估",
        agent=fund_agent,
    )

    task_sentiment = Task(
        description=f"""
对股票 **{stock_name}**（{stock_code}）进行市场情绪分析。

参考技术数据中的RSI、CCI、布林带位置、MFI等指标，分析：
1. 当前市场情绪处于什么阶段（恐慌/怀疑/乐观/狂热）
2. 技术指标的信号共振是偏多还是偏空
3. 是否存在超买或超卖的极端信号
4. 波动率环境对情绪的影响
5. 多空力量对比

输出结构化分析，不少于150字。
""",
        expected_output="情绪分析报告，包含情绪阶段判断、信号共振方向、极端信号识别",
        agent=sent_agent,
    )

    task_debate = Task(
        description=f"""
基于前三位分析师对 **{stock_name}**（{stock_code}）的报告，组织一场多空辩论。

请输出：
1. 🟢 看涨方核心论点（3条，每条用数据支撑）
2. 🔴 看跌方核心论点（3条，每条用数据支撑）
3. ⚖️ 辩论总结：哪方论据更有说服力，为什么

不少于200字。
""",
        expected_output="多空辩论记录，包含双方3条核心论点和辩论总结",
        agent=debate_agent,
    )

    task_conclusion = Task(
        description=f"""
综合前四位分析师和辩论主持对 **{stock_name}**（{stock_code}）的全面分析，给出最终投资建议。

请组织输出：
1. 三方分析摘要（技术/基本面/情绪各一句话）
2. 辩论结论摘要
3. 风险提示

并在末尾严格按以下格式给出结论：
【最终建议】
- 操作: [买入/持有/卖出]
- 置信度: [0.0-1.0]
- 核心逻辑: [一句话总结]

不少于250字。
""",
        expected_output="综合投资建议，包含三方摘要、风险提示和最终操作建议",
        agent=strat_agent,
    )

    return [task_technical, task_fundamental, task_sentiment, task_debate, task_conclusion]


def analyze_single_stock(stock_name: str, stock_code: str) -> dict:
    """
    使用 CrewAI 多智能体框架对单只股票进行分析
    5个独立 Agent 各司其职，协作完成分析
    """
    technical = _get_technical_data(stock_code)
    fundamental = _get_fundamental_data(stock_code)

    agents = _build_agents()
    tasks = _build_tasks(stock_name, stock_code, technical, fundamental, agents)

    crew = Crew(
        agents=list(agents),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    raw_output = str(result)

    action = "持有"
    confidence = 0.5
    for line in raw_output.split("\n"):
        if "操作" in line or "action" in line.lower():
            if "买入" in line:
                action = "买入"
            elif "卖出" in line:
                action = "卖出"
            elif "持有" in line:
                action = "持有"
        if "置信度" in line or "confidence" in line.lower():
            nums = re.findall(r"([\d.]+)", line)
            if nums:
                confidence = min(max(float(nums[0]) / (100 if float(nums[0]) > 1 else 1), 0.0), 1.0)

    return {
        "code": stock_code,
        "name": stock_name,
        "technical": technical,
        "fundamental": fundamental,
        "analysis": raw_output,
        "action": action,
        "confidence": confidence,
        "retry_count": 0,
    }
