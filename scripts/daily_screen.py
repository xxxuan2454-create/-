#!/usr/bin/env python
"""每日收盘后全市场策略筛选（Sequoia-X + qstock），结果存入SQLite。

用法：python scripts/daily_screen.py
建议：每天 15:30 后执行一次（cron / 手动均可）
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import init_db
from db.store import save_stock_picks
from config import STOCK_POOL
from strategies.sequoia_x import screen_stock_pool
from strategies.qstock_scorer import screen_by_comprehensive


def main():
    init_db()

    stock_total = len(STOCK_POOL)
    print(f"=" * 50)
    print(f"每日策略筛选 - {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"股票池: {stock_total} 只")
    print(f"=" * 50)

    # ── Sequoia-X 技术面筛选 ──
    print("\n[1/2] Sequoia-X 技术面筛选（20线程并行）...")
    t0 = time.time()

    def seq_progress(done, total):
        pct = done / total * 100
        if done % 200 == 0 or done == total:
            print(f"  进度: {done}/{total} ({pct:.1f}%)")

    df_seq = screen_stock_pool(progress_callback=seq_progress)
    t1 = time.time()
    print(f"  Sequoia-X 完成: {len(df_seq)} 条命中, 耗时 {t1 - t0:.0f}s")

    if not df_seq.empty:
        picks = df_seq.to_dict(orient="records")
        save_stock_picks("sequoia_x", picks)
        print(f"  已保存 {len(picks)} 条到 DB")

    # ── qstock 多因子评分 ──
    print("\n[2/2] qstock 多因子评分（200只，15线程并行）...")
    t0 = time.time()

    def qs_progress(done, total):
        if done % 50 == 0 or done == total:
            print(f"  进度: {done}/{total}")

    results = screen_by_comprehensive(
        limit=50, stock_limit=200, progress_callback=qs_progress
    )
    t1 = time.time()
    print(f"  qstock 完成: {len(results)} 条, 耗时 {t1 - t0:.0f}s")

    if results:
        picks = [
            {"code": r["code"], "name": r["name"],
             "score": r["total_score"], "strategy": "qstock"}
            for r in results
        ]
        save_stock_picks("qstock", picks)
        print(f"  已保存 {len(picks)} 条到 DB")

    print(f"\n{'=' * 50}")
    print(f"全部完成! 总耗时约 {(time.time() - t0 + t1 - t0):.0f}s")
    print(f"打开 Streamlit → 选股筛选 → 综合推荐 查看结果")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
