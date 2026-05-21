"""首页仪表盘"""

import streamlit as st
import pandas as pd

from data.fetcher import fetch_index_data
from db.store import get_accuracy_stats, get_stock_picks, get_predictions
from db.models import init_db


@st.cache_data(ttl=300)  # 缓存 5 分钟
def _get_index_data() -> dict[str, float]:
    """获取指数数据，超时或失败返回默认值"""
    try:
        return fetch_index_data()
    except Exception:
        return {"上证指数": 0, "深证成指": 0, "沪深300": 0, "创业板指": 0}


def show():
    st.markdown("# 📈 A股智能选股与预测系统")
    init_db()

    user_id = st.session_state.get("user_id", 1)

    # ── 大盘指数概览 ──
    st.markdown("## 大盘指数")
    if st.button("🔄 刷新指数", key="refresh_index"):
        st.cache_data.clear()

    index_data = _get_index_data()

    cols = st.columns(len(index_data))
    for i, (name, change) in enumerate(index_data.items()):
        color = "#ef5350" if change > 0 else ("#26a69a" if change < 0 else "#9e9e9e")
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "─")
        with cols[i]:
            st.metric(label=name, value="", delta=f"{arrow} {change:.2f}%",
                      delta_color="normal" if change > 0 else "inverse")

    st.markdown("---")

    # ── 今日推荐 ──
    st.markdown("## 今日策略推荐 TOP 10")
    picks = get_stock_picks(limit=10)

    if picks:
        df_picks = pd.DataFrame(picks)
        cols_to_show = ["stock_name", "stock_code", "score"]
        available = [c for c in cols_to_show if c in df_picks.columns]
        st.dataframe(
            df_picks[available],
            use_container_width=True,
            hide_index=True,
            column_config={
                "stock_name": "股票名称",
                "stock_code": "股票代码",
                "score": "评分/涨幅%",
            },
        )
    else:
        st.info("暂无选股结果，请前往「选股筛选」页面运行策略。")

    # ── 预测准确率 ──
    st.markdown("---")
    st.markdown("## 预测统计")
    stats = get_accuracy_stats(user_id=user_id)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("总预测数", stats.get("total_predictions", 0))
    with c2:
        st.metric("已回测", stats.get("accuracy_checked", 0))
    with c3:
        st.metric("正确", stats.get("correct", 0))
    with c4:
        st.metric("准确率", f"{stats.get('accuracy', 0)}%")

    # ── 近7日预测明细 ──
    st.markdown("---")
    st.markdown("## 📅 近7日预测明细")
    recent = get_predictions(limit=100, user_id=user_id)

    if recent:
        rows = []
        for p in recent:
            # 判断对错
            pred = p.get("ai_prediction", "") or "-"
            actual = p.get("actual_result", "") or "待验证"
            is_correct = ""
            if actual != "待验证":
                if (pred == actual) or (pred in ("偏涨","看涨") and actual == "涨") or (pred in ("偏跌","看跌") and actual == "跌"):
                    is_correct = "✅"
                else:
                    is_correct = "❌"

            rows.append({
                "日期": str(p.get("predicted_at", "") or p.get("created_at", ""))[:10],
                "股票": p.get("stock_name", ""),
                "本卦": p.get("zhu_gua_name", ""),
                "变卦": p.get("bian_gua_name", "") or "-",
                "AI预测": pred,
                "预测时价": p.get("predicted_price", 0),
                "实盘结果": actual,
                "实盘涨跌": f"{p.get('actual_change_pct', 0):+.2f}%" if p.get("accuracy_checked") else "-",
                "验证": is_correct,
            })

        df = pd.DataFrame(rows)
        # 高亮颜色
        def color_rows(row):
            if row["验证"] == "✅":
                return ["background-color: rgba(0,180,0,0.08)"] * len(row)
            elif row["验证"] == "❌":
                return ["background-color: rgba(200,0,0,0.06)"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df.style.apply(color_rows, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("暂无预测记录，快去「六爻占卜」试试吧！")

