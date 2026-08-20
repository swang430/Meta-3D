"""P2-29：ASC/B2 正式模型加载证据 hook。

治的缺口（P1-47C 按设计保留的）：`f64.model_loaded` 对三管线都是必填，
但归档只在 GCM 分支触发、且 ASC/B2 加载序列缺两条证据探针 ——
ASC/B2 的正式执行 formal_acceptance 恒 false。

手册依据（NotebookLM 2026-08-20，原文非推断）：状态机与文件来源无关
（AN §2.1 + UR §20.4.3.14，「手册未说明」按来源区分）；判成功流程不分
文件类型（AN §2.2.2/§2.2.4）；加载未 GO = STOPPED（AN §2.1 原文）。
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceVerdict,
    InstrumentEnvironment,
    ScpiExchangeRef,
)
from app.services.execution_scpi_evidence import (
    finalize_execution_scpi_evidence,
    record_f64_command_capture,
    register_required_scpi_evidence,
)
# 复用 47C 的 DB 脚手架（fixture 靠导入进本模块命名空间生效），别再抄一份
from tests.test_p1_47c_execution_scpi_evidence import (  # noqa: F401
    _db_schema,
    _execution,
    db,
)
from app.core.logging_config import current_execution_id


@pytest.fixture(autouse=True)
def _isolate_execution_contextvar():
    """47C 的 _execution 帮手会 set current_execution_id 且从不还原 ——
    泄漏会把后续无关测试的日志行标上本文件的 execution UUID
    （p2_29 + p1_36 合跑实证复现）。本文件自净：每条测试后复位。
    47C 自身与更早的泄漏源（commissioning 端点测试）是遗留问题，另行记录。"""
    token = current_execution_id.set("-")
    yield
    current_execution_id.reset(token)

_HAL = pathlib.Path(__file__).resolve().parents[1] / "app/hal/propsim_f64.py"
_MEASURE = (pathlib.Path(__file__).resolve().parents[1]
            / "app/services/mimo_ota/executors/measure.py")


# ── 行为门：真 builder（子类只覆写环境快照，recipe/scope/判定全走生产代码）──

class _LiveEnvF64:
    def __init__(self):
        from app.hal.propsim_f64 import RealPropsimF64Driver
        self._real = RealPropsimF64Driver(
            "channelEmulator", {"ip": "127.0.0.1", "port": 3334}
        )

    def capture_evidence_environment(self):
        return InstrumentEnvironment(
            instrument_id="channelEmulator",
            instrument="f64",
            model="PROPSIM F64",
            firmware_version="2.0",
            captured_from_live_connection=True,
        )

    def build_p0_5_command_evidence(self, **kwargs):
        from app.hal.scpi_evidence import build_f64_evidence, scope_for_evidence
        scope = scope_for_evidence(
            kwargs["evidence_key"], self.capture_evidence_environment()
        )
        return build_f64_evidence(scope=scope, **kwargs)


def _wire_window(execution, *, load_file, with_state=True, with_model_state=True):
    """ASC/B2 加载事务的 wire 形态：drain → FILE → OPC → ERR → 探针×2。"""
    rows = [("pre", "SYST:ERR?", "query", "response", '0,"No error"'),
            ("file", f"CALC:FILT:FILE {load_file}", "command", "ok", None),
            ("opc", "*OPC?", "query", "response", "1"),
            ("err", "SYST:ERR?", "query", "response", '0,"No error"')]
    if with_model_state:
        rows.append(("model-state", "DIAG:SIMU:MODEL:STATE?", "query",
                     "response", "model=loaded"))
    if with_state:
        rows.append(("state", "DIAG:SIMU:STATE?", "query", "response", "STOPPED"))
    return [ScpiExchangeRef(exchange_id=eid, instrument_id="channelEmulator",
                            operation=op, command=cmd,
                            execution_id=str(execution.id), capture_id="p2-29",
                            sequence=i, result_type=rt, response=resp)
            for i, (eid, cmd, op, rt, resp) in enumerate(rows)]


@pytest.mark.parametrize("load_file", [
    "runtime_emulation.smu",          # ASC runtime 编译产物
    "b2_parametric_tdl.smu",          # B-2 .rtc/.tap 编译产物
])
def test_asc_b2_wire_window_reaches_applied(db, load_file):
    """ASC/B2 的完整加载事务经真 builder 到 APPLIED —— 命令集与 GCM 同一，
    手册确认语义与文件来源无关，所以现有 recipe 原样可用、零新目录条目。"""
    execution = _execution(db)
    register_required_scpi_evidence(
        execution, requirement_id="f64.model_loaded",
        evidence_key="f64.model_load", requested=load_file,
        required_evidence_level=EvidenceLevel.APPLIED)
    record_f64_command_capture(
        execution, requirement_id="f64.model_loaded",
        evidence_key="f64.model_load", requested=load_file,
        driver=_LiveEnvF64(), exchanges=_wire_window(execution, load_file=load_file))
    summary = finalize_execution_scpi_evidence(execution)
    item = summary.items[0]
    assert item.evidence_level == EvidenceLevel.APPLIED, item.reason
    assert item.verdict == EvidenceVerdict.PASSED, item.reason
    assert summary.formal_acceptance is True


def test_missing_state_probe_stays_below_applied(db):
    """fail-closed 回归：少 STATE? 探针就到不了 APPLIED —— 这正是改动前
    ASC/B2 的处境，也是「探针行被删」时兜底的行为门。"""
    execution = _execution(db)
    register_required_scpi_evidence(
        execution, requirement_id="f64.model_loaded",
        evidence_key="f64.model_load", requested="runtime_emulation.smu",
        required_evidence_level=EvidenceLevel.APPLIED)
    record_f64_command_capture(
        execution, requirement_id="f64.model_loaded",
        evidence_key="f64.model_load", requested="runtime_emulation.smu",
        driver=_LiveEnvF64(),
        exchanges=_wire_window(execution, load_file="runtime_emulation.smu",
                               with_state=False))
    summary = finalize_execution_scpi_evidence(execution)
    assert summary.items[0].evidence_level != EvidenceLevel.APPLIED
    assert summary.formal_acceptance is False


# ── 源码门：探针位置与归档条件（让「删一行/改回 GCM-only」当场红）──

def _branch(src: str, anchor: str) -> str:
    """取成功分支：从 anchor 到它后面第一个 _readback_topology() 调用。"""
    i = src.index(anchor)
    j = src.index("await self._readback_topology()", i)
    return src[i:j]


def test_asc_and_b2_success_branches_carry_both_probes():
    """ASC 与 B2 成功分支必须在拓扑回读前带两条证据探针（与 GCM preflight 对称）。
    让它红的改法：删掉任一 `_query_model_state_for_evidence` / `_query_simulation_state`。"""
    src = _HAL.read_text(encoding="utf-8")
    for anchor in ("self._active_pipeline = F64Pipeline.ASC_RUNTIME",
                   "self._active_pipeline = F64Pipeline.B2_PARAMETRIC_TDL"):
        seg = _branch(src, anchor)
        for probe in ("_query_model_state_for_evidence()",
                      "_query_simulation_state()"):
            assert probe in seg, (
                f"{anchor.split('.')[-1]} 分支缺 {probe} —— 证据窗口拼不齐，"
                "该管线的 f64.model_loaded 永远到不了 APPLIED")


def test_measure_record_hook_not_gated_on_engine_mode():
    """归档条件必须按驱动能力判，不按管线枚举 —— 三管线同一 FILE 事务。
    让它红的改法：把条件改回 `engine_mode == EngineMode.GCM_NATIVE and ...`。"""
    src = _MEASURE.read_text(encoding="utf-8")
    i = src.index("record_f64_command_capture(")
    gate = src[max(0, i - 600):i]
    assert 'hasattr(emulator, "build_p0_5_command_evidence")' in gate
    assert not re.search(r"engine_mode\s*==\s*EngineMode\.GCM_NATIVE\s*\n?\s*and\s*hasattr",
                         gate), "归档 hook 又被锁回 GCM-only —— ASC/B2 抓了交换不落证"
