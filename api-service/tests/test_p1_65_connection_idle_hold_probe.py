"""P1-65 A 组：`connection_idle_hold_probe` —— P2-4 / P1-6 idle-drop 的 C 类观察载体。

故障：「会话空置 N 秒后是否断开 / 是否触发重连」这个现象没有任何 checked-in 载体，
每次现场都靠临时脚本或口头回忆。本序列只做三件事：`*IDN?` → 空置 N 秒
（期间不发任何命令）→ `*IDN?`，并把驱动上能 getattr 到的会话 / 重连迹象前后对比。

本文件守的门：
- mock 拒绝 / 驱动未加载拒绝 / 无 `_query` 原语拒绝 / 未知 category 拒绝 /
  `hold_seconds` 超 900 或非正数拒绝（拒绝时一条命令都不发、也不 sleep）；
- 空置实打实调用 `asyncio.sleep(hold_seconds)`（monkeypatch 换成立即返回并断言秒数），
  **空置期间不发任何命令**（sleep 被调用那一刻驱动只收到过 1 条命令）；
- 只读不变量：驱动只收到 `*IDN?`；
- 判定三态：第二次 IDN 成功且无重连迹象 → SUCCESS；第二次失败或驱动有重连迹象 →
  UNDETERMINED（是观察结果，不是序列失败，summary 写清）；第一次就失败 → BLOCKER，
  且不再 sleep；
- caveat（runner 租约默认开监控、1 Hz 广播会给仪器发流量）必须写进 summary 与 extra，
  `monitoring_state` 取自租约门的真实值（enabled / disabled），拿不到写 unknown。
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from app.diagnostics.protocol import driver_not_loaded_summary
from app.diagnostics.sequences import connection_idle_hold_probe as seq


class _ScriptedIdle:
    """回放式假驱动：按顺序回放 `_query` 的结果；元素是 Exception 就抛。
    可选 `rebuild_session_on_call`：第 N 次调用时先走一遍 `_silent_reconnect()`
    —— 子类按**真驱动**的属性名实现（内审 F1：初版用的 `_visa_session` 在 F64 上 0 处）。
    基类本身不带任何会话属性（= 没有会话属性可读的驱动）。"""

    def __init__(self, responses, rebuild_session_on_call=None):
        self.calls = []
        self._responses = list(responses)
        self._rebuild_on = rebuild_session_on_call

    def _silent_reconnect(self):
        pass

    def _query(self, cmd):
        self.calls.append(cmd)
        if self._rebuild_on is not None and len(self.calls) == self._rebuild_on:
            self._silent_reconnect()
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class _F64Shaped(_ScriptedIdle):
    """F64 形态：异步 `_query`；会话对象是 `_visa_resource`；
    `_silent_reconnect_visa` 换 `_visa_resource`、清 `_identity_response`（propsim_f64.py），
    重连后 `_reconnect_retry_after` 又会被 `_note_io_success` 归零 —— 照真驱动写，
    让「只看 _reconnect_retry_after」这种假判据在这里必然漏判。"""

    def __init__(self, responses, rebuild_session_on_call=None):
        super().__init__(responses, rebuild_session_on_call)
        self._visa_resource = object()
        self._identity_response = "Keysight,F8800A,SN,1.0"
        self._reconnect_retry_after = 0.0

    def _silent_reconnect(self):
        self._reconnect_retry_after = 30.0
        self._identity_response = None
        self._visa_resource = object()

    async def _query(self, cmd):  # type: ignore[override]
        out = super()._query(cmd)
        self._reconnect_retry_after = 0.0  # _note_io_success：命令跑通即归零
        return out


class _UxmShaped(_ScriptedIdle):
    """UXM 形态：同步 `_query`；会话对象是 `_visa_session`；
    `_silent_reconnect_visa` 换 `_visa_session`、清 `_identity_response` /
    `_platform_identity_response`（uxm_base_station.py）。"""

    def __init__(self, responses, rebuild_session_on_call=None):
        super().__init__(responses, rebuild_session_on_call)
        self._visa_session = object()
        self._identity_response = "Keysight Technologies,E7515B,SN,28.21"
        self._platform_identity_response = "platform"

    def _silent_reconnect(self):
        self._identity_response = None
        self._platform_identity_response = None
        self._visa_session = object()


def _run(drv, params=None, category="channelEmulator"):
    hal = MagicMock()
    hal.drivers = {category: drv} if drv is not None else {}
    return asyncio.run(seq.run(
        MagicMock(), hal, params or {}, log=lambda *_: None,
    ))


@pytest.fixture
def fake_sleep(monkeypatch):
    """把 asyncio.sleep 换成立即返回，并记录每次传入的秒数。"""
    calls = []

    async def _sleep(seconds, *_a, **_k):
        calls.append(seconds)

    monkeypatch.setattr(seq.asyncio, "sleep", _sleep)
    return calls


# ── 元数据 ──────────────────────────────────────────────────────────

def test_metadata_declares_optional_categories_and_params():
    assert seq.metadata.required_categories == []
    assert set(seq.metadata.optional_categories) == {
        "channelEmulator", "baseStation", "signalAnalyzer", "positioner", "rfSwitch",
    }
    schema = {p["name"]: p for p in seq.metadata.params_schema}
    assert schema["category"]["type"] == "string"
    assert schema["category"]["default"] == "channelEmulator"
    assert schema["hold_seconds"]["type"] == "number"
    assert schema["hold_seconds"]["default"] == 120
    assert seq.metadata.safe_during_test is False
    assert inspect.iscoroutinefunction(seq.run)


# ── 拒绝门（拒绝时一条命令都不发、也不 sleep）─────────────────────────

def test_refuses_mock_driver(fake_sleep):
    mock_cls = type("MockChannelEmulator", (), {"_query": lambda self, c: ""})
    result = _run(mock_cls())
    assert result.success is False
    assert "mock" in result.summary.lower()
    assert fake_sleep == []


def test_refuses_when_driver_not_loaded(fake_sleep):
    result = _run(None)
    assert result.success is False
    assert result.summary == driver_not_loaded_summary("channelEmulator")
    assert fake_sleep == []


def test_refuses_driver_without_query_primitive(fake_sleep):
    class _NoQuery:
        pass

    result = _run(_NoQuery())
    assert result.success is False
    assert "_query" in result.summary
    assert fake_sleep == []


def test_refuses_unknown_category(fake_sleep):
    drv = _ScriptedIdle(["x", "x"])
    result = _run(drv, {"category": "vna"}, category="vna")
    assert result.success is False
    assert "category" in result.summary
    assert drv.calls == []
    assert fake_sleep == []


@pytest.mark.parametrize("bad", [900.1, 901, 3600, 0, -5, "abc", None])
def test_refuses_hold_seconds_outside_0_900(fake_sleep, bad):
    drv = _ScriptedIdle(["x", "x"])
    result = _run(drv, {"hold_seconds": bad})
    assert result.success is False
    assert "hold_seconds" in result.summary
    assert drv.calls == []
    assert fake_sleep == []


def test_hold_seconds_exactly_900_is_accepted(fake_sleep):
    drv = _ScriptedIdle(["IDN-A", "IDN-A"])
    result = _run(drv, {"hold_seconds": 900})
    assert result.success is True
    assert fake_sleep == [900]


# ── SUCCESS：会话存活 ────────────────────────────────────────────────

def test_idle_hold_session_alive_is_success(fake_sleep):
    drv = _ScriptedIdle(["Keysight,F8800A,1", "Keysight,F8800A,1"])
    result = _run(drv, {"hold_seconds": 120})

    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"
    assert fake_sleep == [120]
    assert drv.calls == ["*IDN?", "*IDN?"]
    assert result.extra["hold_seconds"] == 120
    assert result.extra["idn_before"] == "Keysight,F8800A,1"
    assert result.extra["idn_after"] == "Keysight,F8800A,1"
    assert result.extra["reconnect_signs"] == []
    assert "120" in result.summary and "存活" in result.summary
    labels = [s.label for s in result.steps]
    assert labels == ["*IDN? (空置前)", "空置 120 s", "*IDN? (空置后)"]
    assert result.steps[0].raw == "Keysight,F8800A,1"
    assert result.steps[1].raw is None  # 空置步没有仪器回复
    assert result.steps[2].raw == "Keysight,F8800A,1"


def test_default_params_are_channel_emulator_and_120s(fake_sleep):
    drv = _ScriptedIdle(["a", "a"])
    result = _run(drv)
    assert result.success is True
    assert fake_sleep == [120]
    assert result.extra["category"] == "channelEmulator"


def test_async_query_primitive_is_awaited(fake_sleep):
    drv = _F64Shaped(["a", "a"])
    result = _run(drv, {"hold_seconds": 5, "category": "baseStation"}, category="baseStation")
    assert result.success is True
    assert result.extra["idn_after"] == "a"
    assert drv.calls == ["*IDN?", "*IDN?"]


def test_no_command_is_sent_during_hold(monkeypatch):
    """不变量：sleep 被调用的那一刻，驱动恰好只收到过 1 条命令；结束时总共 2 条。"""
    drv = _ScriptedIdle(["a", "a"])
    seen_at_sleep = []

    async def _sleep(seconds, *_a, **_k):
        seen_at_sleep.append(list(drv.calls))

    monkeypatch.setattr(seq.asyncio, "sleep", _sleep)
    _run(drv, {"hold_seconds": 30})
    assert seen_at_sleep == [["*IDN?"]]
    assert drv.calls == ["*IDN?", "*IDN?"]


def test_read_only_invariant_only_idn_is_ever_sent(fake_sleep):
    drv = _ScriptedIdle(["a", "a"])
    _run(drv, {"hold_seconds": 10})
    assert set(drv.calls) == {"*IDN?"}


# ── UNDETERMINED：观察结果 ───────────────────────────────────────────

def test_second_idn_failure_is_observation_not_sequence_failure(fake_sleep):
    drv = _ScriptedIdle(["a", TimeoutError("VI_ERROR_TMO")])
    result = _run(drv, {"hold_seconds": 120})

    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["observation"] == "idle_drop"
    assert result.extra["idn_after"] is None
    assert "空置后会话断开/重连，现象已记录" in result.summary
    assert drv.calls == ["*IDN?", "*IDN?"]
    assert fake_sleep == [120]
    after = result.steps[2]
    assert after.success is False
    assert after.raw is None
    assert "VI_ERROR_TMO" in after.detail


def test_f64_shaped_silent_reconnect_on_second_idn_is_observation(fake_sleep):
    """F64：空置掉线 → 第二条 *IDN? 触发静默重连成功 → IDN 文本相同、
    `_reconnect_retry_after` 前后都是 0.0 —— 只有 `_visa_resource` 换了对象、
    `_identity_response` 被清，序列必须据此记成 idle_drop（内审 F1 的漏判形态）。"""
    drv = _F64Shaped(["a", "a"], rebuild_session_on_call=2)
    result = _run(drv, {"hold_seconds": 60})

    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["observation"] == "idle_drop"
    assert "_visa_resource" in result.extra["reconnect_signs"]
    assert "_identity_response" in result.extra["reconnect_signs"]
    assert "空置后会话断开/重连，现象已记录" in result.summary


def test_uxm_shaped_silent_reconnect_on_second_idn_is_observation(fake_sleep):
    drv = _UxmShaped(["a", "a"], rebuild_session_on_call=2)
    result = _run(drv, {"hold_seconds": 60, "category": "baseStation"}, category="baseStation")

    assert result.success is False
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["observation"] == "idle_drop"
    assert set(result.extra["reconnect_signs"]) >= {
        "_visa_session", "_identity_response", "_platform_identity_response",
    }


@pytest.mark.parametrize("shape,category", [(_F64Shaped, "channelEmulator"), (_UxmShaped, "baseStation")])
def test_reconnect_triggered_by_first_idn_is_not_counted_as_idle_drop(fake_sleep, shape, category):
    """快照必须取在首条 *IDN? 成功之后：F64 常态是首条命令就先静默重连一次，
    这不是空置造成的 —— 记成 idle_drop 就是反向假观察（内审 F1）。"""
    drv = shape(["a", "a"], rebuild_session_on_call=1)
    result = _run(drv, {"hold_seconds": 60, "category": category}, category=category)

    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["reconnect_signs"] == []


def test_session_sign_attrs_are_real_driver_reconnect_side_effects():
    """不变量门：`_SESSION_SIGN_ATTRS` 里的每个名字都必须真的在某个真驱动的
    `_silent_reconnect_visa` 里被赋值（防表里再混进 `_session_rebuilds` 这类不存在的名字），
    且两台真驱动各自的会话对象属性都在表里（F64 `_visa_resource` / UXM `_visa_session`）。
    变异：把 `_visa_resource` 从表里去掉 → 红；往表里加个幻想名字 → 红。"""
    import inspect
    import re

    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.uxm_base_station import RealUxmDriver

    assigned = {}
    for cls in (RealPropsimF64Driver, RealUxmDriver):
        src = inspect.getsource(cls._silent_reconnect_visa)
        assigned[cls.__name__] = set(re.findall(r"self\.(\w+)\s*=[^=]", src))

    for attr in seq._SESSION_SIGN_ATTRS:
        assert any(attr in names for names in assigned.values()), (
            f"{attr!r} 不是任何真驱动 _silent_reconnect_visa 的赋值目标 —— 幻想属性"
        )
    # 判定器自测：正则真能从源码里抽到赋值目标
    assert "_visa_resource" in assigned["RealPropsimF64Driver"]
    assert "_visa_session" in assigned["RealUxmDriver"]
    # 两台驱动的会话对象属性都必须在表里（空置掉线后 IDN 文本不变，只有它们换）
    assert "_visa_resource" in seq._SESSION_SIGN_ATTRS
    assert "_visa_session" in seq._SESSION_SIGN_ATTRS
    assert "_identity_response" in seq._SESSION_SIGN_ATTRS


# ── BLOCKER：第一次就不通 ────────────────────────────────────────────

def test_first_idn_failure_is_blocker_and_skips_hold(fake_sleep):
    drv = _ScriptedIdle([ConnectionError("boom"), "never"])
    result = _run(drv, {"hold_seconds": 120})

    assert result.success is False
    assert result.extra["verdict"] == "BLOCKER"
    assert drv.calls == ["*IDN?"]
    assert fake_sleep == [], "第一次就不通，不该再空置等待"
    assert len(result.steps) == 1
    assert result.steps[0].success is False


# ── caveat：空置不是真空置 ───────────────────────────────────────────

def test_caveat_and_monitoring_state_are_recorded(fake_sleep, monkeypatch):
    monkeypatch.setattr(seq, "is_test_monitoring_enabled", lambda: True)
    drv = _ScriptedIdle(["a", "a"])
    result = _run(drv, {"hold_seconds": 15})
    assert result.extra["monitoring_state"] == "enabled"
    assert "监控" in result.summary and "1 Hz" in result.summary
    assert "caveat" in result.extra and "1 Hz" in result.extra["caveat"]


def test_monitoring_state_unknown_when_gate_unreadable(fake_sleep, monkeypatch):
    def _boom():
        raise RuntimeError("gate unavailable")

    monkeypatch.setattr(seq, "is_test_monitoring_enabled", _boom)
    drv = _ScriptedIdle(["a", "a"])
    result = _run(drv, {"hold_seconds": 15})
    assert result.extra["monitoring_state"] == "unknown"
    assert result.success is True  # 监控门读不到不影响判定，只影响 caveat 的精度


def test_monitoring_state_disabled_outside_lease(fake_sleep):
    """测试进程里没有租约 → 真实的租约门返回 False → disabled（不是 unknown）。"""
    drv = _ScriptedIdle(["a", "a"])
    result = _run(drv, {"hold_seconds": 15})
    assert result.extra["monitoring_state"] == "disabled"
