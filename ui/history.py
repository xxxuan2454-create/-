"""预测历史回顾 + 准确率统计"""

import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from db.store import get_predictions, get_accuracy_stats, update_actual_result
from db.models import init_db
from ui.divination import _visual_hexagram, _visual_bian_hexagram
from divination.yingqi import is_yingqi_expired
from datetime import date


def show():
    st.markdown("# 📋 预测历史记录")
    init_db()

    # ── 统计概览 ──
    stats = get_accuracy_stats(user_id=st.session_state.get("user_id", 1))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("总预测数", stats["total_predictions"])
    with c2:
        st.metric("已回测", stats["accuracy_checked"])
    with c3:
        st.metric("预测正确", stats["correct"])
    with c4:
        st.metric("准确率", f"{stats['accuracy']}%")

    st.markdown("---")

    # ── 股票筛选状态 ──
    filter_name = st.session_state.get("history_filter_stock_name")
    filter_code = st.session_state.get("history_filter_stock_code")

    if filter_code:
        col_back, col_info = st.columns([1, 4])
        with col_back:
            if st.button("← 返回全部", type="primary", key="back_to_all"):
                st.session_state.pop("history_filter_stock_code", None)
                st.session_state.pop("history_filter_stock_name", None)
                st.rerun()
        with col_info:
            st.info(f"当前筛选: **{filter_name}** ({filter_code})")

    # ── 条数 ──
    limit = st.slider("显示条数", 10, 200, 50, key="history_limit")

    # ── 查询 ──
    predictions = get_predictions(stock_code=filter_code, limit=limit, user_id=st.session_state.get("user_id", 1))

    if not predictions:
        st.info("暂无预测记录。")
        return

    # ── 格式化表格 ──
    rows = []
    for p in predictions:
        expired = is_yingqi_expired(p)
        yq_str = str(p.get("yingqi_date", "") or "")
        rows.append({
            "ID": p["id"],
            "股票": p.get("stock_name", ""),
            "代码": p.get("stock_code", ""),
            "本卦": p.get("zhu_gua_name", ""),
            "变卦": p.get("bian_gua_name", "") or "-",
            "AI预测": p.get("ai_prediction", ""),
            "AI建议": _extract_suggestion(p.get("ai_analysis") or ""),
            "置信度": f"{p.get('ai_confidence', 0) * 100:.0f}%" if p.get("ai_confidence") else "-",
            "预测价格": p.get("predicted_price", 0),
            "实际涨跌": p.get("actual_result", "待验证"),
            "实际涨跌幅": f"{p.get('actual_change_pct', 0):+.2f}%" if p.get("accuracy_checked") else "-",
            "应期": yq_str[:10] if yq_str else "-",
            "预测时间": str(p.get("predicted_at", ""))[:19],
            "_expired": expired,
        })

    df = pd.DataFrame(rows)

    # 高亮: 应期过期=灰色, 正确=绿, 错误=红
    def highlight_accuracy(row):
        if row.get("_expired"):
            return ["color: #999; background-color: rgba(150,150,150,0.08)"] * len(row)
        pred = row.get("AI预测", "")
        actual = row.get("实际涨跌", "")
        if actual == "待验证":
            return [""] * len(row)
        if pred == actual:
            return ["background-color: rgba(0,200,0,0.1)"] * len(row)
        else:
            return ["background-color: rgba(200,0,0,0.1)"] * len(row)

    event = st.dataframe(
        df.style.apply(highlight_accuracy, axis=1),
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
    )

    # ── 点击行: 筛选 or 卦象详情 ──
    selected_rows = event.get("selection", {}).get("rows", [])
    if selected_rows:
        idx = selected_rows[0]
        selected = predictions[idx]

        if not filter_code:
            # 无筛选时 → 点击股票行 = 按该股筛选
            st.session_state["history_filter_stock_code"] = selected.get("stock_code", "")
            st.session_state["history_filter_stock_name"] = selected.get("stock_name", "")
            st.rerun()
        else:
            # 已筛选时 → 点击行 = 显示卦象详情
            _show_hexagram_detail(selected)

    # ── 卦象详情: 已筛选且无行选中时也显示第一条 ──
    if filter_code and not selected_rows and predictions:
        _show_hexagram_detail(predictions[0])

    # ── 准确率图表 ──
    st.markdown("---")
    st.markdown("### 预测准确率趋势")

    checked = [p for p in predictions if p.get("accuracy_checked")]
    if len(checked) >= 5:
        checked.sort(key=lambda x: x.get("predicted_at", ""))
        dates = []
        acc_rates = []
        correct_cum = 0
        total_cum = 0
        for p in checked:
            total_cum += 1
            pred = p.get("ai_prediction", "")
            actual = p.get("actual_result", "")
            if ((pred == "涨" and actual == "涨") or
                (pred == "跌" and actual == "跌") or
                (pred == "平" and actual == "平")):
                correct_cum += 1
            dates.append(str(p.get("predicted_at", ""))[:10])
            acc_rates.append(correct_cum / total_cum * 100)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=acc_rates, mode="lines+markers",
                                name="累计准确率", line=dict(color="#42a5f5")))
        fig.add_hline(y=50, line_dash="dash", line_color="gray",
                     annotation_text="随机基准线 50%")
        fig.update_layout(
            title="累计预测准确率趋势",
            xaxis_title="日期",
            yaxis_title="准确率 (%)",
            yaxis_range=[0, 100],
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── 手动更新实际结果 ──
    st.markdown("---")
    st.markdown("### 手动回测 (更新实际结果)")
    with st.expander("点击展开"):
        pred_id = st.number_input("预测ID", min_value=1, step=1)
        col1, col2 = st.columns(2)
        with col1:
            actual_price = st.number_input("实际收盘价", value=0.0, step=0.01)
        with col2:
            actual_change = st.number_input("实际涨跌幅 (%)", value=0.0, step=0.01)

        if st.button("✅ 更新实际结果"):
            update_actual_result(pred_id, actual_price, actual_change)
            st.success(f"已更新预测 #{pred_id} 的实际结果！")
            st.rerun()


def _show_hexagram_detail(selected: dict) -> None:
    """渲染点击行的卦象详情"""
    st.markdown("---")
    st.markdown(f"### 🔮 卦象详情: {selected.get('stock_name', '')} (#{selected['id']})")

    zhu_full_raw = selected.get("zhu_gua_full", "{}")
    if isinstance(zhu_full_raw, str):
        zhu_full = json.loads(zhu_full_raw)
    else:
        zhu_full = zhu_full_raw or {}

    bian_full_raw = selected.get("bian_gua_full") or "{}"
    if isinstance(bian_full_raw, str):
        bian_full = json.loads(bian_full_raw)
    else:
        bian_full = bian_full_raw or {}

    try:
        changing_raw = selected.get("changing_lines", "[]")
        changing_lines = json.loads(changing_raw) if isinstance(changing_raw, str) else changing_raw
    except (json.JSONDecodeError, TypeError):
        changing_lines = []

    all_lines = zhu_full.get("_all_lines", [])
    liuqin = zhu_full.get("_liuqin", [])

    # 旧版数据没有嵌入 _all_lines/_liuqin，从卦码重建
    if not all_lines and zhu_full.get("code"):
        all_lines, liuqin = _reconstruct_all_lines(zhu_full, changing_lines)

    if not all_lines:
        st.info("该记录卦象数据不完整，无法显示。")
        return

    gua_col1, gua_col2 = st.columns(2)

    with gua_col1:
        st.markdown(f"#### 🏛️ 本卦: **{zhu_full.get('name', '')}** {zhu_full.get('symbol', '')}")
        st.caption(f"{zhu_full.get('type', '')} | {zhu_full.get('guaGong', '')}宫")
        _visual_hexagram(all_lines, liuqin, "zhu")

    with gua_col2:
        if bian_full:
            st.markdown(f"#### 🔄 变卦: **{bian_full.get('name', '')}** {bian_full.get('symbol', '')}")
            st.caption(f"{bian_full.get('type', '')} | {bian_full.get('guaGong', '')}宫")
            fake_result = {
                "bian_gua": bian_full,
                "changing_lines": changing_lines,
            }
            # 优先使用嵌入的变卦六亲/纳甲数据
            if zhu_full.get("_bian_all_lines"):
                fake_result["_bian_all_lines"] = zhu_full["_bian_all_lines"]
                fake_result["_bian_liuqin"] = zhu_full.get("_bian_liuqin", [])
            _visual_bian_hexagram(fake_result)
        else:
            st.markdown("#### 无变卦")

    # ── AI 预测报告 ──
    ai_analysis = selected.get("ai_analysis") or ""
    if ai_analysis:
        st.markdown("---")
        st.markdown("### 🤖 AI 解卦预测")
        st.markdown(ai_analysis)
    else:
        gua_ci = zhu_full.get("guaCi", "")
        if gua_ci:
            with st.expander("📖 卦辞"):
                st.markdown(gua_ci[:500])


def _extract_suggestion(ai_analysis: str) -> str:
    """从 AI 分析文本中提取「操作建议」"""
    if not ai_analysis:
        return ""
    for line in ai_analysis.split("\n"):
        line = line.strip()
        if "操作建议" in line:
            # 提取冒号后的内容
            for sep in ["：", ":"]:
                if sep in line:
                    suggestion = line.split(sep, 1)[1].strip()
                    # 去掉 HTML 注释
                    if "<!--" in suggestion:
                        suggestion = suggestion.split("<!--")[0].strip()
                    # 去掉 markdown 加粗标记
                    suggestion = suggestion.replace("**", "").strip()
                    return suggestion
            return line
    return ""


def _reconstruct_all_lines(zhu_full: dict, changing_lines: list[int]) -> tuple[list, list]:
    """从卦码 + 动爻 重建 all_lines 和 liuqin (兼容旧版记录)"""
    from divination.bagua import (
        BA_GUA, BA_GUA_BY_CODE, get_najia_for_hexagram, get_liuqin_for_lines,
    )

    code = zhu_full.get("code", "")
    if len(code) != 6:
        return [], []

    xia_code = code[:3]
    shang_code = code[3:]
    xia_bagua = BA_GUA_BY_CODE.get(xia_code)
    shang_bagua = BA_GUA_BY_CODE.get(shang_code)

    # 纳甲
    najia_lines = get_najia_for_hexagram(
        xia_bagua.name if xia_bagua else "",
        shang_bagua.name if shang_bagua else "",
    ) if xia_bagua and shang_bagua else []

    # 六亲
    gong_wx = None
    gua_gong = zhu_full.get("guaGong", "")
    gong_bagua = BA_GUA.get(gua_gong)
    gong_wx = gong_bagua.wuxing if gong_bagua else ""
    liuqin = get_liuqin_for_lines(gong_wx, najia_lines) if najia_lines else []

    shi_yao = zhu_full.get("shiYao", 0)
    ying_yao = zhu_full.get("yingYao", 0)
    changing_set = set(changing_lines) if changing_lines else set()

    all_lines = []
    for i in range(6):
        pos = i + 1
        is_yang = code[i] == "1"
        is_changing = pos in changing_set

        yao_name = "老阳" if is_yang and is_changing else \
                   "老阴" if (not is_yang) and is_changing else \
                   "少阳" if is_yang else "少阴"

        all_lines.append({
            "position": pos,
            "yao_name": yao_name,
            "is_changing": is_changing,
            "liuqin": liuqin[i] if i < len(liuqin) else "",
            "najia": f"{najia_lines[i]['tiangan']}{najia_lines[i]['dizhi']}" if i < len(najia_lines) else "",
            "is_shi_yao": pos == shi_yao,
            "is_ying_yao": pos == ying_yao,
        })

    return all_lines, liuqin
