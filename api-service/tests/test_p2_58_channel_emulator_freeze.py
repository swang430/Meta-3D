# -*- coding: utf-8 -*-
"""P2-58 ①：execution freeze 冻住 channelEmulator binding 的**同一** digest。

镜像 `base_station_adapter_profile.py:173-320` 的 freeze 段；每条门都配了一条让它
变红的变异并实跑过（见 PR 描述的变异表）：

  门 1  首次 freeze 写入 `CE_FREEZE_CONFIG_KEY`，`binding_digest` 复用 resolver 的
        —— 变异：freeze 里自己重算 binding_digest → 红
  门 2  二次调用复用、不再解析（resolver 调用计数 == 1，且 lock=True）
        —— 变异：删「已存在则返回」分支 / lock=True→False → 红
  门 3  已存在冻结件损坏 / 被篡改 → ValueError（中文），且不静默重冻
        —— 变异：删结构校验 → 红
  门 4  解析失败 → ValueError 穿出，config **无** CE 键 —— 变异：吞异常写空 dict → 红
  门 5  runner 接线：CE freeze 抛 → rollback + CaseNotExecutable；happy path 落冻结件
        —— 变异：删 runner 里的 CE freeze 调用 → 红
  门 6  identity 键集合逐字 = 设计稿 §8.4；resolved_binding 无 execution_mode / runtime_driver；
        BS 专属块没抄进来 —— 变异：改一个键名 → 红
  门 7  commissioning `_freeze_instrument_lease` 接线 —— 变异：删调用 → 红
  门 8  回填守门：有进度且无 CE 冻结件 → ValueError；`phase_progress: []` 不算进度
        —— 变异：删守门 → 红
  门 9  不变量：两个调用方文件里 CE freeze 调用次数 == BS freeze 调用次数，且在其后

脚手架复用 `tests/test_p2_58_channel_emulator_binding.py`（Agent A）的写法。
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal import MockChannelEmulator, MockPositioner
from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestExecution
from app.services import channel_emulator_binding as ceb
from app.services import test_case_runner as tcr
from app.services.base_station_adapter_profile import (
    FREEZE_CONFIG_KEY as BS_FREEZE_CONFIG_KEY,
)
from app.services.channel_emulator_binding import (
    CE_FREEZE_CONFIG_KEY,
    CE_FREEZE_IDENTITY_KEYS,
    freeze_channel_emulator_binding,
    freeze_execution_channel_emulator_binding,
    resolve_channel_emulator_binding,
)
from app.services.instrument_hal_service import get_hal_service
from tests.base_station_mock_factory import registered_mock_base_station

REPO_ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------
# 脚手架（镜像 Agent A 的测试文件）
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


def _configured(
    db,
    *,
    model_name: str = "PROPSIM F64",
    driver_mode: str = "real",
    endpoint: str = "192.0.2.10",
):
    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        driver_mode=driver_mode,
    )
    db.add(category)
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="Keysight",
        model=model_name,
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint=endpoint,
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": endpoint,
                "driver_mode": driver_mode,
                "role": "primary_channel_emulator",
            }
        ],
    )
    db.add_all([connection, lab])
    db.commit()
    return category, model, connection, lab


def _unbound(db, *, driver_mode: str = "mock"):
    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        driver_mode=driver_mode,
    )
    db.add(category)
    db.flush()
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": None,
                "connection_endpoint": None,
                "driver_mode": driver_mode,
                "role": "primary_channel_emulator",
            }
        ],
    )
    db.add(lab)
    db.commit()
    return category, lab


def _f64(endpoint: str = "192.0.2.10", instrument_id: str = "ce"):
    return RealPropsimF64Driver(instrument_id, {"ip_address": endpoint})


def _mock(instrument_id: str = "ce"):
    return MockChannelEmulator(instrument_id, {})


def _hal(driver):
    return SimpleNamespace(drivers={} if driver is None else {"channelEmulator": driver})


def _execution(db, **config):
    execution = TestExecution(status="pending", config=dict(config))
    db.add(execution)
    db.commit()
    return execution


# ----------------------------------------------------------------------
# 门 1：首次 freeze 写入冻结件，binding_digest 复用 resolver 的那一个
# ----------------------------------------------------------------------


def test_first_freeze_persists_snapshot_with_the_resolver_digest(db):
    _, model, connection, lab = _configured(db)
    hal = _hal(_f64())
    execution = _execution(db, keep="me")

    frozen = freeze_channel_emulator_binding(db, hal, execution, lab)
    resolved = resolve_channel_emulator_binding(db, hal, lab)  # lock=False 的独立解析

    assert frozen["binding_digest"] == resolved.binding_digest
    assert frozen["resolved_binding"] == resolved.stable_projection()
    assert frozen["resolved_binding"]["binding_digest"] == resolved.binding_digest
    # 契约解释 #4：dict，不是类型化模型
    assert frozen["expected_driver_connection"] == {
        "host": "192.0.2.10",
        "port": None,
        "resource": None,
    }
    assert frozen["category_id"] == resolved.category_id
    assert frozen["instrument_model_id"] == str(model.id)
    assert frozen["instrument_connection_id"] == str(connection.id)
    assert frozen["lab_profile_id"] == str(lab.id)
    assert frozen["expected_driver_module"] == RealPropsimF64Driver.__module__
    assert frozen["expected_driver_name"] == "RealPropsimF64Driver"
    identity = {key: value for key, value in frozen.items() if key != "digest"}
    assert frozen["digest"] == canonical_payload_digest(identity)
    # 既有 config 键保留，冻结件原子追加
    assert execution.config == {"keep": "me", CE_FREEZE_CONFIG_KEY: frozen}

    db.commit()
    db.expire_all()
    reloaded = db.get(TestExecution, execution.id)
    assert reloaded is not None
    assert reloaded.config[CE_FREEZE_CONFIG_KEY] == frozen


def test_simulated_freeze_has_no_driver_connection_but_shares_the_binding_digest(db):
    _, _, _, lab = _configured(db, driver_mode="auto")

    real = freeze_channel_emulator_binding(db, _hal(_f64()), _execution(db), lab)
    simulated = freeze_channel_emulator_binding(db, _hal(_mock()), _execution(db), lab)

    assert real["expected_driver_connection"] == {
        "host": "192.0.2.10",
        "port": None,
        "resource": None,
    }
    assert simulated["expected_driver_connection"] is None
    # 装 mock 还是装真驱动，binding 真值一样 → binding_digest 一样（运行期身份不进 digest）
    assert simulated["binding_digest"] == real["binding_digest"]
    assert simulated["resolved_binding"] == real["resolved_binding"]
    # 冻结件自己的 digest 覆盖 expected_driver_connection → 两者不同（镜像 BS）
    assert simulated["digest"] != real["digest"]


def test_diagnostic_unbound_freezes_with_null_identity_fields(db):
    _, lab = _unbound(db)
    execution = _execution(db)

    frozen = freeze_channel_emulator_binding(db, _hal(_mock()), execution, lab)

    assert frozen["resolved_binding"]["status"] == "diagnostic_unbound"
    assert frozen["instrument_model_id"] is None
    assert frozen["instrument_connection_id"] is None
    assert frozen["expected_driver_module"] is None
    assert frozen["expected_driver_name"] is None
    assert frozen["expected_driver_connection"] is None
    assert frozen["lab_profile_id"] == str(lab.id)
    assert frozen["binding_digest"] == resolve_channel_emulator_binding(
        db, _hal(_mock("other")), lab
    ).binding_digest


# ----------------------------------------------------------------------
# 门 2：二次调用复用，不再解析；首次解析用 lock=True
# ----------------------------------------------------------------------


def test_second_freeze_reuses_the_snapshot_without_resolving_again(db, monkeypatch):
    _, _, _, lab = _configured(db)
    hal = _hal(_f64())
    execution = _execution(db)
    lock_flags: list[object] = []
    original = ceb.resolve_channel_emulator_binding

    def _counting(*args, **kwargs):
        lock_flags.append(kwargs.get("lock"))
        return original(*args, **kwargs)

    monkeypatch.setattr(ceb, "resolve_channel_emulator_binding", _counting)

    first = freeze_channel_emulator_binding(db, hal, execution, lab)
    assert lock_flags == [True], "首次冻结必须 lock=True 解析"
    config_after_first = deepcopy(execution.config)

    second = freeze_channel_emulator_binding(db, hal, execution, lab)

    assert lock_flags == [True], "二次调用不得再解析"
    assert second == first
    assert second is execution.config[CE_FREEZE_CONFIG_KEY]
    assert execution.config == config_after_first


# ----------------------------------------------------------------------
# 门 3：已存在冻结件损坏 / 被篡改 → ValueError（中文），且不静默重冻
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("tamper_key", "与其 digest 不一致（冻结件被篡改）"),
        ("extra_key", "与其 digest 不一致（冻结件被篡改）"),
        ("drop_digest", "缺少 digest"),
        ("drop_binding_digest", "缺少 binding_digest"),
        ("empty_binding_digest", "缺少 binding_digest"),
        ("not_a_dict", "不是 dict"),
    ],
)
def test_corrupted_existing_freeze_is_rejected_not_refrozen(db, corruption, message):
    _, _, _, lab = _configured(db)
    hal = _hal(_f64())
    execution = _execution(db)
    frozen = freeze_channel_emulator_binding(db, hal, execution, lab)

    corrupted: object = deepcopy(frozen)
    if corruption == "tamper_key":
        corrupted["lab_profile_id"] = str(uuid4())
    elif corruption == "extra_key":
        corrupted["injected"] = True
    elif corruption == "drop_digest":
        del corrupted["digest"]
    elif corruption == "drop_binding_digest":
        del corrupted["binding_digest"]
    elif corruption == "empty_binding_digest":
        corrupted["binding_digest"] = ""
    else:
        corrupted = "not-a-dict"
    execution.config = {**execution.config, CE_FREEZE_CONFIG_KEY: corrupted}
    db.commit()

    with pytest.raises(ValueError, match=rf"已冻结的 channelEmulator binding .*{message}"):
        freeze_channel_emulator_binding(db, hal, execution, lab)
    # fail-closed：损坏的冻结件不能被静默重冻覆盖
    assert execution.config[CE_FREEZE_CONFIG_KEY] == corrupted


# ----------------------------------------------------------------------
# 门 4：解析失败 → ValueError 穿出，config 里没有 CE 键
# ----------------------------------------------------------------------


def test_resolution_failure_propagates_and_leaves_config_untouched(db):
    _, _, _, lab = _configured(db)
    lab.instrument_bindings = []
    db.commit()
    execution = _execution(db, keep=1)

    with pytest.raises(ValueError, match="恰好包含一条 channelEmulator binding（当前 0 条）"):
        freeze_channel_emulator_binding(db, _hal(_f64()), execution, lab)

    assert CE_FREEZE_CONFIG_KEY not in execution.config
    assert execution.config == {"keep": 1}


# ----------------------------------------------------------------------
# 门 6：identity 键集合逐字 = 设计稿 §8.4；不抄 BS 专属块
# ----------------------------------------------------------------------


def test_frozen_identity_keys_match_design_section_8_4_verbatim(db):
    assert CE_FREEZE_CONFIG_KEY == "channel_emulator_binding_freeze"
    assert CE_FREEZE_CONFIG_KEY != BS_FREEZE_CONFIG_KEY
    assert CE_FREEZE_IDENTITY_KEYS == {
        "schema_version",
        "category_id",
        "instrument_model_id",
        "instrument_connection_id",
        "lab_profile_id",
        "expected_driver_module",
        "expected_driver_name",
        "expected_driver_connection",
        "binding_digest",
        "resolved_binding",
    }
    _, _, _, lab = _configured(db)

    frozen = freeze_channel_emulator_binding(db, _hal(_f64()), _execution(db), lab)

    assert set(frozen) == CE_FREEZE_IDENTITY_KEYS | {"digest"}
    assert frozen["schema_version"] == 1
    # stable_projection 的排除集：运行期身份不进冻结件
    assert "execution_mode" not in frozen["resolved_binding"]
    assert "runtime_driver" not in frozen["resolved_binding"]
    assert set(frozen["resolved_binding"]) == (
        set(ceb.ResolvedChannelEmulatorBinding.model_fields)
        - {"execution_mode", "runtime_driver"}
    )
    # P1-75 / P2-54 的 BaseStation 专属块，CE 在 ① 无对应物，不得抄进来
    assert {
        "resolution",
        "compatibility",
        "mimo_ota_configuration",
        "cmw500_lte_2x2_formal_capability",
        "profile",
    }.isdisjoint(frozen)


# ----------------------------------------------------------------------
# 门 8：freeze_execution_* 的回填守门与悬空引用
# ----------------------------------------------------------------------


def test_execution_with_progress_cannot_backfill_a_missing_freeze(db):
    _, _, _, lab = _configured(db)
    execution = _execution(db)
    execution.measurements = {"phases": {"measure": {"status": "success"}}}
    db.commit()

    with pytest.raises(ValueError, match="不能用当前 channelEmulator 配置回填冻结件"):
        freeze_execution_channel_emulator_binding(
            db, _hal(_f64()), execution, SimpleNamespace(lab_profile_id=lab.id)
        )
    assert CE_FREEZE_CONFIG_KEY not in execution.config


def test_empty_phase_progress_is_not_progress_and_existing_freeze_survives_progress(db):
    _, _, _, lab = _configured(db)
    hal = _hal(_f64())
    # runner 建行时就带 `phase_progress: []`，不能被当成「已有进度」
    execution = _execution(db, phase_progress=[])
    test_case = SimpleNamespace(lab_profile_id=lab.id)

    frozen = freeze_execution_channel_emulator_binding(db, hal, execution, test_case)
    assert execution.config[CE_FREEZE_CONFIG_KEY] == frozen

    execution.measurements = {"phases": {"measure": {"status": "success"}}}
    db.commit()
    again = freeze_execution_channel_emulator_binding(db, hal, execution, test_case)
    assert again == frozen


@pytest.mark.parametrize(
    ("dangling", "message"),
    [
        ("no_lab_profile_id", "TestCase 没有 LabProfile"),
        ("lab_missing", "所选 LabProfile 已不存在"),
        ("execution_missing", "TestExecution 已不存在"),
    ],
)
def test_execution_freeze_rejects_dangling_references(db, dangling, message):
    _, _, _, lab = _configured(db)
    execution = _execution(db)
    test_case = SimpleNamespace(lab_profile_id=lab.id)
    if dangling == "no_lab_profile_id":
        test_case = SimpleNamespace()
    elif dangling == "lab_missing":
        test_case = SimpleNamespace(lab_profile_id=uuid4())
    else:
        execution = SimpleNamespace(id=uuid4())

    with pytest.raises(ValueError, match=message):
        freeze_execution_channel_emulator_binding(db, _hal(_f64()), execution, test_case)


# ----------------------------------------------------------------------
# 门 5 / 门 7：两条执行路径都接上了（runner / commissioning）
# ----------------------------------------------------------------------


@pytest.fixture
def runner_lab(db):
    """镜像 tests/test_arch1_case_runner.py 的 lab fixture，再加 channelEmulator。"""

    hal = get_hal_service()
    saved = dict(hal.drivers)
    hal.drivers["baseStation"] = registered_mock_base_station(
        "mock-bs", {"model": "UXM 5G E7515B"}
    )
    hal.drivers["positioner"] = MockPositioner("mock-positioner", {})
    hal.drivers["channelEmulator"] = MockChannelEmulator("mock-ce", {})
    chamber = create_chamber_from_preset(
        ChamberType.TYPE_C.value, name="CE-Freeze Chamber"
    )
    db.add(chamber)
    db.flush()
    categories = {
        key: InstrumentCategory(
            category_key=key, category_name=key, driver_mode="mock", is_active=True
        )
        for key in ("baseStation", "positioner", "channelEmulator")
    }
    db.add_all(categories.values())
    db.flush()
    db.add(
        InstrumentConnection(
            category_id=categories["baseStation"].id,
            endpoint=None,
            connection_params=None,
            created_by="test",
        )
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": None,
                "connection_endpoint": None,
                "driver_mode": "mock",
                "role": key if key != "channelEmulator" else "primary_channel_emulator",
            }
            for key, category in categories.items()
        ],
        is_active=True,
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)
    try:
        yield lab
    finally:
        hal.drivers.clear()
        hal.drivers.update(saved)
        tcr._RUNNING_TASKS.clear()


def _make_case(db, lab):
    from app.services.mimo_ota.factory import build_mimo_ota_test_case

    test_case, _ = build_mimo_ota_test_case(
        db,
        name="ce-freeze-case",
        lab_profile_id=lab.id,
        config_overrides={},
        created_by="test",
    )
    return test_case


def test_runner_refuses_launch_when_channel_emulator_freeze_fails(db, runner_lab, monkeypatch):
    case = _make_case(db, runner_lab)

    def _boom(*_args, **_kwargs):
        raise ValueError("CE 冻结失败（测试注入）")

    monkeypatch.setattr(tcr, "freeze_execution_channel_emulator_binding", _boom)
    rollbacks: list[bool] = []
    original_rollback = db.rollback

    def _spy_rollback():
        rollbacks.append(True)
        return original_rollback()

    monkeypatch.setattr(db, "rollback", _spy_rollback)

    with pytest.raises(
        tcr.CaseNotExecutable,
        match="信道仿真器 binding 无法冻结.*CE 冻结失败（测试注入）",
    ):
        tcr.launch_test_case_execution(db, case.id)

    assert rollbacks, "runner 必须 rollback 已 flush 的执行行"
    assert db.query(TestExecution).count() == 0
    assert tcr._RUNNING_TASKS == {}


async def test_runner_freezes_channel_emulator_alongside_base_station(db, runner_lab, monkeypatch):
    case = _make_case(db, runner_lab)

    async def _no_phases(_execution_id):
        return None

    monkeypatch.setattr(tcr, "_run_case", _no_phases)

    execution = tcr.launch_test_case_execution(db, case.id)
    task = tcr._RUNNING_TASKS.get(str(execution.id))
    if task is not None:
        await task

    frozen = execution.config[CE_FREEZE_CONFIG_KEY]
    expected = resolve_channel_emulator_binding(db, get_hal_service(), runner_lab)
    assert frozen["binding_digest"] == expected.binding_digest
    assert frozen["resolved_binding"] == expected.stable_projection()
    assert frozen["lab_profile_id"] == str(runner_lab.id)
    assert frozen["resolved_binding"]["status"] == "diagnostic_unbound"
    # 与 BaseStation 同刻冻结在同一行 config 里
    assert BS_FREEZE_CONFIG_KEY in execution.config


def _commissioning_execution(db, case):
    execution = TestExecution(
        test_case_id=case.id,
        status="pending",
        config={"step_descriptors": []},
        executed_by="commissioning_api",
    )
    db.add(execution)
    db.flush()
    return execution


def test_commissioning_lease_freeze_propagates_channel_emulator_failure(db, runner_lab, monkeypatch):
    from app.api import commissioning

    case = _make_case(db, runner_lab)
    execution = _commissioning_execution(db, case)

    def _boom(*_args, **_kwargs):
        raise ValueError("CE 冻结失败（测试注入）")

    monkeypatch.setattr(commissioning, "freeze_execution_channel_emulator_binding", _boom)

    # 5 个调用点都只接 `except ValueError` —— 必须以 ValueError 原样穿出
    with pytest.raises(ValueError, match="CE 冻结失败（测试注入）"):
        commissioning._freeze_instrument_lease(
            db, execution, case, include_positioner=False
        )


def test_commissioning_lease_freeze_writes_channel_emulator_snapshot(db, runner_lab):
    from app.api import commissioning

    case = _make_case(db, runner_lab)
    execution = _commissioning_execution(db, case)

    validator = commissioning._freeze_instrument_lease(
        db, execution, case, include_positioner=True
    )
    db.commit()

    frozen = execution.config[CE_FREEZE_CONFIG_KEY]
    expected = resolve_channel_emulator_binding(db, get_hal_service(), runner_lab)
    assert frozen["binding_digest"] == expected.binding_digest
    assert frozen["lab_profile_id"] == str(runner_lab.id)
    assert BS_FREEZE_CONFIG_KEY in execution.config
    assert callable(validator)


# ----------------------------------------------------------------------
# 门 9：不变量 —— BS freeze 在哪调，CE freeze 就跟在它后面调（数量对等 + 顺序）
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "api-service/app/services/test_case_runner.py",
        "api-service/app/api/commissioning.py",
    ],
)
def test_channel_emulator_freeze_is_called_wherever_base_station_freeze_is(relative):
    source = (REPO_ROOT / relative).read_text(encoding="utf-8")
    base_station_call = "freeze_execution_base_station_adapter_profile("
    channel_emulator_call = "freeze_execution_channel_emulator_binding("

    assert source.count(base_station_call) == 1
    assert source.count(channel_emulator_call) == source.count(base_station_call)
    assert source.index(channel_emulator_call) > source.index(base_station_call)
