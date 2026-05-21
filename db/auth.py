"""用户注册与登录"""

import hashlib
import secrets
from db.models import get_connection


def _hash_password(password: str, salt: str = "") -> tuple[str, str]:
    """SHA-256 加盐哈希"""
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return h, salt


def register_user(username: str, password: str) -> tuple[bool, str]:
    """注册新用户，返回 (成功, 消息)"""
    username = username.strip()
    if len(username) < 2:
        return False, "用户名至少2个字符"
    if len(password) < 4:
        return False, "密码至少4个字符"

    pw_hash, salt = _hash_password(password)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, f"{salt}:{pw_hash}"),
        )
        conn.commit()
        return True, "注册成功"
    except Exception:
        return False, "用户名已存在"
    finally:
        conn.close()


def login_user(username: str, password: str) -> tuple[int | None, str]:
    """登录验证，返回 (user_id, 消息)"""
    username = username.strip()

    conn = get_connection()
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not row:
        return None, "用户名不存在"

    stored = row["password_hash"]
    try:
        salt, expected_hash = stored.split(":", 1)
    except ValueError:
        return None, "密码数据损坏"

    actual_hash, _ = _hash_password(password, salt)
    if actual_hash == expected_hash:
        return row["id"], "登录成功"

    return None, "密码错误"
