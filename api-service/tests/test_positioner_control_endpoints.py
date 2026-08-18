"""U-5: positioner (转台) standalone 控制端点测试 (home/move/position/stop/sweep)。

补 standalone REST 入口让现场单独验证转台 (回零/定位/4方位扫), 不依赖完整 cal 流程
(2026-05-27 现场无 standalone 路径 → U-5 "无结论"; 见 morning-log §10)。
mock driver 测端点逻辑; driver 协议行为由 test_aerotech_* 覆盖。不需硬件。
"""
from __future__ import annotations

import pytest

from app.api.instrument import (
    PositionerMoveRequest,
    PositionerSweepRequest,
    _positioner_stop_flag,
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


class _ReadFailPositioner(_FakePositioner):
    async def get_position(self):
        raise RuntimeError("PFBK timeout")  # 模拟回读通信坏 (Codex P2)


class _TrackedStopPositioner(_FakePositioner):
    def __init__(self):
        super().__init__()
        self.operator_stop_generation = 0

    def note_operator_stop(self):
        self.operator_stop_generation += 1


class _AbortMidSweepPositioner(_FakePositioner):
    """move_to 后置急停 flag, 模拟 operator 急停落在 sweep 中途 (Codex P1)。"""

    async def move_to(self, az, el):
        _positioner_stop_flag["requested"] = True
        return await super().move_to(az, el)


class _FakeHal:
    def __init__(self, drivers):
        self.drivers = drivers


def _patch_hal(monkeypatch, drivers):
    import app.services.instrument_hal_service as svc
    monkeypatch.setattr(svc, "get_hal_service", lambda: _FakeHal(drivers))


@pytest.fixture(autouse=True)
def _reset_abort_flag():
    """急停 flag 是模块级共享状态, 每测试前后归零防污染。"""
    _positioner_stop_flag["requested"] = False
    yield
    _positioner_stop_flag["requested"] = False


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


class TestPositionReadFailure:
    """Codex P2 #132: PFBK 读失败不伪造到位, 显式失败 (现场不误判转台在 home)。"""

    async def test_position_endpoint_read_fail(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _ReadFailPositioner()})
        r = await positioner_position()
        assert r.ok is False and r.reason == "position_read_failed"

    async def test_move_read_fail_not_false_success(self, monkeypatch):
        # 动作可能成功但回读失败 → 不报假 Az=0.00° 成功
        _patch_hal(monkeypatch, {"positioner": _ReadFailPositioner()})
        r = await positioner_move(PositionerMoveRequest(azimuth=90.0))
        assert r.ok is False and r.reason == "position_read_failed"

    async def test_sweep_read_fail_stops(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _ReadFailPositioner()})
        r = await positioner_sweep(PositionerSweepRequest(home_first=False))
        assert r.ok is False and r.reason == "position_read_failed"
        assert r.points[0].actual_azimuth is None
        assert r.points[0].within_tolerance is None

    async def test_stop_read_fail_keeps_confirmed_stop_but_returns_unknown_position(
        self, monkeypatch
    ):
        _patch_hal(monkeypatch, {"positioner": _ReadFailPositioner()})

        r = await positioner_stop()

        assert r.ok is True
        assert r.azimuth is None
        assert r.elevation is None
        assert "位置未知" in (r.message or "")


class TestEmergencyStopCoordination:
    """Codex P1 #132: 急停时 in-flight sweep 须停止调度后续 move。"""

    async def test_stop_sets_abort_flag(self, monkeypatch):
        _patch_hal(monkeypatch, {"positioner": _FakePositioner()})
        await positioner_stop()
        assert _positioner_stop_flag["requested"] is True

    async def test_stop_publishes_operator_intent_to_the_shared_driver(self, monkeypatch):
        driver = _TrackedStopPositioner()
        _patch_hal(monkeypatch, {"positioner": driver})

        await positioner_stop()

        assert driver.operator_stop_generation == 1

    async def test_sweep_aborts_on_stop_request(self, monkeypatch):
        # 急停落在第一步后 → 第二步循环顶 abort, 不继续发 move
        _patch_hal(monkeypatch, {"positioner": _AbortMidSweepPositioner()})
        r = await positioner_sweep(
            PositionerSweepRequest(angles=[0.0, 90.0, 180.0], home_first=False)
        )
        assert r.ok is False and r.reason == "aborted"
        assert len(r.points) == 1  # 只完成第一步, 后续 move 被中止

    async def test_move_clears_stale_abort_flag(self, monkeypatch):
        # 单次 move 开始清除旧急停态 (急停后还能手动 move)
        _patch_hal(monkeypatch, {"positioner": _FakePositioner()})
        _positioner_stop_flag["requested"] = True
        r = await positioner_move(PositionerMoveRequest(azimuth=45.0))
        assert r.ok is True
        assert _positioner_stop_flag["requested"] is False
