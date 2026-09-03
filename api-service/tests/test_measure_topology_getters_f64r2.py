"""F64R-2: 编排层读驱动拓扑的防御性 helper 单测。

`measure.py` 用鸭子类型从 CE 驱动读端口信息 (`getattr` 探能力 → 调 getter)。返回值直接
拿去**给硬件寻址**, 所以"拿到的不是个正经端口号"必须一律降级成"未知"让上层 fail-loud,
而不是崩、也不是拿它去配口。本文件逐个钉这些边缘形态。

三个 helper 的分工:
  · `_call_topology_getter` — 调用 + 三种"拿不到"的区分 (无此方法 / 抛异常 / **返回
    coroutine**)。coroutine 单独识别是因为它意味着**代码问题**(getter 被改成 async),
    不该被报成"仪器读不到"去误导排障。
  · `_read_port_count` — 只认正整数 (口数), 用于 sanity bound。
  · `_read_port_list`  — 只认全正整数的非空列表 (口号), 用于逐口下发。
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.mimo_ota.executors.measure import (
    _call_topology_getter,
    _read_port_count,
    _read_port_list,
)
from app.hal.channel_emulator_manifest import channel_emulator_manifest_for


class _Bare:
    """没有任何拓扑 getter 的驱动 (mock CE / 非 F64)。"""

    # P2-57：不声明任何能力 —— fail-closed 下等价于「都不支持」
    adapter_manifest = channel_emulator_manifest_for(
        adapter_id="bare", model_name="Bare", vendor="test", implemented=(),
    )


def _emu(**getters):
    emu = MagicMock()
    # P2-57：`MagicMock()` 上的能力查询是 fail-closed 的，**无需额外置空**。
    # ⚠️ 原因不是「类上没有 adapter_manifest」（内审 R2 F8 指出那句话是错的，
    #    这版注释按实况重写）：Mock 会**自动生成**任意属性，
    #    `getattr(mock, "adapter_manifest")` 返回的是一个真值 Mock。
    #    真正兜住它的是 `channel_emulator_manifest_of` 判的
    #    `isinstance(..., ChannelEmulatorManifest)` —— 不是 manifest 一律当没有。
    # ⚠️ 复用本替身去测「需要 CE 能力」的路径时，必须显式给
    #    `adapter_manifest = channel_emulator_manifest_for(...)`，否则那条路径会被
    #    判成「不支持」而静默跳过（不报错），断言会打在一个根本没执行的分支上。
    for name, val in getters.items():
        setattr(emu, name, val)
    return emu


# ───────────── _read_port_count ─────────────

class TestReadPortCount:
    def test_missing_getter_is_unknown(self):
        assert _read_port_count(_Bare(), "get_active_input_count") is None

    def test_getter_raising_is_unknown(self):
        emu = _emu(get_active_input_count=MagicMock(side_effect=RuntimeError("boom")))
        assert _read_port_count(emu, "get_active_input_count") is None

    @pytest.mark.parametrize("bad", [None, 0, -1, True, False, "4", 4.5, [4], {}])
    def test_non_positive_int_is_unknown(self, bad):
        """bool 是 int 的子类 —— True 被当成"1 个口"是荒谬的, 显式排除。"""
        emu = _emu(get_active_input_count=MagicMock(return_value=bad))
        assert _read_port_count(emu, "get_active_input_count") is None

    def test_positive_int_passes(self):
        emu = _emu(get_active_input_count=MagicMock(return_value=4))
        assert _read_port_count(emu, "get_active_input_count") == 4


# ───────────── _read_port_list ─────────────

class TestReadPortList:
    def test_missing_getter_is_unknown(self):
        assert _read_port_list(_Bare(), "get_active_output_ports") is None

    @pytest.mark.parametrize("bad", [
        None, [], (), 32, "1,2", [0], [-1], [1, 0], [1, "2"], [1, 2.5], [True], [1, None],
    ])
    def test_malformed_list_is_unknown(self, bad):
        """任一元素不是正整数 → **整体**判未知, 不返回半个列表 ——
        拿残缺端口号配硬件比不配更危险 (会配到别的口上)。"""
        emu = _emu(get_active_output_ports=MagicMock(return_value=bad))
        assert _read_port_list(emu, "get_active_output_ports") is None

    def test_non_contiguous_ports_pass_through(self):
        """★ 非连续端口号必须原样透传 —— 这正是"只回读口数然后 range(1,N+1)"
        推不出来、会配错的形态。"""
        emu = _emu(get_active_output_ports=MagicMock(return_value=[2, 4]))
        assert _read_port_list(emu, "get_active_output_ports") == [2, 4]

    def test_tuple_accepted(self):
        emu = _emu(get_active_output_ports=MagicMock(return_value=(1, 2, 3)))
        assert _read_port_list(emu, "get_active_output_ports") == [1, 2, 3]


# ───────────── coroutine: 代码问题 ≠ 仪器故障 ─────────────

class TestAsyncGetterDiagnosis:
    def test_coroutine_return_is_unknown_and_logged_as_code_problem(self, caplog):
        """getter 被改成 async (或测试替身用 AsyncMock) → 返回 coroutine。

        必须 ① 判"未知"不崩、② 日志**点名是代码问题** —— 否则这次纯代码重构会被下游
        报成"仿真未加载 / MODEL:INFO? 回读失败", 把改代码诬告成仪器故障, 现场按错误
        方向排查仪表。"""
        emu = _emu(get_active_output_ports=AsyncMock(return_value=[1, 2]))
        # ⚠ 全量顺序跑时, in-process alembic 的 fileConfig(disable_existing_loggers=True)
        # 会把已导入的 logger 永久 .disabled —— 单跑绿、全量红的经典 flaky。断言 emit
        # 前必须复位 (memory: test_logger_emit_alembic_pollution)。
        _lg = logging.getLogger("app.services.mimo_ota.executors.measure")
        _lg.disabled = False
        _lg.propagate = True
        with caplog.at_level(logging.ERROR, logger=_lg.name):
            assert _read_port_list(emu, "get_active_output_ports") is None
        assert any("coroutine" in r.message or "coroutine" in r.getMessage()
                   for r in caplog.records), caplog.text
        assert any("不是仪器故障" in r.getMessage() for r in caplog.records)

    def test_coroutine_is_closed_no_never_awaited_warning(self, recwarn):
        """顺带 close() 掉那个 coroutine, 不留 never-awaited 警告污染测试输出。"""
        emu = _emu(get_active_input_count=AsyncMock(return_value=4))
        assert _read_port_count(emu, "get_active_input_count") is None
        assert not [w for w in recwarn if "never awaited" in str(w.message)]

    def test_call_topology_getter_returns_raw_value(self):
        """底层 helper 不做类型判断, 原样返回 —— 类型策略归两个上层 helper。"""
        emu = _emu(get_active_output_ports=MagicMock(return_value="whatever"))
        assert _call_topology_getter(emu, "get_active_output_ports") == "whatever"


# ───────────── 编排层两个 fail-loud / ensure 分支 (复审变异实证曾零覆盖) ─────────────

class TestOrchestrationTopologyBranches:
    """`_apply_output_gain` 与 `_apply_manual_input_reference` 里跟拓扑相关的分支。

    这些分支之前**一条用例都没钉住** —— 复审用变异证明: 删掉 ensure 调用、把 crest
    的 fail-loud 改成 `if False`, 全套测试照样绿 (fake 里根本没有 `ensure_topology`
    属性, 那段代码从不进入)。防御性代码最容易这样空转。
    """

    @staticmethod
    def _executor():
        from app.services.mimo_ota.executors.measure import MeasureExecutor
        return MeasureExecutor()

    async def test_output_gain_ensures_topology_before_reading_ports(self):
        """★ 冷缓存 → 先 await ensure_topology() 再读口号 (删掉那几行会红)。"""
        order: list = []
        emu = MagicMock()
        cold = {"v": True}

        async def _ensure():
            order.append("ensure")
            cold["v"] = False
            return True

        async def _gain(port, db):
            order.append(f"gain{port}")
            return True

        emu.ensure_topology = _ensure
        emu.get_active_output_ports = lambda: None if cold["v"] else [2, 4]
        emu.set_output_gain = _gain
        err = await self._executor()._apply_output_gain(
            emulator=emu, gain_db=-3.0, execution_id="t")
        assert err is None, err
        assert order == ["ensure", "gain2", "gain4"], "没先补读就读口号 → 冷缓存下会误拒"

    async def test_output_gain_fails_loud_when_topology_unknown_after_ensure(self):
        """补读了也读不到 → 拒发, 且一条 SCPI 都不发。"""
        emu = MagicMock()
        emu.ensure_topology = AsyncMock(return_value=False)
        emu.get_active_output_ports = lambda: None
        emu.set_output_gain = AsyncMock(return_value=True)
        err = await self._executor()._apply_output_gain(
            emulator=emu, gain_db=-3.0, execution_id="t")
        assert err and "物理输出口未知" in err
        emu.set_output_gain.assert_not_awaited()

    async def test_manual_ref_refuses_crest_when_input_ports_unknown(self):
        """★ crest 要下发却不知道发给谁 → fail-loud, **不静默零下发报成功**。

        旧代码用 `_tx_antennas`(实例默认 2, 永不为 0) 一定会发几条; 换成回读后才可能
        "一条都没发", 此时若仍 success=True 就是本项目一直在抓的零下发假成功。"""
        emu = MagicMock()
        # P2-57：能力由 manifest 回答 —— 本替身要走到「crest 下发拒绝」那一格，
        # 必须先声明它**实现了** set_baseband_power（否则在能力门就被挡掉，
        # 测不到本用例真正要守的零下发假成功）。
        type(emu).adapter_manifest = channel_emulator_manifest_for(
            adapter_id="crest_emu", model_name="Crest Emu", vendor="test",
            implemented=("set_baseband_power",),
        )
        emu.set_baseband_power = AsyncMock(return_value=True)
        emu.set_crest_factor = AsyncMock(return_value=True)
        emu.get_active_input_ports = lambda: None          # 口号未知
        cfg = MagicMock(f64_input_ref_dbm=-15.0, f64_crest_db=12.0)
        payload = await self._executor()._apply_manual_input_reference(
            emulator=emu, config=cfg, execution_id="t")
        assert payload["success"] is False
        assert "crest 下发拒绝" in (payload["failure_reason"] or "")
        emu.set_crest_factor.assert_not_awaited()
