"""
认证工具 - 用户注册、登录、密码验证
"""

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import Column, Integer, String

from app.db.database import SessionLocal, engine
from app.db.models import Base, User


def _create_user_table():
    """确保 users 表存在"""
    Base.metadata.create_all(bind=engine)


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """哈希密码，返回 (hash, salt)"""
    if salt is None:
        salt = secrets.token_hex(16)
    hash_value = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return hash_value.hex(), salt


def verify_password(password: str, hash_value: str, salt: str) -> bool:
    """验证密码"""
    new_hash, _ = hash_password(password, salt)
    return new_hash == hash_value


def register_user(username: str, password: str) -> tuple[bool, str]:
    """
    注册新用户
    返回: (成功标志, 消息)
    """
    _create_user_table()

    if not username or not password:
        return False, "用户名和密码不能为空"

    if len(password) < 6:
        return False, "密码长度至少6位"

    with SessionLocal() as db:
        # 检查用户名是否已存在
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return False, "用户名已存在"

        # 创建用户
        password_hash, salt = hash_password(password)
        user = User(
            username=username,
            password_hash=f"{password_hash}:{salt}",
            created_at=datetime.now().isoformat()
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return True, f"用户 {username} 注册成功"


def login_user(username: str, password: str) -> tuple[bool, str, int]:
    """
    登录用户
    返回: (成功标志, 消息, user_id)
    """
    _create_user_table()

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return False, "用户名或密码错误", -1

        password_hash, salt = hash_password(password, user.password_hash.split(':')[1])
        if password_hash != user.password_hash.split(':')[0]:
            return False, "用户名或密码错误", -1

        return True, f"登录成功", user.id


def get_user(user_id: int) -> User | None:
    """获取用户信息"""
    with SessionLocal() as db:
        return db.query(User).filter(User.id == user_id).first()
