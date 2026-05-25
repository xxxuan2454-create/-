"""六爻占卜页面 - 摇卦→解卦→预测→保存"""

import json
import time
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from divination.liuyao import cast_full_hexagram, format_divination_result
from divination.predictor import predict_stock
from divination.yingqi import calculate_yingqi, is_yingqi_expired
from divination.bagua import BA_GUA
from data.fetcher import fetch_stock_history, fetch_stock_info
from data.technical import compute_all_indicators, indicator_summary_text
from db.store import save_prediction, save_divination_cast, update_ai_prediction, get_halfday_stock_count, get_today_stock_prediction, resolve_stock_daily_conflicts
from db.models import init_db
from config import STOCK_POOL


def show():
    st.markdown("# 🔮 六爻占卜·股价预测")

    init_db()

    # ── 选股 ──
    st.markdown("### 1️⃣ 选择股票")

    linked = st.session_state.get("active_stock")

    col1, col2 = st.columns([3, 1])

    with col1:
        search_query = st.text_input(
            "搜索股票名称或代码",
            placeholder="输入关键词搜索...（如 茅台 / 宁德 / 600519）",
            key="div_search_input",
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
                    "选择股票",
                    options=list(stock_options.keys()),
                    index=default_idx,
                    key="div_stock_select",
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
                st.info("输入股票名称或代码搜索，选中后将自动联动到「🤖 多智能体分析」页面")

    with col2:
        use_random = st.checkbox("随机选股", value=False, key="random_stock")

    if use_random:
        import random
        stock_names = list(STOCK_POOL.keys())
        selected_name = random.choice(stock_names)
        selected_code = STOCK_POOL[selected_name]
        st.info(f"随机选中: **{selected_name}**")

    # ── 联动到智能分析 ──
    st.session_state["active_stock"] = {"name": selected_name, "code": selected_code}

    st.markdown(f"## 📌 当前占卜股票: **{selected_name}** ({selected_code})")
    st.caption("🔗 已联动到「🤖 多智能体分析」，切换侧边栏即可直接分析此股")

    # ── 显示股票信息 ──
    # 获取当前股价
    df = fetch_stock_history(selected_code, period="1mo")
    current_price = 0.0
    change_pct = 0.0
    if not df.empty and len(df) >= 2:
        import math
        raw_close = df["close"].iloc[-1]
        raw_prev = df["close"].iloc[-2]
        if not (pd.isna(raw_close) or pd.isna(raw_prev)):
            current_price = float(raw_close)
            prev_price = float(raw_prev)
            if prev_price > 0:
                change_pct = round((current_price - prev_price) / prev_price * 100, 2)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("当前价格", f"¥{current_price:.2f}")
    with c2:
        st.metric("代码", selected_code)
    with c3:
        delta_str = f"{change_pct:+.2f}%"
        st.metric("今日涨跌", delta_str, delta=delta_str)

    # ── 近30日K线 ──
    if not df.empty:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df.index[-30:],
            open=df["open"].iloc[-30:],
            high=df["high"].iloc[-30:],
            low=df["low"].iloc[-30:],
            close=df["close"].iloc[-30:],
            name=selected_name,
        ))
        fig.update_layout(
            title=f"{selected_name} 近30日走势",
            height=300,
            xaxis_rangeslider_visible=False,
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── 起卦次数检查 (每只股票 上午/下午 各1卦，以中午12点为界) ──
    user_id = st.session_state.get("user_id", 1)
    from datetime import datetime
    now_hour = datetime.now().hour
    is_morning = now_hour < 12
    period_name = "上午" if is_morning else "下午"

    am_cnt, pm_cnt = get_halfday_stock_count(user_id, selected_code)
    period_cnt = am_cnt if is_morning else pm_cnt

    if period_cnt >= 1:
        st.warning(f"⚠️ {selected_name} 今日{period_name}已起卦 1 次，请等到下一时段或换一只股票。")
        cast_disabled = True

        # 加载并展示今日已有的卦象与AI预测
        record = get_today_stock_prediction(user_id, selected_code)
        if record and record.get("zhu_gua_full"):
            div_result, pred, yq = _reconstruct_from_record(record)
            st.session_state["divination_result"] = div_result
            st.session_state["yingqi"] = yq
            st.session_state["divination_stock_code"] = selected_code
            if pred["analysis"]:
                st.session_state["prediction"] = pred
    else:
        st.info(f"📅 {selected_name} 今日上午 {am_cnt}/1 卦 | 下午 {pm_cnt}/1 卦")
        cast_disabled = False

    # ── 摇卦按钮 ──
    st.markdown("### 2️⃣ 起卦")

    cast_col, _ = st.columns([1, 2])
    with cast_col:
        cast_btn = st.button(
            "🎲 摇卦占卜" if not cast_disabled else "🔒 今日次数已用完",
            type="primary",
            use_container_width=True,
            disabled=cast_disabled,
            help="随机模拟三枚铜钱摇卦六次，生成卦象" if not cast_disabled else f"每只股票每半天限1卦，{selected_name}今日{period_name}已占过",
        )

    if cast_btn:
        with st.spinner("🪙 摇卦中... 正在排盘..."):
            placeholder = st.empty()
            lines_preview = []
            for i in range(6):
                time.sleep(0.3)
                import random
                toss = sum(random.randint(0, 1) for _ in range(3))
                results_map = {0: "⚋⚋ 老阴", 1: "⚊ 少阳", 2: "⚋ 少阴", 3: "⚊⚊ 老阳"}
                lines_preview.append(f"第{i+1}摇: {results_map[toss]}")
                placeholder.markdown("\n".join(lines_preview))

            divination_result = cast_full_hexagram()
            divination_text = format_divination_result(divination_result)
            yingqi = calculate_yingqi(divination_result)

        placeholder.empty()

        st.session_state["divination_result"] = divination_result
        st.session_state["divination_text"] = divination_text
        st.session_state["yingqi"] = yingqi
        st.session_state["divination_stock_code"] = selected_code

        # 保存卦象
        try:
            pred_id = save_divination_cast(
                stock_code=selected_code,
                stock_name=selected_name,
                zhu_gua_name=divination_result["zhu_gua"]["name"],
                zhu_gua_full=_embed_hexagram_data(divination_result),
                bian_gua_name=divination_result["bian_gua"]["name"] if divination_result["bian_gua"] else "",
                bian_gua_full=divination_result["bian_gua"],
                changing_lines=divination_result["changing_lines"],
                dong_yao_details=json.dumps(divination_result["dong_yao_details"], ensure_ascii=False),
                ti_yong_analysis=json.dumps(divination_result["tiyong"], ensure_ascii=False),
                predicted_price=current_price,
                yingqi_date=yingqi["date"],
                user_id=user_id,
            )
            st.session_state["prediction_id"] = pred_id
        except Exception as e:
            st.warning(f"卦象保存失败: {e}")

        # 自动调用AI预测
        if has_api_key():
            # 获取完整技术指标数据用于AI分析
            try:
                inds = compute_all_indicators(selected_code, period="6mo")
                tech_summary = indicator_summary_text(inds)
            except Exception:
                tech_summary = f"近30日价格: {current_price}, 今日涨跌幅: {change_pct}%"

            with st.spinner("🤖 AI正在解卦并预测涨跌..."):
                try:
                    prediction = predict_stock(
                        stock_name=selected_name,
                        stock_code=selected_code,
                        current_price=current_price,
                        change_pct=change_pct,
                        technical_summary=tech_summary,
                    )
                    st.session_state["prediction"] = prediction

                    # 更新DB记录
                    pid = st.session_state.get("prediction_id")
                    if pid:
                        update_ai_prediction(
                            prediction_id=pid,
                            ai_prediction=prediction["prediction"],
                            ai_confidence=prediction["confidence"],
                            ai_analysis=prediction["analysis"],
                            ai_model="deepseek",
                            retry_count=prediction.get("retry_count", 0),
                        )
                        # 检查同日上/下午预测是否冲突
                        conflict = resolve_stock_daily_conflicts(user_id, selected_code)
                        if conflict:
                            st.session_state["divination_conflict"] = conflict
                            if conflict["winner_id"] == pid:
                                st.success(
                                    f"✅ 本次预测(置信度 {prediction['confidence']*100:.0f}%) "
                                    f"同日冲突中胜出，已覆盖另一卦"
                                )
                            else:
                                st.warning(
                                    f"⚠️ 本次预测方向「{prediction['prediction']}」(置信度 {prediction['confidence']*100:.0f}%) "
                                    f"已被同日另一卦「{conflict['winner_direction']}」(置信度 {conflict['winner_confidence']*100:.0f}%) 覆盖"
                                )
                except Exception as e:
                    st.error(f"AI调用失败: {e}")
        else:
            st.warning("未配置 DEEPSEEK_API_KEY，跳过AI预测")

    # ── 显示卦象 ──
    if "divination_result" in st.session_state:
        # 如果当前选股与缓存卦象不匹配，清除旧数据并尝试加载当前选股的今日卦象
        cached_code = st.session_state.get("divination_stock_code", "")
        if cached_code != selected_code:
            st.session_state.pop("divination_result", None)
            st.session_state.pop("divination_text", None)
            st.session_state.pop("yingqi", None)
            st.session_state.pop("prediction", None)
            st.session_state.pop("divination_stock_code", None)
            if cast_disabled:
                record = get_today_stock_prediction(user_id, selected_code)
                if record and record.get("zhu_gua_full"):
                    div_result, pred, yq = _reconstruct_from_record(record)
                    st.session_state["divination_result"] = div_result
                    st.session_state["yingqi"] = yq
                    st.session_state["divination_stock_code"] = selected_code
                    if pred["analysis"]:
                        st.session_state["prediction"] = pred

    if "divination_result" in st.session_state:
        st.markdown("---")
        st.markdown("### 卦象排盘")

        result = st.session_state["divination_result"]
        zhu = result["zhu_gua"]
        bian = result["bian_gua"]

        # 卦象可视化 - compact visual hexagram diagram
        gua_col1, gua_col2 = st.columns(2)

        with gua_col1:
            st.markdown(f"#### 🏛️ 本卦: **{zhu['name']}** {zhu['symbol']}")
            st.caption(f"{zhu['type']} | {zhu['guaGong']}宫 | 五行{result['gong_wuxing']}")
            _visual_hexagram(result["all_lines"], result["liuqin"], "zhu")

        with gua_col2:
            if bian:
                st.markdown(f"#### 🔄 变卦: **{bian['name']}** {bian['symbol']}")
                st.caption(f"{bian['type']} | {bian['guaGong']}宫")
                _visual_bian_hexagram(result)
            else:
                st.markdown("#### 无变卦")

        # 体用生克
        tiyong = result["tiyong"]
        st.markdown("---")
        st.markdown("#### ⚖️ 体用生克分析")

        tc1, tc2 = st.columns(2)
        with tc1:
            st.markdown(f"**体卦(内)**: {tiyong.get('ti_gua', '')} ({tiyong.get('ti_wuxing', '')})")
            st.markdown(f"**用卦(外)**: {tiyong.get('yong_gua', '')} ({tiyong.get('yong_wuxing', '')})")
        with tc2:
            relation = tiyong.get("relation", "")
            sentiment = "🐂 看涨" if tiyong.get("sentiment") == "bullish" else "🐻 看跌"
            st.markdown(f"**生克关系**: {relation}")
            st.markdown(f"**卦象倾向**: {sentiment}")
        st.info(tiyong.get("description", ""))

        # 应期
        yingqi = st.session_state.get("yingqi", {})
        if yingqi:
            st.markdown("#### 📅 应期推算")
            days = yingqi.get("days", 0)
            yq_date = yingqi.get("date", "")
            expired = yingqi.get("expired", False)
            if expired:
                st.warning(f"⚠️ 应期已过 ({yq_date})，此卦已失效，建议重新起卦。")
            else:
                st.info(f"📅 应期: **{yq_date}** (约 {days} 天后)，在此之前预测有效。")
            st.caption(f"推算依据: {yingqi.get('reason', '')}")

        # 动爻详情
        if result["dong_yao_details"]:
            st.markdown("#### 📜 动爻详解")
            for d in result["dong_yao_details"]:
                st.markdown(f"**第{d['position']}爻** ({d['liuqin']} | {d['najia']})")
                st.markdown(f"> {d['yao_ci']}")

        # 卦辞
        st.markdown("#### 📖 本卦卦辞")
        st.markdown(zhu.get("guaCi", "")[:500])

        # ── 显示AI预测结果 ──
        if "prediction" in st.session_state:
            st.markdown("---")
            pred = st.session_state["prediction"]

            # 预测结果卡片
            direction = pred["prediction"]
            dir_color = {"涨": "#ef5350", "跌": "#26a69a", "平": "#9e9e9e"}.get(direction, "#9e9e9e")
            dir_emoji = {"涨": "📈", "跌": "📉", "平": "➡️"}.get(direction, "➡️")

            st.markdown(f"### {dir_emoji} AI预测结果")
            d1, d2 = st.columns(2)
            with d1:
                st.markdown(f"## <span style='color:{dir_color}'>{direction}</span>", unsafe_allow_html=True)
            with d2:
                st.metric("置信度", f"{pred['confidence'] * 100:.0f}%")
                st.caption(f"重试次数: {pred.get('retry_count', 0)}")

            # 完整分析文本
            st.markdown("### 📝 AI详细分析")
            st.markdown(pred["analysis"])


def _build_all_lines_for_gua(gua: dict) -> tuple[list, list]:
    """根据卦象字典(code/guaGong/shiYao/yingYao)计算纳甲、六亲、世应

    返回 (all_lines, liuqin) 供 _visual_hexagram / _visual_bian_hexagram 使用
    """
    from divination.bagua import (
        BA_GUA, BA_GUA_BY_CODE, get_najia_for_hexagram, get_liuqin_for_lines,
    )

    code = gua.get("code", "")
    if len(code) != 6:
        return [], []

    xia_code = code[:3]
    shang_code = code[3:]
    xia_bagua = BA_GUA_BY_CODE.get(xia_code)
    shang_bagua = BA_GUA_BY_CODE.get(shang_code)

    najia_lines = get_najia_for_hexagram(
        xia_bagua.name if xia_bagua else "",
        shang_bagua.name if shang_bagua else "",
    ) if xia_bagua and shang_bagua else []

    gong_bagua = BA_GUA.get(gua.get("guaGong", ""))
    gong_wx = gong_bagua.wuxing if gong_bagua else ""
    liuqin = get_liuqin_for_lines(gong_wx, najia_lines) if najia_lines else []

    shi_yao = gua.get("shiYao", 0)
    ying_yao = gua.get("yingYao", 0)

    all_lines = []
    for i in range(6):
        pos = i + 1
        is_yang = code[i] == "1"
        all_lines.append({
            "position": pos,
            "yao_name": "少阳" if is_yang else "少阴",
            "is_changing": False,  # 变卦本身没有动爻，由调用方设置
            "liuqin": liuqin[i] if i < len(liuqin) else "",
            "najia": f"{najia_lines[i]['tiangan']}{najia_lines[i]['dizhi']}" if i < len(najia_lines) else "",
            "is_shi_yao": pos == shi_yao,
            "is_ying_yao": pos == ying_yao,
        })

    return all_lines, liuqin


def _embed_hexagram_data(result: dict) -> dict:
    """将 all_lines / liuqin 嵌入 zhu_gua 字典，方便历史记录还原卦象图"""
    zhu = dict(result["zhu_gua"])
    zhu["_all_lines"] = result.get("all_lines", [])
    zhu["_liuqin"] = result.get("liuqin", [])
    zhu["_changing_lines"] = result.get("changing_lines", [])

    # 同时嵌入变卦的纳甲/六亲数据
    bian = result.get("bian_gua")
    if bian:
        bian_all, bian_lq = _build_all_lines_for_gua(bian)
        zhu["_bian_all_lines"] = bian_all
        zhu["_bian_liuqin"] = bian_lq
    return zhu


def _reconstruct_from_record(record: dict):
    """从DB记录重建 divination_result, prediction, yingqi 三个字典"""
    zhu_full = json.loads(record["zhu_gua_full"]) if isinstance(record.get("zhu_gua_full"), str) else (record.get("zhu_gua_full") or {})

    all_lines = zhu_full.pop("_all_lines", [])
    liuqin = zhu_full.pop("_liuqin", [])
    changing_lines_embedded = zhu_full.pop("_changing_lines", [])
    bian_all_lines = zhu_full.pop("_bian_all_lines", [])
    bian_liuqin = zhu_full.pop("_bian_liuqin", [])

    bian_gua = json.loads(record["bian_gua_full"]) if isinstance(record.get("bian_gua_full"), str) else record.get("bian_gua_full")
    dong_yao_details = json.loads(record["dong_yao_details"]) if isinstance(record.get("dong_yao_details"), str) else record.get("dong_yao_details", [])
    ti_yong = json.loads(record["ti_yong_analysis"]) if isinstance(record.get("ti_yong_analysis"), str) else record.get("ti_yong_analysis", {})

    from divination.bagua import BA_GUA
    gong_wuxing = ""
    gua_gong = zhu_full.get("guaGong", "")
    if gua_gong:
        gong_bagua = BA_GUA.get(gua_gong)
        if gong_bagua:
            gong_wuxing = gong_bagua.wuxing

    changing_lines_raw = record.get("changing_lines")
    if changing_lines_raw:
        changing_lines = json.loads(changing_lines_raw) if isinstance(changing_lines_raw, str) else changing_lines_raw
    else:
        changing_lines = changing_lines_embedded

    divination_result = {
        "zhu_gua": zhu_full,
        "bian_gua": bian_gua,
        "changing_lines": changing_lines,
        "dong_yao_details": dong_yao_details,
        "tiyong": ti_yong,
        "all_lines": all_lines,
        "liuqin": liuqin,
        "gong_wuxing": gong_wuxing,
        "_bian_all_lines": bian_all_lines,
        "_bian_liuqin": bian_liuqin,
        "bian_all_lines": bian_all_lines,
        "bian_liuqin": bian_liuqin,
    }

    prediction = {
        "prediction": record.get("ai_prediction") or "N/A",
        "confidence": record.get("ai_confidence") or 0.5,
        "analysis": record.get("ai_analysis") or "",
        "retry_count": record.get("retry_count") or 0,
    }

    yingqi = {"date": record.get("yingqi_date") or "", "days": 0, "reason": "从历史记录恢复"}
    if yingqi["date"]:
        from datetime import date
        try:
            target = date.fromisoformat(yingqi["date"])
            delta = (target - date.today()).days
            yingqi["days"] = max(0, delta)
            yingqi["expired"] = delta < 0
        except ValueError:
            pass

    return divination_result, prediction, yingqi


def _visual_hexagram(all_lines: list, liuqin: list, gua_type: str):
    """渲染六爻卦象图 - 从上爻到初爻，含纳甲、六亲、世应、动爻标记"""
    LIUQIN_COLORS = {
        "妻财": "#f5b342", "官鬼": "#8d6e63", "父母": "#42a5f5",
        "兄弟": "#ef5350", "子孙": "#66bb6a",
    }
    YAO_SHORT = {"老阳": "⚊老阳", "少阳": "⚊少阳", "老阴": "⚋老阴", "少阴": "⚋少阴"}

    html_parts = ['<div style="font-family: monospace; line-height: 1.8; padding: 4px 0;">']
    for i in reversed(range(6)):
        info = all_lines[i]
        is_yang = "阳" in info["yao_name"]
        is_changing = info["is_changing"]
        lq = liuqin[i] if i < len(liuqin) else ""
        color = LIUQIN_COLORS.get(lq, "#bdbdbd")
        najia = info.get("najia", "")

        markers = []
        if info["is_shi_yao"]:
            markers.append('<span style="color:#ff9800;font-weight:bold;">⚡世</span>')
        if info["is_ying_yao"]:
            markers.append('<span style="color:#9c27b0;font-weight:bold;">👁应</span>')
        if is_changing:
            markers.append('<span style="color:#ff1744;font-weight:bold;">🔴动</span>')

        bar_style = f"height:10px; border-radius:3px; background:{color}; display:inline-block;"
        if is_changing:
            bar_style += " box-shadow: 0 0 8px #ff1744; border: 1px solid #ff1744;"
        if is_yang:
            yao_html = f'<span style="{bar_style} width:90px;"></span>'
        else:
            yao_html = (
                f'<span style="{bar_style} width:38px; margin-right:14px;"></span>'
                f'<span style="{bar_style} width:38px;"></span>'
            )

        marker_str = " ".join(markers)
        html_parts.append(
            f'<div style="white-space:nowrap; margin:3px 0;">'
            f'{yao_html}'
            f'<span style="margin-left:10px; font-size:13px; color:#333; font-weight:bold;">{lq or "　"}</span>'
            f'<span style="margin-left:8px; font-size:11px; color:#888;">{najia}</span>'
            f'<span style="margin-left:8px; font-size:12px;">{marker_str}</span>'
            f'</div>'
        )
    html_parts.append('</div>')
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def _visual_bian_hexagram(result: dict):
    """渲染变卦卦象图 - 含纳甲、六亲、世应、动爻标记，尺寸与 _visual_hexagram 完全一致"""
    bian = result.get("bian_gua")
    if not bian:
        return

    LIUQIN_COLORS = {
        "妻财": "#f5b342", "官鬼": "#8d6e63", "父母": "#42a5f5",
        "兄弟": "#ef5350", "子孙": "#66bb6a",
    }

    changing = set(result.get("changing_lines", []))

    # 优先使用嵌入的变卦详细数据，否则现场计算
    bian_all_lines = result.get("_bian_all_lines") or result.get("bian_all_lines", [])
    bian_liuqin = result.get("_bian_liuqin") or result.get("bian_liuqin", [])

    if not bian_all_lines:
        bian_all_lines, bian_liuqin = _build_all_lines_for_gua(bian)

    html_parts = ['<div style="font-family: monospace; line-height: 1.8; padding: 4px 0;">']
    for i in reversed(range(6)):
        info = bian_all_lines[i] if i < len(bian_all_lines) else {}
        is_yang = bool(info.get("yao_name", "").startswith("少") and "阳" in info.get("yao_name", "")) or \
                  (bian.get("code", "")[i] == "1" if i < len(bian.get("code", "")) else False)
        if not info:
            is_yang = bian.get("code", "")[i] == "1" if i < len(bian.get("code", "")) else False

        pos = i + 1
        is_changed = pos in changing
        lq = bian_liuqin[i] if i < len(bian_liuqin) else ""
        color = LIUQIN_COLORS.get(lq, "#bdbdbd")
        najia = info.get("najia", "") if info else ""

        markers = []
        if info:
            if info.get("is_shi_yao"):
                markers.append('<span style="color:#ff9800;font-weight:bold;">⚡世</span>')
            if info.get("is_ying_yao"):
                markers.append('<span style="color:#9c27b0;font-weight:bold;">👁应</span>')
        if is_changed:
            markers.append('<span style="color:#ff1744;font-weight:bold;font-size:14px;">◆ 变爻</span>')

        bar_style = f"height:10px; border-radius:3px; background:{color}; display:inline-block;"
        if is_changed:
            bar_style += " box-shadow: 0 0 12px #ff1744, 0 0 4px #ff1744; border: 2px solid #ff1744;"

        if is_yang:
            yao_html = f'<span style="{bar_style} width:90px;"></span>'
        else:
            yao_html = (
                f'<span style="{bar_style} width:38px; margin-right:14px;"></span>'
                f'<span style="{bar_style} width:38px;"></span>'
            )

        # 变爻行加红色渐变背景
        row_style = ""
        if is_changed:
            row_style = "background: linear-gradient(90deg, rgba(255,23,68,0.15) 0%, rgba(255,23,68,0.03) 50%, transparent 100%); border-radius: 4px;"

        marker_str = " ".join(markers)
        lq_color = "#d32f2f" if is_changed else "#333"
        html_parts.append(
            f'<div style="white-space:nowrap; margin:3px 0; {row_style}">'
            f'{yao_html}'
            f'<span style="margin-left:10px; font-size:13px; color:{lq_color}; font-weight:bold;">{lq or "　"}</span>'
            f'<span style="margin-left:8px; font-size:11px; color:#888;">{najia}</span>'
            f'<span style="margin-left:8px; font-size:12px;">{marker_str}</span>'
            f'</div>'
        )
    html_parts.append('</div>')
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def has_api_key() -> bool:
    import os
    return bool(os.getenv("DEEPSEEK_API_KEY"))
