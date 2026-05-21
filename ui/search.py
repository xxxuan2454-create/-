"""股票搜索页面 - 按名称或代码搜索任意A股"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.fetcher import fetch_stock_history, fetch_stock_info
from data.realtime import get_realtime_quotes
from data.stock_list import search_all_stocks, get_stock_count


def _try_code_formats(code: str) -> list[str]:
    """尝试所有可能的yfinance代码格式"""
    code = code.replace(" ", "").upper()
    if len(code) == 6 and code.isdigit():
        if code.startswith(("6", "9")):
            return [f"{code}.SS"]
        elif code.startswith(("0", "2", "3")):
            return [f"{code}.SZ"]
        else:
            return [f"{code}.SS", f"{code}.SZ"]
    return [code]


def show():
    st.markdown("# 🔎 股票搜索")
    total = get_stock_count()
    st.caption(f"全A股数据库: {total:,} 只股票")

    query = st.text_input(
        "输入股票名称或代码",
        placeholder="例如: 贵州茅台 / 600519 / 宁德时代 / 300750",
        key="stock_search_input",
    )

    if not query:
        st.info("请输入股票名称或代码进行搜索")
        return

    # DB模糊搜索 (名称/代码)
    results = search_all_stocks(query, limit=50)

    if results:
        st.success(f"找到 {len(results)} 只匹配股票")
        if len(results) == 1:
            r = results[0]
            show_stock_detail(r["name"], r["code"])
        else:
            cols = st.columns(3)
            for i, r in enumerate(results):
                with cols[i % 3]:
                    if st.button(f"{r['name']}\n{r['code']}", key=f"sr_{r['code']}"):
                        st.session_state["search_stock"] = r
                        st.session_state["active_stock"] = r  # 联动到六爻/多智能体页
                        st.rerun()
            if "search_stock" in st.session_state:
                st.markdown("---")
                s = st.session_state["search_stock"]
                show_stock_detail(s["name"], s["code"])
    else:
        # DB找不到，尝试yfinance直接查询
        with st.spinner(f"正在从yfinance查询 '{query}' ..."):
            result = _yf_dynamic_search(query)
        if result:
            st.success(f"找到: {result['name']} ({result['code']})")
            show_stock_detail(result["name"], result["code"])
        else:
            st.error(f"未找到 '{query}'，请检查代码是否正确。")


def _yf_dynamic_search(query: str) -> dict | None:
    """yfinance 动态查询 (通过 fetcher 模块间接调用)"""
    query = query.strip().replace(" ", "")
    for fmt in _try_code_formats(query):
        try:
            info = fetch_stock_info(fmt)
            name = info.get("name", "")
            if name and len(name) > 1:
                return {"name": name, "code": fmt}
        except Exception:
            continue
    return None


def show_stock_detail(name: str, code: str) -> None:
    """展示单只股票的详细信息"""
    st.markdown("---")
    st.markdown(f"## {name} ({code})")

    # 联动到其他页面
    st.session_state["active_stock"] = {"name": name, "code": code}
    st.info("📌 该股票已选中，前往「🔮 六爻占卜」或「🤖 多智能体分析」即可直接用此股分析")

    # ── 基本信息 ──
    info = fetch_stock_info(code)
    rt = get_realtime_quotes([code])

    c1, c2, c3, c4 = st.columns(4)

    if code in rt:
        r = rt[code]
        with c1:
            st.metric("实时价格", f"¥{r['current_price']:.2f}",
                     delta=f"{r.get('change_pct', 0):+.2f}%")
        with c2:
            st.metric("今开", f"¥{r.get('open', 0):.2f}")
        with c3:
            st.metric("最高/最低", f"¥{r.get('high', 0):.2f} / ¥{r.get('low', 0):.2f}")
        with c4:
            st.metric("成交量", f"{r.get('volume', 0)//10000}万手")

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        pe = info.get("pe_ratio")
        st.metric("PE", f"{pe:.1f}" if pe else "N/A")
    with c6:
        pb = info.get("pb_ratio")
        st.metric("PB", f"{pb:.2f}" if pb else "N/A")
    with c7:
        roe = info.get("roe")
        st.metric("ROE", f"{roe*100:.1f}%" if roe else "N/A")
    with c8:
        mc = info.get("market_cap")
        st.metric("市值", f"{mc/1e8:.0f}亿" if mc else "N/A")

    if info.get("sector"):
        st.caption(f"行业: {info.get('sector', '')} / {info.get('industry', '')}")

    # ── 财务指标 ──
    st.markdown("### 财务指标")
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        st.metric("利润率", f"{info.get('profit_margin', 0)*100:.1f}%" if info.get('profit_margin') else "N/A")
    with fc2:
        st.metric("营收增速", f"{info.get('revenue_growth', 0)*100:.1f}%" if info.get('revenue_growth') else "N/A")
    with fc3:
        st.metric("利润增速", f"{info.get('earnings_growth', 0)*100:.1f}%" if info.get('earnings_growth') else "N/A")
    with fc4:
        st.metric("股息率", f"{info.get('dividend_yield', 0)*100:.2f}%" if info.get('dividend_yield') else "N/A")

    # ── K线图 ──
    st.markdown("### 历史走势")
    period = st.selectbox("周期", ["1mo", "3mo", "6mo", "1y", "2y"],
                          index=1, format_func=lambda x: {
                              "1mo": "1个月", "3mo": "3个月",
                              "6mo": "6个月", "1y": "1年", "2y": "2年"
                          }.get(x, x), key="kline_period")

    df = fetch_stock_history(code, period=period)
    if not df.empty:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
        )

        fig.add_trace(go.Candlestick(
            x=df.index, open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name=name,
        ), row=1, col=1)

        close = df["close"]
        for w, color in [(5, "#ff9800"), (20, "#42a5f5"), (60, "#ab47bc")]:
            ma = close.rolling(w).mean()
            fig.add_trace(go.Scatter(
                x=df.index, y=ma, mode="lines",
                name=f"MA{w}", line=dict(color=color, width=1),
            ), row=1, col=1)

        colors = ["#ef5350" if df["close"].iloc[i] >= df["open"].iloc[i]
                  else "#26a69a" for i in range(len(df))]
        fig.add_trace(go.Bar(
            x=df.index, y=df["volume"], name="成交量", marker_color=colors,
        ), row=2, col=1)

        fig.update_layout(
            height=500, xaxis_rangeslider_visible=False,
            showlegend=True, template="plotly_dark",
        )
        fig.update_xaxes(title_text="日期", row=2, col=1)
        fig.update_yaxes(title_text="价格", row=1, col=1)
        fig.update_yaxes(title_text="成交量", row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)

        # ── 统计 ──
        st.markdown("### 价格统计")
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.metric("最新价", f"¥{close.iloc[-1]:.2f}")
        with sc2:
            st.metric("期间最高", f"¥{df['high'].max():.2f}")
        with sc3:
            st.metric("期间最低", f"¥{df['low'].min():.2f}")
        with sc4:
            chg = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100
            st.metric("期间涨幅", f"{chg:+.2f}%")
    else:
        st.warning("无法获取历史数据")
