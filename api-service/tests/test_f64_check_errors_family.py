"""R10 平行族正修 (2026-07-04): 11 个原 `_check_errors`-only 站点的 fail-loud。

背景 (Codex #202 R10 域枚举): F64 参数设置 / 加载方法原是 `写 → _check_errors
(→None 只 log) → return True` —— SCPI 拒绝 (-113/-222 等) 只进错误队列不抛
异常, 假成功让参数没生效上层却继续跑 (set_path_loss/set_output_gain 在校准
补偿链, 假成功 = 补偿没生效静默; upload_asc_files 在 Pipeline B 加载路)。

正修: 收敛到 `_gated_write_transaction` (锁事务 drain → 写 → _first_error 门)
或加载门, 被拒 → False + logger.error (经 JsonFormatter 落 logs/*.jsonl →
/system-logs/tail → GUI Dashboard 日志面板可见)。

本文件钉每个方法: (a) clean 队列 → True + 真实 SCPI 下发; (b) 被拒 → False。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.hal.propsim_f64 import F64InputMeasMode, RealPropsimF64Driver


def _make_driver(*, err_after_writes=None):
    """mock 驱动。err_after_writes: 若给定, 每条非查询写命令后往队列压该错误
    (模拟本次写序列被 F64 拒绝); drain 循环读到 clean 才停, 只有"写序列产生"
    的错误留给门 —— 写后注入比固定队列稳 (不会被前置 drain 误吃)。"""
    drv = RealPropsimF64Driver("propsim-test", {})
    drv._channel_count = 2
    drv._tx_antennas = 2
    drv._rx_antennas = 2
    visa = MagicMock()
    queue: list = []

    def _q(cmd):
        if "SYST:ERR" in cmd:
            return queue.pop(0) if queue else '0,"No error"'
        return "1"  # *OPC? 等

    visa.query.side_effect = _q
    visa.write.return_value = None
    drv._visa_resource = visa

    async def _w(cmd, timeout=None):
        visa.write(cmd)
        if err_after_writes and "SYST:ERR" not in cmd:
            queue.append(err_after_writes)

    async def _query(cmd, timeout=None):
        return visa.query(cmd)

    drv._write = _w  # type: ignore[assignment]
    drv._query = _query  # type: ignore[assignment]
    return drv, visa


def _writes(visa):
    return [c.args[0] for c in visa.write.call_args_list]


# 每个 case: (方法名, 调用 lambda, 期望 clean 路径出现的 SCPI 子串)
_PARAM_CASES = [
    ("set_path_loss", lambda d: d.set_path_loss(distance_m=None, path_loss_db=12.0), "OUTP:LOSS:SET"),
    ("set_doppler", lambda d: d.set_doppler(frequency_hz=0.0), "DIAG:SIMU:MOB:MAN:CH"),
    ("set_baseband_power", lambda d: d.set_baseband_power(-15.0), "INP:LEV:AMP:CH"),
    ("set_external_attenuators", lambda d: d.set_external_attenuators({1: 3.0}), "OUTP:GAIN:CH"),
    ("set_output_path_loss", lambda d: d.set_output_path_loss(2, 8.0), "OUTP:LOSS:SET 2,8.0"),
    ("set_output_gain", lambda d: d.set_output_gain(3, -4.0), "OUTP:GAIN:CH 3,-4.00"),
    ("set_crest_factor", lambda d: d.set_crest_factor(1, 12.0), "INP:CRE:SET 1,12.00"),
    ("set_input_measurement_mode",
     lambda d: d.set_input_measurement_mode(1, F64InputMeasMode.BURST), "INP:MEAS:MODE:SET"),
    ("set_burst_trigger_level", lambda d: d.set_burst_trigger_level(1, -20.0),
     "INP:MEAS:BURST:TRIG:SET 1,-20.00"),
]


class TestParamMethodsCleanPath:
    @pytest.mark.parametrize("name,call,scpi", _PARAM_CASES)
    @pytest.mark.asyncio
    async def test_clean_queue_returns_true_and_writes(self, name, call, scpi):
        drv, visa = _make_driver()
        ok = await call(drv)
        assert ok is True, name
        assert any(scpi in s for s in _writes(visa)), (name, _writes(visa))


class TestParamMethodsFailLoud:
    @pytest.mark.parametrize("name,call,_scpi", _PARAM_CASES)
    @pytest.mark.asyncio
    async def test_rejected_returns_false(self, name, call, _scpi):
        """SCPI 被拒 (队列有 -222 越界) → False (不再假成功)。"""
        drv, visa = _make_driver(err_after_writes='-222,"Data out of range"')
        ok = await call(drv)
        assert ok is False, f"{name} 被拒仍返 True (假成功)"
        assert "-222" in (drv._last_error or ""), name

    @pytest.mark.asyncio
    async def test_error_logged_for_gui_visibility(self, caplog):
        """被拒经 logger.error 上报 (JsonFormatter → /system-logs → GUI 面板)。
        用 monkeypatch logger 避开全量顺序耦合 caplog 污染。"""
        import app.hal.propsim_f64 as f64_mod

        logged: list = []
        drv, _ = _make_driver(err_after_writes='-113,"Undefined header"')
        orig = f64_mod.logger.error
        f64_mod.logger.error = lambda msg, *a, **k: (logged.append(str(msg)), orig(msg, *a, **k))
        try:
            await drv.set_output_gain(1, 2.0)
        finally:
            f64_mod.logger.error = orig
        assert any("被拒" in m for m in logged), logged


class TestUploadAscFilesLoadGate:
    """upload_asc_files (ASC Pipeline B) 加载路: 原全程无门 (P0-8 母题 —
    *OPC? 对缺失/损坏 .smu 照答 1), R10 补 _first_error 门。"""

    def _make_asc_driver(self, *, load_error=None):
        drv = RealPropsimF64Driver("propsim-asc", {})
        drv._channel_count = 2
        visa = MagicMock()
        queue: list = []

        def _q(cmd):
            if "SYST:ERR" in cmd:
                return queue.pop(0) if queue else '0,"No error"'
            if "STATE?" in cmd:                    # Codex #223: CLOSE 后确认卸载 → CLOSED
                return "CLOSED"
            return "1"

        visa.query.side_effect = _q
        drv._visa_resource = visa
        writes: list = []

        async def _w(cmd, timeout=None):
            writes.append(cmd)
            visa.write(cmd)
            if load_error and cmd.startswith("CALC:FILT:FILE"):
                queue.append(load_error)  # 载入后 F64 压错误 (但 *OPC? 仍答 1)

        async def _query(cmd, timeout=None):
            return visa.query(cmd)

        async def _ftp(local, remote):
            return ["runtime_emulation.smu"]  # 模拟成功传输

        drv._write = _w  # type: ignore[assignment]
        drv._query = _query  # type: ignore[assignment]
        drv._ftp_upload_directory = _ftp  # type: ignore[assignment]
        return drv, writes

    @pytest.mark.asyncio
    async def test_clean_load_returns_true(self):
        drv, writes = self._make_asc_driver()
        ok = await drv.upload_asc_files("/tmp/asc", "UMa-CDL-C")
        assert ok is True
        assert any(w.startswith("CALC:FILT:FILE") for w in writes)
        assert drv._loaded_emulation_file  # 缓存已更新

    @pytest.mark.asyncio
    async def test_load_rejected_fails_loud_no_stale_file(self):
        """加载被拒 (-200 No simulation opened) → False + _loaded_emulation_file
        清空 (从 None 起, 门后不误设)。"""
        drv, _ = self._make_asc_driver(load_error='-200,"No simulation opened"')
        assert drv._loaded_emulation_file is None
        ok = await drv.upload_asc_files("/tmp/asc", "UMa-CDL-C")
        assert ok is False
        assert "-200" in (drv._last_error or "")
        assert drv._loaded_emulation_file is None

    @pytest.mark.asyncio
    async def test_load_rejected_clears_prior_loaded_file(self):
        """Codex #211 follow-up: 上次成功 load 过, 新 ASC load 被拒 (CLOSE 已
        发) → 清空旧 _loaded_emulation_file, 不谎报'还开着' (原判'缓存不动'
        是错的 — CLOSE 已改变状态)。"""
        drv, _ = self._make_asc_driver(load_error='-200,"No simulation opened"')
        drv._loaded_emulation_file = "D:\\old\\prev.smu"  # 脏态: 上次加载
        ok = await drv.upload_asc_files("/tmp/asc", "UMa-CDL-C")
        assert ok is False
        assert drv._loaded_emulation_file is None  # 旧文件清空


class TestErrorReachesGuiLogPanel:
    """用户要求: 被拒的错误/告警要到达 GUI 日志面板。验证 driver 的
    logger.error 经生产的 ContextFilter + JsonFormatter 产出的 JSON 满足
    /system-logs/tail?level=ERROR 的过滤 + LogEntry 解析契约 (→ ZoneLogsAlerts
    面板)。固化此链路防将来改 formatter 字段静默断链。"""

    @pytest.mark.asyncio
    async def test_rejected_error_serializes_for_system_logs_tail(self):
        import io
        import json
        import logging

        from app.core.logging_config import (
            ContextFilter,
            JsonFormatter,
            current_instrument_id,
            current_session_id,
        )

        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(ContextFilter())  # 生产链路: contextvar → record
        lg = logging.getLogger("app.hal.propsim_f64.familytest")
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)
        lg.propagate = False

        # HAL 调用时 contextvar 已由中间件/HAL 层设 (此处模拟)
        tok_i = current_instrument_id.set("propsim-f64-caict")
        tok_s = current_session_id.set("sess-throughput-01")
        drv_logger = logging.getLogger("app.hal.propsim_f64")
        # 测试隔离: 前序 test_channel_asset_migration 的 alembic in-process
        # upgrade 走 fileConfig(disable_existing_loggers=True) 会把已导入的
        # propsim_f64 logger 永久 .disabled=True 且不恢复 → 本用例是全套件
        # 第一个真断言 logger emit 的用例, 会踩到该既存污染。显式复位 +
        # finally 还原 (生产不受影响: logging_config 用 dictConfig
        # disable_existing_loggers=False)。
        was_disabled = drv_logger.disabled
        drv_logger.disabled = False
        try:
            # 真 driver 被拒 → 真 logger.error (走同一 logger 家族)
            drv, _ = _make_driver(err_after_writes='-222,"Data out of range"')
            drv_logger.addHandler(handler)
            try:
                await drv.set_output_gain(3, -4.0)
            finally:
                drv_logger.removeHandler(handler)
        finally:
            drv_logger.disabled = was_disabled
            current_instrument_id.reset(tok_i)
            current_session_id.reset(tok_s)

        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        err_objs = [json.loads(l) for l in lines if json.loads(l)["level"] == "ERROR"]
        assert err_objs, "被拒未产生 ERROR 级日志 → GUI 面板 (level=ERROR 过滤) 看不到"
        rejected = [o for o in err_objs if "被拒" in o["msg"]]
        assert rejected, err_objs
        entry = rejected[0]
        # /system-logs/tail 的 LogEntry 逐字段: ts/level/logger/instrument_id/msg
        assert entry["instrument_id"] == "propsim-f64-caict"  # 面板 instrument 列
        assert entry["session_id"] == "sess-throughput-01"
        assert "set_output_gain" in entry["msg"] and "-222" in entry["msg"]


class TestGatedWriteTransactionAtomicity:
    @pytest.mark.asyncio
    async def test_transaction_holds_lock_across_write_and_gate(self):
        """事务持锁: drain → 写 → 门 整段临界区, 并发轮询不插入。"""
        import asyncio
        import time

        drv = RealPropsimF64Driver("propsim-atomic", {})
        drv._channel_count = 1
        calls: list = []

        class _V:
            timeout = 5000

            def write(self, cmd):
                calls.append(cmd)
                time.sleep(0.002)

            def query(self, cmd):
                calls.append(cmd)
                time.sleep(0.002)
                return "1" if cmd == "*OPC?" else '0,"No error"'

        drv._visa_resource = _V()
        ok, _ = await asyncio.gather(
            drv.set_output_gain(1, 3.0), drv._query("POLL?")
        )
        assert ok is True
        # 事务区间 = 首条 SYST:ERR? (drain) .. 门的 SYST:ERR? — POLL? 只能在区外
        first_err = calls.index("SYST:ERR?")
        last_err = len(calls) - 1 - calls[::-1].index("SYST:ERR?")
        assert "POLL?" not in calls[first_err:last_err + 1], calls
