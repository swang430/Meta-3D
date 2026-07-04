"""可重入 asyncio 锁 — SCPI 事务与单命令互斥共用 (P1-21 + Codex #203 R3)。

背景: F64/FS16 的 `_do_write`/`_do_query` 每条命令持 `_scpi_lock` (P1-21 ①,
防 broadcaster 并发串线)。但 "动作 + 错误队列判定" 的复合序列 (GO 门 /
AUTOSET 门 / load 门) 需要**整段原子** — 单命令锁下 broadcaster 轮询会插进
两步之间, 留下自己的错误条目 (gate 误报) 或抢先消费本次动作的错误 (漏报,
Codex #203 R3)。

`asyncio.Lock` 不可重入 — 事务外层持锁后, 序列内 `self._query(...)` 经
`_do_query` 再取锁会死锁。本锁记录持有 task, **同 task 重入直通** (深度
计数), 使事务代码可以照常使用 `self._write`/`self._query` (测试对这两层的
monkeypatch 也天然兼容), 不需要平行的 *_unlocked 原语家族。

单事件循环语义: 持有权以 `asyncio.current_task()` 为身份, 跨 await 点稳定;
`to_thread` 的工作线程不触碰本锁 (锁只在协程层进出)。
"""
from __future__ import annotations

import asyncio
from typing import Optional


class ReentrantAsyncLock:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: Optional[asyncio.Task] = None
        self._depth = 0

    def locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self) -> "ReentrantAsyncLock":
        cur = asyncio.current_task()
        if self._owner is cur:
            self._depth += 1
            return self
        await self._lock.acquire()
        self._owner = cur
        self._depth = 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()
