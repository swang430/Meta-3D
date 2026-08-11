"""attach 里程碑的判据 —— 内审 F6：这批的头号修复此前零覆盖。

2026-08-07 现场：`_probe_ue_attached` 拿 `query_ue_capability()` 判 DUT 挂没挂上，
而那查的是**能力**（支持几层、什么调制）不是**状态**（现在连上了没有）；IRAT 方言
上那几条命令全是 `None`，恒返回 `source="unavailable"` → 里程碑恒判 False →
相位必然 FAILED。换源到 `get_cell_state()`（`start_signaling()` 已经在用、当天
双向验证过：17:38:29 读到 `CONN` 判成功、17:42:29 一直读 `'ON'` 判超时）。

内审造的变异「判据放宽成 `!= OFF`」在 70 个用例下全绿 —— 换源本身没有任何门。
本文件补上。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

from app.hal.base_station import CellState


def _probe_factory(driver, is_mock: bool):
    """复刻 measure.py 的 `_probe_ue_attached` 判定，用于隔离测试。

    ⚠ 这是**镜像**不是被测体 —— 单靠它会变成"测我自己写的副本"。
    下面 `test_measure_uses_the_same_judgement` 用源码结构断言把它跟真实现
    钉在一起：真实现改了判据而这里没跟，那条门会红。
    """
    async def _probe(stage: str) -> Dict[str, Any]:
        if is_mock:
            return {"stage": stage, "attached": None, "simulated": True,
                    "reason": "BS 是 mock 驱动 — 未测（mock 的小区状态是编的）"}
        if not hasattr(driver, "get_cell_state"):
            return {"stage": stage, "attached": None,
                    "reason": "BS 驱动无 get_cell_state — 未测"}
        try:
            state = await driver.get_cell_state()
        except Exception as e:  # noqa: BLE001
            return {"stage": stage, "attached": False,
                    "reason": f"小区状态查询抛异常: {type(e).__name__}: {e}"}
        raw = getattr(state, "value", state)
        if state == CellState.CONNECTED:
            return {"stage": stage, "attached": True, "reason": "ok",
                    "cell_state": raw}
        return {"stage": stage, "attached": False,
                "reason": f"小区状态 {raw!r} ≠ CONN — DUT 未 attach",
                "cell_state": raw}
    return _probe


class _FakeBS:
    def __init__(self, state: Optional[CellState] = None, raises: bool = False):
        self._state, self._raises = state, raises

    async def get_cell_state(self) -> CellState:
        if self._raises:
            raise RuntimeError("VI_ERROR_TMO")
        return self._state


class TestAttachJudgement:
    """⭐ 行为门：只有 `CONNected` 算挂上。"""

    @pytest.mark.parametrize("state,expected,why", [
        (CellState.CONNECTED, True, "手册枚举里 CONNected 才是 UE 已连接"),
        (CellState.ON, False,
         "⭐ ON = 小区开着但没 UE —— 2026-08-07 后两轮 60 秒超时读到的就是它。"
         "判据放宽成 `!= OFF` 会把这一格判成 attach 成功"),
        (CellState.IDLE, False, "IDLE = 等待接入，不是已接入"),
        (CellState.OFF, False, "小区都没开"),
        (CellState.ERROR, False, "读不到 ≠ 挂上了"),
    ], ids=["CONN", "ON", "IDLE", "OFF", "ERROR"])
    def test_only_connected_counts_as_attached(self, state, expected, why):
        probe = _probe_factory(_FakeBS(state), is_mock=False)
        assert asyncio.run(probe("bypass"))["attached"] is expected, why

    def test_query_exception_is_not_attached(self):
        """查询抛异常 = 读不到，**不能**当成挂上了。"""
        probe = _probe_factory(_FakeBS(raises=True), is_mock=False)
        r = asyncio.run(probe("fading"))
        assert r["attached"] is False
        assert "VI_ERROR_TMO" in r["reason"], "异常细节被吞了，现场没法排查"

    def test_mock_driver_never_produces_a_green_milestone(self):
        """⭐ 内审 F6 的另一半：mock 下**不许**报 attached=True。

        `hasattr(bs, "get_cell_state")` 恒为真（抽象基类与 MockBaseStation 都有
        定义），而 mock 的 `start_signaling()` 直接把 `_cell_state = CONNECTED`
        —— 旧判据会让 mock 跑出绿色里程碑并一路写进报告。
        """
        probe = _probe_factory(_FakeBS(CellState.CONNECTED), is_mock=True)
        r = asyncio.run(probe("bypass"))
        assert r["attached"] is None, (
            "mock 驱动报出了 attached=True —— 编的状态会进 result_payload 和报告"
        )
        assert r.get("simulated") is True, "mock 那格没标 simulated"


class TestMeasureUsesTheSameJudgement:
    """⭐ 把上面的镜像钉在真实现上 —— 否则改了 measure.py 这些门照样绿。"""

    def _body(self) -> str:
        """取 `_probe_ue_attached` 的函数体。

        ⚠ **不用"往后数 N 个字符"** —— 那依赖 docstring 长度这个偶然事实，
        改几行注释就红（本门第一版就是这么红的，而内审刚好也批评过同一形态）。
        改成锚在两个稳定的代码位置之间：函数定义 → 它下面第一个消费里程碑的
        `if config.f64_bypass_mode`。
        """
        import inspect
        from app.services.mimo_ota.executors import measure

        src = inspect.getsource(measure)
        start = src.index("async def _probe_ue_attached")
        end = src.index(
            "if config.f64_bypass_mode is not None and config.f64_fade_after_attach",
            start,
        )
        assert end > start, "锚点顺序变了，门需要重新定位"
        return src[start:end]

    def test_probe_judges_on_cell_state_not_ue_capability(self):
        """变异：把判据换回 `query_ue_capability` → 本条红。"""
        body = self._body()
        assert "get_cell_state" in body, (
            "attach 判据不再走 get_cell_state —— 2026-08-07 实证 "
            "query_ue_capability 在 IRAT 上恒 unavailable，会让里程碑恒 False"
        )
        assert "CellState.CONNECTED" in body, "判据没钉在 CONNected 上"
        # ⚠ 判"有没有真的调它"，不判"字面出现过" —— 本函数的 docstring 里
        #   写着"上一版用的是 query_ue_capability"，裸词判据会被自己的注释
        #   喂成假红（本门第二版就这么红的；G17 那条也栽在同一形态）。
        assert "base_station.query_ue_capability" not in body, (
            "又调回了 UE 能力查询 —— 那查的是'支持几层'不是'连上没有'"
        )
        assert "await base_station.get_cell_state()" in body, (
            "没有真的调用 get_cell_state —— 只在注释里提到不算"
        )

    def test_mock_is_judged_by_driver_identity_not_hasattr(self):
        """变异：把 `is_mock_driver(base_station)` 换回纯 `hasattr` 判断 → 本条红。"""
        body = self._body()
        assert "is_mock_driver(base_station)" in body, (
            "mock 判定又回到 hasattr —— 那个恒为真（基类和 MockBaseStation 都有 "
            "get_cell_state），mock 会跑出绿色里程碑"
        )
        # 顺序也要对：mock 判定必须在 hasattr 之前，否则永远走不到
        assert body.index("is_mock_driver(base_station)") < body.index(
            'hasattr(base_station, "get_cell_state")'
        ), "mock 判定排在 hasattr 之后 —— hasattr 恒真，前面就返回了"


class TestBypassAssistOrdering:
    """「扶一把」必须在 attach **之前**建立直通 —— 外审 #304 P1。

    上一版把直通建立放在 F64 段（`_probe_ue_attached` 之后 500 多行），而
    `start_signaling()` 等 attach 失败就直接 return —— 于是这个开关**只在
    DUT 已经自己挂上之后才生效**，救不了它宣称要救的场景。顺序反了，
    开关就是装饰。
    """

    def _src(self) -> str:
        import inspect
        from app.services.mimo_ota.executors import measure
        return inspect.getsource(measure)

    def test_bypass_is_established_before_the_first_attach_attempt(self):
        """⭐ 顺序不变量。变异：把 attach 前那段直通建立删掉/挪到
        `start_signaling()` 之后 → 本条红。"""
        src = self._src()

        assist = src.index("attach 前已置 F64 直通")
        signaling = src.index("signaling_started = await base_station.start_signaling()")

        assert assist < signaling, (
            "直通建立排在 start_signaling 之后 —— attach 失败会直接 return，"
            "这个开关只能在 DUT 已经自己挂上之后才生效，救不了它要救的场景"
        )

    def test_assist_failure_is_loud_not_silently_skipped(self):
        """开了开关却建不起直通时必须 fail-loud。

        静默跳过 = 在**没有直通**的情况下去 attach，然后把失败归给 DUT ——
        而真因是我们没把梯子搭上。

        变异：把那三处 `return StepExecutionResult(FAILED)` 改成 `pass` → 本条红。
        """
        src = self._src()
        head = src.index("attach 前已置 F64 直通")
        block = src[src.index("if config.f64_bypass_mode is not None:", 0, head):head]

        assert block.count("StepExecutionStatus.FAILED") >= 3, (
            "attach 前建立直通的三条失败路径（无 CE / stop_emulation 失败 / "
            "set_passthrough_mode 失败）没有全部 fail-loud"
        )
        assert "不静默降级" in block, "缺少'不静默降级'的显式声明"


class TestColdStartRfInitializationOrdering:
    """暗室首测必须由**本次 execution** 建好 F64 初始态再尝试 attach。

    2026-08-07 的旧顺序先执行 ``start_signaling``，DUT attach 成功后才加载
    ``.smu``。这会静默依赖 F64 上一轮残留的模型、中心频率和 STATIC 档位；
    冷启动或换场景时不可重复。
    """

    def _src(self) -> str:
        import inspect
        from app.services.mimo_ota.executors import measure
        return inspect.getsource(measure)

    def test_model_frequency_and_workpoint_are_ready_before_attach(self):
        """模型加载、频率门、输出与显式输入工作点均早于第一次 attach。"""
        src = self._src()
        signaling = src.index(
            "signaling_started = await base_station.start_signaling()"
        )

        required_before_attach = {
            "本次 F64 模型加载": "gen_ok = await generator.generate_and_load",
            "多方频率一致性": "freq_result = check_frequency_consistency",
            "F64 绝对输出电平": "await emulator.set_output_level_dbm",
            "F64 显式输入参考": "await self._apply_manual_input_reference",
        }
        for label, token in required_before_attach.items():
            assert src.index(token) < signaling, (
                f"{label} 仍在 start_signaling 之后 —— attach 会继续依赖仪表遗留状态"
            )

    def test_passthrough_is_built_after_model_load_and_before_attach(self):
        """加载 .smu 会清掉 STATIC；因此旁路只能在本次加载后建立一次。"""
        src = self._src()
        load = src.index("gen_ok = await generator.generate_and_load")
        signaling = src.index(
            "signaling_started = await base_station.start_signaling()"
        )
        between = src[load:signaling]

        assert "await emulator.set_passthrough_mode(" in between, (
            "本次模型加载后、attach 前没有建立 F64 旁路；冷启动仍不能 attach"
        )
        assert "await _assist_ce.set_passthrough_mode(" not in src[:load], (
            "仍在模型加载前写旁路 —— 随后的 .smu 加载会把它清掉，属于无效动作"
        )

    def test_channel_initialization_failures_return_before_attach(self):
        """模型/频率/工作点/旁路失败时，控制流必须在 attach 调用之前返回。"""
        src = self._src()
        load = src.index("gen_ok = await generator.generate_and_load")
        signaling = src.index(
            "signaling_started = await base_station.start_signaling()"
        )
        initialization = src[load:signaling]

        assert initialization.count("StepExecutionStatus.FAILED") >= 8, (
            "RF 初始化的 fail-loud 分支没有完整位于 start_signaling 之前"
        )


class TestManagedAttachDynamicGate:
    """标准吞吐量流程不能只在 PRECHECK 延后门，却不在初始化后补回来。"""

    def test_gate_requires_real_connected_readback(self):
        from app.services.mimo_ota.executors import measure

        gate = getattr(measure, "_managed_attach_failure", None)
        assert callable(gate), "缺少 MEASURE 内受控 attach 的动态门"
        assert gate(
            managed=True,
            strict=True,
            base_station_is_real=True,
            milestone={"attached": True, "reason": "ok"},
        ) is None
        failure = gate(
            managed=True,
            strict=True,
            base_station_is_real=True,
            milestone={"attached": False, "reason": "cell ON != CONN"},
        )
        assert failure and "cell ON != CONN" in failure

    def test_mock_and_explicit_opt_out_do_not_fake_a_failure(self):
        from app.services.mimo_ota.executors import measure

        gate = getattr(measure, "_managed_attach_failure", None)
        assert callable(gate), "缺少 MEASURE 内受控 attach 的动态门"
        unknown = {"attached": None, "simulated": True, "reason": "mock"}
        assert gate(
            managed=True, strict=True, base_station_is_real=False,
            milestone=unknown,
        ) is None
        assert gate(
            managed=True, strict=False, base_station_is_real=True,
            milestone={"attached": False, "reason": "not connected"},
        ) is None

    def test_final_attach_gate_runs_before_azimuth_sampling(self):
        import inspect
        from app.services.mimo_ota.executors import measure

        src = inspect.getsource(measure)
        gate = src.index("_managed_attach_failure(", src.index("class MeasureExecutor"))
        sampling = src.index("# --- Per-azimuth measurement loop", gate)
        assert gate < sampling

    def test_deferred_identity_and_capability_checks_run_after_attach(self):
        import inspect
        from app.services.mimo_ota.executors import measure

        src = inspect.getsource(measure)
        start = src.index("# --- 标准受控 attach 动态门")
        end = src.index("# --- P2-11 Phase 6", start)
        block = src[start:end]
        assert "query_ue_capability" in block
        assert "check_sim_identity" in block
        assert "precheck_strict_sim_identity" in block
        assert "check_dut_capability_mismatch" in block
        assert "不能拿" in block and "声明 IMSI" in block
        assert 'controlled_attach.pop("ue_info_snapshot", None)' in block, (
            "动态回读失败时仍保留初始化前的 UE 快照，会让旧能力值跟新的 "
            "verified_at 一起被误认成本轮证据"
        )
        assert '"checked_at": attach_checked_at' in block
        assert 'controlled_attach.pop("verified_at", None)' in block
        assert (
            'base_station_is_real and final_attach.get("attached") is True'
            in block
        ), "mock/失败的 attach 也写 verified_at，会制造已经验真的假证据"

    def test_commissioning_ui_does_not_require_preinitialized_attach(self):
        from pathlib import Path

        ui = (
            Path(__file__).parents[2]
            / "gui/src/components/Commissioning/index.tsx"
        ).read_text(encoding="utf-8")
        assert "DUT attach 登记（严格门必需）" not in ui
        assert "不登记则真仪表下 precheck 必 FAIL" not in ui
        assert "DUT 身份登记（可选）" in ui
        assert "正式连接由执行器在按 TestCase 初始化后确认" in ui
