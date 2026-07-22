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

    async def set_baseband_power(self, power_dbm: float) -> bool:
        self.calls.append(("set_baseband_power", power_dbm))
        return self._ok

    async def set_crest_factor(self, input_num: int, crest_db: float) -> bool:
        self.calls.append(("set_crest_factor", input_num, crest_db))
        return self._ok and input_num not in self._fail_ports


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
    assert ("set_baseband_power", -17.0) in fake_driver.calls


def test_input_reference_failure(client, monkeypatch):
    driver = _FakeF64Driver(ok=False)
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda key: driver)
    resp = client.post(BASE + "/input-reference", json={"power_dbm": -17.0})
    data = resp.json()
    assert data["ok"] is False
    assert data["last_error"] == "驱动失败(测试注入)"


def test_crest_factor_default_ports(client, fake_driver):
    """未显式给 input_ports → 默认 1-4 全下发。"""
    resp = client.post(BASE + "/crest-factor", json={"crest_db": 15.0})
    data = resp.json()
    assert data["ok"] is True
    assert data["ports"] == {"1": True, "2": True, "3": True, "4": True}


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

    async def set_baseband_power(self, power_dbm):
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
