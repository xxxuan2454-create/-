"""一次性脚本: 将 SQLite 数据迁移到 Supabase"""

import sqlite3
import sys
from datetime import date

# 添加项目根目录到 path
sys.path.insert(0, '/Users/xiangxuan/stock-predictor')

from db.supabase_client import get_supabase

DB_PATH = '/Users/xiangxuan/stock-predictor/stock_predictor.db'


def migrate():
    sqlite_conn = sqlite3.connect(DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sb = get_supabase()

    # 检查 Supabase 表是否为空 (避免重复迁移)
    existing = sb.table("predictions").select("*", count="exact").execute()
    if existing.count and existing.count > 0:
        print(f"Supabase 已有 {existing.count} 条预测记录，跳过迁移")
        print("如需重新迁移，请先清空 Supabase 表")
        sqlite_conn.close()
        return

    # ── 1. users ──
    users = sqlite_conn.execute("SELECT * FROM users").fetchall()
    for u in users:
        u_dict = dict(u)
        sb.table("users").insert({
            "id": u_dict["id"],
            "username": u_dict["username"],
            "password_hash": u_dict["password_hash"],
            "created_at": u_dict.get("created_at", ""),
        }).execute()
    print(f"  迁移 users: {len(users)} 条")

    # ── 2. predictions (保留原ID用于关联) ──
    predictions = sqlite_conn.execute("SELECT * FROM predictions ORDER BY id").fetchall()
    for p in predictions:
        p_dict = dict(p)
        sb.table("predictions").insert({
            "id": p_dict["id"],
            "user_id": p_dict.get("user_id", 1),
            "stock_code": p_dict.get("stock_code", ""),
            "stock_name": p_dict.get("stock_name", ""),
            "zhu_gua_name": p_dict.get("zhu_gua_name", ""),
            "zhu_gua_full": p_dict.get("zhu_gua_full", ""),
            "bian_gua_name": p_dict.get("bian_gua_name", ""),
            "bian_gua_full": p_dict.get("bian_gua_full", ""),
            "changing_lines": p_dict.get("changing_lines", ""),
            "dong_yao_details": p_dict.get("dong_yao_details", ""),
            "ti_yong_analysis": p_dict.get("ti_yong_analysis", ""),
            "ai_prediction": p_dict.get("ai_prediction", ""),
            "ai_confidence": p_dict.get("ai_confidence", 0),
            "ai_analysis": p_dict.get("ai_analysis", ""),
            "ai_model": p_dict.get("ai_model", ""),
            "retry_count": p_dict.get("retry_count", 0),
            "predicted_at": p_dict.get("predicted_at", ""),
            "predicted_price": p_dict.get("predicted_price", 0),
            "target_date": p_dict.get("target_date", date.today().isoformat()),
            "actual_result": p_dict.get("actual_result", ""),
            "actual_price": p_dict.get("actual_price", 0),
            "actual_change_pct": p_dict.get("actual_change_pct", 0),
            "accuracy_checked": p_dict.get("accuracy_checked", 0),
            "created_at": p_dict.get("created_at", ""),
            "yingqi_date": p_dict.get("yingqi_date", ""),
        }).execute()
    print(f"  迁移 predictions: {len(predictions)} 条")

    # ── 3. stock_picks ──
    picks = sqlite_conn.execute("SELECT * FROM stock_picks").fetchall()
    for pk in picks:
        pk_dict = dict(pk)
        sb.table("stock_picks").insert({
            "strategy": pk_dict.get("strategy", ""),
            "stock_code": pk_dict.get("stock_code", ""),
            "stock_name": pk_dict.get("stock_name", ""),
            "score": pk_dict.get("score", 0),
            "analysis_json": pk_dict.get("analysis_json", ""),
            "picked_at": pk_dict.get("picked_at", ""),
        }).execute()
    print(f"  迁移 stock_picks: {len(picks)} 条")

    # ── 4. quality_logs ──
    logs = sqlite_conn.execute("SELECT * FROM quality_logs").fetchall()
    for log in logs:
        log_dict = dict(log)
        sb.table("quality_logs").insert({
            "call_type": log_dict.get("call_type", ""),
            "input_summary": log_dict.get("input_summary", ""),
            "retry_count": log_dict.get("retry_count", 0),
            "quality_passed": log_dict.get("quality_passed", 0),
            "fail_reason": log_dict.get("fail_reason", ""),
            "response_length": log_dict.get("response_length", 0),
            "created_at": log_dict.get("created_at", ""),
        }).execute()
    print(f"  迁移 quality_logs: {len(logs)} 条")

    sqlite_conn.close()
    print("\n✅ 迁移完成!")


if __name__ == "__main__":
    migrate()
