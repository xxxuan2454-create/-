"""用户注册与登录 (Supabase)"""

from __future__ import annotations

import hashlib
import secrets
from db.supabase_client import get_supabase


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

    # 检查用户名是否已存在
    existing = (
        get_supabase()
        .table("users")
        .select("id", count="exact")
        .eq("username", username)
        .execute()
    )
    if existing.count:
        return False, "用户名已存在"

    get_supabase().table("users").insert({
        "username": username,
        "password_hash": f"{salt}:{pw_hash}",
    }).execute()

    return True, "注册成功"


def login_user(username: str, password: str) -> tuple[int | None, str]:
    """登录验证，返回 (user_id, 消息)"""
    username = username.strip()

    resp = (
        get_supabase()
        .table("users")
        .select("id,password_hash")
        .eq("username", username)
        .execute()
    )
    rows = resp.data or []

    if not rows:
        return None, "用户名不存在"

    row = rows[0]
    stored = row.get("password_hash", "")
    try:
        stored_salt, expected_hash = stored.split(":", 1)
    except ValueError:
        return None, "密码数据损坏"

    actual_hash, _ = _hash_password(password, stored_salt)
    if actual_hash == expected_hash:
        return row["id"], "登录成功"

    return None, "密码错误"
