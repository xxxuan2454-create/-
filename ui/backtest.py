"""量化回测页面 - K线信号回测 (akquant + Plotly)"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.fetcher import fetch_stock_history
from ui.stock_picker import resolve_stock_selection
from data.markets import detect_market


STRATEGY_HELP = {
    "ma_cross": "**均线金叉死叉**: 快线上穿慢线→买入，快线下穿慢线→卖出。适合趋势行情。",
    "rsi_reversal": "**RSI超买超卖**: RSI低于超卖线→买入，RSI高于超买线→卖出。适合震荡行情。",
    "bb_mean_reversion": "**布林带均值回归**: 价格跌破下轨→买入，突破上轨→卖出。适合区间震荡行情。",
}


def show():
    st.markdown("# ⚡ 策略回测")
    st.caption("用历史数据模拟交易策略，看买卖信号能不能跑赢「买入不动」")

    # ── 选股 ──
    active = st.session_state.get("active_stock")
    if active:
        selected_name = active.get("name", "")
        selected_code = active.get("code", "")
        market = active.get("market") or detect_market(selected_code)
        st.info(f"📌 已联动选中: **{selected_name}** ({selected_code})（来自六爻/多智能体页面）")
        if st.button("✕ 取消联动", key="clear_bt_active"):
            st.session_state.pop("active_stock", None)
            st.rerun()
    else:
        selected_name, selected_code, market = resolve_stock_selection("bt", linked=None)
        if not selected_code:
            return

    # ── 策略选择 ──
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        strategy_name = st.selectbox(
            "交易策略",
            options=["ma_cross", "rsi_reversal", "bb_mean_reversion"],
            format_func=lambda x: {
                "ma_cross": "📈 均线金叉死叉",
                "rsi_reversal": "📉 RSI 超买超卖",
                "bb_mean_reversion": "📊 布林带均值回归",
            }.get(x, x),
        )
        st.markdown(STRATEGY_HELP.get(strategy_name, ""))

    with col2:
        period = st.selectbox(
            "回测周期",
            options=["6mo", "1y", "2y", "5y"],
            index=1,
            format_func=lambda x: {"6mo": "半年", "1y": "1年", "2y": "2年", "5y": "5年"}.get(x, x),
        )
    with col3:
        capital = st.number_input("初始资金(万)", value=10, min_value=1, max_value=1000, step=1) * 10000

    # 策略参数
    with st.expander("⚙️ 策略参数"):
        if strategy_name == "ma_cross":
            p1, p2 = st.columns(2)
            with p1:
                ma_fast = st.slider("快线周期", 3, 30, 5)
            with p2:
                ma_slow = st.slider("慢线周期", 10, 60, 20)
            params = {"ma_fast": ma_fast, "ma_slow": ma_slow}
        elif strategy_name == "rsi_reversal":
            p1, p2, p3 = st.columns(3)
            with p1:
                rsi_period = st.slider("RSI周期", 5, 30, 14)
            with p2:
                rsi_oversold = st.slider("超卖线(买入)", 10, 40, 30)
            with p3:
                rsi_overbought = st.slider("超买线(卖出)", 60, 90, 70)
            params = {"rsi_period": rsi_period, "rsi_oversold": rsi_oversold, "rsi_overbought": rsi_overbought}
        else:
            p1, p2 = st.columns(2)
            with p1:
                bb_period = st.slider("布林带周期", 10, 50, 20)
            with p2:
                bb_std = st.slider("标准差倍数", 1.0, 3.0, 2.0, 0.1)
            params = {"bb_period": bb_period, "bb_std": bb_std}

    # ── 运行 ──
    if st.button("🚀 开始回测", type="primary", use_container_width=True):
        with st.spinner("加载数据..."):
            df = fetch_stock_history(selected_code, period=period, timeout=15)

        if df.empty or len(df) < 60:
            st.error("数据不足，可能原因: 1) yfinance 网络超时（国内需代理/VPN） 2) 该股票数据不足60个交易日，请尝试更短周期或重新点击「开始回测」重试。")
            return

        result = run_backtest(df, strategy_name, params, capital)
        if result.get("error"):
            st.error(result["error"])
            return

        st.session_state["bt_result"] = result
        st.session_state["bt_df"] = df
        st.session_state["bt_name"] = selected_name
        st.session_state["bt_code"] = selected_code
        st.session_state["bt_strategy"] = strategy_name
        st.session_state["bt_params"] = params

    if "bt_result" not in st.session_state:
        st.info("👆 选择策略后点击「开始回测」")
        return

    result = st.session_state["bt_result"]
    df = st.session_state["bt_df"]
    bt_name = st.session_state.get("bt_name", selected_name)
    perf = result.get("performance", {})

    # ═══════════════════════════════════════
    # 核心结论 - 大字号
    # ═══════════════════════════════════════
    st.markdown("---")
    strat_return = perf.get("total_return", 0)
    bh_return = perf.get("buy_hold_return", 0)
    win = perf.get("win_rate", 0)
    trades = perf.get("trades", 0)

    r1, r2, r3 = st.columns(3)
    with r1:
        delta_color = "normal" if strat_return > 0 else "inverse"
        st.metric("策略总收益", f"{strat_return:+.1f}%",
                  delta=f"vs 买入持有 {bh_return:+.1f}%", delta_color=delta_color)
    with r2:
        st.metric("胜率", f"{win:.0f}%", delta=f"{trades} 笔交易")
    with r3:
        dd = perf.get("max_drawdown", 0)
        st.metric("最大回撤", f"{dd:.1f}%")

    # ═══════════════════════════════════════
    # 收益曲线 (策略 vs 买入持有)
    # ═══════════════════════════════════════
    st.markdown("### 📈 收益曲线")
    st.caption("蓝色 = 策略累计收益 | 灰色虚线 = 买入不动")

    equity = result.get("equity_curve", ([], []))
    bench = result.get("benchmark_equity", ([], []))

    if equity[1]:
        fig = go.Figure()

        eq_normalized = [v / capital * 100 - 100 for v in equity[1]]
        fig.add_trace(go.Scatter(
            x=equity[0], y=eq_normalized, mode="lines",
            name="策略收益%", line=dict(color="#42a5f5", width=2),
        ))

        if bench[1]:
            bh_normalized = [v / capital * 100 - 100 for v in bench[1]]
            fig.add_trace(go.Scatter(
                x=bench[0], y=bh_normalized, mode="lines",
                name="买入持有%", line=dict(color="#9e9e9e", width=1, dash="dot"),
            ))

        fig.add_hline(y=0, line_dash="solid", line_color="gray", line_width=0.5)

        fig.update_layout(
            height=350, showlegend=True,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis_title="收益率 %",
        )
        st.plotly_chart(fig, use_container_width=True)

    # ═══════════════════════════════════════
    # 每笔交易盈亏一览
    # ═══════════════════════════════════════
    trades_list = result.get("trades_list", [])
    if trades_list:
        with st.expander("📋 每笔交易明细"):
            st.dataframe(pd.DataFrame(trades_list), use_container_width=True, hide_index=True)


def run_backtest(df: pd.DataFrame, strategy: str, params: dict, capital: float = 100_000) -> dict:
    """轻量级向量化回测引擎"""
    try:
        import akquant as aq
    except ImportError:
        return {"error": "akquant 不可用（Streamlit Cloud 不支持 TA-Lib C 依赖），请本地运行回测"}

    close = df["close"].values
    # 统一转为字符串日期，避免 session_state 序列化导致 1970 年问题
    date_strs = [str(d).split(" ")[0] for d in df.index]
    n = len(close)

    # ── 信号生成 ──
    if strategy == "ma_cross":
        fast = aq.talib.SMA(df["close"], timeperiod=params["ma_fast"])
        slow = aq.talib.SMA(df["close"], timeperiod=params["ma_slow"])
        signals = np.zeros(n, dtype=int)
        for i in range(1, n):
            if fast[i] > slow[i] and fast[i-1] <= slow[i-1]:
                signals[i] = 1
            elif fast[i] < slow[i] and fast[i-1] >= slow[i-1]:
                signals[i] = -1

    elif strategy == "rsi_reversal":
        rsi = aq.talib.RSI(df["close"], timeperiod=params["rsi_period"])
        signals = np.zeros(n, dtype=int)
        for i in range(1, n):
            if rsi[i] > params["rsi_overbought"] and rsi[i-1] <= params["rsi_overbought"]:
                signals[i] = -1
            elif rsi[i] < params["rsi_oversold"] and rsi[i-1] >= params["rsi_oversold"]:
                signals[i] = 1

    elif strategy == "bb_mean_reversion":
        upper, mid, lower = aq.talib.BBANDS(
            df["close"], timeperiod=params["bb_period"], nbdevup=params["bb_std"],
        )
        signals = np.zeros(n, dtype=int)
        for i in range(1, n):
            if close[i] < lower[i] and close[i-1] >= lower[i-1]:
                signals[i] = 1
            elif close[i] > upper[i] and close[i-1] <= upper[i-1]:
                signals[i] = -1
    else:
        return {"error": f"未知策略: {strategy}"}

    # ── 模拟交易 ──
    position = 0
    cash = float(capital)
    equity_curve = []
    benchmark_equity = []
    drawdown_curve = []
    trade_markers = []
    trades_list = []

    initial_price = float(close[0])
    peak_equity = cash

    for i in range(n):
        price = float(close[i])
        signal = signals[i]

        if signal == 1 and cash > 0:
            position = int(cash / price * 0.95)
            cost = position * price * 1.0003
            if position > 0:
                cash -= cost
                trade_markers.append({"date": date_strs[i], "price": price, "type": "buy"})
                trades_list.append({
                    "日期": date_strs[i], "操作": "买入",
                    "价格": round(price, 2), "股数": position, "金额": round(cost),
                })

        elif signal == -1 and position > 0:
            proceeds = position * price * (1 - 0.0003 - 0.001)
            cash += proceeds
            trade_markers.append({"date": date_strs[i], "price": price, "type": "sell"})
            prev_buys = [t for t in trades_list if "买入" in str(t.get("操作", ""))]
            entry = prev_buys[-1]["价格"] if prev_buys else price
            pnl_pct = (price - entry) / entry * 100
            trades_list.append({
                "日期": date_strs[i], "操作": "卖出",
                "价格": round(price, 2), "股数": position, "金额": round(proceeds),
                "盈亏": f"{pnl_pct:+.2f}%",
            })
            position = 0

        equity = cash + position * price
        equity_curve.append(equity)
        benchmark_equity.append(capital / initial_price * price)
        peak_equity = max(peak_equity, equity)
        dd = (equity - peak_equity) / peak_equity * 100 if peak_equity > 0 else 0
        drawdown_curve.append(dd)

    # 平仓
    if position > 0:
        cash += position * float(close[-1]) * (1 - 0.001)

    final_equity = cash
    total_return = (final_equity - capital) / capital * 100
    buy_hold_return = (close[-1] - close[0]) / close[0] * 100

    # ── 统计 ──
    eq_series = pd.Series(equity_curve)
    rets = eq_series.pct_change().dropna()
    years = max(len(rets) / 252, 0.1)
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0
    max_dd = min(drawdown_curve) if drawdown_curve else 0

    sell_pnls = []
    for t in trades_list:
        if t.get("操作") == "卖出" and "盈亏" in t:
            try:
                sell_pnls.append(float(t["盈亏"].replace("%", "").replace("+", "")))
            except (ValueError, KeyError):
                pass

    win_rate = sum(1 for p in sell_pnls if p > 0) / len(sell_pnls) * 100 if sell_pnls else 0

    return {
        "performance": {
            "total_return": round(total_return, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2),
            "win_rate": round(win_rate, 1),
            "trades": len(sell_pnls),
            "buy_hold_return": round(buy_hold_return, 2),
        },
        "equity_curve": (date_strs, equity_curve),
        "benchmark_equity": (date_strs, benchmark_equity),
        "drawdown_curve": (date_strs, drawdown_curve),
        "trade_markers": trade_markers,
        "trades_list": trades_list,
    }
