"""正式测试与破坏性诊断共享的进程内互斥占位。

当前部署契约是单 API 进程、单事件循环。这里刻意不用 ``asyncio.Lock``：
``try_acquire_unsafe_diagnostic`` 的检查与占位之间没有 ``await``，因此在同一
事件循环内是不可插入的原子段。若以后扩为多 worker，必须把这个占位迁到数据库
或分布式锁；本模块不宣称跨进程互斥。
"""
from __future__ import annotations

from typing import Optional, Tuple
from uuid import uuid4


# (token, sequence_key)；只允许一个破坏性诊断占用 HAL。
_ACTIVE_UNSAFE_DIAGNOSTIC: Optional[Tuple[str, str]] = None


def active_unsafe_diagnostic() -> Optional[str]:
    """返回当前破坏性诊断 key；无占用则返回 ``None``。"""
    if _ACTIVE_UNSAFE_DIAGNOSTIC is None:
        return None
    return _ACTIVE_UNSAFE_DIAGNOSTIC[1]


def try_acquire_unsafe_diagnostic(sequence_key: str) -> Optional[str]:
    """无等待地检查并占位；忙时返回 ``None``，成功时返回释放 token。"""
    global _ACTIVE_UNSAFE_DIAGNOSTIC
    if _ACTIVE_UNSAFE_DIAGNOSTIC is not None:
        return None
    token = uuid4().hex
    _ACTIVE_UNSAFE_DIAGNOSTIC = (token, sequence_key)
    return token


def release_unsafe_diagnostic(token: str) -> bool:
    """只允许持有者释放，避免旧请求误删后来者的占位。"""
    global _ACTIVE_UNSAFE_DIAGNOSTIC
    if (
        _ACTIVE_UNSAFE_DIAGNOSTIC is None
        or _ACTIVE_UNSAFE_DIAGNOSTIC[0] != token
    ):
        return False
    _ACTIVE_UNSAFE_DIAGNOSTIC = None
    return True


def reset_unsafe_diagnostic_guard_for_tests() -> None:
    """测试隔离专用；生产代码不得调用。"""
    global _ACTIVE_UNSAFE_DIAGNOSTIC
    _ACTIVE_UNSAFE_DIAGNOSTIC = None
