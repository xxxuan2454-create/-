"""Stock list index (SQLite): A-share + US symbols for search."""

from __future__ import annotations

import csv
from pathlib import Path

from data.markets import MARKET_CN, MARKET_US
from db.models import get_connection

_DATA_DIR = Path(__file__).resolve().parent
_CN_CSV = _DATA_DIR / "all_stocks.csv"
_US_CSV = _DATA_DIR / "all_us_stocks.csv"


def _ensure_schema(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS all_stocks (
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            exchange TEXT,
            market TEXT NOT NULL DEFAULT 'CN',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (code, market)
        )
    """)
    cursor.execute("PRAGMA table_info(all_stocks)")
    columns = {row[1] for row in cursor.fetchall()}
    if "market" not in columns:
        cursor.execute("ALTER TABLE all_stocks ADD COLUMN market TEXT NOT NULL DEFAULT 'CN'")
        cursor.execute(
            "UPDATE all_stocks SET market = 'CN' WHERE market IS NULL OR market = ''"
        )


def _sync_csv(cursor, csv_path: Path, market: str) -> int:
    if not csv_path.exists():
        print(f"股票列表文件不存在: {csv_path}")
        return 0

    count = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("code", "").strip()
            name = row.get("name", "").strip()
            exchange = row.get("exchange", "").strip()
            if not code or not name:
                continue
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO all_stocks (code, name, exchange, market)
                    VALUES (?, ?, ?, ?)
                    """,
                    (code, name, exchange, market),
                )
                count += 1
            except Exception:
                continue
    return count


def sync_full_stock_list() -> int:
    """从静态 CSV 同步 A 股 + 美股列表到 SQLite，返回总条数。"""
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_schema(cursor)

    cn_count = _sync_csv(cursor, _CN_CSV, MARKET_CN)
    us_count = _sync_csv(cursor, _US_CSV, MARKET_US)

    conn.commit()
    conn.close()
    print(f"同步完成: A股 {cn_count} 只, 美股 {us_count} 只")
    return cn_count + us_count


def search_all_stocks(
    query: str,
    limit: int = 30,
    market: str | None = None,
) -> list[dict]:
    """按名称或代码模糊搜索；market 为 CN/US，None 表示搜索全部市场。"""
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_schema(cursor)

    query = query.strip()
    if not query:
        conn.close()
        return []

    like = f"%{query}%"
    if market:
        cursor.execute(
            """
            SELECT code, name, exchange, market FROM all_stocks
            WHERE market = ? AND (code LIKE ? OR name LIKE ?)
            ORDER BY name
            LIMIT ?
            """,
            (market, like, like, limit),
        )
    else:
        cursor.execute(
            """
            SELECT code, name, exchange, market FROM all_stocks
            WHERE code LIKE ? OR name LIKE ?
            ORDER BY market, name
            LIMIT ?
            """,
            (like, like, limit),
        )

    rows = [
        {"code": r[0], "name": r[1], "exchange": r[2], "market": r[3]}
        for r in cursor.fetchall()
    ]
    conn.close()
    return rows


def get_stock_count(market: str | None = None) -> int:
    """获取索引中的股票数量；market 为 CN/US，None 表示全部。"""
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_schema(cursor)

    if market:
        cursor.execute(
            "SELECT COUNT(*) FROM all_stocks WHERE market = ?",
            (market,),
        )
    else:
        cursor.execute("SELECT COUNT(*) FROM all_stocks")

    count = cursor.fetchone()[0]
    conn.close()
    return count
