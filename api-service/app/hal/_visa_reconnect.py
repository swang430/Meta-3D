"""Shared PyVISA conn-lost classifier for the silent-reconnect pattern.

PR #14 added transparent silent reconnect to the Aerotech driver (raw
asyncio socket). PR #15 brings the equivalent pattern to PyVISA-backed
drivers (F64, FS16, UXM in this rollout — ENA waits for evidence).

The retry loop itself stays in-driver because each driver owns its own
PyVISA resource string + open kwargs + timeout-context bookkeeping;
factoring only the classifier (which is a constant lookup) is the
sweet spot for code reuse without forcing every driver into the same
retry mould.

The same Codex P2 lesson from #14 applies here:
  - ``VI_ERROR_CONN_LOST`` (0xBFFF00B5) → socket dropped, retry.
  - ``VI_ERROR_INV_OBJECT`` (0xBFFF000E) → session handle dead, retry.
  - ``VI_ERROR_TMO`` (0xBFFF0015) → device too slow, NOT a socket drop;
    must propagate so the caller can decide.

PyVISA-level equivalent (F64R-1, 2026-07-25 实测 pyvisa 1.16.2):
  - ``pyvisa.errors.InvalidSession`` → 在**已 close 的 Resource** 上再发命令时抛。
    它**不是** ``VisaIOError`` 的子类 (MRO: InvalidSession → Error → Exception),
    因为 ``Resource.session`` 这个 property 在 ``_session is None`` 时就抛了, 根本
    走不到 VISA C 库那层去返回 INV_OBJECT。语义上跟 INV_OBJECT 完全一致 ——
    "这个会话已经没了, 重建才有救" —— 所以归进 conn-lost。
    ⚠ 漏了它的后果是**驱动永久死态**: 崩溃恢复路会故意保留已关闭的句柄 (见
    ``propsim_f64._silent_reconnect_visa``: 置 None 会让 ``if not self._visa_resource``
    把驱动短路成"从未连接"), 若这类异常既不算 conn-lost 也不算 timeout, 后续命令
    就既不排水也不触发重连, 网络恢复了也再也不会自愈。

Adding new conn-lost codes/类型 here is a one-line change that automatically
covers every driver using ``is_visa_conn_lost``.

===================================================================
ResourceManager 所有权 (F64R-8, 2026-07-25) —— **本节是权威说明, 别在驱动里另写一版**
===================================================================
**驱动绝不能调 ``rm.close()``。** 只关自己的 resource/session, RM 引用置 None 即可。

原因 (全部实测, pyvisa 1.16.2):
  · ``ResourceManager`` 是**按后端缓存的单例** —— 同一后端下反复取到**同一个对象**。
    ⚠ **"共用一个 RM"是环境相关的, 别记成全仓只有一个** (2026-07-25 审查纠正):
    ``highlevel.py::_get_default_wrapper()`` 的逻辑是"**先探 IVI 二进制, 找到就返回
    ivi**, 否则 py"(还可被环境变量 ``PYVISA_LIBRARY`` 覆盖), 于是 ——
      - **开发机**(无 IVI): 默认解析成 ``py``, ``ResourceManager()`` 与
        ``ResourceManager('@py')`` 是同一个对象 → 13 个驱动全落在**一个** RM 上;
      - **装了 NI-VISA / Keysight IO Libraries 的机器**(跑 UXM 的现场机很可能属此类):
        写 ``ResourceManager()`` 的 8 个 (UXM / CMW500 / FSW / SMW200A / MXG / ENA /
        X-Series SA / ETS) 落在 **ivi** RM; 写 ``'@py'`` 的 5 个 (F64 / FS16 / ZNA /
        FSVA / RF switch) 落在 **py** RM → **分成两组**。
    ⇒ 禁令对**每一组各自成立**, 所以下面的规则不受环境影响。但**别据此推出"那就在 HAL
    shutdown 统一 close 一次"** —— 在 IVI 环境下那只关掉一半, 另一半照样被连带关闭。
  · ``ResourceManager.close()`` 的源码是 ``for resource in self._created_resources:
    resource.close()`` —— 官方 docstring 原文明写 "this will also terminate connections
    obtained from other ResourceManager instances"。
  ⇒ 任何**一个**仪表 disconnect 时调 ``rm.close()``, 就把**其余全部仪表**的会话一起关了。
    现场表现: HAL 重载 / 单仪表重连之后, 别的仪表"莫名其妙断了"。

为什么"只关自己的 resource"就够: socket 是挂在 resource 上的, 关 resource 即释放
(F64 的 3334 端口只容一条远程连接, 这条已实证)。RM 本身是进程级基础设施 ——
**没有任何驱动有资格代表整个进程关掉它**。

进程退出时 RM 会被 pyvisa 自己收尾: ``ResourceManager.__new__`` 里
``atexit.register(call_close)`` + ``obj._atexit_handler = call_close``
(highlevel.py:3008-3025, 源码注释原文 "Register an atexit handler to ensure the
Resource Manager is properly closed"); ``close()`` 自己会 ``atexit.unregister``。
注: 注册的是 ``WeakMethod`` 包装 —— RM 若已被 GC 就什么都不做, 这是对的。
(2026-07-25 Codex 曾判"pyvisa 没有 atexit 处理器"要求删掉这句, 经查源码**该断言不成立**,
依据留在此处以免下轮重提; 退一步说, 就算没有 atexit, 进程退出时 OS 也会回收 socket,
本节的驱动级禁令不依赖这一条。)
"""
from __future__ import annotations

# VPP-4.3 (VISA Library Specification) status codes.
_CONN_LOST_CODES = frozenset({
    0xBFFF00B5,  # VI_ERROR_CONN_LOST
    0xBFFF000E,  # VI_ERROR_INV_OBJECT
})


def is_visa_conn_lost(exc: BaseException) -> bool:
    """Tell apart 'controller dropped the socket' from every other
    VisaIOError (timeout / parse / device-state).

    Returns False if PyVISA isn't importable in this environment (e.g.
    Mock-only test mode) so callers don't have to guard the import.
    """
    # ⚠ 这里**故意不收** ``ConnectionError``（2026-08-07 撤回）。
    #
    # pyvisa-py 的 raw SOCKET 后端确实可能直接透出 ``BrokenPipeError`` /
    # ``ConnectionResetError`` 而不包成 ``VisaIOError`` —— 这条观察是对的，
    # 但它**只对具体调用点成立**，不该抬进四个驱动共用的判据：
    #
    #   · F64 需要它的那一个点（`propsim_f64.py` 的 `DIAG:SIMU:STATE?` 失败分支）
    #     **早就有** `self._is_visa_conn_lost(e) or isinstance(e, ConnectionError)`，
    #     且那处注释逐条论证过为何收窄到 `ConnectionError`、为何故意不收裸 `OSError`。
    #     共享层再放宽一次是重复，不是补缺。
    #   · UXM / FS16 / ENA 三个驱动**没有**对应的实测依据。UXM 尤其危险：
    #     判成断链后会静默重连并**重发同一条 `BSE:`/`CALL:` 写命令**，
    #     而重复信令是有副作用的；它自己还用 `ConnectionError("[UXM] Not connected")`
    #     表示"从来没连过"，跟"对端断了"混进同一个判据里语义就废了。
    #
    # 结论：放宽留在需要它的驱动里做 override，共享层保持严格。
    # 契约由 `tests/test_fs16_uxm_ena_visa_reconnect.py::TestConnLostClassifier`
    # 的 `is_conn_lost(ConnectionResetError("plain")) is False` 守着。
    try:
        import pyvisa
    except ImportError:
        return False
    # 已 close 的 Resource 上再发命令 → InvalidSession (非 VisaIOError 子类, 见模块
    # docstring)。语义等同 INV_OBJECT: 会话没了, 重建才有救。
    if isinstance(exc, pyvisa.errors.InvalidSession):
        return True
    if not isinstance(exc, pyvisa.errors.VisaIOError):
        return False
    code = getattr(exc, "error_code", None)
    if code is None:
        return False
    # error_code on Windows can be the signed-32 form; normalise to
    # unsigned for comparison against the spec hex constants.
    return (code & 0xFFFFFFFF) in _CONN_LOST_CODES


def is_visa_timeout(exc: BaseException) -> bool:
    """VI_ERROR_TMO (0xBFFF0015) — device 没在窗口内应答。P1-21 ②: 这类
    错误后会话可能残留迟到应答 (下一条 query 会读错位), 调用方应做轻量
    排水 (SYST:ERR? 循环) 而不是直接重载。与 conn-lost 互斥分类。"""
    try:
        import pyvisa
    except ImportError:
        return False
    if not isinstance(exc, pyvisa.errors.VisaIOError):
        return False
    code = getattr(exc, "error_code", None)
    if code is None:
        return False
    return (code & 0xFFFFFFFF) == 0xBFFF0015  # VI_ERROR_TMO
