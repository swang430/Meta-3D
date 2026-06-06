"""P1-6 — FS16 / UXM / ENA silent-reconnect integration tests.

F64 已有 12 个 silent-reconnect 集成测试 (test_f64_visa_reconnect.py, PR #15)。
FS16 / UXM / ENA 继承同一模式 (共享 classifier ``app.hal._visa_reconnect``
+ 各自的 ``_silent_reconnect_visa`` + ``_do_write`` / ``_do_query`` retry 包装),
但一直没有 driver-specific 集成测试 (P1-6, 之前 incident-conditional hold,
现按用户要求补全本地测试覆盖)。

三驱动共享的契约 (与 F64 同):
  1. ``VI_ERROR_CONN_LOST`` (0xBFFF00B5) → 一次 reconnect + retry。
  2. ``VI_ERROR_INV_OBJECT`` (0xBFFF000E) → 一次 reconnect + retry。
  3. ``VI_ERROR_TMO`` (0xBFFF0015) → 不 reconnect, 让超时传播 (Codex #14/#15 教训)。
  4. 非 VISA 异常 → 不 reconnect。
  5. bounded — 第二次连续 conn-lost 仍抛 (无死循环, 只 reconnect 一次)。
  6. reconnect 自身失败 → 原始 conn-lost VISA error 传播 (不被掩盖)。
  7. healthy path — 一切正常时不 reconnect。

driver-specific 差异 (也钉死):
  - FS16: async ``_do_*``; 未连接 → RuntimeError; resource=``_visa_resource`` / rm=``_rm``。
  - UXM:  sync  ``_do_*``; 未连接 → ConnectionError; resource=``_visa_session`` / rm=``_visa_rm``。
  - ENA:  sync  ``_do_*``; 未连接 → 静默 no-op (write→None / query→""); resource=``_visa_session`` / rm=``_visa_rm``。

不连真实仪器: PyVISA resource 用 fake 注入, write/query 可编程 fail-then-succeed。
"""
from __future__ import annotations

from typing import List, Optional

import pytest

pyvisa = pytest.importorskip("pyvisa")

from app.hal.propsim_fs16 import RealPropsimFs16Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.keysight_ena import RealKeysightEnaDriver

# VISA 错误码常量 (与共享 classifier app.hal._visa_reconnect 一致)
VI_ERROR_CONN_LOST = 0xBFFF00B5
VI_ERROR_INV_OBJECT = 0xBFFF000E
VI_ERROR_TMO = 0xBFFF0015


# ---------------------------------------------------------------------------
# Fakes (三驱动共用)
# ---------------------------------------------------------------------------

class _FakeVisaResource:
    """记录 write/query, 可编程在前 N 次调用抛指定 VisaIOError 再成功。"""

    def __init__(self, name: str = "primary") -> None:
        self.name = name
        self.writes: List[str] = []
        self.queries: List[str] = []
        self.write_fail_with: List[Optional[BaseException]] = []
        self.query_fail_with: List[Optional[BaseException]] = []
        self.query_response: str = "OK\n"
        self.timeout: int = 5000
        # UXM SOCKET 分支 / FS16 open kwargs 可能 set 这些, 给 fake 加上免得 AttributeError
        self.read_termination: Optional[str] = None
        self.write_termination: Optional[str] = None
        self.closed = False

    def write(self, cmd: str) -> None:
        if self.write_fail_with:
            exc = self.write_fail_with.pop(0)
            if exc is not None:
                raise exc
        self.writes.append(cmd)

    def query(self, cmd: str) -> str:
        if self.query_fail_with:
            exc = self.query_fail_with.pop(0)
            if exc is not None:
                raise exc
        self.queries.append(cmd)
        return self.query_response

    def close(self) -> None:
        self.closed = True


class _FakeResourceManager:
    """从预置列表发 fake resource: 第一次 reconnect 拿第一个, 以此类推。
    列表空时 open_resource 抛 OSError —— 用来模拟 'reconnect 失败'。"""

    def __init__(self, resources: List[_FakeVisaResource]) -> None:
        self._resources = list(resources)
        self.open_calls: int = 0

    def open_resource(self, *_args, **_kwargs) -> _FakeVisaResource:
        self.open_calls += 1
        if not self._resources:
            raise OSError("reconnect: open_resource called more times than fakes provided")
        return self._resources.pop(0)


def _mk_visa_error(code_unsigned: int) -> "pyvisa.errors.VisaIOError":
    return pyvisa.errors.VisaIOError(code_unsigned)


# ---------------------------------------------------------------------------
# Builders — 把每个驱动接上 fake session + fake RM, 跳过真实 connect()
# ---------------------------------------------------------------------------

def _build_fs16(primary: _FakeVisaResource, *, post_reconnect: List[_FakeVisaResource] = None):
    d = RealPropsimFs16Driver("fs16-test", {"ip": "192.168.0.50", "port": 5025})
    d._visa_resource = primary
    d._rm = _FakeResourceManager(post_reconnect or [])
    d.ip_address = "192.168.0.50"
    d.port = 5025
    return d


def _build_uxm(primary: _FakeVisaResource, *, post_reconnect: List[_FakeVisaResource] = None):
    d = RealUxmDriver("uxm-test", {"ip": "192.168.100.10", "port": 5025})
    d._visa_session = primary
    d._visa_rm = _FakeResourceManager(post_reconnect or [])
    # 不含 "SOCKET" → 跳过 _silent_reconnect_visa 里设 termination 的分支
    d._active_resource_string = "TCPIP::192.168.100.10::hislip2::INSTR"
    return d


def _build_ena(primary: _FakeVisaResource, *, post_reconnect: List[_FakeVisaResource] = None):
    d = RealKeysightEnaDriver("ena-test", {"ip": "192.168.100.40"})
    d._visa_session = primary
    d._visa_rm = _FakeResourceManager(post_reconnect or [])
    d.ip_address = "192.168.100.40"
    return d


# ===========================================================================
# FS16 (async)
# ===========================================================================

class TestFs16Reconnect:
    @pytest.mark.asyncio
    async def test_conn_lost_on_query_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_response = "READY\n"
        d = _build_fs16(primary, post_reconnect=[replacement])

        result = await d._do_query("*IDN?")
        assert result == "READY\n"
        assert primary.closed is True
        assert replacement.queries == ["*IDN?"]
        assert d._rm.open_calls == 1

    @pytest.mark.asyncio
    async def test_inv_object_on_write_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.write_fail_with = [_mk_visa_error(VI_ERROR_INV_OBJECT)]
        replacement = _FakeVisaResource("post-reconnect")
        d = _build_fs16(primary, post_reconnect=[replacement])

        await d._do_write("INIT")
        assert replacement.writes == ["INIT"]
        assert primary.closed is True

    @pytest.mark.asyncio
    async def test_timeout_propagates_without_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_TMO)]
        d = _build_fs16(primary, post_reconnect=[])

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            await d._do_query("SYST:ERR?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == VI_ERROR_TMO
        assert d._rm.open_calls == 0

    @pytest.mark.asyncio
    async def test_non_visa_error_propagates_without_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [RuntimeError("not a VISA error")]
        d = _build_fs16(primary, post_reconnect=[])

        with pytest.raises(RuntimeError):
            await d._do_query("*IDN?")
        assert d._rm.open_calls == 0

    @pytest.mark.asyncio
    async def test_second_consecutive_conn_lost_is_bounded(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        d = _build_fs16(primary, post_reconnect=[replacement])

        with pytest.raises(pyvisa.errors.VisaIOError):
            await d._do_query("*IDN?")
        assert d._rm.open_calls == 1  # 只 reconnect 一次, 无第三次尝试

    @pytest.mark.asyncio
    async def test_reconnect_failure_surfaces_original_error(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        d = _build_fs16(primary, post_reconnect=[])  # 空 RM → reopen 抛 OSError

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            await d._do_query("*IDN?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == VI_ERROR_CONN_LOST

    @pytest.mark.asyncio
    async def test_healthy_path_no_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_response = "PROPSIM FS16,4,RF\n"
        d = _build_fs16(primary, post_reconnect=[])

        result = await d._do_query("*IDN?")
        assert result == "PROPSIM FS16,4,RF\n"
        assert d._rm.open_calls == 0
        assert primary.closed is False

    @pytest.mark.asyncio
    async def test_not_connected_raises_runtime_error(self):
        d = _build_fs16(_FakeVisaResource(), post_reconnect=[])
        d._visa_resource = None
        with pytest.raises(RuntimeError):
            await d._do_query("*IDN?")


# ===========================================================================
# UXM (sync)
# ===========================================================================

class TestUxmReconnect:
    def test_conn_lost_on_query_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_response = "READY\n"
        d = _build_uxm(primary, post_reconnect=[replacement])

        result = d._do_query("*IDN?")
        assert result == "READY\n"
        assert replacement.queries == ["*IDN?"]
        assert d._visa_rm.open_calls == 1

    def test_inv_object_on_write_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.write_fail_with = [_mk_visa_error(VI_ERROR_INV_OBJECT)]
        replacement = _FakeVisaResource("post-reconnect")
        d = _build_uxm(primary, post_reconnect=[replacement])

        d._do_write("INIT")
        assert replacement.writes == ["INIT"]
        assert primary.closed is True
        assert d._visa_rm.open_calls == 1

    def test_timeout_propagates_without_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_TMO)]
        d = _build_uxm(primary, post_reconnect=[])

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            d._do_query("SYST:ERR?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == VI_ERROR_TMO
        assert d._visa_rm.open_calls == 0

    def test_non_visa_error_propagates_without_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [RuntimeError("not a VISA error")]
        d = _build_uxm(primary, post_reconnect=[])

        with pytest.raises(RuntimeError):
            d._do_query("*IDN?")
        assert d._visa_rm.open_calls == 0

    def test_second_consecutive_conn_lost_is_bounded(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        d = _build_uxm(primary, post_reconnect=[replacement])

        with pytest.raises(pyvisa.errors.VisaIOError):
            d._do_query("*IDN?")
        assert d._visa_rm.open_calls == 1

    def test_reconnect_failure_surfaces_original_error(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        d = _build_uxm(primary, post_reconnect=[])

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            d._do_query("*IDN?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == VI_ERROR_CONN_LOST

    def test_healthy_path_no_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_response = "Keysight,E7515B\n"
        d = _build_uxm(primary, post_reconnect=[])

        result = d._do_query("*IDN?")
        assert result == "Keysight,E7515B\n"
        assert d._visa_rm.open_calls == 0
        assert primary.closed is False

    def test_not_connected_raises_connection_error(self):
        d = _build_uxm(_FakeVisaResource(), post_reconnect=[])
        d._visa_session = None
        with pytest.raises(ConnectionError):
            d._do_query("*IDN?")


# ===========================================================================
# ENA (sync) — 注意未连接是 **静默 no-op**, 不是抛异常 (legacy 契约)
# ===========================================================================

class TestEnaReconnect:
    def test_conn_lost_on_query_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_response = "READY\n"
        d = _build_ena(primary, post_reconnect=[replacement])

        result = d._do_query("*IDN?")
        assert result == "READY\n"
        assert replacement.queries == ["*IDN?"]
        assert d._visa_rm.open_calls == 1

    def test_inv_object_on_write_retries_after_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.write_fail_with = [_mk_visa_error(VI_ERROR_INV_OBJECT)]
        replacement = _FakeVisaResource("post-reconnect")
        d = _build_ena(primary, post_reconnect=[replacement])

        d._do_write("INIT")
        assert replacement.writes == ["INIT"]
        assert primary.closed is True
        assert d._visa_rm.open_calls == 1

    def test_timeout_propagates_without_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_TMO)]
        d = _build_ena(primary, post_reconnect=[])

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            d._do_query("SYST:ERR?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == VI_ERROR_TMO
        assert d._visa_rm.open_calls == 0

    def test_non_visa_error_propagates_without_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [RuntimeError("not a VISA error")]
        d = _build_ena(primary, post_reconnect=[])

        with pytest.raises(RuntimeError):
            d._do_query("*IDN?")
        assert d._visa_rm.open_calls == 0

    def test_second_consecutive_conn_lost_is_bounded(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        replacement = _FakeVisaResource("post-reconnect")
        replacement.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        d = _build_ena(primary, post_reconnect=[replacement])

        with pytest.raises(pyvisa.errors.VisaIOError):
            d._do_query("*IDN?")
        assert d._visa_rm.open_calls == 1

    def test_reconnect_failure_surfaces_original_error(self):
        primary = _FakeVisaResource("primary")
        primary.query_fail_with = [_mk_visa_error(VI_ERROR_CONN_LOST)]
        d = _build_ena(primary, post_reconnect=[])

        with pytest.raises(pyvisa.errors.VisaIOError) as exc_info:
            d._do_query("*IDN?")
        assert (exc_info.value.error_code & 0xFFFFFFFF) == VI_ERROR_CONN_LOST

    def test_healthy_path_no_reconnect(self):
        primary = _FakeVisaResource("primary")
        primary.query_response = "Keysight,ENA\n"
        d = _build_ena(primary, post_reconnect=[])

        result = d._do_query("*IDN?")
        assert result == "Keysight,ENA\n"
        assert d._visa_rm.open_calls == 0
        assert primary.closed is False

    def test_not_connected_is_silent_noop(self):
        """ENA legacy 契约: 未连接时 write→None / query→"" 静默, 不抛 (与 UXM/FS16 不同)。"""
        d = _build_ena(_FakeVisaResource(), post_reconnect=[])
        d._visa_session = None
        assert d._do_query("*IDN?") == ""
        assert d._do_write("INIT") is None


# ===========================================================================
# 共享 classifier (app.hal._visa_reconnect.is_visa_conn_lost) —— 三驱动 delegate
# ===========================================================================

class TestConnLostClassifier:
    @pytest.mark.parametrize("driver_cls", [
        RealPropsimFs16Driver, RealUxmDriver, RealKeysightEnaDriver,
    ])
    def test_each_driver_delegates_to_shared_classifier(self, driver_cls):
        is_conn_lost = driver_cls._is_visa_conn_lost
        assert is_conn_lost(_mk_visa_error(VI_ERROR_CONN_LOST)) is True
        assert is_conn_lost(_mk_visa_error(VI_ERROR_INV_OBJECT)) is True
        assert is_conn_lost(_mk_visa_error(VI_ERROR_TMO)) is False
        assert is_conn_lost(RuntimeError("not visa")) is False
        assert is_conn_lost(ConnectionResetError("plain")) is False
