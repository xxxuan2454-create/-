"""六爻应期推算 - 基于动爻地支/六亲/五行生克"""

from datetime import date, timedelta

# 地支 → 基础时间数 (子1→亥12，代表相对时间基数)
DI_ZHI_NUMBER = {
    "子": 1, "丑": 2, "寅": 3, "卯": 4,
    "辰": 5, "巳": 6, "午": 7, "未": 8,
    "申": 9, "酉": 10, "戌": 11, "亥": 12,
}

# 地支 → 时间远近 (near/mid/far)
DI_ZHI_RANGE = {
    "子": "near", "丑": "near", "寅": "near", "卯": "near",
    "辰": "mid",  "巳": "mid",  "午": "mid",  "未": "mid",
    "申": "far",  "酉": "far",  "戌": "far",  "亥": "far",
}

# 六亲 → 速度修正因子
LIUQIN_SPEED = {
    "官鬼": 0.5,   # 急迫 → 加速
    "妻财": 1.0,   # 正常
    "兄弟": 1.2,   # 竞争 → 稍慢
    "子孙": 1.5,   # 拖延 → 慢
    "父母": 1.8,   # 滞后 → 最慢
}

# 五行相生: 金→水→木→火→土→金
WUXING_SHENG = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
# 五行相克: 金→木→土→水→火→金
WUXING_KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}


def calculate_yingqi(divination_result: dict) -> dict:
    """推算应期日期和推算理由

    返回: {"date": date, "days": int, "reason": str, "expired": bool}
    """
    dong_yao_details = divination_result.get("dong_yao_details", [])
    tiyong = divination_result.get("tiyong", {})

    if not dong_yao_details:
        # 静卦: 无动爻, 应期按本卦卦宫定 (7天)
        return _jing_gua_yingqi(divination_result)

    # 取第一个动爻（最重要的一爻）计算应期
    main_dong = dong_yao_details[0]
    najia = main_dong.get("najia", "")       # e.g. "甲子" → dizhi = "子"
    liuqin = main_dong.get("liuqin", "")     # e.g. "妻财"
    wuxing = main_dong.get("wuxing", "")     # e.g. "水"
    position = main_dong.get("position", 1)  # 1-6

    # 1. 提取地支
    dizhi = ""
    for dz in DI_ZHI_NUMBER:
        if dz in najia:
            dizhi = dz
            break

    # 2. 基础时间单位: 日
    base_num = DI_ZHI_NUMBER.get(dizhi, 3)

    # 3. 地支远近 → 时间乘数
    distance = DI_ZHI_RANGE.get(dizhi, "mid")
    distance_mult = {"near": 1, "mid": 3, "far": 7}[distance]

    # 4. 六亲速度因子
    speed_factor = LIUQIN_SPEED.get(liuqin, 1.0)

    # 5. 五行生克修正
    gong_wx = divination_result.get("gong_wuxing", "")
    wuxing_factor = _wuxing_modifier(wuxing, gong_wx)

    # 6. 体用关系修正
    tiyong_factor = _tiyong_modifier(tiyong)

    # 7. 多动爻修正 (动爻越多, 事情越复杂, 应期越短)
    multi_dong = min(len(dong_yao_details) - 1, 3) * 0.2

    # 综合计算天数
    days = base_num * distance_mult * speed_factor * wuxing_factor * tiyong_factor
    days = days * (1 - multi_dong)  # 多动爻加速
    days = max(1, min(round(days), 180))  # 限制在 1-180 天

    yingqi_date = date.today() + timedelta(days=days)

    # 构建推导说明
    reason_parts = []
    if dizhi:
        reason_parts.append(f"动爻纳甲「{najia}」地支「{dizhi}」(基数{base_num})")
    if liuqin:
        reason_parts.append(f"六亲「{liuqin}」(速度因子×{speed_factor})")
    if wuxing and gong_wx:
        reason_parts.append(f"爻五行「{wuxing}」vs 宫五行「{gong_wx}」(×{wuxing_factor})")
    if tiyong:
        rel = tiyong.get("relation", "")
        if rel:
            reason_parts.append(f"体用「{rel}」(×{tiyong_factor})")
    if len(dong_yao_details) > 1:
        reason_parts.append(f"{len(dong_yao_details)}动爻(加速×{1-multi_dong:.1f})")

    distance_names = {"near": "近期", "mid": "中期", "far": "远期"}
    reason = (
        f"{distance_names.get(distance, '中期')}应期, 约{days}天"
        f" ({'/'.join(reason_parts)})"
    )

    return {
        "date": yingqi_date.isoformat(),
        "days": days,
        "reason": reason,
        "expired": date.today() > yingqi_date,
    }


def _jing_gua_yingqi(result: dict) -> dict:
    """静卦应期: 以卦宫五行为主, 默认7天"""
    gong_wx = result.get("gong_wuxing", "")
    zhu = result.get("zhu_gua", {})
    gua_name = zhu.get("name", "未知") if isinstance(zhu, dict) else "未知"

    days = 7  # 静卦默认一周
    yingqi_date = date.today() + timedelta(days=days)

    return {
        "date": yingqi_date.isoformat(),
        "days": days,
        "reason": f"静卦「{gua_name}」(卦宫{gong_wx}): 六爻不动, 以本卦卦辞为主, 应期约{days}天",
        "expired": date.today() > yingqi_date,
    }


def _wuxing_modifier(yao_wx: str, gong_wx: str) -> float:
    """五行生克对时间的影响因子"""
    if not yao_wx or not gong_wx:
        return 1.0

    if yao_wx == gong_wx:
        return 1.0        # 比和, 正常
    if WUXING_SHENG.get(yao_wx) == gong_wx:
        return 0.7        # 爻生宫: 泄气, 应期短
    if WUXING_SHENG.get(gong_wx) == yao_wx:
        return 1.3        # 宫生爻: 旺相, 应期长
    if WUXING_KE.get(yao_wx) == gong_wx:
        return 0.8        # 爻克宫: 有力, 稍短
    if WUXING_KE.get(gong_wx) == yao_wx:
        return 1.5        # 宫克爻: 受制, 应期长

    return 1.0


def _tiyong_modifier(tiyong: dict) -> float:
    """体用关系对时间的影响因子"""
    if not tiyong:
        return 1.0

    relation = tiyong.get("relation", "")
    sentiment = tiyong.get("sentiment", "")

    # 体生用(泄): 稍快, 用生体(旺): 稍慢
    if "生" in relation:
        if "体生" in relation or tiyong.get("ti_gua", "") in relation.split("生")[0]:
            return 0.8  # 体生用: 泄气, 快
        else:
            return 1.3  # 用生体: 旺相, 慢
    if "克" in relation:
        if sentiment == "bullish":
            return 0.9  # 体克用: 吉, 稍快
        else:
            return 1.4  # 用克体: 凶, 慢

    return 1.0


def is_yingqi_expired(record: dict) -> bool:
    """检查一条预测记录的应期是否已过"""
    yingqi_str = record.get("yingqi_date", "")
    if not yingqi_str:
        return False
    try:
        from datetime import date
        yq_date = date.fromisoformat(str(yingqi_str)[:10])
        return date.today() > yq_date
    except (ValueError, TypeError):
        return False
