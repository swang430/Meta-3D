"""P2-74：行程时间超过控制器套接字空闲超时的 MOVEABS 必然断连 —— 按阻塞预算拆段。

真机事实（scpi.log* 共 33 次 MOVEABS）：成功的全是 0 s（已在目标位）或 2.1 s（10° 小步）；
仅有的两次行程 > 10 s（08-27 `X 100`、09-16 `X -90`）都恰在第 10.0 s 失败。
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

import pytest

from app.hal.aerotech_positioner import (
    AerotechCommandRejected,
    AerotechError,
    AerotechOperatorStopRequested,
    RealAerotechDriver,
)


SOCKET_IDLE_TIMEOUT_S = 10.0  # 集成说明 Socket2Timeout；真机实测 reset 恰在 10.0 s


class ControllerLikeDriver(RealAerotechDriver):
    """按真机行为造的假控制器：MOVEABS 阻塞到移动完成，占线 > 10 s 即 reset 连接。"""

    def __init__(self, *, start_deg: float, feed: float = 5.0, budget_s: float | None = None,
                 encoder_moves: bool = True):
        config: dict[str, Any] = {
            "ip": "192.0.2.10",
            "position_tolerance_deg": 0.5,
            "poll_interval_s": 0.0,
            "settle_timeout_s": 0.1,
            "motion_truth_units_verified": True,
            "motion_truth_user_units": "degree",
            "motion_truth_min_deg": -180.0,
            "motion_truth_max_deg": 360.0,
            "motion_truth_xf_speed": feed,
            "motion_truth_coordinate_offset_verified": True,
            "motion_truth_coordinate_offset_deg": 0.0,
        }
        if budget_s is not None:
            config["blocking_command_budget_s"] = budget_s
        super().__init__("p2-74-positioner", config)
        self._axes_present = ["X"]
        self.position_deg = float(start_deg)
        self.encoder_moves = encoder_moves
        self.sent: list[str] = []
        self.blocked_seconds: list[float] = []
        self.stop_before_command: dict[str, int] = defaultdict(int)

    async def _send(self, command: str, *, expected_operator_stop_generation: int | None = None) -> str:
        if (
            expected_operator_stop_generation is not None
            and self.operator_stop_generation() != expected_operator_stop_generation
        ):
            raise AerotechOperatorStopRequested("operator stop requested")
        self.sent.append(command)
        if command.startswith("MOVEABS X "):
            target = float(command.split()[2])
            travel_s = abs(target - self.position_deg) / float(command.split("XF")[1])
            self.blocked_seconds.append(travel_s)
            if travel_s > SOCKET_IDLE_TIMEOUT_S:
                # 真机：阻塞等待期间线路无往返，控制器把连接当空闲并 reset。
                raise ConnectionResetError("[Errno 54] Connection reset by peer")
            if self.encoder_moves:
                self.position_deg = target
            return ""
        if command.startswith(("ENABLE ", "ABORT ", "WAIT INPOS ")):
            return ""
        if command == "PFBK(X)":
            return f"{self.position_deg:.6f}"
        if command == "VFBK(X)":
            return "0"
        raise AssertionError(f"unexpected command: {command}")

    def moveabs_targets(self) -> list[float]:
        return [float(c.split()[2]) for c in self.sent if c.startswith("MOVEABS X ")]


@pytest.mark.asyncio
async def test_long_move_is_split_so_no_single_moveabs_blocks_past_the_budget():
    # 09-16 的形态：90° 起步、5°/s。不拆段 = 18 s 阻塞 = 第 10 s 断连。
    driver = ControllerLikeDriver(start_deg=90.0, feed=5.0)  # 默认预算 6 s

    assert await driver.move_to(0.0, 0.0) is True

    assert driver.moveabs_targets() == [60.0, 30.0, 0.0]
    assert all(t <= driver.blocking_command_budget_s for t in driver.blocked_seconds)
    assert max(driver.blocked_seconds) < SOCKET_IDLE_TIMEOUT_S
    assert driver.position_deg == 0.0
    # 每段都走既有的 WAIT INPOS + PFBK 真值门。
    assert driver.sent.count("WAIT INPOS X") == 3
    assert driver.sent.count("PFBK(X)") >= 4  # 起点 1 次 + 每段 1 次
    assert "ABORT X" not in driver.sent


@pytest.mark.asyncio
async def test_move_within_budget_keeps_the_single_moveabs_wire_sequence():
    driver = ControllerLikeDriver(start_deg=0.0, feed=5.0)  # 10° / 5°/s = 2 s ≤ 6 s

    assert await driver.move_to(10.0, 0.0) is True

    assert driver.moveabs_targets() == [10.0]
    assert driver.sent.count("WAIT INPOS X") == 1


@pytest.mark.asyncio
async def test_unsplit_long_move_reproduces_the_field_failure():
    # 对照：预算设得比套接字超时还大 = 不拆段 → 复现 09-16 的断连。
    driver = ControllerLikeDriver(start_deg=90.0, feed=5.0, budget_s=60.0)

    assert await driver.move_to(0.0, 0.0) is False

    assert driver.moveabs_targets() == [0.0]
    assert driver.blocked_seconds == [18.0]
    # 假控制器在 _send 层直接抛 ConnectionResetError，绕过了真 _send 的「重连 → 结局未知」翻译；
    # 这里证明的是「阻塞过久必失败 + 任何异常出口都急停」，不是那条翻译路径（它由 test_p1_56 覆盖）。
    assert "ABORT X" in driver.sent


@pytest.mark.asyncio
async def test_operator_stop_between_segments_sends_no_further_moveabs():
    driver = ControllerLikeDriver(start_deg=90.0, feed=5.0)
    original = driver._wait_for_settle

    async def _stop_after_first_segment(**kwargs):
        await original(**kwargs)
        if driver.moveabs_targets() == [60.0]:
            driver.note_operator_stop()  # 第一段停稳后操作员叫停

    driver._wait_for_settle = _stop_after_first_segment  # type: ignore[method-assign]

    assert await driver.move_to(0.0, 0.0) is False

    assert driver.moveabs_targets() == [60.0]
    assert "ABORT X" in driver.sent
    # 叫停发生在段间：第二段的 MOVEABS 一条都没发出去。
    assert not any(c.startswith("MOVEABS X 30.") for c in driver.sent)


@pytest.mark.asyncio
async def test_segment_whose_encoder_did_not_move_fails_closed_before_the_next_segment():
    driver = ControllerLikeDriver(start_deg=90.0, feed=5.0, encoder_moves=False)

    assert await driver.move_to(0.0, 0.0) is False

    assert driver.moveabs_targets() == [60.0]  # 第一段真值门就拦下
    assert "ABORT X" in driver.sent


@pytest.mark.parametrize(
    ("current", "target", "feed", "budget", "expected"),
    [
        (0.0, 10.0, 5.0, 6.0, [10.0]),                       # 2 s，一段
        (0.0, 30.0, 5.0, 6.0, [30.0]),                       # 恰好 6 s，仍一段
        (0.0, 31.0, 5.0, 6.0, [15.5, 31.0]),                 # 刚超预算，两段
        (90.0, -90.0, 5.0, 6.0, [60.0, 30.0, 0.0, -30.0, -60.0, -90.0]),  # 反向 180°
        (0.0, 180.0, 20.0, 6.0, [90.0, 180.0]),              # 9 s，两段
    ],
)
def test_segment_plan_never_exceeds_budget_and_ends_exactly_on_target(current, target, feed, budget, expected):
    driver = ControllerLikeDriver(start_deg=current, feed=feed, budget_s=budget)

    plan = driver._plan_program_segments(current_program=current, program_target=target, feed=feed)

    assert plan == pytest.approx(expected)
    assert plan[-1] == target
    previous = current
    for step in plan:
        assert abs(step - previous) / feed <= budget + 1e-9
        previous = step


@pytest.mark.parametrize("bad_budget", [0.0, -1.0, float("nan"), float("inf")])
def test_blocking_budget_must_be_finite_positive(bad_budget):
    with pytest.raises(ValueError):
        ControllerLikeDriver(start_deg=0.0, budget_s=bad_budget)


def test_segment_plan_rejects_non_finite_inputs_before_io():
    driver = ControllerLikeDriver(start_deg=0.0)
    with pytest.raises(AerotechError):
        driver._plan_program_segments(current_program=math.nan, program_target=10.0, feed=5.0)
    with pytest.raises(AerotechError):
        driver._plan_program_segments(current_program=0.0, program_target=10.0, feed=0.0)


class _ScriptedStreams:
    """最小的 StreamReader / StreamWriter 替身：按脚本回字节，走真驱动的 _tx_rx。"""

    def __init__(self, replies: list[bytes]):
        self.buffer = bytearray(b"".join(replies))
        self.written: list[bytes] = []

    # writer
    def write(self, data: bytes) -> None:
        self.written.append(bytes(data))

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return False

    # reader
    async def readexactly(self, n: int) -> bytes:
        if len(self.buffer) < n:
            import asyncio
            raise asyncio.IncompleteReadError(bytes(self.buffer), n)
        out = bytes(self.buffer[:n]); del self.buffer[:n]
        return out

    async def readline(self) -> bytes:
        idx = self.buffer.find(b"\n")
        end = len(self.buffer) if idx < 0 else idx + 1
        out = bytes(self.buffer[:end]); del self.buffer[:end]
        return out


@pytest.mark.asyncio
async def test_expected_axis_probe_rejection_is_not_logged_as_error(caplog):
    # 单轴台每次连接都会探测 PFBK(Y) 并被控制器拒（"!"）：预期结果，不该按 ERROR 记
    # （09-16 一天 30 条）。走真驱动的 _send → _tx_rx，只替换线路字节。
    # 前序测试在进程内跑 alembic fileConfig(disable_existing_loggers=True) 会把已导入的 logger
    # 永久置为 disabled，单跑绿、全量红（memory: feedback_test_logger_emit_alembic_pollution）。先复位。
    # 复现对：tests/test_channel_asset_migration.py + 本文件（去掉复位即红）。
    target_logger = logging.getLogger("app.hal.aerotech_positioner")
    target_logger.disabled = False
    target_logger.propagate = True

    driver = RealAerotechDriver("p2-74-probe", {"ip": "192.0.2.10"})
    streams = _ScriptedStreams([b"!\n"])  # 探测 Y 轴：拒绝
    driver._reader = streams  # type: ignore[assignment]
    driver._writer = streams  # type: ignore[assignment]

    with caplog.at_level(logging.INFO, logger="app.hal.aerotech_positioner"):
        assert await driver._probe_axis("Y") is False
    probe_records = [r for r in caplog.records if "PFBK(Y)" in r.getMessage()]
    assert probe_records
    assert all(r.levelno < logging.ERROR for r in probe_records)
    assert driver._expected_rejection_cmd is None

    # 对照：非探测命令被拒仍按 ERROR 记。
    caplog.clear()
    streams2 = _ScriptedStreams([b"!\n"])
    driver._reader = streams2  # type: ignore[assignment]
    driver._writer = streams2  # type: ignore[assignment]
    with caplog.at_level(logging.INFO, logger="app.hal.aerotech_positioner"):
        with pytest.raises(AerotechCommandRejected):
            await driver._send("ENABLE X")
    assert any(r.levelno == logging.ERROR and "ENABLE X" in r.getMessage() for r in caplog.records)
