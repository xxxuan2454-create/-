"""六爻起卦逻辑 - 模拟三枚铜钱摇卦六次 (基于 liu-yao 实现)"""

import json
import random

from divination.bagua import (
    Yao, BA_GUA, BA_GUA_BY_CODE, BA_GUA_BY_XIANTIAN,
    NA_JIA, WU_XING, DI_ZHI, TIAN_GAN,
    get_najia_for_hexagram, get_liuqin_for_lines, analyze_tiyong,
    analyze_stock_divination,
)
from divination.hexagrams import get_hexagram_by_code, get_hexagram_by_name


def cast_coins() -> Yao:
    """
    模拟三枚铜钱摇卦一次
    每枚铜钱: 正面(字)=2分, 反面(花)=3分 (或相反, 用随机模拟)
    simplify: random(0,1) x 3 → sum 0/1/2/3
    """
    toss = sum(random.randint(0, 1) for _ in range(3))
    return Yao(toss)


def cast_full_hexagram() -> dict:
    """
    完整起卦: 摇6次 (从初爻到上爻, 从下往上)
    返回完整的卦象信息
    """
    # 摇6次, 从初爻(第1次)到上爻(第6次)
    lines: list[Yao] = [cast_coins() for _ in range(6)]

    # 构建本卦code (从初爻到上爻)
    zhu_code = "".join(yao.line_code for yao in lines)
    zhu_gua = get_hexagram_by_code(zhu_code)

    # 构建变卦code (变爻翻转)
    bian_code = "".join(yao.changing_line_code for yao in lines)
    bian_gua = get_hexagram_by_code(bian_code) if bian_code != zhu_code else None

    # 找出动爻位置
    changing_line_positions = [i + 1 for i, yao in enumerate(lines) if yao.is_changing]

    # 八卦信息
    xia_gua_name = zhu_gua["code"][:3] if zhu_gua else ""
    shang_gua_name = zhu_gua["code"][3:] if zhu_gua else ""
    xia_bagua = BA_GUA_BY_CODE.get(xia_gua_name)
    shang_bagua = BA_GUA_BY_CODE.get(shang_gua_name)

    # 纳甲
    najia_lines = get_najia_for_hexagram(
        xia_bagua.name if xia_bagua else "",
        shang_bagua.name if shang_bagua else "",
    )

    # 六亲
    gong_wuxing = BA_GUA.get(zhu_gua["guaGong"]) if zhu_gua else None
    gong_wx = gong_wuxing.wuxing if gong_wuxing else ""
    liuqin = get_liuqin_for_lines(gong_wx, najia_lines) if najia_lines else []

    # 世应
    shi_yao = zhu_gua.get("shiYao", 0) if zhu_gua else 0
    ying_yao = zhu_gua.get("yingYao", 0) if zhu_gua else 0

    # 体用生克
    tiyong = analyze_tiyong(xia_bagua, shang_bagua, changing_line_positions) if xia_bagua and shang_bagua else {}

    # 动爻详情
    dong_yao_details = []
    for pos in changing_line_positions:
        idx = pos - 1
        detail = {
            "position": pos,  # 1-6
            "yao_type": lines[idx].display,
            "yao_ci": zhu_gua["yaoCi"][idx] if zhu_gua and idx < len(zhu_gua.get("yaoCi", [])) else "",
            "liuqin": liuqin[idx] if idx < len(liuqin) else "",
            "najia": f"{najia_lines[idx]['tiangan']}{najia_lines[idx]['dizhi']}" if idx < len(najia_lines) else "",
            "wuxing": najia_lines[idx]["wuxing"] if idx < len(najia_lines) else "",
            "is_shi_yao": pos == shi_yao,
            "is_ying_yao": pos == ying_yao,
        }
        dong_yao_details.append(detail)

    # 六爻完整信息
    all_lines_info = []
    for i in range(6):
        all_lines_info.append({
            "position": i + 1,
            "yao_name": lines[i].display,
            "is_changing": lines[i].is_changing,
            "liuqin": liuqin[i] if i < len(liuqin) else "",
            "najia": f"{najia_lines[i]['tiangan']}{najia_lines[i]['dizhi']}" if i < len(najia_lines) else "",
            "is_shi_yao": (i + 1) == shi_yao,
            "is_ying_yao": (i + 1) == ying_yao,
        })

    # 股票预测专项分析 (财爻+世应+六亲)
    stock_analysis = analyze_stock_divination(
        gong_wx, liuqin, najia_lines,
        shi_yao, ying_yao, changing_line_positions, tiyong,
    ) if zhu_gua else {}

    return {
        "zhu_gua": zhu_gua,
        "bian_gua": bian_gua,
        "lines": [yao.value for yao in lines],
        "lines_display": [yao.display for yao in lines],
        "changing_lines": changing_line_positions,
        "dong_yao_details": dong_yao_details,
        "all_lines": all_lines_info,
        "najia_lines": najia_lines,
        "liuqin": liuqin,
        "tiyong": tiyong,
        "stock_analysis": stock_analysis,
        "shi_yao": shi_yao,
        "ying_yao": ying_yao,
        "gong_wuxing": gong_wx,
        "no_change": bian_gua is None,
    }


def format_divination_result(result: dict) -> str:
    """格式化占卜结果为可读文本 (用于AI输入)"""
    zhu = result["zhu_gua"]
    bian = result["bian_gua"]
    tiyong = result["tiyong"]

    lines_text = []
    for i, info in enumerate(result["all_lines"]):
        markers = []
        if info["is_shi_yao"]:
            markers.append("世")
        if info["is_ying_yao"]:
            markers.append("应")
        if info["is_changing"]:
            markers.append("○动")
        marker_str = f" [{','.join(markers)}]" if markers else ""
        lines_text.append(
            f"  第{i+1}爻: {info['yao_name']} | {info['liuqin']} | {info['najia']}{marker_str}"
        )

    text = f"""
## 六爻排盘结果

**本卦**: {zhu['name']} {zhu['symbol']} ({zhu['type']})
  卦宫: {zhu['guaGong']}宫 (五行属{result['gong_wuxing']})
  卦辞: {zhu['guaCi'][:200]}...

"""
    if bian:
        text += f"**变卦**: {bian['name']} {bian['symbol']} ({bian['type']})\n"
    else:
        text += "**无变卦 (静卦)** \n"

    text += f"""
体用生克:
  - 体卦(内): {tiyong.get('ti_gua', '')} (五行: {tiyong.get('ti_wuxing', '')})
  - 用卦(外): {tiyong.get('yong_gua', '')} (五行: {tiyong.get('yong_wuxing', '')})
  - 关系: {tiyong.get('relation', '')} → {tiyong.get('description', '')}
  - 市场情绪: {'看涨' if tiyong.get('sentiment') == 'bullish' else '看跌'}

六爻排布 (从初爻到上爻):
{chr(10).join(lines_text)}

动爻详情:
"""
    for d in result["dong_yao_details"]:
        text += f"  第{d['position']}爻: {d['yao_type']} | {d['liuqin']} | {d['najia']}\n"
        text += f"    爻辞: {d['yao_ci']}\n"

    if result["no_change"]:
        text += "\n*此卦为静卦，六爻不动，以本卦卦辞为主判断。*\n"

    # 股票预测六爻分析
    sa = result.get("stock_analysis", {})
    if sa and sa.get("analysis"):
        text += "\n## 六爻股票预测分析 (财爻·世应·六亲)\n\n"
        text += f"**综合判断**: {sa.get('overall', '')} ({sa.get('overall_desc', '')})\n"
        text += f"多方信号: {sa.get('bullish_signals', 0)} | 空方信号: {sa.get('bearish_signals', 0)} | 净得分: {sa.get('net_score', 0)}\n\n"
        text += "**分析详情**:\n"
        for a in sa["analysis"]:
            text += f"  - {a}\n"
        text += f"\n**财爻位置**: {sa.get('cai_yao_positions', [])}\n"
        text += f"**世爻({sa.get('shi_liuqin', '')})** vs **应爻({sa.get('ying_liuqin', '')})**\n"

    return text
