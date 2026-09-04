# -*- coding: utf-8 -*-
"""P2-59 ①：ChannelEmulatorExecutionPlan —— 冻结、对账、消费。

门覆盖（每条配变异，见 PR 记录）：
  ① 纯计划：canonical payload / digest 稳定、14 操作恰好一次按序、拼错就炸、禁当 bool、
     engine_mode → 加载模式映射覆盖 EngineMode 全集；
  ② 启动期冻结：紧跟 binding（缺 binding 拒）、已存在只校验不重算、篡改 / 坏结构拒、
     已有进度的执行行拒绝回填、加载模式不被支持在启动期 fail-loud；
  ③ MEASURE 对账：缺席 / 漂移 / 坏冻结件 → RuntimeError，匹配 → 返回 live 计划；
  ④ 消费方：手动定标读的是计划不是驱动 manifest（交叉场景：manifest 说有、计划说无 → skipped）；
     结构档粗筛：measure.py 不再直接调 manifest 能力查询，两处写方按序接上。
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.channel_emulator_execution_plan import (
    CHANNEL_EMULATOR_PHASE_ORDER,
    ENGINE_MODE_TO_REQUESTED_LOAD_MODE,
    ChannelEmulatorExecutionPlan,
    ChannelEmulatorExecutionPlanItem,
    plan_from_frozen_payload,
    requested_channel_emulator_load_mode,
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import (
    CHANNEL_EMULATOR_OPERATIONS,
    ChannelEmulatorManifest,
)
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.propsim_fs16 import RealPropsimFs16Driver
from app.models.test_plan import TestCase, TestExecution
from app.schemas.mimo_ota.config import MIMOOTAConfiguration
from app.services.channel_emulator_binding import CE_FREEZE_CONFIG_KEY
from app.services.channel_emulator_execution_plan import (
    CE_PLAN_FREEZE_CONFIG_KEY,
    channel_emulator_for_execution_plan,
    freeze_channel_emulator_execution_plan,
    freeze_execution_channel_emulator_plan,
    resolve_live_channel_emulator_execution_plan,
    verify_frozen_channel_emulator_execution_plan,
)
from app.services.channel_generation.base_generator import EngineMode
from app.services.mimo_ota.executors.measure import MeasureExecutor

REPO_APP = Path(__file__).resolve().parents[1] / "app"
F64_MANIFEST = RealPropsimF64Driver.adapter_manifest
FS16_MANIFEST = RealPropsimFs16Driver.adapter_manifest
MOCK_MANIFEST = MockChannelEmulator.adapter_manifest
BINDING_DIGEST = "b" * 64


# ----------------------------------------------------------------------
# 脚手架
# ----------------------------------------------------------------------


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _hal(driver):
    return SimpleNamespace(drivers={} if driver is None else {"channelEmulator": driver})


def _f64():
    return RealPropsimF64Driver("ce", {"ip_address": "192.0.2.10"})


def _configuration(engine_mode: str = "keysight_gcm"):
    return MIMOOTAConfiguration(engine_mode=engine_mode).model_dump(mode="json")


def _execution(
    db,
    *,
    engine_mode: str = "keysight_gcm",
    with_binding: bool = True,
    bind_case: bool = True,
    configuration=None,
    **config,
):
    """执行行 + 它绑的 TestCase 行（冻结从 `load_mimo_ota_config(execution)` 取配置，与 MEASURE 同源）。"""

    if with_binding:
        config = {CE_FREEZE_CONFIG_KEY: {"binding_digest": BINDING_DIGEST}, **config}
    test_case_id = None
    if bind_case:
        case = TestCase(
            name=f"p2-59-{uuid4().hex[:8]}",
            test_type="MIMO_OTA",
            configuration=_configuration(engine_mode) if configuration is None else configuration,
            created_by="pytest",
        )
        db.add(case)
        db.commit()
        test_case_id = case.id
    execution = TestExecution(status="pending", config=dict(config), test_case_id=test_case_id)
    db.add(execution)
    db.commit()
    return execution


def _plan(manifest=F64_MANIFEST, load_mode="native_model", source="hal"):
    return resolve_channel_emulator_execution_plan(
        manifest=manifest,
        driver_source=source,
        requested_load_mode=load_mode,
        binding_digest=BINDING_DIGEST,
    )


def _frozen(plan):
    return {**plan.as_payload(), "digest": plan.digest}


# ----------------------------------------------------------------------
# ① 纯计划
# ----------------------------------------------------------------------


def test_plan_payload_is_canonical_regardless_of_manifest_operation_order():
    reordered = ChannelEmulatorManifest(
        **{**F64_MANIFEST.model_dump(), "operations": tuple(reversed(F64_MANIFEST.operations))}
    )
    a, b = _plan(F64_MANIFEST), _plan(reordered)

    assert tuple(item.operation for item in a.operations) == CHANNEL_EMULATOR_OPERATIONS
    assert a.as_payload() == b.as_payload()
    assert a.digest == b.digest
    assert len(a.digest) == 64
    # payload 是 JSON 安全的、且 digest 对不含 digest 的 payload 计算
    assert "digest" not in a.as_payload()
    assert plan_from_frozen_payload(_frozen(a)).digest == a.digest


def test_plan_covers_every_operation_exactly_once_in_canonical_order_and_rejects_foreign_ops():
    plan = _plan()
    with pytest.raises(ValueError, match="unknown channel emulator operation"):
        plan.item("stop_emulaton")
    with pytest.raises(ValueError, match="not a known channel emulator operation"):
        ChannelEmulatorExecutionPlanItem(
            operation="stop_emulaton", planned=True, capability_source="x", reason="y"
        )
    # 少一项 / 顺序不对都拒
    with pytest.raises(ValueError, match="exactly once"):
        ChannelEmulatorExecutionPlan(
            **{**plan.__dict__, "operations": plan.operations[1:]}
        )
    with pytest.raises(ValueError, match="exactly once"):
        ChannelEmulatorExecutionPlan(
            **{**plan.__dict__, "operations": tuple(reversed(plan.operations))}
        )
    with pytest.raises(ValueError, match="phase_order"):
        ChannelEmulatorExecutionPlan(
            **{**plan.__dict__, "phase_order": tuple(reversed(CHANNEL_EMULATOR_PHASE_ORDER))}
        )
    for obj in (plan, plan.item("stop_emulation")):
        with pytest.raises(TypeError, match="must not be used as bool"):
            bool(obj)


def test_plan_planned_and_rejection_follow_manifest_declarations():
    f64, fs16 = _plan(F64_MANIFEST), _plan(FS16_MANIFEST)

    assert f64.planned("set_passthrough_mode") is True
    assert f64.item("set_passthrough_mode").capability_source == (
        "manifest.operations:set_passthrough_mode"
    )
    assert fs16.planned("set_passthrough_mode") is False
    rejection = fs16.rejection("set_passthrough_mode")
    assert rejection.startswith("propsim_fs16 的执行计划未包含 set_passthrough_mode：")
    assert fs16.item("set_passthrough_mode").reason in rejection
    # 与 channel_emulator_implements 同一条规矩：拼错就炸，不当「不支持」
    with pytest.raises(ValueError):
        f64.planned("set_passthrough_mod")


def test_engine_mode_table_covers_every_engine_mode_with_the_strategy_load_modes():
    assert set(ENGINE_MODE_TO_REQUESTED_LOAD_MODE) == {mode.value for mode in EngineMode}
    # 逐条取自策略实际下发的 ChannelLoadMode（gcm / asc / external_asc / b2）
    assert requested_channel_emulator_load_mode("keysight_gcm") == "native_model"
    assert requested_channel_emulator_load_mode("mimo_first_asc") == "external_waveform"
    assert requested_channel_emulator_load_mode("external_asc") == "external_waveform"
    assert requested_channel_emulator_load_mode("b2_parametric_tdl") == "parametric_tdl"
    with pytest.raises(ValueError, match="未知 engine_mode"):
        requested_channel_emulator_load_mode("keysight_gcm ")


def test_plan_records_unsupported_or_undeclared_load_mode_without_raising():
    fs16 = _plan(FS16_MANIFEST, "native_model")
    assert fs16.load_mode_planned is False
    assert fs16.load_mode_reason == next(
        item.reason for item in FS16_MANIFEST.load_modes if item.mode == "native_model"
    )
    undeclared = ChannelEmulatorManifest(
        **{**MOCK_MANIFEST.model_dump(), "load_modes": MOCK_MANIFEST.load_modes[:1]}
    )
    plan = _plan(undeclared, "parametric_tdl")
    assert plan.load_mode_planned is False
    assert "未声明加载模式 parametric_tdl" in plan.load_mode_reason
    with pytest.raises(ValueError, match="requires a channel emulator manifest"):
        resolve_channel_emulator_execution_plan(
            manifest=None,  # type: ignore[arg-type]
            driver_source="hal",
            requested_load_mode="native_model",
            binding_digest=BINDING_DIGEST,
        )


def test_driver_for_plan_mirrors_measure_fallback_rule():
    f64 = _f64()
    assert channel_emulator_for_execution_plan(_hal(f64)) == (f64, "hal")
    assert channel_emulator_for_execution_plan(_hal(None)) == (
        MockChannelEmulator,
        "fallback_mock",
    )
    assert channel_emulator_for_execution_plan(SimpleNamespace()) == (
        MockChannelEmulator,
        "fallback_mock",
    )
    live = resolve_live_channel_emulator_execution_plan(
        _hal(None), engine_mode="keysight_gcm", binding_digest=BINDING_DIGEST
    )
    assert (live.adapter_id, live.driver_source) == ("mock_channel_emulator", "fallback_mock")
    with pytest.raises(ValueError, match="没有声明 channel emulator manifest"):
        resolve_live_channel_emulator_execution_plan(
            _hal(object()), engine_mode="keysight_gcm", binding_digest=BINDING_DIGEST
        )


# ----------------------------------------------------------------------
# ② 启动期冻结
# ----------------------------------------------------------------------


def test_freeze_persists_plan_next_to_binding_freeze_and_reuses_without_recompute(db):
    execution = _execution(db, keep="me")

    frozen = freeze_channel_emulator_execution_plan(db, _hal(_f64()), execution)

    expected = _plan(F64_MANIFEST, "native_model")
    assert frozen == {**expected.as_payload(), "digest": expected.digest}
    assert frozen["binding_digest"] == BINDING_DIGEST
    assert execution.config == {
        "keep": "me",
        CE_FREEZE_CONFIG_KEY: {"binding_digest": BINDING_DIGEST},
        CE_PLAN_FREEZE_CONFIG_KEY: frozen,
    }
    db.commit()
    db.expire_all()
    reloaded = db.get(TestExecution, execution.id)
    assert reloaded.config[CE_PLAN_FREEZE_CONFIG_KEY] == frozen

    # 二次调用：换了驱动、改了用例的 engine_mode 也原样复用，不重算
    case = db.get(TestCase, reloaded.test_case_id)
    case.configuration = _configuration("mimo_first_asc")
    db.commit()
    again = freeze_channel_emulator_execution_plan(db, _hal(MockChannelEmulator("ce", {})), reloaded)
    assert again == frozen
    assert again["adapter_id"] == "propsim_f64"


def test_freeze_requires_binding_freeze_first_and_rejects_bad_configuration(db):
    with pytest.raises(ValueError, match="binding 尚未冻结"):
        freeze_channel_emulator_execution_plan(db, _hal(_f64()), _execution(db, with_binding=False))
    # 没绑 TestCase / 配置不合法：与 MEASURE 同源的读取失败 → 同一句可操作的 ValueError
    with pytest.raises(ValueError, match="无法读取执行的 MIMO OTA 配置"):
        freeze_channel_emulator_execution_plan(db, _hal(_f64()), _execution(db, bind_case=False))
    with pytest.raises(ValueError, match="无法读取执行的 MIMO OTA 配置"):
        freeze_channel_emulator_execution_plan(
            db, _hal(_f64()), _execution(db, configuration={"engine_mode": 42})
        )


def test_freeze_fails_loud_at_launch_when_requested_load_mode_is_not_implemented(db):
    fs16 = RealPropsimFs16Driver("ce", {"ip_address": "192.0.2.11"})
    execution = _execution(db)

    with pytest.raises(ValueError, match="未声明支持本用例要求的加载模式 native_model"):
        freeze_channel_emulator_execution_plan(db, _hal(fs16), execution)
    # 拒绝时什么都没写
    assert CE_PLAN_FREEZE_CONFIG_KEY not in execution.config


def test_tampered_or_malformed_frozen_plan_is_rejected_not_refrozen(db):
    frozen = _frozen(_plan())
    tampered = {**frozen, "load_mode_planned": False}
    execution = _execution(db, **{CE_PLAN_FREEZE_CONFIG_KEY: tampered})
    with pytest.raises(ValueError, match="冻结件被篡改"):
        freeze_channel_emulator_execution_plan(db, _hal(_f64()), execution)

    malformed = {key: value for key, value in frozen.items() if key != "operations"}
    execution = _execution(db, **{CE_PLAN_FREEZE_CONFIG_KEY: malformed})
    with pytest.raises(ValueError, match="结构不合法"):
        freeze_channel_emulator_execution_plan(db, _hal(_f64()), execution)
    assert execution.config[CE_PLAN_FREEZE_CONFIG_KEY] == malformed


def test_execution_freeze_refuses_backfill_when_progress_exists_but_reuses_existing(db):
    progressed = _execution(db, phase_progress=[{"phase": "PRECHECK"}])
    with pytest.raises(ValueError, match="不能用当前 channelEmulator 配置回填执行计划"):
        freeze_execution_channel_emulator_plan(db, _hal(_f64()), progressed)
    assert CE_PLAN_FREEZE_CONFIG_KEY not in progressed.config

    frozen = _frozen(_plan())
    already = _execution(
        db, phase_progress=[{"phase": "PRECHECK"}], **{CE_PLAN_FREEZE_CONFIG_KEY: frozen}
    )
    assert freeze_execution_channel_emulator_plan(db, _hal(_f64()), already) == frozen

    fresh = _execution(db)
    written = freeze_execution_channel_emulator_plan(db, _hal(_f64()), fresh)
    assert db.get(TestExecution, fresh.id).config[CE_PLAN_FREEZE_CONFIG_KEY] == written

    with pytest.raises(ValueError, match="TestExecution 已不存在"):
        freeze_execution_channel_emulator_plan(
            db, _hal(_f64()), SimpleNamespace(id=fresh.id.__class__(int=0))
        )


# ----------------------------------------------------------------------
# ③ MEASURE 对账
# ----------------------------------------------------------------------


def _measure_context(config: dict):
    return SimpleNamespace(test_execution=SimpleNamespace(config=config))


def test_measure_rejects_missing_frozen_plan_or_binding_before_io():
    cfg = SimpleNamespace(engine_mode="keysight_gcm")
    with pytest.raises(RuntimeError, match="execution plan is not frozen"):
        MeasureExecutor._channel_emulator_plan_context(
            _measure_context({CE_FREEZE_CONFIG_KEY: {"binding_digest": BINDING_DIGEST}}),
            _hal(_f64()),
            cfg,
        )
    with pytest.raises(RuntimeError, match="binding 尚未冻结"):
        MeasureExecutor._channel_emulator_plan_context(
            _measure_context({CE_PLAN_FREEZE_CONFIG_KEY: _frozen(_plan())}), _hal(_f64()), cfg
        )


def test_measure_rejects_drifted_plan_and_accepts_matching_one():
    frozen_f64 = _frozen(_plan(F64_MANIFEST, "native_model"))
    config = {
        CE_FREEZE_CONFIG_KEY: {"binding_digest": BINDING_DIGEST},
        CE_PLAN_FREEZE_CONFIG_KEY: frozen_f64,
    }
    cfg = SimpleNamespace(engine_mode="keysight_gcm")

    # 冻结时 HAL 装的是 F64，测量时 HAL 里没有 CE → 漂移（③ 后不再兜底 mock）
    with pytest.raises(RuntimeError, match="does not match the loaded driver"):
        MeasureExecutor._channel_emulator_plan_context(_measure_context(config), _hal(None), cfg)
    # 驱动没变、engine_mode 变了 → 也是漂移
    with pytest.raises(RuntimeError, match="does not match the loaded driver"):
        MeasureExecutor._channel_emulator_plan_context(
            _measure_context(config), _hal(_f64()), SimpleNamespace(engine_mode="mimo_first_asc")
        )
    # 篡改的冻结件不因 digest 相等而放行
    tampered = {**config, CE_PLAN_FREEZE_CONFIG_KEY: {**frozen_f64, "adapter_id": "propsim_fs16"}}
    with pytest.raises(RuntimeError, match="冻结件被篡改"):
        MeasureExecutor._channel_emulator_plan_context(_measure_context(tampered), _hal(_f64()), cfg)

    live = MeasureExecutor._channel_emulator_plan_context(
        _measure_context(config), _hal(_f64()), cfg
    )
    assert isinstance(live, ChannelEmulatorExecutionPlan)
    assert live.digest == frozen_f64["digest"]
    assert verify_frozen_channel_emulator_execution_plan(frozen_f64, live) is None


# ----------------------------------------------------------------------
# ④ 消费方
# ----------------------------------------------------------------------


def _manual_ref_emulator():
    emu = AsyncMock()
    type(emu).adapter_manifest = F64_MANIFEST  # manifest 说：set_baseband_power 有
    emu.get_active_input_ports = MagicMock(return_value=[1, 2])
    emu.get_active_input_count = MagicMock(return_value=2)
    emu.set_baseband_power = AsyncMock(return_value=True)
    emu.set_crest_factor = AsyncMock(return_value=True)
    emu.measure_input = AsyncMock(return_value=(-15.0, 11.0))
    return emu


@pytest.mark.asyncio
async def test_manual_input_reference_consumes_the_plan_not_the_driver_manifest():
    cfg = MIMOOTAConfiguration(f64_input_ref_dbm=-15.0)
    emu = _manual_ref_emulator()

    # 交叉场景：manifest 说有、计划说无 → 按计划跳过（回退成读 manifest 的变异会在这里红）
    skipped = await MeasureExecutor()._apply_manual_input_reference(
        emulator=emu, plan=_plan(FS16_MANIFEST), config=cfg, execution_id="t"
    )
    assert skipped["skipped"] is True and skipped["success"] is False
    emu.set_baseband_power.assert_not_awaited()

    # 计划说有 → 下发
    applied = await MeasureExecutor()._apply_manual_input_reference(
        emulator=emu, plan=_plan(F64_MANIFEST), config=cfg, execution_id="t"
    )
    assert applied["skipped"] is False and applied["success"] is True
    emu.set_baseband_power.assert_awaited_once_with(-15.0)


def test_measure_no_longer_queries_driver_capability_directly_and_reconciles_before_first_ce_use():
    source = (REPO_APP / "services/mimo_ota/executors/measure.py").read_text(encoding="utf-8")
    assert "channel_emulator_implements(" not in source
    assert "channel_emulator_rejection(" not in source
    reconcile = source.index("ce_plan = self._channel_emulator_plan_context(context, hal, config)")
    assert source.count("self._channel_emulator_plan_context(") == 1
    # 对账在第一处消费之前、在取到 emulator 之后
    assert source.index('emulator = hal.drivers.get("channelEmulator")') < reconcile
    assert reconcile < source.index('ce_plan.planned("set_passthrough_mode")')
    # ③ 后 MeasureExecutor 不再自造 mock；执行作用域已在更外层完成冻结身份对账。
    assert "falling back to MockChannelEmulator" not in source
    assert "MockChannelEmulator(" not in source
    # 但不早于路损 / 证书等与 CE 无关的前置门（它们的拒绝不该被计划缺席顶掉）
    assert source.index("evaluate_path_loss_preflight(") < reconcile
    assert reconcile < source.index("plan=ce_plan,")
    # 直通进入、前置停止、终态退出三项都必须由冻结计划声明。
    assert source.count("ce_plan.planned(") == 3
    assert source.count("plan.planned(") == 4  # 三处直通生命周期 + 手动定标参数


def test_both_freeze_writers_freeze_the_plan_right_after_the_binding():
    for rel in ("services/test_case_runner.py", "api/commissioning.py"):
        source = (REPO_APP / rel).read_text(encoding="utf-8")
        binding_calls = [
            i for i in range(len(source))
            if source.startswith("freeze_execution_channel_emulator_binding(", i)
        ]
        plan_calls = [
            i for i in range(len(source))
            if source.startswith("freeze_execution_channel_emulator_plan(", i)
        ]
        assert len(binding_calls) == 1 and len(plan_calls) == 1, rel
        assert binding_calls[0] < plan_calls[0], rel
        # 两次调用之间没有别的仪器操作 / 提交（紧跟）
        between = source[binding_calls[0]:plan_calls[0]]
        assert "commit(" not in between and "await " not in between, rel


def test_plan_context_is_a_staticmethod_like_its_base_station_mirror():
    assert isinstance(
        inspect.getattr_static(MeasureExecutor, "_channel_emulator_plan_context"), staticmethod
    )
