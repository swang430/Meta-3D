"""暗室首测前逐设备自检端点测试 (借鉴转台/EMCenter standalone 验证理念)。

首测前主动探测各 HAL driver 连接 + 响应 (get_metrics), 让操作员先确认各设备单独通,
把"首测中途撞设备细节"前移成"首测前先单独验设备"。mock driver, 不需硬件。
"""
from __future__ import annotations

from app.api.commissioning import device_selfcheck


class _FakeDriver:
    def __init__(self, status="connected", responsive=True):
        self.status = status
        self._responsive = responsive

    async def get_metrics(self):
        if not self._responsive:
            raise RuntimeError("no response")
        return {}


class _FakeHal:
    def __init__(self, drivers):
        self.drivers = drivers


def _patch_hal(monkeypatch, drivers):
    import app.services.instrument_hal_service as svc
    monkeypatch.setattr(svc, "get_hal_service", lambda: _FakeHal(drivers))


class TestDeviceSelfcheck:
    async def test_all_ready(self, monkeypatch):
        _patch_hal(monkeypatch, {
            "channelEmulator": _FakeDriver(),
            "positioner": _FakeDriver(),
        })
        r = await device_selfcheck()
        assert r.all_ready is True
        assert len(r.devices) == 2
        assert all(d.connected and d.responsive for d in r.devices)

    async def test_one_unresponsive(self, monkeypatch):
        _patch_hal(monkeypatch, {
            "channelEmulator": _FakeDriver(),
            "positioner": _FakeDriver(responsive=False),
        })
        r = await device_selfcheck()
        assert r.all_ready is False
        pos = next(d for d in r.devices if d.category == "positioner")
        assert pos.connected is True and pos.responsive is False
        assert pos.detail  # 有错误详情供操作员定位

    async def test_one_disconnected(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FakeDriver(status="disconnected")})
        r = await device_selfcheck()
        assert r.all_ready is False
        assert r.devices[0].connected is False

    async def test_no_drivers(self, monkeypatch):
        _patch_hal(monkeypatch, {})
        r = await device_selfcheck()
        assert r.all_ready is False and r.devices == []
        assert "无 HAL 驱动" in r.message

    async def test_enum_status_value(self, monkeypatch):
        # status 是 InstrumentStatus enum 时也能识别 (用 .value 提取, 不被 str(enum) 坑)
        from app.hal.base import InstrumentStatus
        _patch_hal(monkeypatch, {"positioner": _FakeDriver(status=InstrumentStatus.READY)})
        r = await device_selfcheck()
        assert r.devices[0].connected is True


def test_endpoint_path_reachable():
    """Codex P2 #133 回归: router prefix=/commissioning, 端点须用 /device-selfcheck (非
    /commissioning/device-selfcheck, 否则双前缀 → GUI 调 /commissioning/device-selfcheck 撞 404)。
    单测调函数测不到路由路径, 这里用 TestClient 钉死实际 HTTP 路径可达 (非 404)。"""
    from fastapi.testclient import TestClient
    from app.main import app
    resp = TestClient(app).post("/api/v1/commissioning/device-selfcheck")
    assert resp.status_code == 200, f"期望 200, 得 {resp.status_code} (路由路径注册错?)"
    assert "all_ready" in resp.json()
