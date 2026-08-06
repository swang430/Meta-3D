"""P0-2 (S1/S2/S3/S5) 行为门: UXM 配置单一真值源。

变异自验对应表 (⓪-④, 每条注明"把哪行改回去, 哪条测试红"):

- D1 状态换源: `test_attach_polls_status_query_not_switch_echo` —— 把
  start_signaling 轮询改回 `CELL_STATE_QUERY` (ACTive 开关回读) → 红
  (断言轮询期间真的发过 `BSE:STATus:NR5G:CELL1?`, 钉的是**发出的查询**,
  不是 fake 的中间量)。
- D1 白名单不猜: `test_attach_switch_echo_shape_never_judged` —— "0"/"1"
  这类枚举外回复永不判 attach 成功。
- D1 去缓存断言: `test_activation_write_does_not_cache_on` —— 恢复
  `self._cell_state = CellState.ON` 那行 → 红。
- D2 APPLY 契约: `test_apply_sent_once_when_cell_on` (删 APPLY 块 → 红) +
  `test_apply_not_sent_when_cell_off` (OFF 乱发 → 红)。
- D5 假绿: `test_hal_init_apply_failure_row_is_warn_not_ok` —— 把
  status 改回恒 "ok" → 红。

fake 语义按真机形态造 (memory: fake 教错模型是反向改写生产代码的高危路):
IRAT 的 ACTive:STATe? 回 "0"/"1"; BSE:STATus:NR5G:<cell>? 回手册枚举
(OFF|ON|CONNected|IDLE|AGGRegated|ACTivated); 5G_NR_Test 的旧查询回文本态。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.hal.base_station import CellState
from app.hal.uxm_base_station import RealUxmDriver


# ─────────────────────────────────────────────────────────────────────
# 假 VISA 会话: 按查询前缀路由回复, 记录全部写入与查询
# ─────────────────────────────────────────────────────────────────────

class _FakeUxmSession:
    """回复表驱动的假会话。replies 按「查询串包含的子串 → 回复」匹配,
    先命中先用; 未命中回 ""。"""

    def __init__(self, replies: Dict[str, str]):
        self.replies = dict(replies)
        self.written: List[str] = []
        self.queried: List[str] = []
        self.timeout = 5000

    def write(self, cmd: str) -> None:
        self.written.append(cmd.strip())

    def query(self, cmd: str) -> str:
        c = cmd.strip()
        self.queried.append(c)
        for needle, reply in self.replies.items():
            if needle in c:
                return reply
        return ""


def _mk_irat_driver(replies: Dict[str, str]) -> tuple[RealUxmDriver, _FakeUxmSession]:
    d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
    sess = _FakeUxmSession(replies)
    d._visa_session = sess
    return d, sess


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """start_signaling 每轮 sleep(2.0) — 测试里快进, 保持轮次语义。"""
    real_sleep = asyncio.sleep

    async def _instant(_secs):
        await real_sleep(0)

    import app.hal.uxm_base_station as uxm_mod
    monkeypatch.setattr(uxm_mod.asyncio, "sleep", _instant)
    yield


# ─────────────────────────────────────────────────────────────────────
# D1 attach 轮询换源
# ─────────────────────────────────────────────────────────────────────

class TestAttachTruthSource:
    @pytest.mark.asyncio
    async def test_attach_polls_status_query_not_switch_echo(self):
        """变异门: 轮询必须发 BSE:STATus:NR5G:CELL1? — 改回 ACTive 回读即红。

        fake 复刻真机形态: 开关回读永远 "1" (自己写的回声), 状态查询回
        CONNected — 旧代码在这形态下永远判不了成功 (R1)。"""
        d, sess = _mk_irat_driver({
            "*OPC?": "1",
            "BSE:STATus:NR5G:CELL1?": "CONNected",
            "ACTive:STATe?": "1",
        })
        ok = await d.start_signaling(timeout_s=6)
        assert ok is True
        assert d._cell_state == CellState.CONNECTED
        # 钉发出的查询本身 (真实生效端), 不钉 fake 内部状态
        assert any(q == "BSE:STATus:NR5G:CELL1?" for q in sess.queried), sess.queried

    @pytest.mark.asyncio
    async def test_attach_switch_echo_shape_never_judged(self):
        """若状态口被误接回开关回读 ("1"), 白名单拒判 — 超时如实失败,
        绝不把 "1" 当 attach 成功 (R1 的原始灾难形态)。"""
        d, sess = _mk_irat_driver({
            "*OPC?": "1",
            "BSE:STATus:NR5G:CELL1?": "1",   # 枚举外 — 白名单必须拒
            "ACTive:STATe?": "1",
        })
        ok = await d.start_signaling(timeout_s=4)
        assert ok is False
        assert d._cell_state != CellState.CONNECTED

    @pytest.mark.asyncio
    async def test_attach_timeout_keeps_idle_status_visible(self):
        """真没连上 (状态一直 IDLE): 超时失败, 状态缓存如实反映 IDLE。"""
        d, _ = _mk_irat_driver({
            "*OPC?": "1",
            "BSE:STATus:NR5G:CELL1?": "IDLE",
            "ACTive:STATe?": "1",
        })
        ok = await d.start_signaling(timeout_s=4)
        assert ok is False
        assert d._cell_state == CellState.IDLE

    @pytest.mark.asyncio
    async def test_activation_write_does_not_cache_on(self):
        """D1 去缓存断言: 激活命令发出 ≠ 状态是 ON。状态读不出 (枚举外)
        时缓存必须保持原值, 不许被"我发了命令"改写。"""
        d, _ = _mk_irat_driver({
            "*OPC?": "1",
            "BSE:STATus:NR5G:CELL1?": "GARBAGE",
            "ACTive:STATe?": "1",
        })
        await d.start_signaling(timeout_s=2)
        # agent 门 F1 连带: 只禁"置活跃态" (ON/CONNECTED = 假状态), 不禁
        # "如实置 ERROR" — 别把危险侧钉成契约。安全兜底已换源: disconnect/
        # load_state_file 现在无条件发 stop, 不再依赖这个缓存当门。
        assert d._cell_state not in (CellState.ON, CellState.CONNECTED), (
            "零次成功解析却置了活跃态 — 缓存断言回潮 (P0-2 D1)"
        )

    @pytest.mark.asyncio
    async def test_5gnr_dialect_falls_back_to_legacy_text_query(self):
        """5G_NR_Test 无 CELL_STATUS_QUERY (手册查不到, 留 None) — 轮询
        fallback 旧文本查询 (旧注释宣称回 CONN 文本 — 出处不可考待现场核,
        fake 按该宣称造, 若现场证伪连测试一起改)。"""
        d = RealUxmDriver("uxm-5g", {"ip": "10.0.0.1"})  # 默认 5G_NR_Test
        sess = _FakeUxmSession({
            "*OPC?": "1",
            "ACTive:STATe?": "CONN",   # 旧注释宣称的文本形态 (待现场核)
        })
        d._visa_session = sess
        ok = await d.start_signaling(timeout_s=4)
        assert ok is True
        # fallback 用的是旧查询 (裸 CONFig 前缀, 无 BSE:)
        assert any("ACTive:STATe?" in q for q in sess.queried)
        assert not any(q.startswith("BSE:STATus") for q in sess.queried)


# ─────────────────────────────────────────────────────────────────────
# D1 get_cell_state 白名单
# ─────────────────────────────────────────────────────────────────────

class TestGetCellState:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw,expected", [
        ("OFF", CellState.OFF),
        ("CONNected", CellState.CONNECTED),   # 手册长形 + 混合大小写
        ('"IDLE"', CellState.IDLE),           # 带引号形态
        ("ON", CellState.IDLE),               # 小区起了无 UE
        ("AGGRegated", CellState.CONNECTED),
        # agent 门 F5: ATT/ACT 族此前零用例 (删 token 全绿), 长短双形补齐
        ("ATT", CellState.CONNECTED),
        ("ATTACHED", CellState.CONNECTED),
        ("ACT", CellState.CONNECTED),
        ("ACTivated", CellState.CONNECTED),
    ])
    async def test_manual_enum_mapping(self, raw, expected):
        d, _ = _mk_irat_driver({"BSE:STATus:NR5G:CELL1?": raw})
        assert await d.get_cell_state() == expected

    @pytest.mark.asyncio
    async def test_out_of_enum_reports_error_not_guess(self):
        """"0"/"1" (开关回声形态) 或任意垃圾 → ERROR, 不猜 (R2 ② 的正修:
        旧代码把 "0"/"1" 全落 ERROR 是碰巧, 现在是显式白名单契约)。"""
        d, _ = _mk_irat_driver({"BSE:STATus:NR5G:CELL1?": "1"})
        assert await d.get_cell_state() == CellState.ERROR


# ─────────────────────────────────────────────────────────────────────
# D2 APPLY 契约
# ─────────────────────────────────────────────────────────────────────

_APPLY = "BSE:CONFig:NR5G:APPLY"


def _echo_session_for_config(
    active_state: str,
    status_reply: str = "ON",
    syst_err: str = "0,No error",
    status_sequence: Optional[List[str]] = None,
) -> _FakeUxmSession:
    """set_cell_config 用的回显 fake: 回读=最近写入值 (P1-19 对账语义),
    ACTive 开关与 STATus 协议栈状态各自可参数化 — 两者独立正是 R2 的实况
    (开关是回声, 状态是真话)。status_sequence 给"过渡态"场景: 逐次弹出,
    弹尽后停在最后一个 (真机重启期先 OFF 后 ON 的形态)。"""
    sess = _FakeUxmSession({})
    written = sess.written
    seq = list(status_sequence) if status_sequence else None

    def _query(cmd: str) -> str:
        c = cmd.strip()
        sess.queried.append(c)
        if c == "*OPC?":
            return "1"
        # UXM 生产代码必须走 Test App profile 的 ERR 命令；fake 按查询语义
        # 匹配，不把旧硬编码短写 SYST:ERR? 教成唯一合法拼法（P1-41）。
        if "ERR" in c.upper():
            return syst_err
        if c.endswith("ACTive:STATe?"):
            return active_state
        if c.startswith("BSE:STATus:NR5G"):
            if seq is not None:
                return seq.pop(0) if len(seq) > 1 else seq[0]
            return status_reply
        base = c.rstrip("?")
        for w in reversed(written):
            if w.startswith(base + " "):
                return w[len(base) + 1:]
        return "0"

    sess.query = _query  # type: ignore[method-assign]
    return sess


class TestApplyContract:
    @pytest.mark.asyncio
    async def test_apply_sent_once_when_cell_on(self):
        """ON 态直写批次收尾必须恰好一次 APPLY (删 D2 块 → 红)。"""
        d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
        d._visa_session = _echo_session_for_config(active_state="1")
        ok = await d.set_cell_config({"dl_power_dbm": -46.0})
        assert ok is True
        applies = [w for w in d._visa_session.written if w == _APPLY]
        assert len(applies) == 1, d._visa_session.written

    @pytest.mark.asyncio
    async def test_apply_not_sent_when_cell_off(self):
        """OFF 态写配置不发 APPLY (手册: 开小区时自动应用)。"""
        d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
        d._visa_session = _echo_session_for_config(active_state="0")
        ok = await d.set_cell_config({"dl_power_dbm": -46.0})
        assert ok is True
        assert _APPLY not in d._visa_session.written

    @pytest.mark.asyncio
    async def test_apply_with_stack_off_fails_loud(self):
        """#236 Codex P1: 开关 ON 但 APPLY 后协议栈 STATus=OFF — 现场 07-21
        的原始故障形态 ("ACTive=1 但 STATus 持续 OFF") — 必须 return False,
        不许靠缓存回读判绿 (改回只记日志 → 本测试红)。"""
        d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
        d._visa_session = _echo_session_for_config(
            active_state="1", status_reply="OFF")
        ok = await d.set_cell_config({"dl_power_dbm": -46.0})
        assert ok is False, "协议栈 OFF 却报成功 — 二层生效核对没接闸"
        assert _APPLY in d._visa_session.written  # APPLY 发了, 是生效被拒

    @pytest.mark.asyncio
    async def test_apply_with_unreadable_status_fails_loud(self):
        """APPLY 后状态读不出 (空/枚举外) → 同样失败 — 通用契约: 读不到
        如实报, 不当成一致。"""
        d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
        d._visa_session = _echo_session_for_config(
            active_state="1", status_reply="")
        ok = await d.set_cell_config({"dl_power_dbm": -46.0})
        assert ok is False

    @pytest.mark.asyncio
    async def test_apply_rejected_via_error_queue_fails(self):
        """#236 R2 P1a: APPLY 被拒时 write 照常返回、错误只进 SYST:ERR? —
        旧栈跑旧配置 (状态非 OFF) + 回读回显缓存新值, 双检查全过。错误队列
        检查必须把它拦下 (删该检查 → 本测试红)。"""
        d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
        d._visa_session = _echo_session_for_config(
            active_state="1", status_reply="ON",
            syst_err="-200,Execution error")
        ok = await d.set_cell_config({"dl_power_dbm": -46.0})
        assert ok is False, "APPLY 进错误队列却报成功 — F64R-4 同母题假成功"

    @pytest.mark.asyncio
    async def test_apply_transitional_off_recovers_within_window(self):
        """#236 R2 P1b: APPLY 重配活动小区会异步重启 (实证 10s+ 量级),
        过渡期 STATus 合法地停 OFF — 窗口必须等它回来, 不许 1 次重试就
        误判失败 (窗口砍短 → 本测试红)。"""
        d = RealUxmDriver("uxm-irat", {"ip": "10.0.0.2", "uxm_profile": "irat"})
        d._visa_session = _echo_session_for_config(
            active_state="1",
            status_sequence=["OFF", "OFF", "OFF", "OFF", "ON"])
        ok = await d.set_cell_config({"dl_power_dbm": -46.0})
        assert ok is True, "重启过渡态被误判成配置失败 — 窗口太短"


# ─────────────────────────────────────────────────────────────────────
# D5 HAL-init 假绿 (service 级)
# ─────────────────────────────────────────────────────────────────────

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import (
    InstrumentCategory as InstrumentCategoryModel,
    InstrumentModel,
)
from app.services.instrument_hal_service import DriverMode, InstrumentHALService

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


class TestHalInitApplyFailureWarnRow:
    @pytest.fixture(autouse=True)
    def _db(self, monkeypatch):
        Base.metadata.create_all(bind=_engine)
        import app.db.database as dbmod
        monkeypatch.setattr(dbmod, "SessionLocal", _Session)
        yield
        Base.metadata.drop_all(bind=_engine)

    @pytest.mark.asyncio
    async def test_hal_init_apply_failure_row_is_warn_not_ok(self, monkeypatch):
        """默认配置下发失败 → 就绪行必须 warn 且 detail 说明 (改回恒 "ok" → 红)。

        mock 驱动本无 apply_topology_profile — 注入一个返回 applied=False 的,
        复刻现场 07-21 "apply 失败但面板全绿" 的形态 (R6)。topology id 用
        in-code registry 里的真 id (DB 无行时 service 会 fallback 到它)。"""
        from app.hal.base_station import MockBaseStation
        from app.hal.uxm_test_profiles import (
            _PROFILE_REGISTRY, _register_builtin_profiles,
        )
        if not _PROFILE_REGISTRY:
            _register_builtin_profiles()
        topo_id = next(iter(_PROFILE_REGISTRY))

        async def _fail_apply(self, profile_dc):
            return {"applied": False, "reason": "注入: 复刻现场 apply 失败"}

        monkeypatch.setattr(
            MockBaseStation, "apply_topology_profile", _fail_apply,
            raising=False,
        )
        monkeypatch.setattr(
            MockBaseStation, "_default_topology_profile_id", topo_id,
            raising=False,
        )

        self._seed_base_station_category()

        svc = InstrumentHALService(mode=DriverMode.MOCK)
        await svc._initialize_from_db()

        report = svc.last_readiness_report
        assert report is not None, "init 后无就绪报告"
        rows = [r for r in report.drivers if r.category == "baseStation"]
        assert rows, "就绪报告里没有 baseStation 行 — fixture 没走到成功分支"
        row = rows[0]
        assert row.status == "warn", (
            f"apply 失败但就绪行是 {row.status!r} — P0-2 D5 假绿回潮"
        )
        assert "未应用" in row.detail or "下发" in row.detail

    @pytest.mark.asyncio
    async def test_header_tally_counts_warn_as_loaded(self, monkeypatch, caplog):
        """agent 门 F6: 头行计数必须认 warn — 改回只数 "ok" 会报
        "0/1 categories loaded" 跟表格 warn 行自相矛盾。"""
        import logging as _logging
        from app.hal.base_station import MockBaseStation
        from app.hal.uxm_test_profiles import (
            _PROFILE_REGISTRY, _register_builtin_profiles,
        )
        if not _PROFILE_REGISTRY:
            _register_builtin_profiles()
        topo_id = next(iter(_PROFILE_REGISTRY))

        async def _fail_apply(self, profile_dc):
            return {"applied": False, "reason": "注入"}

        monkeypatch.setattr(
            MockBaseStation, "apply_topology_profile", _fail_apply, raising=False)
        monkeypatch.setattr(
            MockBaseStation, "_default_topology_profile_id", topo_id, raising=False)
        self._seed_base_station_category()

        # 防 alembic fileConfig 污染 (memory: 断言 logger emit 前复位 .disabled)
        _logging.getLogger(
            "app.services.instrument_hal_service").disabled = False
        with caplog.at_level(_logging.INFO,
                             logger="app.services.instrument_hal_service"):
            svc = InstrumentHALService(mode=DriverMode.MOCK)
            await svc._initialize_from_db()
        tally = [r.getMessage() for r in caplog.records
                 if "categories loaded" in r.getMessage()]
        assert tally, "没找到头行计数日志"
        assert "1/1 categories loaded" in tally[-1], tally[-1]
        assert "warn(配置未落)" in tally[-1], tally[-1]

    @pytest.mark.asyncio
    async def test_stale_topology_selection_row_is_warn(self, monkeypatch):
        """agent 门 F6: 操作员选的 topology 已不存在 (DB 与 in-code registry
        都查不到) → 就绪行 warn + detail 说明"已失效"。"""
        from app.hal.base_station import MockBaseStation

        async def _apply(self, profile_dc):
            return {"applied": True}

        monkeypatch.setattr(
            MockBaseStation, "apply_topology_profile", _apply, raising=False)
        monkeypatch.setattr(
            MockBaseStation, "_default_topology_profile_id",
            "__p02_does_not_exist__", raising=False)
        self._seed_base_station_category()

        svc = InstrumentHALService(mode=DriverMode.MOCK)
        await svc._initialize_from_db()
        rows = [r for r in svc.last_readiness_report.drivers
                if r.category == "baseStation"]
        assert rows and rows[0].status == "warn", rows
        assert "已失效" in rows[0].detail

    def _seed_base_station_category(self) -> None:
        db = _Session()
        try:
            cat = InstrumentCategoryModel(
                id=uuid.uuid4(),
                category_key="baseStation",
                category_name="Base Station",
                is_active=True,
                display_order=1,
            )
            db.add(cat)
            db.flush()
            model = InstrumentModel(
                id=uuid.uuid4(),
                category_id=cat.id,
                vendor="Keysight",
                model="E7515B",
                capabilities={},
            )
            db.add(model)
            db.flush()
            cat.selected_model_id = model.id
            db.commit()
        finally:
            db.close()
