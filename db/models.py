"""SQLite 数据库模型与初始化"""

import sqlite3
from pathlib import Path

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """初始化数据库表"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 1,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            zhu_gua_name TEXT,
            zhu_gua_full TEXT,
            bian_gua_name TEXT,
            bian_gua_full TEXT,
            changing_lines TEXT,
            dong_yao_details TEXT,
            ti_yong_analysis TEXT,
            ai_prediction TEXT,
            ai_confidence REAL,
            ai_analysis TEXT,
            ai_model TEXT,
            retry_count INTEGER DEFAULT 0,
            predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            predicted_price REAL,
            target_date DATE,
            actual_result TEXT,
            actual_price REAL,
            actual_change_pct REAL,
            accuracy_checked INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            yingqi_date DATE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS stock_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            score REAL,
            analysis_json TEXT,
            picked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quality_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_type TEXT NOT NULL,
            input_summary TEXT,
            retry_count INTEGER DEFAULT 0,
            quality_passed INTEGER DEFAULT 0,
            fail_reason TEXT,
            response_length INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 迁移: 为已有数据库添加新列 (忽略已存在列的错误)
    for col, col_def in [
        ("user_id", "INTEGER DEFAULT 1"),
        ("yingqi_date", "DATE"),
    ]:
        try:
            conn.execute(f"ALTER TABLE predictions ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass  # 列已存在

    conn.commit()
    conn.close()
