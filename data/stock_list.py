"""全A股列表管理 - 通过adata获取并缓存到SQLite"""

from db.models import get_connection


def sync_full_stock_list() -> int:
    """从adata同步全A股列表到SQLite，返回股票总数"""
    import adata

    try:
        df = adata.stock.info.all_code()
    except Exception as e:
        print(f"adata同步失败: {e}")
        return 0

    if df.empty:
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
    for _, row in df.iterrows():
        try:
            raw_code = str(row.get("stock_code", "")).strip()
            name = str(row.get("short_name", "")).strip()
            exchange_raw = str(row.get("exchange", "")).strip()

            if not raw_code or not name or len(raw_code) < 6:
                continue
            # Normalize to 6-digit code
            raw_code = raw_code.zfill(6)

            # Map exchange to yfinance suffix
            if raw_code.startswith(("6", "9")):
                yf_code = f"{raw_code}.SS"
                exchange = "SSE"
            elif raw_code.startswith(("0", "2", "3", "8")):
                yf_code = f"{raw_code}.SZ"
                exchange = "SZSE"
            elif raw_code.startswith(("4", "8")):
                yf_code = f"{raw_code}.BJ"
                exchange = "BSE"
            else:
                continue

            cursor.execute(
                "INSERT OR REPLACE INTO all_stocks (code, name, exchange) VALUES (?, ?, ?)",
                (yf_code, name, exchange),
            )
            count += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    print(f"同步完成: {count} 只A股")
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
