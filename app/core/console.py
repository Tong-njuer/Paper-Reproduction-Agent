# ============================================================
# 控制台输出工具模块
# ============================================================
# 提供跨平台控制台输出支持。
# 处理 Windows（GBK）与 UTF-8 系统的编码问题。
#
# Usage:
#   from app.core.console import print, info, warn, error
#
# Console Output Format:
#   [MODULE] Message - 标准化的前缀格式
# ============================================================

import sys
import os

# 在 Windows 上尝试启用 UTF-8 模式
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


def safe_print(*args, **kwargs):
    """
    处理编码问题的打印函数。

    在带有 GBK 控制台的 Windows 上，
    会尝试正确编码或替换不支持的字符。
    """
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        encoded_args = []
        for arg in args:
            if isinstance(arg, str):
                encoded_args.append(arg.encode('gbk', errors='replace').decode('gbk'))
            else:
                encoded_args.append(arg)
        print(*encoded_args, **kwargs)


# ============================================================
# 便捷函数
# ============================================================

def info(msg: str, module: str = "APP"):
    """Print an info message."""
    safe_print(f"[{module}] {msg}")


def warn(msg: str, module: str = "APP"):
    """Print a warning message."""
    safe_print(f"[{module}] WARNING: {msg}")


def error(msg: str, module: str = "APP"):
    """Print an error message."""
    safe_print(f"[{module}] ERROR: {msg}")


def success(msg: str, module: str = "APP"):
    """Print a success message."""
    safe_print(f"[{module}] SUCCESS: {msg}")


# ============================================================
# Emoji Replacements (ASCII alternatives)
# ============================================================

EMOJI_MAP = {
    '[OK]': '[OK]',
    '[X]': '[X]',
    '[!]': '[!]',
    '[INFO]': '[INFO]',
    '[STAT]': '[STAT]',
    '[NOTE]': '[NOTE]',
    '[PKG]': '[PKG]',
    '[RUN]': '[RUN]',
    '[END]': '[END]',
    '[NEW]': '[NEW]',
    '[BRAIN]': '[BRAIN]',
    '[RETRY]': '[SYNC]',
    '[THINK]': '[THINK]',
    '[EXEC]': '[EXEC]',
    '[OUT]': '[OUT]',
    '[IN]': '[IN]',
    '[REFLECT]': '[REFLECT]',
    '[LEARN]': '[LEARN]',
    '[SEARCH]': '[SEARCH]',
    '[FIX]': '[FIX]',
    '[GOAL]': '[GOAL]',
    '[STEP]': '[STEP]',
    '[STOP]': '[STOP]',
    '[DEMO]': '[DEMO]',
    '[AGENT]': '[AGENT]',
    '[TIME]': '[TIME]',
    '[SAVE]': '[SAVE]',
    '[PIN]': '[PIN]',
    '[LINK]': '[LINK]',
    '[WAIT]': '[WAIT]',
    '[RETRY]': '[RETRY]',
    '[SKIP]': '[SKIP]',
    '[BRANCH]': '[BRANCH]',
    '[ADD]': '[ADD]',
    '[REMOVE]': '[REMOVE]',
}


def strip_emoji(text: str) -> str:
    """
    Replace emojis with ASCII alternatives.

    Args:
        text: Text that may contain emojis

    Returns:
        str: Text with emojis replaced by ASCII
    """
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    return text


def print_with_emoji_fallback(*args, **kwargs):
    """
    Print with emoji fallback on Windows.

    Replaces known emojis with ASCII alternatives if encoding fails.
    """
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        new_args = []
        for arg in args:
            if isinstance(arg, str):
                new_args.append(strip_emoji(arg))
            else:
                new_args.append(arg)
        print(*new_args, **kwargs)
