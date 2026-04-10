"""
用户上下文 - 存储当前登录用户的ID
"""

import threading

# 线程本地上下文（适用于Web多用户场景）
_thread_local = threading.local()


def set_current_user_id(user_id: int):
    """设置当前用户ID"""
    _thread_local.user_id = user_id


def get_current_user_id() -> int | None:
    """获取当前用户ID"""
    return getattr(_thread_local, 'user_id', None)


def clear_current_user():
    """清除当前用户（登出时调用）"""
    _thread_local.user_id = None
