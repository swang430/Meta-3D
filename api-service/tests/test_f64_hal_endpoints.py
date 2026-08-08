"""P2-1 (onsite-20260721-todo): F64 现场编排端点路由级单测。

2026-07-21 现场收口 — 5 个哑执行工具端点 (emulation-control / output-gain /
output-calibration / input-reference / crest-factor)。

按 feedback_fastapi_router_prefix_no_double 教训用 TestClient 打真路径 (函数级
单测测不到路由 404); 按端点三分支矩阵覆盖: driver 未加载 404 / 驱动缺方法·非法
参数 400 / 正常路径 (成功 + 失败透传 last_error)。driver 经 monkeypatch
`_get_loaded_hal_driver` 注入假对象, 不依赖全局 HAL 状态。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import pytest

import app.api.instrument as instrument_api

BASE = "/api/v1/instruments/channelEmulator"


class _FakeF64Driver:
    """假 F64: 覆盖 6 端点消费的全部驱动方法, 行为可配置。"""

    def __init__(
        self,
        *,
        ok: bool = True,
        calib: Optional[Dict[str, float]] = None,
        fail_ports: Optional[set] = None,
    ):
        self._ok = ok
        self._calib = calib
        self._fail_ports = fail_ports or set()
        self._emulation_running = False
        self._last_error: Optional[str] = None if ok else "驱动失败(测试注入)"
        self.calls: List[tuple] = []
        # F64R-2: 冷缓存 (后端重启后驱动忘了拓扑, 但 F64 仍加载着仿真)。端点必须先
        # await ensure_topology() 补读, 才读得到口号 —— 不 await 就退化成 400。
        self._input_ports: Optional[List[int]] = None
        self.local_control_reserved = False
        self._visa_resource = object()
        self._loaded_emulation_file: Optional[str] = None

    async def ensure_topology(self) -> bool:
        self.calls.append(("ensure_topology",))
        self._input_ports = [3, 5]        # 补读回来的真实口号 (非连续)
        return True

    def get_active_input_ports(self) -> Optional[List[int]]:
        return list(self._input_ports) if self._input_ports else None

    async def start_emulation(self) -> bool:
        self.calls.append(("start_emulation",))
        self._emulation_running = self._ok
        return self._ok

    async def stop_emulation(self) -> bool:
        self.calls.append(("stop_emulation",))
        if self._ok:
            self._emulation_running = False
        return self._ok

    async def set_output_gain(self, port: int, gain_db: float) -> bool:
        self.calls.append(("set_output_gain", port, gain_db))
        return self._ok and port not in self._fail_ports

    async def get_output_calibration(self, output_num: int):
        self.calls.append(("get_output_calibration", output_num))
        return self._calib

    async def set_baseband_power(self, power_dbm: float, input_ports=None) -> bool:
        self.calls.append(("set_baseband_power", power_dbm, input_ports))
        return self._ok

    async def set_crest_factor(self, input_num: int, crest_db: float) -> bool:
        self.calls.append(("set_crest_factor", input_num, crest_db))
        return self._ok and input_num not in self._fail_ports

    async def release_to_local_control(self) -> bool:
        self.calls.append(("release_to_local_control",))
        self.local_control_reserved = True
        self._visa_resource = None
        return self._ok

    async def acquire_remote_control(self) -> bool:
        self.calls.append(("acquire_remote_control",))
        if self._ok:
            self.local_control_reserved = False
            self._visa_resource = object()
        return self._ok

    async def load_local_scenario(self, file_path: str) -> bool:
        self.calls.append(("load_local_scenario", file_path))
        if self._ok:
            self._loaded_emulation_file = file_path
        return self._ok

    async def confirm_scenario_loaded(self):
        self.calls.append(("confirm_scenario_loaded",))
        return {
            "confirmed": self._ok and bool(self._loaded_emulation_file),
            "simulation_state": "STOPPED" if self._ok else None,
        }


@pytest.fixture()
def fake_driver(monkeypatch):
    """注入默认成功的假驱动; 测试内可换属性改行为。"""
    driver = _FakeF64Driver()
    monkeypatch.setattr(
        instrument_api, "_get_loaded_hal_driver", lambda key: driver
    )
    return driver


@pytest.fixture()
def no_driver(monkeypatch):
    """HAL 未加载该品类 → 全端点 404。"""
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: None)


# ---------------------------------------------------------------------------
# 404: driver 未加载 (全端点)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/emulation-control", {"action": "start"}),
        ("post", "/output-gain", {"ports": [1], "gain_db": 0.0}),
        ("get", "/output-calibration/1", None),
        ("post", "/input-reference", {"power_dbm": -17.0}),
        ("post", "/crest-factor", {"input_ports": [1], "crest_db": 15.0}),
    ],
)
def test_all_endpoints_404_when_driver_not_loaded(client, no_driver, method, path, body):
    resp = getattr(client, method)(BASE + path, **({"json": body} if body else {}))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# emulation-control
# ---------------------------------------------------------------------------

def test_emulation_control_start_ok(client, fake_driver):
    resp = client.post(BASE + "/emulation-control", json={"action": "start"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["action"] == "start"
    assert data["emulation_running"] is True
    assert data["last_error"] is None
    assert ("start_emulation",) in fake_driver.calls


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/emulation-control", {"action": "start"}),
        ("post", "/output-gain", {"ports": [1], "gain_db": -1.0}),
        ("get", "/output-calibration/1", None),
        ("post", "/input-reference", {"power_dbm": -17.0, "input_ports": [1]}),
        ("post", "/crest-factor", {"input_ports": [1], "crest_db": 15.0}),
        (
            "post",
            "/load-smu",
            {"file_path": r"D:\\User Emulations\\onsite\\attach.smu"},
        ),
    ],
)
def test_f64_standalone_scpi_endpoints_hold_non_polling_lease(
    client, fake_driver, monkeypatch, method, path, body
):
    events = []

    @asynccontextmanager
    async def _lease(purpose, **kwargs):
        events.append(("enter", purpose, kwargs))
        try:
            yield
        finally:
            events.append(("exit", purpose))

    monkeypatch.setattr(
        instrument_api, "instrument_test_lease", _lease, raising=False
    )
    resp = getattr(client, method)(BASE + path, **({"json": body} if body else {}))

    assert resp.status_code == 200, resp.text
    assert events[0][0] == "enter"
    assert events[0][2] == {
        "control_f64": True,
        "control_uxm": False,
        "enable_monitoring": False,
    }
    assert events[-1][0] == "exit"


def test_emulation_control_stop_ok(client, fake_driver):
    resp = client.post(BASE + "/emulation-control", json={"action": "stop"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert ("stop_emulation",) in fake_driver.calls


def test_emulation_control_action_normalized(client, fake_driver):
    """action 大小写/空白容忍 ('  Start ' → start)。"""
    resp = client.post(BASE + "/emulation-control", json={"action": "  Start "})
    assert resp.status_code == 200
    assert resp.json()["action"] == "start"


def test_emulation_control_invalid_action_400(client, fake_driver):
    resp = client.post(BASE + "/emulation-control", json={"action": "reboot"})
    assert resp.status_code == 400


def test_emulation_control_failure_carries_last_error(client, monkeypatch):
    driver = _FakeF64Driver(ok=False)
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: driver)
    resp = client.post(BASE + "/emulation-control", json={"action": "start"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["last_error"] == "驱动失败(测试注入)"


def test_emulation_control_driver_without_method_400(client, monkeypatch):
    """驱动缺 start/stop_emulation (如 mock/别品类) → 400 而非 AttributeError。"""

    class _Bare:
        pass

    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: _Bare())
    resp = client.post(BASE + "/emulation-control", json={"action": "start"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# F64 Local/Remote ownership + explicit .smu fallback
# ---------------------------------------------------------------------------

def test_release_to_local_control(client, fake_driver):
    resp = client.post(BASE + "/control-ownership", json={"action": "release_local"})
    assert resp.status_code == 200
    assert resp.json()["control_mode"] == "ate_socket_released"
    assert resp.json()["remote_polling_suppressed"] is True
    assert ("release_to_local_control",) in fake_driver.calls


def test_acquire_remote_control(client, fake_driver):
    fake_driver.local_control_reserved = True
    resp = client.post(BASE + "/control-ownership", json={"action": "acquire_remote"})
    assert resp.status_code == 200
    assert resp.json()["control_mode"] == "remote"
    assert ("acquire_remote_control",) in fake_driver.calls


def test_control_operation_holds_shared_unsafe_token(client, fake_driver, monkeypatch):
    from app.services.execution_exclusion_guard import active_unsafe_diagnostic

    original = fake_driver.release_to_local_control

    async def checked_release():
        assert active_unsafe_diagnostic() == "f64_control_operation"
        return await original()

    monkeypatch.setattr(fake_driver, "release_to_local_control", checked_release)
    resp = client.post(BASE + "/control-ownership", json={"action": "release_local"})
    assert resp.status_code == 200
    assert active_unsafe_diagnostic() is None


def test_control_operation_refuses_when_unsafe_diagnostic_is_active(client, fake_driver):
    from app.services.execution_exclusion_guard import (
        release_unsafe_diagnostic,
        try_acquire_unsafe_diagnostic,
    )

    token = try_acquire_unsafe_diagnostic("propsim_f64_state_machine")
    assert token is not None
    try:
        resp = client.post(BASE + "/control-ownership", json={"action": "release_local"})
        assert resp.status_code == 409
        assert ("release_to_local_control",) not in fake_driver.calls
    finally:
        release_unsafe_diagnostic(token)


def test_load_smu_uses_lease_then_loads_explicit_path(client, fake_driver):
    fake_driver.local_control_reserved = True
    path = r"D:\\User Emulations\\onsite\\attach.smu"
    resp = client.post(BASE + "/load-smu", json={"file_path": path})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["loaded_file"] == path
    assert fake_driver.calls[-2:] == [
        ("load_local_scenario", path),
        ("confirm_scenario_loaded",),
    ]
    # Remote/Local 取得已集中到 instrument_test_lease；端点不得再绕过租约
    # 直接操作驱动控制权（租约行为由 test_instrument_test_lease 覆盖）。
    assert ("acquire_remote_control",) not in fake_driver.calls
    assert resp.json()["verification"]["simulation_state"] == "STOPPED"


def test_load_smu_disconnected_driver_is_delegated_to_control_lease(client, fake_driver):
    fake_driver.local_control_reserved = False
    fake_driver._visa_resource = None
    path = r"D:\\User Emulations\\onsite\\attach.smu"
    resp = client.post(BASE + "/load-smu", json={"file_path": path})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert ("acquire_remote_control",) not in fake_driver.calls


def test_load_smu_refuses_non_smu_path(client, fake_driver):
    resp = client.post(BASE + "/load-smu", json={"file_path": r"D:\\x.rtc"})
    assert resp.status_code == 400
    assert not any(call[0] == "load_local_scenario" for call in fake_driver.calls)


def test_load_smu_refuses_relative_path(client, fake_driver):
    resp = client.post(BASE + "/load-smu", json={"file_path": "onsite/attach.smu"})
    assert resp.status_code == 400
    assert not any(call[0] == "load_local_scenario" for call in fake_driver.calls)


# ---------------------------------------------------------------------------
# output-gain
# ---------------------------------------------------------------------------

def test_output_gain_batch_ok(client, fake_driver):
    resp = client.post(BASE + "/output-gain", json={"ports": [1, 2, 3], "gain_db": -5.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["ports"] == {"1": True, "2": True, "3": True}
    assert [c for c in fake_driver.calls if c[0] == "set_output_gain"] == [
        ("set_output_gain", 1, -5.0),
        ("set_output_gain", 2, -5.0),
        ("set_output_gain", 3, -5.0),
    ]


def test_output_gain_partial_reject_reported(client, monkeypatch):
    """2026-07-21 实证场景: per-port 上限不同 → 部分口被拒, ok=False 且 per-port 可见。"""
    driver = _FakeF64Driver(fail_ports={2})
    driver._last_error = "-200 Parameter exceeds set limits"
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: driver)
    resp = client.post(BASE + "/output-gain", json={"ports": [1, 2], "gain_db": 30.0})
    data = resp.json()
    assert data["ok"] is False
    assert data["ports"] == {"1": True, "2": False}
    assert "exceeds" in data["last_error"]


# ---------------------------------------------------------------------------
# output-calibration
# ---------------------------------------------------------------------------

def test_output_calibration_ok(client, monkeypatch):
    driver = _FakeF64Driver(calib={"gain_db": -3.0, "phase_deg": 0.0})
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: driver)
    resp = client.get(BASE + "/output-calibration/5")
    data = resp.json()
    assert data["ok"] is True
    assert data["output_num"] == 5
    assert data["calibration"] == {"gain_db": -3.0, "phase_deg": 0.0}


def test_output_calibration_null_readback(client, fake_driver):
    """2026-07-21 实测: 本机固件读不回 → ok=False + calibration=null (契约钉死)。"""
    resp = client.get(BASE + "/output-calibration/1")
    data = resp.json()
    assert data["ok"] is False
    assert data["calibration"] is None


# ---------------------------------------------------------------------------
# input-reference / crest-factor
# ---------------------------------------------------------------------------

def test_input_reference_ok(client, fake_driver):
    resp = client.post(BASE + "/input-reference", json={"power_dbm": -17.0})
    data = resp.json()
    assert data["ok"] is True
    assert data["power_dbm"] == -17.0
    # 不传 ports → **透传 None 给驱动**(由驱动用回读的真实口号下发, F64R-2;
    # 旧注释写的"推断 1..N"正是本 PR 在治的错口径), 响应则回显实际生效的口号。
    assert ("set_baseband_power", -17.0, None) in fake_driver.calls
    assert data["input_ports"] == [3, 5]


def test_input_reference_echoes_readback_ports(client, fake_driver):
    """F64R-2: 没传 ports 时响应回显**实际生效的口号** —— 操作员排"是不是只配了
    一半"时,需要从响应就能看出到底写了哪几个口。"""
    resp = client.post(BASE + "/input-reference", json={"power_dbm": -17.0})
    data = resp.json()
    assert data["ok"] is True
    assert data["input_ports"] == [3, 5]


def test_input_reference_explicit_ports(client, fake_driver):
    """Codex #221 R5 P2: 上层按真实激活拓扑显式传 input_ports → 透传给驱动
    (解决冷缓存 _tx_antennas 漂移只设部分口的 MIMO 输入不平衡)。"""
    resp = client.post(
        BASE + "/input-reference",
        json={"power_dbm": -17.0, "input_ports": [1, 2, 3, 4]},
    )
    data = resp.json()
    assert data["ok"] is True
    assert data["input_ports"] == [1, 2, 3, 4]
    assert ("set_baseband_power", -17.0, [1, 2, 3, 4]) in fake_driver.calls


def test_input_reference_failure(client, monkeypatch):
    driver = _FakeF64Driver(ok=False)
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: driver)
    resp = client.post(BASE + "/input-reference", json={"power_dbm": -17.0})
    data = resp.json()
    assert data["ok"] is False
    assert data["last_error"] == "驱动失败(测试注入)"


def test_crest_factor_uses_readback_ports_when_not_given(client, fake_driver):
    """F64R-2: 不给 input_ports → 用驱动**回读的真实输入口号**, 不是硬编码 1-4。

    取代原 `test_crest_factor_default_ports`(钉旧的 `default=[1,2,3,4]`)—— 那个默认值
    在非连续口下会配错口, 且跟兄弟端点 /input-reference 的口径不一致。这里用非连续
    口 {3,5} 钉住"口号来自回读"。"""
    resp = client.post(BASE + "/crest-factor", json={"crest_db": 15.0})
    data = resp.json()
    assert data["ok"] is True
    assert data["ports"] == {"3": True, "5": True}


def test_crest_factor_refuses_when_topology_unknown(client, fake_driver):
    """F64R-2: 不给 ports 且拓扑读不到 → 400 fail-loud, 不猜 1-4 也不静默零下发。"""
    async def _ensure_fails():                      # 补读了也没读到 (真机不支持 GROUP:*)
        fake_driver.calls.append(("ensure_topology",))
        return False
    fake_driver.ensure_topology = _ensure_fails
    resp = client.post(BASE + "/crest-factor", json={"crest_db": 15.0})
    assert resp.status_code == 400
    assert "物理输入口未知" in resp.json()["detail"]


def test_crest_factor_partial_reject(client, monkeypatch):
    driver = _FakeF64Driver(fail_ports={3})
    driver._last_error = "CREST rejected"
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: driver)
    resp = client.post(
        BASE + "/crest-factor", json={"input_ports": [1, 3], "crest_db": 12.0}
    )
    data = resp.json()
    assert data["ok"] is False
    assert data["ports"] == {"1": True, "3": False}


# ---------------------------------------------------------------------------
# agent F5 — 空列表 fail-loud(422) + 品类命中不支持该操作的驱动(NotImplementedError → 400)
# ---------------------------------------------------------------------------

def test_output_gain_empty_ports_422(client, fake_driver):
    """空 ports → all({})=True 假成功的坑; min_length=1 让它 422 而非静默零下发。"""
    resp = client.post(BASE + "/output-gain", json={"ports": [], "gain_db": 0.0})
    assert resp.status_code == 422


def test_crest_factor_empty_ports_422(client, fake_driver):
    resp = client.post(BASE + "/crest-factor", json={"input_ports": [], "crest_db": 15.0})
    assert resp.status_code == 422


class _FS16LikeDriver:
    """模拟 FS16 / 别的 channel_emulator 品类: 方法存在(继承基类)但 raise
    NotImplementedError。getattr 命中 → 若不捕会裸 500。"""

    async def start_emulation(self):
        raise NotImplementedError("FS16 不支持 start_emulation")

    async def set_baseband_power(self, power_dbm, input_ports=None):
        raise NotImplementedError("FS16 不支持 set_baseband_power")


def test_emulation_control_notimplemented_maps_400(client, monkeypatch):
    monkeypatch.setattr(
        instrument_api, "_get_loaded_hal_driver", lambda key: _FS16LikeDriver()
    )
    resp = client.post(BASE + "/emulation-control", json={"action": "start"})
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


def test_input_reference_notimplemented_maps_400(client, monkeypatch):
    monkeypatch.setattr(
        instrument_api, "_get_loaded_hal_driver", lambda key: _FS16LikeDriver()
    )
    resp = client.post(BASE + "/input-reference", json={"power_dbm": -17.0})
    assert resp.status_code == 400


def test_fs16_real_driver_no_baseband_power_returns_400(client, monkeypatch):
    """Codex #221 R6 P2 (误报) 实证 + 未来回归守门。

    Codex 假设 channelEmulator 绑 RealPropsimFs16Driver 时会继承到"基类单参
    set_baseband_power", 端点传 input_ports → TypeError → 500。运行时实测证伪:
    RealPropsimFs16Driver 整条 MRO (FS16 → ChannelEmulatorDriver → InstrumentDriver
    → ABC → object) **无** set_baseband_power —— Codex 所指的 channel_emulator.py:352
    是模块函数内的闭包死代码, 非类方法; ChannelEmulatorDriver 本身也无此方法。
    真实 FS16 绑 input-reference → getattr→None→HTTPException(400), 无 TypeError/500。

    (上一个用例的 _FS16LikeDriver 测的是"有方法但 raise NotImplementedError"路径;
    本用例测"整条 MRO 无该方法"路径 —— 真实 FS16 走的是后者。)

    守门: 若将来给基类补单参 set_baseband_power, FS16 会继承到它 → 第一条断言变红,
    暴露"端点双参调用该单参方法 → TypeError→500"的回归风险。
    """
    from app.hal.propsim_fs16 import RealPropsimFs16Driver

    # 铁证: 真实 FS16 MRO 无 set_baseband_power (Codex 前提为假)
    assert getattr(RealPropsimFs16Driver, "set_baseband_power", None) is None

    class _NoBasebandDriver:  # 镜像真实 FS16: 无 set_baseband_power
        _last_error = None

    monkeypatch.setattr(
        instrument_api, "_get_loaded_hal_driver", lambda key: _NoBasebandDriver()
    )
    resp = client.post(
        BASE + "/input-reference",
        json={"power_dbm": -17.0, "input_ports": [1, 2, 3, 4]},
    )
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]
