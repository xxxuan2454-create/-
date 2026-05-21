"""预测记录与选股结果 CRUD 操作"""

import json
import hashlib
from datetime import date, datetime
from typing import Any

import pandas as pd

from db.models import get_connection


# ── 预测记录 ──────────────────────────────────────────────────

def save_prediction(
    stock_code: str,
    stock_name: str,
    zhu_gua_name: str,
    zhu_gua_full: dict,
    bian_gua_name: str,
    bian_gua_full: dict | None,
    changing_lines: list[int],
    dong_yao_details: str,
    ti_yong_analysis: str,
    ai_prediction: str,
    ai_confidence: float,
    ai_analysis: str,
    ai_model: str = "",
    predicted_price: float = 0.0,
    retry_count: int = 0,
    yingqi_date: str = "",
    user_id: int = 1,
) -> int:
    """保存一条预测记录，返回记录ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO predictions (
            user_id, stock_code, stock_name, zhu_gua_name, zhu_gua_full, bian_gua_name,
            bian_gua_full, changing_lines, dong_yao_details, ti_yong_analysis,
            ai_prediction, ai_confidence, ai_analysis, ai_model,
            predicted_price, target_date, retry_count, yingqi_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, stock_code, stock_name, zhu_gua_name,
        json.dumps(zhu_gua_full, ensure_ascii=False),
        bian_gua_name,
        json.dumps(bian_gua_full, ensure_ascii=False) if bian_gua_full else None,
        json.dumps(changing_lines),
        dong_yao_details, ti_yong_analysis,
        ai_prediction, ai_confidence, ai_analysis, ai_model,
        predicted_price, date.today().isoformat(), retry_count, yingqi_date,
    ))
    conn.commit()
    rid = cursor.lastrowid
    conn.close()
    return rid


def get_predictions(
    stock_code: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int = 1,
) -> list[dict]:
    """查询预测记录"""
    conn = get_connection()
    cursor = conn.cursor()
    if stock_code:
        cursor.execute(
            "SELECT * FROM predictions WHERE user_id = ? AND stock_code = ? ORDER BY predicted_at DESC LIMIT ? OFFSET ?",
            (user_id, stock_code, limit, offset),
        )
    else:
        cursor.execute(
            "SELECT * FROM predictions WHERE user_id = ? ORDER BY predicted_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def save_divination_cast(
    stock_code: str, stock_name: str,
    zhu_gua_name: str, zhu_gua_full: dict,
    bian_gua_name: str, bian_gua_full: dict | None,
    changing_lines: list[int], dong_yao_details: str,
    ti_yong_analysis: str, predicted_price: float = 0.0,
    yingqi_date: str = "",
    user_id: int = 1,
) -> int:
    """仅保存卦象 (AI预测前)，返回记录ID供后续更新"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO predictions (
            user_id, stock_code, stock_name, zhu_gua_name, zhu_gua_full, bian_gua_name,
            bian_gua_full, changing_lines, dong_yao_details, ti_yong_analysis,
            predicted_price, target_date, yingqi_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, stock_code, stock_name, zhu_gua_name,
        json.dumps(zhu_gua_full, ensure_ascii=False),
        bian_gua_name,
        json.dumps(bian_gua_full, ensure_ascii=False) if bian_gua_full else None,
        json.dumps(changing_lines), dong_yao_details, ti_yong_analysis,
        predicted_price, date.today().isoformat(), yingqi_date,
    ))
    conn.commit()
    rid = cursor.lastrowid
    conn.close()
    return rid


def update_ai_prediction(
    prediction_id: int, ai_prediction: str, ai_confidence: float,
    ai_analysis: str, ai_model: str = "", retry_count: int = 0,
) -> None:
    """更新已有卦象记录的AI预测结果"""
    conn = get_connection()
    conn.execute("""
        UPDATE predictions SET
            ai_prediction = ?, ai_confidence = ?, ai_analysis = ?,
            ai_model = ?, retry_count = ?,
            predicted_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (ai_prediction, ai_confidence, ai_analysis, ai_model, retry_count, prediction_id))
    conn.commit()
    conn.close()


def update_actual_result(prediction_id: int, actual_price: float, actual_change_pct: float) -> None:
    """更新实际结果"""
    actual_result = "涨" if actual_change_pct > 0 else ("跌" if actual_change_pct < 0 else "平")
    conn = get_connection()
    conn.execute("""
        UPDATE predictions SET actual_result=?, actual_price=?, actual_change_pct=?, accuracy_checked=1
        WHERE id=?
    """, (actual_result, actual_price, actual_change_pct, prediction_id))
    conn.commit()
    conn.close()


def get_accuracy_stats(user_id: int = 1) -> dict:
    """获取预测准确率统计"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM predictions WHERE user_id = ?", (user_id,))
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as checked FROM predictions WHERE user_id = ? AND accuracy_checked = 1", (user_id,))
    checked = cursor.fetchone()["checked"]

    cursor.execute("""
        SELECT COUNT(*) as correct FROM predictions
        WHERE user_id = ?
        AND accuracy_checked = 1
        AND ((ai_prediction = '涨' AND actual_result = '涨')
            OR (ai_prediction = '跌' AND actual_result = '跌')
            OR (ai_prediction = '平' AND actual_result = '平'))
    """, (user_id,))
    correct = cursor.fetchone()["correct"]

    conn.close()
    return {
        "total_predictions": total,
        "accuracy_checked": checked,
        "correct": correct,
        "accuracy": round(correct / checked * 100, 1) if checked > 0 else 0,
    }


def get_today_predictions(user_id: int = 1) -> list[dict]:
    """获取今日预测"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM predictions WHERE user_id = ? AND date(predicted_at) = date('now') ORDER BY predicted_at DESC",
        (user_id,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def resolve_stock_daily_conflicts(user_id: int, stock_code: str) -> dict | None:
    """检查同日同股上午/下午预测是否方向冲突，以置信度高者为准。
    低置信度记录的 ai_analysis 末尾追加覆盖说明。
    返回 {"winner_id": int, "winner_direction": str, "winner_confidence": float, "overridden_ids": [int]}
    无冲突返回 None。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM predictions WHERE user_id = ? AND stock_code = ?"
        " AND date(predicted_at) = date('now') AND ai_prediction IS NOT NULL"
        " ORDER BY ai_confidence DESC",
        (user_id, stock_code),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if len(rows) < 2:
        return None

    winner = rows[0]
    overridden_ids = []

    for r in rows[1:]:
        if r["ai_prediction"] != winner["ai_prediction"]:
            note = (
                f"\n\n---\n"
                f"⚠️ 同日上/下午预测方向冲突：本卦「{r['ai_prediction']}」(置信度 {r['ai_confidence']*100:.0f}%) "
                f"已被「{winner['ai_prediction']}」(置信度 {winner['ai_confidence']*100:.0f}%) 覆盖。"
            )
            new_analysis = (r["ai_analysis"] or "") + note
            conn2 = get_connection()
            conn2.execute(
                "UPDATE predictions SET ai_analysis = ? WHERE id = ?",
                (new_analysis, r["id"]),
            )
            conn2.commit()
            conn2.close()
            overridden_ids.append(r["id"])

    if overridden_ids:
        return {
            "winner_id": winner["id"],
            "winner_direction": winner["ai_prediction"],
            "winner_confidence": winner["ai_confidence"],
            "overridden_ids": overridden_ids,
        }
    return None


def get_today_stock_prediction(user_id: int, stock_code: str) -> dict | None:
    """获取今日某股票最近一条预测记录（含完整卦象和AI结果）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM predictions WHERE user_id = ? AND stock_code = ?"
        " AND date(predicted_at) = date('now') ORDER BY predicted_at DESC LIMIT 1",
        (user_id, stock_code),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_halfday_stock_count(user_id: int, stock_code: str) -> tuple[int, int]:
    """返回 (上午已占数, 下午已占数)，按今日0点/12点分界"""
    conn = get_connection()
    cursor = conn.cursor()
    # 上午: 00:00-11:59, 下午: 12:00-23:59
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM predictions WHERE user_id = ? AND stock_code = ?"
        " AND date(predicted_at) = date('now')"
        " AND CAST(strftime('%H', predicted_at) AS INTEGER) < 12",
        (user_id, stock_code),
    )
    morning = cursor.fetchone()["cnt"]
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM predictions WHERE user_id = ? AND stock_code = ?"
        " AND date(predicted_at) = date('now')"
        " AND CAST(strftime('%H', predicted_at) AS INTEGER) >= 12",
        (user_id, stock_code),
    )
    afternoon = cursor.fetchone()["cnt"]
    conn.close()
    return morning, afternoon


# ── 选股结果 ──────────────────────────────────────────────────

def save_stock_picks(strategy: str, picks: list[dict]) -> None:
    """批量保存选股结果"""
    conn = get_connection()
    cursor = conn.cursor()
    # 清除今日同策略旧结果
    cursor.execute(
        "DELETE FROM stock_picks WHERE strategy = ? AND date(picked_at) = date('now')",
        (strategy,),
    )
    for p in picks:
        cursor.execute(
            "INSERT INTO stock_picks (strategy, stock_code, stock_name, score, analysis_json) VALUES (?, ?, ?, ?, ?)",
            (strategy, p.get("code", ""), p.get("name", ""), p.get("score", 0),
             json.dumps(p, ensure_ascii=False)),
        )
    conn.commit()
    conn.close()


def get_stock_picks(strategy: str | None = None, limit: int = 30) -> list[dict]:
    """获取选股结果"""
    conn = get_connection()
    cursor = conn.cursor()
    if strategy:
        cursor.execute(
            "SELECT * FROM stock_picks WHERE strategy = ? ORDER BY score DESC, picked_at DESC LIMIT ?",
            (strategy, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM stock_picks ORDER BY score DESC, picked_at DESC LIMIT ?",
            (limit,),
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def has_today_screening(strategy: str) -> bool:
    """检查今日是否已有某策略的筛选结果"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM stock_picks WHERE strategy = ? AND date(picked_at) = date('now')",
        (strategy,),
    )
    row = cursor.fetchone()
    conn.close()
    return (row["cnt"] if row else 0) > 0


def get_latest_screening_time(strategy: str) -> str | None:
    """获取某策略最近一次筛选时间，无结果返回 None"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT picked_at FROM stock_picks WHERE strategy = ? ORDER BY picked_at DESC LIMIT 1",
        (strategy,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["picked_at"] if row else None


# ── 质量日志 ──────────────────────────────────────────────────

def get_pending_verifications(user_id: int = 1) -> list[dict]:
    """获取需要验证的预测 (target_date已过但未回测)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM predictions
        WHERE user_id = ?
        AND accuracy_checked = 0
        AND target_date < date('now')
        AND predicted_price > 0
        ORDER BY target_date DESC
    """, (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def auto_backfill_results(user_id: int = 1) -> int:
    """自动回填: 用yfinance获取实际收盘价并更新预测准确度"""
    from data.fetcher import fetch_stock_history
    pending = get_pending_verifications(user_id=user_id)

    if not pending:
        return 0

    count = 0
    for p in pending:
        try:
            df = fetch_stock_history(p["stock_code"], period="1mo")
            if df.empty or len(df) < 2:
                continue

            # 找到target_date之后第一个交易日的收盘价
            target = pd.Timestamp(p["target_date"])
            df.index = pd.to_datetime(df.index)
            after_target = df[df.index > target]

            if after_target.empty:
                continue

            actual_close = float(after_target.iloc[0]["close"])
            predicted_price = float(p["predicted_price"]) if p["predicted_price"] else 0
            if predicted_price > 0:
                actual_change_pct = round(
                    (actual_close - predicted_price) / predicted_price * 100, 2
                )
            else:
                actual_change_pct = 0

            update_actual_result(p["id"], actual_close, actual_change_pct)
            count += 1
        except Exception as e:
            print(f"自动回填 #{p['id']} 失败: {e}")

    return count


def log_quality(call_type: str, input_text: str, retry_count: int,
                quality_passed: bool, fail_reason: str = "",
                response_length: int = 0) -> None:
    """记录AI质量检测日志"""
    conn = get_connection()
    conn.execute(
        "INSERT INTO quality_logs (call_type, input_summary, retry_count, quality_passed, fail_reason, response_length) VALUES (?, ?, ?, ?, ?, ?)",
        (call_type, input_text[:200], retry_count, int(quality_passed),
         fail_reason[:500], response_length),
    )
    conn.commit()
    conn.close()
