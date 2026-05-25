"""数据库初始化 - SQLite 用于本地缓存(all_stocks), Supabase 用于持久化存储"""

import sqlite3

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """获取 SQLite 连接 (仅用于 stock_list 本地缓存)"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """初始化 (Supabase 持久化表通过 supabase_migration.sql 手动创建)"""
    conn = get_connection()
    conn.close()
