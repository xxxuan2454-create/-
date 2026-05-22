"""多智能体分析页面 - CrewAI 架构"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from strategies.trading_agents import _get_technical_data, _get_fundamental_data
from data.fetcher import fetch_stock_history
from config import STOCK_POOL
import math


def _sfmt(v, template="{}", default="N/A"):
    """NaN/None-safe format, returns default for NaN/None values"""
    if v is None:
        return default
    try:
        if math.isnan(float(v)):
            return default
    except (TypeError, ValueError):
        pass
    return template.format(v)


def show():
    st.markdown("# 🤖 多智能体股票分析")

    st.markdown("""
    基于 **CrewAI** 多智能体框架，5个独立 AI Agent 各司其职：
    **技术分析师** → **基本面分析师** → **情绪分析师** → **辩论主持人** → **首席策略官**
    """)

    # ── 选股 ──
    st.markdown("### 选择分析标的")

    linked = st.session_state.get("active_stock")

    search_query = st.text_input(
        "搜索股票名称或代码",
        placeholder="输入关键词搜索...",
        key="ma_search_input",
    )

    if search_query:
        from data.stock_list import search_all_stocks
        results = search_all_stocks(search_query, limit=15)
        if results:
            stock_options = {r["name"]: r["code"] for r in results}
            # 联动股票如果在结果中，默认选中它
            default_idx = 0
            if linked:
                for i, r in enumerate(results):
                    if r["code"] == linked["code"]:
                        default_idx = i
                        break
            selected_name = st.selectbox(
                "选择股票", options=list(stock_options.keys()),
                index=default_idx, key="ma_stock_select",
            )
            selected_code = stock_options[selected_name]
        else:
            st.warning("无匹配股票")
            selected_name = list(STOCK_POOL.keys())[0]
            selected_code = STOCK_POOL[selected_name]
    else:
        if linked:
            selected_name = linked["name"]
            selected_code = linked["code"]
            st.info(f"📌 从其他页面联动: **{linked['name']}** ({linked['code']})，上方搜索框可随时更换股票")
        else:
            selected_name = list(STOCK_POOL.keys())[0]
            selected_code = STOCK_POOL[selected_name]
            st.info("输入股票名称或代码搜索，选中后将自动联动到「🔮 六爻占卜」页面")

    # ── 联动到六爻占卜 ──
    st.session_state["active_stock"] = {"name": selected_name, "code": selected_code}

    # ── 当前分析股票 ──
    st.markdown(f"## 📌 当前分析股票: **{selected_name}** ({selected_code})")
    st.caption("🔗 已联动到「🔮 六爻占卜」，切换侧边栏即可直接起卦")

    # ── 技术面预览 ──
    st.markdown("---")
    st.markdown("### 📊 技术面一览")

    technical = _get_technical_data(selected_code)
    fundamental = _get_fundamental_data(selected_code)

    if technical:
        st.markdown("#### 动量指标")
        cols = st.columns(4)
        with cols[0]:
            st.metric("价格", _sfmt(technical.get('price'), "¥{:.2f}"))
        with cols[1]:
            st.metric("RSI(14)", _sfmt(technical.get("rsi_14"), "{:.1f}"))
        with cols[2]:
            st.metric("MACD柱", _sfmt(technical.get("macd_hist"), "{:.4f}"))
        with cols[3]:
            st.metric("ADX(14)", _sfmt(technical.get("adx_14"), "{:.1f}"))

        st.markdown("#### 趋势与波动")
        cols2 = st.columns(4)
        with cols2[0]:
            st.metric("MA30(日)", _sfmt(technical.get("sma_20"), "¥{:.2f}"))
        with cols2[1]:
            st.metric("MA50(日)", _sfmt(technical.get("sma_50"), "¥{:.2f}"))
        with cols2[2]:
            st.metric("布林上轨", _sfmt(technical.get("bb_upper"), "¥{:.2f}"))
        with cols2[3]:
            st.metric("布林下轨", _sfmt(technical.get("bb_lower"), "¥{:.2f}"))

        st.markdown("#### 周线与量价")
        cols3 = st.columns(4)
        with cols3[0]:
            st.metric("MA10(周)", _sfmt(technical.get("ma10w"), "¥{:.2f}"))
        with cols3[1]:
            st.metric("MFI(14)", _sfmt(technical.get("mfi_14"), "{:.1f}"))
        with cols3[2]:
            st.metric("CCI(14)", _sfmt(technical.get("cci_14"), "{:.1f}"))
        with cols3[3]:
            st.metric("ATR(14)", _sfmt(technical.get("atr_14"), "{:.2f}"))

    # ── 基本面一览 ──
    if fundamental:
        st.markdown("### 📋 基本面一览")
        cols = st.columns(4)
        with cols[0]:
            st.metric("PE", _sfmt(fundamental.get("pe")))
        with cols[1]:
            st.metric("PB", _sfmt(fundamental.get("pb")))
        with cols[2]:
            st.metric("ROE", _sfmt(fundamental.get("roe"), "{}%"))
        with cols[3]:
            st.metric("利润增速", _sfmt(fundamental.get("earnings_growth"), "{}%"))

    # ── 近3月K线 ──
    hist_df = fetch_stock_history(selected_code, period="3mo")
    if not hist_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=hist_df.index,
            open=hist_df["open"],
            high=hist_df["high"],
            low=hist_df["low"],
            close=hist_df["close"],
            name=selected_name, showlegend=False,
        ))
        try:
            import akquant as aq
            close = hist_df["close"]
            ma15 = aq.talib.SMA(close, timeperiod=15, as_series=True)
            ma30 = aq.talib.SMA(close, timeperiod=30, as_series=True)
            for ma_line, c, n in [(ma15, "#ff9800", "MA15(日)"), (ma30, "#42a5f5", "MA30(日)")]:
                fig.add_trace(go.Scatter(x=hist_df.index, y=ma_line, mode="lines",
                                         name=n, line=dict(color=c, width=1)))
        except ImportError:
            pass
        fig.update_layout(height=350, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

    # ── 启动多智能体分析 ──
    st.markdown("---")
    st.markdown("### 🚀 启动多智能体分析")

    if st.button("🧠 开始多智能体分析", type="primary", use_container_width=True):
        if not _has_api_key():
            st.error("请设置 DEEPSEEK_API_KEY 环境变量后重启应用。")
            return

        with st.spinner("""
        🧠 CrewAI 多智能体协作中...
        - 技术分析师 Agent 正在分析MACD/RSI/K线形态
        - 基本面分析师 Agent 正在评估PE/PB/ROE
        - 情绪分析师 Agent 正在解读市场情绪
        - 辩论主持人 Agent 正在组织多空辩论
        - 首席策略官 Agent 正在最终决策...
        """):
            from strategies.crew_agents import analyze_single_stock
            try:
                result = analyze_single_stock(selected_name, selected_code)
            except ImportError as e:
                st.error(f"CrewAI 加载失败（Streamlit Cloud 内存限制）: {e}")
                return

        st.session_state["ma_result"] = result

    # ── 显示分析结果 ──
    if "ma_result" in st.session_state:
        result = st.session_state["ma_result"]

        st.markdown("---")
        st.markdown("### 📝 分析结论")

        action = result["action"]
        action_color = {"买入": "green", "持有": "orange", "卖出": "red"}.get(action, "gray")
        action_emoji = {"买入": "🟢", "持有": "🟡", "卖出": "🔴"}.get(action, "⚪")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"### {action_emoji} <span style='color:{action_color}'>{action}</span>", unsafe_allow_html=True)
        with c2:
            st.metric("置信度", f"{result['confidence'] * 100:.0f}%")
        with c3:
            st.caption(f"重试次数: {result.get('retry_count', 0)}")

        st.markdown("---")
        st.markdown("### 📖 完整分析报告")
        st.markdown(result["analysis"])

        # ── 技术指标详情 ──
        tech = result.get("technical", {})
        if tech and tech.get("data_points", 0) > 0:
            with st.expander("📊 技术指标详情 (akquant TA-Lib 计算)"):
                st.caption(f"趋势判断: **{tech.get('trend', '-')}** | 动量信号: **{tech.get('momentum_signal', '-')}** | 波动率: **{tech.get('volatility_regime', '-')}**")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("RSI(14)", _sfmt(tech.get("rsi_14")))
                    st.metric("CCI(14)", _sfmt(tech.get("cci_14")))
                    st.metric("MFI(14)", _sfmt(tech.get("mfi_14")))
                with c2:
                    st.metric("ADX(14)", _sfmt(tech.get("adx_14")))
                    st.metric("ATR(14)", _sfmt(tech.get("atr_14")))
                    st.metric("MACD柱", _sfmt(tech.get("macd_hist")))
                with c3:
                    st.metric("Stoch K", _sfmt(tech.get("stoch_k")))
                    st.metric("Stoch D", _sfmt(tech.get("stoch_d")))
                    st.metric("W%R", _sfmt(tech.get("willr_14")))
                with c4:
                    st.metric("布林上轨", _sfmt(tech.get("bb_upper")))
                    st.metric("布林中轨", _sfmt(tech.get("bb_mid")))
                    st.metric("布林下轨", _sfmt(tech.get("bb_lower")))
                # 均线
                st.caption(f"均线: MA20={_sfmt(tech.get('sma_20'))} | MA50={_sfmt(tech.get('sma_50'))} | MA200={_sfmt(tech.get('sma_200'))} | 周MA10={_sfmt(tech.get('ma10w'))}")

        # ── 基本面详情 ──
        fund = result.get("fundamental", {})
        if fund:
            with st.expander("📋 基本面详情"):
                fc1, fc2, fc3, fc4 = st.columns(4)
                with fc1:
                    st.metric("行业", _sfmt(fund.get("sector")))
                    st.metric("PE", _sfmt(fund.get("pe")))
                    st.metric("PB", _sfmt(fund.get("pb")))
                with fc2:
                    st.metric("ROE", _sfmt(fund.get("roe"), "{}%"))
                    st.metric("利润率", _sfmt(fund.get("profit_margin"), "{}%"))
                    st.metric("股息率", _sfmt(fund.get("dividend_yield"), "{}%"))
                with fc3:
                    st.metric("营收增速", _sfmt(fund.get("revenue_growth"), "{}%"))
                    st.metric("利润增速", _sfmt(fund.get("earnings_growth"), "{}%"))
                    st.metric("Beta", _sfmt(fund.get("beta")))
                with fc4:
                    mc = fund.get("market_cap")
                    st.metric("市值", _sfmt(mc / 1e8 if mc else None, "{:.0f}亿"))
                    st.metric("负债权益比", _sfmt(fund.get("debt_to_equity")))


def _has_api_key() -> bool:
    import os
    return bool(os.getenv("DEEPSEEK_API_KEY"))
