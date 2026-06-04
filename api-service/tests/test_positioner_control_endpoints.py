"""U-5: positioner (转台) standalone 控制端点测试 (home/move/position/stop/sweep)。

补 standalone REST 入口让现场单独验证转台 (回零/定位/4方位扫), 不依赖完整 cal 流程
(2026-05-27 现场无 standalone 路径 → U-5 "无结论"; 见 morning-log §10)。
mock driver 测端点逻辑; driver 协议行为由 test_aerotech_* 覆盖。不需硬件。
"""
from __future__ import annotations

from app.api.instrument import (
    PositionerMoveRequest,
    PositionerSweepRequest,
    positioner_home,
    positioner_move,
    positioner_position,
    positioner_stop,
    positioner_sweep,
)


class _FakePositioner:
    """干净可控的转台 driver 替身 (端点逻辑测试用)。"""

    def __init__(self):
        self._az = 0.0
        self._el = 0.0

    async def move_to(self, az, el):
        self._az, self._el = az, el
        return True

    async def get_position(self):
        return (self._az, self._el)

    async def stop(self):
        return True

    async def reset(self):
        self._az = self._el = 0.0
        return True


class _FailMovePositioner(_FakePositioner):
    async def move_to(self, az, el):
        return False  # 模拟定位失败 (到位超时 / 故障)


class _DriftPositioner(_FakePositioner):
    async def move_to(self, az, el):
        self._az = az + 5.0  # 到位但超差 5° (degree/counts 换算错 / 机械)
        return True


class _FakeHal:
    def __init__(self, drivers):
        self.drivers = drivers


def _patch_hal(monkeypatch, drivers):
    import app.services.instrument_hal_service as svc
    monkeypatch.setattr(svc, "get_hal_service", lambda: _FakeHal(drivers))


class TestHappyPath:
    async def test_move_then_position_readback(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FakePositioner()})
        r = await positioner_move(PositionerMoveRequest(azimuth=90.0))
        assert r.ok is True and abs(r.azimuth - 90.0) < 0.01
        p = await positioner_position()
        assert p.ok is True and abs(p.azimuth - 90.0) < 0.01

    async def test_home_zeroes(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FakePositioner()})
        await positioner_move(PositionerMoveRequest(azimuth=180.0))
        r = await positioner_home()
        assert r.ok is True and abs(r.azimuth) < 0.01

    async def test_stop(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FakePositioner()})
        r = await positioner_stop()
        assert r.ok is True

    async def test_sweep_4_azimuth(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FakePositioner()})
        r = await positioner_sweep(PositionerSweepRequest())
        assert r.ok is True
        assert [p.target for p in r.points] == [0.0, 90.0, 180.0, 270.0]
        assert all(p.within_tolerance for p in r.points)

    async def test_sweep_custom_angles_no_home(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FakePositioner()})
        r = await positioner_sweep(
            PositionerSweepRequest(angles=[0.0, 45.0], home_first=False)
        )
        assert r.ok is True and len(r.points) == 2


class TestDriverNotLoaded:
    async def test_move_no_driver(self, monkeypatch):
        _patch_hal(monkeypatch, {})
        r = await positioner_move(PositionerMoveRequest(azimuth=90.0))
        assert r.ok is False
        assert r.reason == "driver_not_loaded"
        assert r.message  # 可操作提示 (检查仪器选 + IP + reload)

    async def test_home_no_driver(self, monkeypatch):
        _patch_hal(monkeypatch, {})
        r = await positioner_home()
        assert r.ok is False and r.reason == "driver_not_loaded"

    async def test_sweep_no_driver(self, monkeypatch):
        _patch_hal(monkeypatch, {})
        r = await positioner_sweep(PositionerSweepRequest())
        assert r.ok is False and r.reason == "driver_not_loaded"

    async def test_not_a_positioner(self, monkeypatch):
        class _NotPos:
            pass

        _patch_hal(monkeypatch, {"positioner": _NotPos()})
        r = await positioner_move(PositionerMoveRequest(azimuth=0.0))
        assert r.ok is False and r.reason == "not_a_positioner"


class TestFailureModes:
    async def test_move_failed(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FailMovePositioner()})
        r = await positioner_move(PositionerMoveRequest(azimuth=90.0))
        assert r.ok is False and r.reason == "move_failed"

    async def test_sweep_move_failed_stops_early(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FailMovePositioner()})
        r = await positioner_sweep(PositionerSweepRequest(home_first=False))
        assert r.ok is False and r.reason == "move_failed"
        # 第一个角度就失败 → 只 1 个点
        assert len(r.points) == 1 and r.points[0].within_tolerance is False

    async def test_sweep_tolerance_exceeded(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _DriftPositioner()})
        r = await positioner_sweep(
            PositionerSweepRequest(angles=[0.0, 90.0], home_first=False, tolerance_deg=0.5)
        )
        assert r.ok is False and r.reason == "tolerance_exceeded"
        assert all(p.within_tolerance is False for p in r.points)
