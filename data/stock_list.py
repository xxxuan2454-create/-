"""全A股列表管理 - 通过adata获取并缓存到SQLite"""

from db.models import get_connection


def sync_full_stock_list() -> int:
    """从静态CSV同步全A股列表到SQLite，返回股票总数"""
    import csv
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent / "all_stocks.csv"
    if not csv_path.exists():
        print(f"股票列表文件不存在: {csv_path}")
        return 0

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS all_stocks (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            exchange TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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
                    "INSERT OR REPLACE INTO all_stocks (code, name, exchange) VALUES (?, ?, ?)",
                    (code, name, exchange),
                )
                count += 1
            except Exception:
                continue

    conn.commit()
    conn.close()
    print(f"同步完成: {count} 只A股（来自静态CSV）")
    return count


def search_all_stocks(query: str, limit: int = 30) -> list[dict]:
    """搜索全A股（名称或代码模糊匹配）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM all_stocks")
    total = cursor.fetchone()[0]

    if total == 0:
        conn.close()
        return []

    query = query.strip()
    cursor.execute(
        "SELECT code, name, exchange FROM all_stocks WHERE code LIKE ? OR name LIKE ? LIMIT ?",
        (f"%{query}%", f"%{query}%", limit),
    )
    rows = [{"code": r[0], "name": r[1], "exchange": r[2]} for r in cursor.fetchall()]
    conn.close()
    return rows


def get_stock_count() -> int:
    """获取数据库中股票总数"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM all_stocks")
    count = cursor.fetchone()[0]
    conn.close()
    return count
