"""预测记录与选股结果 CRUD 操作 (Supabase)"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from db.supabase_client import get_supabase


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
    resp = (
        get_supabase()
        .table("predictions")
        .insert({
            "user_id": user_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "zhu_gua_name": zhu_gua_name,
            "zhu_gua_full": json.dumps(zhu_gua_full, ensure_ascii=False),
            "bian_gua_name": bian_gua_name,
            "bian_gua_full": json.dumps(bian_gua_full, ensure_ascii=False) if bian_gua_full else None,
            "changing_lines": json.dumps(changing_lines),
            "dong_yao_details": dong_yao_details,
            "ti_yong_analysis": ti_yong_analysis,
            "ai_prediction": ai_prediction,
            "ai_confidence": ai_confidence,
            "ai_analysis": ai_analysis,
            "ai_model": ai_model,
            "predicted_price": predicted_price,
            "target_date": date.today().isoformat(),
            "retry_count": retry_count,
            "yingqi_date": yingqi_date,
        })
        .execute()
    )
    return resp.data[0]["id"] if resp.data else 0


def get_predictions(
    stock_code: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int = 1,
) -> list[dict]:
    """查询预测记录"""
    query = (
        get_supabase()
        .table("predictions")
        .select("*")
        .eq("user_id", user_id)
        .order("predicted_at", desc=True)
        .limit(limit)
    )
    if stock_code:
        query = query.eq("stock_code", stock_code)
    if offset:
        query = query.offset(offset)
    resp = query.execute()
    return resp.data or []


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
    resp = (
        get_supabase()
        .table("predictions")
        .insert({
            "user_id": user_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "zhu_gua_name": zhu_gua_name,
            "zhu_gua_full": json.dumps(zhu_gua_full, ensure_ascii=False),
            "bian_gua_name": bian_gua_name,
            "bian_gua_full": json.dumps(bian_gua_full, ensure_ascii=False) if bian_gua_full else None,
            "changing_lines": json.dumps(changing_lines),
            "dong_yao_details": dong_yao_details,
            "ti_yong_analysis": ti_yong_analysis,
            "predicted_price": predicted_price,
            "target_date": date.today().isoformat(),
            "yingqi_date": yingqi_date,
        })
        .execute()
    )
    return resp.data[0]["id"] if resp.data else 0


def update_ai_prediction(
    prediction_id: int, ai_prediction: str, ai_confidence: float,
    ai_analysis: str, ai_model: str = "", retry_count: int = 0,
) -> None:
    """更新已有卦象记录的AI预测结果"""
    get_supabase().table("predictions").update({
        "ai_prediction": ai_prediction,
        "ai_confidence": ai_confidence,
        "ai_analysis": ai_analysis,
        "ai_model": ai_model,
        "retry_count": retry_count,
        "predicted_at": datetime.now().isoformat(),
    }).eq("id", prediction_id).execute()


def update_actual_result(prediction_id: int, actual_price: float, actual_change_pct: float) -> None:
    """更新实际结果"""
    actual_result = "涨" if actual_change_pct > 0 else ("跌" if actual_change_pct < 0 else "平")
    get_supabase().table("predictions").update({
        "actual_result": actual_result,
        "actual_price": actual_price,
        "actual_change_pct": actual_change_pct,
        "accuracy_checked": 1,
    }).eq("id", prediction_id).execute()


def get_accuracy_stats(user_id: int = 1) -> dict:
    """获取预测准确率统计"""
    sb = get_supabase()
    total_resp = sb.table("predictions").select("*", count="exact").eq("user_id", user_id).execute()
    total = total_resp.count

    checked_resp = (
        sb.table("predictions").select("*", count="exact")
        .eq("user_id", user_id)
        .eq("accuracy_checked", 1)
        .execute()
    )
    checked = checked_resp.count

    correct = 0
    if checked > 0:
        rows = (
            sb.table("predictions")
            .select("ai_prediction,actual_result")
            .eq("user_id", user_id)
            .eq("accuracy_checked", 1)
            .execute()
        ).data or []
        for r in rows:
            pred = r.get("ai_prediction", "")
            actual = r.get("actual_result", "")
            if ((pred == "涨" and actual == "涨") or
                (pred == "跌" and actual == "跌") or
                (pred == "平" and actual == "平")):
                correct += 1

    return {
        "total_predictions": total,
        "accuracy_checked": checked,
        "correct": correct,
        "accuracy": round(correct / checked * 100, 1) if checked > 0 else 0,
    }


def get_today_predictions(user_id: int = 1) -> list[dict]:
    """获取今日预测"""
    today = date.today().isoformat()
    resp = (
        get_supabase()
        .table("predictions")
        .select("*")
        .eq("user_id", user_id)
        .gte("predicted_at", today)
        .order("predicted_at", desc=True)
        .execute()
    )
    return resp.data or []


def resolve_stock_daily_conflicts(user_id: int, stock_code: str) -> dict | None:
    """检查同日同股上午/下午预测是否方向冲突，以置信度高者为准"""
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    resp = (
        get_supabase()
        .table("predictions")
        .select("*")
        .eq("user_id", user_id)
        .eq("stock_code", stock_code)
        .gte("predicted_at", today)
        .lt("predicted_at", tomorrow)
        .not_.is_("ai_prediction", "null")
        .order("ai_confidence", desc=True)
        .execute()
    )
    rows = resp.data or []

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
            get_supabase().table("predictions").update({
                "ai_analysis": new_analysis,
            }).eq("id", r["id"]).execute()
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
    """获取今日某股票最近一条预测记录"""
    today = date.today().isoformat()
    resp = (
        get_supabase()
        .table("predictions")
        .select("*")
        .eq("user_id", user_id)
        .eq("stock_code", stock_code)
        .gte("predicted_at", today)
        .order("predicted_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def get_halfday_stock_count(user_id: int, stock_code: str) -> tuple[int, int]:
    """返回 (上午已占数, 下午已占数)，按今日0点/12点分界"""
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    noon_today = f"{today}T12:00:00"

    resp = (
        get_supabase()
        .table("predictions")
        .select("predicted_at")
        .eq("user_id", user_id)
        .eq("stock_code", stock_code)
        .gte("predicted_at", today)
        .lt("predicted_at", tomorrow)
        .execute()
    )
    rows = resp.data or []

    morning = sum(1 for r in rows if (r.get("predicted_at") or "") < noon_today)
    afternoon = len(rows) - morning
    return morning, afternoon


# ── 选股结果 ──────────────────────────────────────────────────

def save_stock_picks(strategy: str, picks: list[dict]) -> None:
    """批量保存选股结果"""
    sb = get_supabase()
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # 清除今日同策略旧结果
    sb.table("stock_picks").delete()\
        .eq("strategy", strategy)\
        .gte("picked_at", today)\
        .lt("picked_at", tomorrow)\
        .execute()

    for p in picks:
        sb.table("stock_picks").insert({
            "strategy": strategy,
            "stock_code": p.get("code", ""),
            "stock_name": p.get("name", ""),
            "score": p.get("score", 0),
            "analysis_json": json.dumps(p, ensure_ascii=False),
        }).execute()


def get_stock_picks(strategy: str | None = None, limit: int = 30) -> list[dict]:
    """获取选股结果"""
    query = (
        get_supabase()
        .table("stock_picks")
        .select("*")
        .order("score", desc=True)
        .order("picked_at", desc=True)
        .limit(limit)
    )
    if strategy:
        query = query.eq("strategy", strategy)
    resp = query.execute()
    return resp.data or []


def has_today_screening(strategy: str) -> bool:
    """检查今日是否已有某策略的筛选结果"""
    today = date.today().isoformat()
    resp = (
        get_supabase()
        .table("stock_picks")
        .select("*", count="exact")
        .eq("strategy", strategy)
        .gte("picked_at", today)
        .execute()
    )
    return (resp.count or 0) > 0


def get_latest_screening_time(strategy: str) -> str | None:
    """获取某策略最近一次筛选时间"""
    resp = (
        get_supabase()
        .table("stock_picks")
        .select("picked_at")
        .eq("strategy", strategy)
        .order("picked_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0].get("picked_at") if rows else None


# ── 质量日志 ──────────────────────────────────────────────────

def get_pending_verifications(user_id: int = 1) -> list[dict]:
    """获取需要验证的预测 (target_date已过但未回测)"""
    today = date.today().isoformat()
    resp = (
        get_supabase()
        .table("predictions")
        .select("*")
        .eq("user_id", user_id)
        .eq("accuracy_checked", 0)
        .lt("target_date", today)
        .gt("predicted_price", 0)
        .order("target_date", desc=True)
        .execute()
    )
    return resp.data or []


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
    get_supabase().table("quality_logs").insert({
        "call_type": call_type,
        "input_summary": input_text[:200],
        "retry_count": retry_count,
        "quality_passed": int(quality_passed),
        "fail_reason": fail_reason[:500],
        "response_length": response_length,
    }).execute()
