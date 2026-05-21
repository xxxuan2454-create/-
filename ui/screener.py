"""选股筛选器 - Sequoia-X 7策略 + qstock 多因子评分"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from strategies.sequoia_x import screen_stock_pool, run_all_sequoia_strategies
from strategies.qstock_scorer import screen_by_comprehensive, comprehensive_score
from data.fetcher import fetch_stock_history
from db.store import save_stock_picks, get_stock_picks, has_today_screening, get_latest_screening_time
from config import STOCK_POOL


def show():
    st.markdown("# 🔍 选股筛选器")

    # ── 策略选择 ──
    st.markdown("### 选择策略")
    tab1, tab2, tab3 = st.tabs(["Sequoia-X 技术面", "qstock 多因子评分", "综合推荐"])

    # ── Tab 1: Sequoia-X ──
    with tab1:
        st.markdown("基于 Sequoia-X 的7大技术面筛选策略")

        # ── 缓存结果 ──
        if has_today_screening("sequoia_x"):
            cached_time = get_latest_screening_time("sequoia_x") or ""
            st.success(f"✅ 今日筛选已完成 ({cached_time[:16]})，直接查看结果：")
            cached_picks = get_stock_picks("sequoia_x", limit=100)
            if cached_picks:
                df_cached = pd.DataFrame(cached_picks)
                available_cols = [c for c in ["stock_name", "stock_code", "score"] if c in df_cached.columns]
                st.dataframe(
                    df_cached[available_cols],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "stock_name": "股票名称", "stock_code": "股票代码",
                        "score": "今日涨幅%",
                    },
                )
            st.divider()
            st.caption("如需刷新结果，选择策略后点击下方按钮（耗时约5-8分钟）")

        strategies = st.multiselect(
            "选择策略 (可多选)",
            options=["MaVolume", "TurtleTrade", "HighTightFlag",
                     "LimitUpShakeout", "UptrendLimitDown", "RPSBreakout"],
            default=["MaVolume", "TurtleTrade", "RPSBreakout"],
            format_func=lambda x: {
                "MaVolume": "均线金叉放量",
                "TurtleTrade": "海龟突破",
                "HighTightFlag": "高紧旗形",
                "LimitUpShakeout": "涨停震仓",
                "UptrendLimitDown": "趋势跌停",
                "RPSBreakout": "RPS突破",
            }.get(x, x),
        )

        if st.button("🚀 运行技术面筛选", type="primary", key="run_seq"):
            progress_bar = st.progress(0)
            progress_text = st.empty()

            def update_progress(done, total):
                progress_bar.progress(min(done / total, 1.0))
                progress_text.text(f"筛选进度... {done}/{total}")

            with st.spinner(f"正在并行筛选 {len(STOCK_POOL)} 只股票 (20线程, akshare源)..."):
                df = screen_stock_pool(strategies, progress_callback=update_progress)

            progress_bar.empty()
            progress_text.empty()

            if df.empty:
                st.warning("未筛选出符合条件的股票。")
            else:
                st.success(f"筛选出 {len(df)} 条结果")
                st.dataframe(
                    df.drop(columns=["strategy"], errors="ignore"),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "name": "股票名称",
                        "code": "股票代码",
                        "score": "今日涨幅%",
                        "price": "当前价格",
                        "volume": "成交量",
                    },
                )
                picks = df.to_dict(orient="records")
                save_stock_picks("sequoia_x", picks)

                show_top_kline(df)

    # ── Tab 2: qstock 多因子 ──
    with tab2:
        st.markdown("基于 qstock 的RPS多因子评分系统")

        # ── 缓存结果 ──
        if has_today_screening("qstock"):
            cached_time = get_latest_screening_time("qstock") or ""
            st.success(f"✅ 今日评分已完成 ({cached_time[:16]})，直接查看结果：")
            q_cached = get_stock_picks("qstock", limit=50)
            if q_cached:
                df_q = pd.DataFrame(q_cached)
                available_cols = [c for c in ["stock_name", "stock_code", "score"] if c in df_q.columns]
                st.dataframe(
                    df_q[available_cols],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "stock_name": "股票", "stock_code": "代码",
                        "score": "综合评分",
                    },
                )
                # Cached bar chart
                fig = go.Figure()
                top10 = df_q.head(10)
                fig.add_trace(go.Bar(x=top10["stock_name"], y=top10["score"],
                                     name="综合评分", marker_color="#42a5f5"))
                fig.update_layout(title="TOP10 综合评分（缓存）", xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            st.divider()
            st.caption("如需刷新，点击下方按钮（约1-2分钟）")

        c1, c2 = st.columns(2)
        with c1:
            top_n = st.slider("显示前N只", 5, 50, 20, key="qstock_topn")
        with c2:
            stock_n = st.slider("评分股票池大小", 50, 500, 200, 50,
                               help="越大越慢，200只约需1-2分钟", key="qstock_pool")

        if st.button("📊 运行因子评分", type="primary", key="run_qstock"):
            progress_bar = st.progress(0)
            progress_text = st.empty()

            def update_progress(done, total):
                progress_bar.progress(min(done / total, 1.0))
                progress_text.text(f"数据加载中... {done}/{total}")

            with st.spinner(f"正在并行获取 {stock_n} 只股票数据..."):
                results = screen_by_comprehensive(
                    limit=top_n, stock_limit=stock_n,
                    progress_callback=update_progress,
                )

            progress_bar.empty()
            progress_text.empty()

            if not results:
                st.warning("评分失败，请检查网络。")
            else:
                df = pd.DataFrame(results)
                st.success(f"评分完成，前{top_n}名:")

                show_cols = ["name", "code", "total_score", "rps_score",
                             "factor_score"]
                available = [c for c in show_cols if c in df.columns]
                st.dataframe(
                    df[available],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "name": "股票", "code": "代码",
                        "total_score": "综合评分", "rps_score": "RPS",
                        "factor_score": "因子",
                    },
                )

                # 评分柱状图
                fig = go.Figure()
                top10 = df.head(10)
                fig.add_trace(go.Bar(x=top10["name"], y=top10["total_score"],
                                     name="综合评分", marker_color="#42a5f5"))
                fig.update_layout(title="TOP10 综合评分", xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

                # 保存
                picks = [{"code": r["code"], "name": r["name"],
                         "score": r["total_score"], "strategy": "qstock"} for r in results]
                save_stock_picks("qstock", picks)

    # ── Tab 3: 综合推荐 ──
    with tab3:
        st.markdown("综合所有策略的最新推荐结果")

        seq_picks = get_stock_picks("sequoia_x", limit=15)
        st.markdown("#### Sequoia-X 策略命中")
        if seq_picks:
            st.dataframe(pd.DataFrame(seq_picks)[["stock_name", "stock_code", "score"]],
                       use_container_width=True, hide_index=True)
        else:
            st.info("暂无结果")

        st.markdown("#### qstock 评分TOP")
        q_picks = get_stock_picks("qstock", limit=15)
        if q_picks:
            st.dataframe(pd.DataFrame(q_picks)[["stock_name", "stock_code", "score"]],
                       use_container_width=True, hide_index=True)
        else:
            st.info("暂无结果")


def show_top_kline(df: pd.DataFrame) -> None:
    """展示筛选结果TOP5的K线图"""
    st.markdown("---")
    st.markdown("### 筛选结果 TOP5 K线图")
    top5 = df.drop_duplicates(subset=["code"]).head(5)

    for _, row in top5.iterrows():
        code = row.get("code", "")
        name = row.get("name", "")
        hist_df = fetch_stock_history(code, period="3mo")
        if hist_df.empty:
            continue

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
        )

        fig.add_trace(go.Candlestick(
            x=hist_df.index,
            open=hist_df["open"],
            high=hist_df["high"],
            low=hist_df["low"],
            close=hist_df["close"],
            name=name,
        ), row=1, col=1)

        # MA
        close = hist_df["close"]
        for window, color in [(5, "#ff9800"), (20, "#42a5f5"), (60, "#ab47bc")]:
            ma = close.rolling(window).mean()
            fig.add_trace(go.Scatter(
                x=hist_df.index, y=ma,
                mode="lines", name=f"MA{window}",
                line=dict(color=color, width=1),
            ), row=1, col=1)

        # 成交量
        colors = ["#ef5350" if hist_df["close"].iloc[i] >= hist_df["open"].iloc[i]
                  else "#26a69a" for i in range(len(hist_df))]
        fig.add_trace(go.Bar(
            x=hist_df.index, y=hist_df["volume"],
            name="成交量", marker_color=colors,
        ), row=2, col=1)

        fig.update_layout(
            title=f"{name} ({code})",
            xaxis_rangeslider_visible=False,
            height=500,
            showlegend=False,
            template="plotly_dark",
        )
        fig.update_xaxes(title_text="日期", row=2, col=1)
        fig.update_yaxes(title_text="价格", row=1, col=1)
        fig.update_yaxes(title_text="成交量", row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)
