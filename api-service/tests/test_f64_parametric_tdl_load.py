"""F7 单测 — F64 PARAMETRIC_TDL (.tap/.rtc) B-2 加载原语 (P2-14)。

mock 掉 FTP/SCPI 内部 (_ftp_upload_directory / _write / _query), 只验路由 + 加载体选择
+ pipeline 标记 + 运行时门 + fail-loud。真机 .tap schema / gaussian 谱为现场验证 (V1.0 §9)。
"""
import asyncio

import pytest
from unittest.mock import MagicMock

from app.hal.channel_emulator import ChannelLoadMode
from app.hal.propsim_f64 import F64Pipeline, RealPropsimF64Driver


def _drv(transferred=None, captured=None):
    """mock 驱动: _ftp_upload_directory 返回 transferred, 捕获 CALC:FILT:FILE 命令。"""
    drv = RealPropsimF64Driver("propsim-test", {})
    drv._visa_resource = MagicMock()
    captured = captured if captured is not None else {}

    async def _ftp(local, remote):
        captured["remote"] = remote
        return list(transferred) if transferred is not None else []

    async def _write(cmd, timeout=None):
        captured.setdefault("writes", []).append(cmd)
        # 模拟 F64: 坏 .rtc/.smu 时 CALC:FILT:FILE 后往 SYST:ERR? 压错误 (但 *OPC? 仍答 1)
        if cmd.startswith("CALC:FILT:FILE") and captured.get("load_error"):
            captured.setdefault("err_queue", []).append(captured["load_error"])

    async def _query(cmd, timeout=None, **_kw):
        if "SYST:ERR" in cmd:                      # _drain_errors / _first_error 真实现走这里
            q = captured.get("err_queue")
            return q.pop(0) if q else '0,"No error"'
        if "STATE?" in cmd:                        # Codex #223: CLOSE 后确认卸载 → STATE?→CLOSED
            return "CLOSED"
        return "1"                                 # *OPC? 等

    drv._ftp_upload_directory = _ftp
    drv._write = _write
    drv._query = _query
    return drv, captured


def _load_file(captured):
    return next((w.split(" ", 1)[1] for w in captured.get("writes", [])
                 if w.startswith("CALC:FILT:FILE ")), None)


# ───────────── 声明 / 枚举 ─────────────

def test_parametric_tdl_in_supported_modes():
    drv, _ = _drv()
    assert ChannelLoadMode.PARAMETRIC_TDL in drv.get_supported_load_modes()


def test_f64_pipeline_b2_exists():
    assert F64Pipeline.B2_PARAMETRIC_TDL.value == "b2_parametric_tdl"


# ───────────── 路由 + 加载体选择 ─────────────

def test_load_channel_routes_and_sets_pipeline():
    drv, cap = _drv(transferred=["UMa.rtc"])
    ok = asyncio.run(drv.load_channel(
        ChannelLoadMode.PARAMETRIC_TDL, "UMa-CDL-C", "scenario", {}, waveform_dir="/tmp/b2"))
    assert ok is True
    assert drv._active_pipeline == F64Pipeline.B2_PARAMETRIC_TDL


def test_prefers_compiled_smu_over_rtc():
    drv, cap = _drv(transferred=["x.rtc", "y.smu"])
    asyncio.run(drv.load_parametric_tdl("/tmp/b2", "m"))
    assert _load_file(cap).endswith("y.smu")


def test_loads_rtc_when_no_smu_not_asc_fallback():
    """无 .smu 时加载实际 .rtc, 不是 ASC 的 runtime_emulation.smu fallback (Codex P1)。"""
    drv, cap = _drv(transferred=["model.rtc"])
    asyncio.run(drv.load_parametric_tdl("/tmp/b2", "m"))
    lf = _load_file(cap)
    assert lf.endswith("model.rtc")
    assert "runtime_emulation.smu" not in lf


def test_no_loadable_payload_fails_loud():
    """payload 只有 .tap 无 .smu/.rtc 可加载体 → fail-loud, 不退 ASC fallback (Codex P1)。"""
    drv, cap = _drv(transferred=["model.tap"])
    ok = asyncio.run(drv.load_parametric_tdl("/tmp/b2", "m"))
    assert ok is False
    assert _load_file(cap) is None
    assert drv._active_pipeline != F64Pipeline.B2_PARAMETRIC_TDL


def test_ftp_failure_propagates():
    drv, cap = _drv(transferred=[])
    ok = asyncio.run(drv.load_parametric_tdl("/tmp/b2", "m"))
    assert ok is False
    assert drv._active_pipeline != F64Pipeline.B2_PARAMETRIC_TDL


def test_load_fails_loud_on_syst_err_after_load():
    """坏/不支持的 .rtc/.smu: F64 对 *OPC? 仍答 1 但 SYST:ERR? 报错 → fail-loud return
    False, 不标 B2 active (Codex P1 #169: 否则 B-2 在无有效仿真下静默跑测量; 复刻 GCM
    路 _first_error 门)。"""
    drv, cap = _drv(transferred=["bad.rtc"],
                    captured={"load_error": '-200,"No simulation opened"'})
    ok = asyncio.run(drv.load_parametric_tdl("/tmp/b2", "m"))
    assert ok is False
    assert drv._active_pipeline != F64Pipeline.B2_PARAMETRIC_TDL
    # 确认是【加载后 fail-loud gate】拦的: CALC:FILT:FILE 已发 (加载体选择/FTP 都通过)
    assert _load_file(cap) is not None
    assert drv._loaded_emulation_file is None      # 失败不记 _loaded_emulation_file


def test_requires_waveform_dir():
    drv, _ = _drv()
    with pytest.raises(ValueError, match="waveform_dir"):
        asyncio.run(drv.load_channel(
            ChannelLoadMode.PARAMETRIC_TDL, "m", "s", {}, waveform_dir=None))


# ───────────── 运行时门 (P1 #2) ─────────────

def test_runtime_environment_allowed_after_b2_load():
    """B-2 加载后 (pipeline=B2) set_runtime_environment 不被拒 (Codex P1: CH:MOD:CONT:ENV 是 B-2 核心)。"""
    drv, cap = _drv()
    drv._active_pipeline = F64Pipeline.B2_PARAMETRIC_TDL
    ok = asyncio.run(drv.set_runtime_environment({1: {"environment": 2, "gain_db": -30,
                                                      "delay_ns": 1000, "doppler_hz": 0}}))
    assert ok is True
    assert any(w.startswith("CH:MOD:CONT:ENV") for w in cap.get("writes", []))


def test_runtime_environment_rejected_without_runtime_pipeline():
    drv, _ = _drv()
    drv._active_pipeline = F64Pipeline.GCM_NATIVE          # 非 runtime
    ok = asyncio.run(drv.set_runtime_environment({1: {"environment": 2}}))
    assert ok is False
