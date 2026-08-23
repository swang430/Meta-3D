"""P1-65 / P2-13: `uxm_sim_identity_truth` 的行为门。

故障：roadmap「Blocked on hardware」P2-13（UE 实测 IMSI 与 SIMProfile 声明是否一致）
没有任何 checked-in 载体；precheck 的 SIM 核对（`executors/precheck.py` 2.4b）只拿得到
操作员手敲值，modem 实测 IMSI 从未被读过。

本序列的契约（设计稿 §1/§2/§3）：
- 读 `BSE:INFO:NR5G:<cell>:UEReported:IMSI?`（01_NR_Core.md:39014，Query only）与小区状态；
- 声明值走 precheck 同一取数路径（SIMProfile 表，按 id 或名称）；拿不到 → UNDETERMINED；
- 两边都有且相等 → SUCCESS；不等 → BLOCKER；UE 未 attach / 回空 → UNDETERMINED；
- **IMSI 是 PII**：结果（summary / steps.raw / extra）里只出现 P1-47A 脱敏形态（保留末 4 位），
  完整 IMSI 不得落盘；
- 只在 BSE 方言发；5G_NR_Test → 不发，UNDETERMINED；每步后读错误队列。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from typing import Dict, List
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.diagnostics.sequences import uxm_sim_identity_truth as seq
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)
from app.models.sim_profile import SIMProfile

CELL = UxmLteNrIratProfile.PRIMARY_CELL
ERR = UxmLteNrIratProfile.ERR
STATUS_Q = UxmLteNrIratProfile.CELL_STATUS_QUERY.format(cell=CELL)
IMSI_Q = f"BSE:INFO:NR5G:{CELL}:UEReported:IMSI?"
INJ = "CELL1?;:SYSTem:PRESet:FULL;:BSE:STATus:NR5G:CELL1"  # 内审 F5 的注入串

DECLARED = "460001234567890"
OTHER = "460009876543210"


class _ScriptedBs:
    def __init__(self, profile=UxmLteNrIratProfile, *, status="CONNected",
                 imsi=f'"{DECLARED}"', err_after=None, raise_on=None):
        self._cmds = profile
        self.ops: List[str] = []
        self.writes: List[str] = []
        self._responses: Dict[str, str] = {STATUS_Q: status, IMSI_Q: imsi}
        self._err_after = err_after or {}
        self._raise_on = raise_on
        self._last = None

    def _query(self, cmd):
        self.ops.append(cmd)
        if self._raise_on and cmd == self._raise_on:
            raise TimeoutError(f"timeout on {cmd}")
        if cmd == ERR:
            return self._err_after.get(self._last, '0,"No error"')
        self._last = cmd
        return self._responses.get(cmd, "")

    def _write(self, cmd):
        self.ops.append(cmd)
        self.writes.append(cmd)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def sim(db, monkeypatch):
    """建一张声明卡，并把序列的 DB 打开口指到这个 SQLite 会话。"""
    row = SIMProfile(name="TestSIM-46000", imsi=DECLARED, card_kind="test_sim")
    db.add(row)
    db.commit()
    monkeypatch.setattr(seq, "_open_db", lambda: db)
    return row


def _run(bs, params=None):
    hal = MagicMock()
    hal.drivers = {"baseStation": bs}
    return asyncio.run(seq.run(
        MagicMock(), hal, params or {}, log=lambda *_: None,
    ))


def _dump(result) -> str:
    """把整个结果（summary + steps + extra）序列化成一个字符串，用于 PII 扫描。"""
    return json.dumps(dataclasses.asdict(result), ensure_ascii=False, default=str)


def _assert_err_after_every_step(bs):
    ops = bs.ops
    assert ops
    for i, cmd in enumerate(ops):
        if cmd == ERR:
            continue
        assert i + 1 < len(ops) and ops[i + 1] == ERR, (i, cmd)
    assert ops[-1] == ERR


# ── 门 0 / 1 ───────────────────────────────────────────────────────────

def test_metadata():
    assert seq.metadata.required_categories == ["baseStation"]
    names = {p["name"] for p in seq.metadata.params_schema}
    assert {"cell", "sim_profile"} <= names


def test_refuses_mock_driver():
    class MockUxm:
        _cmds = UxmLteNrIratProfile

        def _query(self, _):
            raise AssertionError("mock 不该收到命令")

    result = _run(MockUxm())
    assert result.success is False and "mock" in result.summary


def test_refuses_when_driver_not_loaded():
    hal = MagicMock()
    hal.drivers = {}
    result = asyncio.run(seq.run(MagicMock(), hal, {}, log=lambda *_: None))
    assert result.success is False and "未加载 baseStation" in result.summary


# ── 门 2：方言门 ────────────────────────────────────────────────────────

def test_5gnr_dialect_sends_nothing_and_is_undetermined(sim):
    bs = _ScriptedBs(Uxm5GNRTestAppProfile)
    result = _run(bs, {"sim_profile": "TestSIM-46000"})
    assert bs.ops == []
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "5G_NR_Test" in result.summary and "未查证" in result.summary


# ── 门 3：只读不变量 + 错误队列 ─────────────────────────────────────────

def test_readonly_sends_only_manual_queries_and_reads_err_after_each(sim):
    bs = _ScriptedBs()
    result = _run(bs, {"sim_profile": "TestSIM-46000"})
    assert bs.writes == []
    assert set(bs.ops) == {STATUS_Q, IMSI_Q, ERR}
    # 手册 `Request IMEI or IMSI` 是 Imm Action（NAS:REQuest）—— 本序列不发
    assert not any("NAS:REQuest" in c for c in bs.ops)
    _assert_err_after_every_step(bs)
    assert result.extra["cell_status"] == "CONNected"


# ── 门 4：判定 ──────────────────────────────────────────────────────────

def test_match_is_success(sim):
    bs = _ScriptedBs()
    result = _run(bs, {"sim_profile": "TestSIM-46000"})
    assert result.extra["verdict"] == "SUCCESS"
    assert result.success is True
    assert result.extra["consistent"] is True
    assert result.extra["sim_profile_name"] == "TestSIM-46000"


def test_mismatch_is_blocker_and_both_values_are_masked(sim):
    bs = _ScriptedBs(imsi=f'"{OTHER}"')
    result = _run(bs, {"sim_profile": "TestSIM-46000"})
    assert result.extra["verdict"] == "BLOCKER"
    assert result.success is False
    assert result.extra["consistent"] is False
    # 两个值都要在结论里（脱敏形态）
    assert result.extra["declared_imsi_masked"].endswith(DECLARED[-4:])
    assert result.extra["reported_imsi_masked"].endswith(OTHER[-4:])
    assert DECLARED[-4:] in result.summary and OTHER[-4:] in result.summary


def test_full_imsi_never_appears_anywhere_in_result(sim):
    """PII 门：完整 IMSI 不得出现在 summary / steps(detail, raw) / extra 任何地方。"""
    for imsi in (DECLARED, OTHER):
        bs = _ScriptedBs(imsi=f'"{imsi}"')
        result = _run(bs, {"sim_profile": "TestSIM-46000"})
        blob = _dump(result)
        assert DECLARED not in blob, "声明 IMSI 完整值泄漏"
        assert OTHER not in blob, "UE 上报 IMSI 完整值泄漏"
        # 但末 4 位要在（现场辨识卡用）
        assert imsi[-4:] in blob
        # raw 仍要存（归档可比对），但存的是脱敏副本
        imsi_steps = [s for s in result.steps if s.label.startswith("UEReported:IMSI?")]
        assert imsi_steps and imsi_steps[0].raw is not None
        assert imsi not in imsi_steps[0].raw


def test_empty_imsi_is_undetermined(sim):
    for empty, status in (('""', "OFF"), ("", "ON"), ('""', "IDLE")):
        bs = _ScriptedBs(imsi=empty, status=status)
        result = _run(bs, {"sim_profile": "TestSIM-46000"})
        assert result.extra["verdict"] == "UNDETERMINED", (empty, status)
        assert result.success is False
        assert status in result.summary


def test_no_sim_profile_param_is_undetermined_but_still_collects(sim):
    bs = _ScriptedBs()
    result = _run(bs)
    assert result.extra["verdict"] == "UNDETERMINED"
    assert result.extra["reported_imsi_masked"].endswith(DECLARED[-4:])
    assert result.extra["declared_imsi_masked"] is None
    assert "sim_profile" in result.summary


def test_unknown_sim_profile_is_undetermined(sim):
    bs = _ScriptedBs()
    result = _run(bs, {"sim_profile": "no-such-card"})
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "no-such-card" in result.summary


def test_sim_profile_resolves_by_id_too(sim):
    bs = _ScriptedBs()
    result = _run(bs, {"sim_profile": str(sim.id)})
    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["sim_profile_name"] == "TestSIM-46000"


def test_declared_card_without_imsi_is_undetermined(db, monkeypatch):
    db.add(SIMProfile(name="NoImsiCard", imsi=None, card_kind="commercial"))
    db.commit()
    monkeypatch.setattr(seq, "_open_db", lambda: db)
    bs = _ScriptedBs()
    result = _run(bs, {"sim_profile": "NoImsiCard"})
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "NoImsiCard" in result.summary


def test_db_failure_is_undetermined_not_crash(sim, monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(seq, "_open_db", _boom)
    bs = _ScriptedBs()
    result = _run(bs, {"sim_profile": "TestSIM-46000"})
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "db down" in result.summary


def test_query_error_is_recorded(sim):
    bs = _ScriptedBs(imsi="", err_after={IMSI_Q: '-113,"Undefined header"'})
    result = _run(bs, {"sim_profile": "TestSIM-46000"})
    assert result.extra["readback_errors"] == {IMSI_Q: '-113,"Undefined header"'}
    assert result.extra["verdict"] == "UNDETERMINED"
    assert "不支持" not in result.summary


def test_cell_injection_sends_nothing(sim):
    """内审 F5：`cell` 白名单 CELL1..CELL14 | SELected；注入串零 SCPI。
    变异：去掉 `_validate_cell` 校验 → 红。"""
    for bad in (INJ, "CELL0", "CELL15", "CELL1;*RST", "SELected?"):
        bs = _ScriptedBs()
        result = _run(bs, {"cell": bad, "sim_profile": "TestSIM-46000"})
        assert bs.ops == [], repr(bad)
        assert result.extra["verdict"] != "SUCCESS", repr(bad)
        assert "白名单" in result.summary, repr(bad)


def test_cell_whitelist_normalises_into_imsi_query(sim):
    bs = _ScriptedBs()
    bs._responses[f"BSE:INFO:NR5G:CELL2:UEReported:IMSI?"] = f'"{DECLARED}"'
    bs._responses[UxmLteNrIratProfile.CELL_STATUS_QUERY.format(cell="CELL2")] = "CONNected"
    result = _run(bs, {"cell": "cell2", "sim_profile": "TestSIM-46000"})
    assert result.extra["cell"] == "CELL2"
    assert "BSE:INFO:NR5G:CELL2:UEReported:IMSI?" in bs.ops
    assert result.extra["verdict"] == "SUCCESS"


def test_transport_exception_is_aborted(sim):
    bs = _ScriptedBs(raise_on=IMSI_Q)
    result = _run(bs, {"sim_profile": "TestSIM-46000"})
    assert result.extra["verdict"] == "ABORTED"
    assert "TimeoutError" in result.summary
