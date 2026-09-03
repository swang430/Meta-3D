# -*- coding: utf-8 -*-
"""P2-58 ①：`ResolvedChannelEmulatorBinding` resolver 的门。

每条门在 PR 里都配了一条让它变红的变异并实跑过（见 PR 描述的变异表）。
形态镜像 `tests/test_p2_44_base_station_binding_resolver.py`。
"""

from __future__ import annotations

import ast
import inspect
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.channel_emulator_manifest import ChannelEmulatorManifest
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.hal.propsim_fs16 import RealPropsimFs16Driver
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.schemas.channel_emulator_binding import ChannelEmulatorBindingPreviewResponse
from app.services import channel_emulator_binding as ceb
from app.services.channel_emulator_binding import (
    ChannelEmulatorBindingPreview,
    ChannelEmulatorRuntimeDriverIdentity,
    ResolvedChannelEmulatorBinding,
    build_channel_emulator_binding_preview,
    resolve_channel_emulator_binding,
)


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


def _configured(
    db,
    *,
    model_name: str = "PROPSIM F64",
    driver_mode: str = "real",
    endpoint: str = "192.0.2.10",
    category_key: str = "channelEmulator",
):
    category = InstrumentCategory(
        category_key=category_key,
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


def _f64(endpoint: str = "192.0.2.10", instrument_id: str = "ce"):
    return RealPropsimF64Driver(instrument_id, {"ip_address": endpoint})


def _fs16(endpoint: str = "192.0.2.10"):
    return RealPropsimFs16Driver("ce", {"ip_address": endpoint})


def _mock(instrument_id: str = "ce"):
    return MockChannelEmulator(instrument_id, {})


def _hal(driver):
    return SimpleNamespace(drivers={} if driver is None else {"channelEmulator": driver})


def _forbid_io(monkeypatch, driver):
    """任何 transport / SCPI 入口一旦被碰就 fail —— 验证打在真实生效端。"""

    for name in ("connect", "_query", "_write", "_do_query", "_do_write", "query", "write"):
        if hasattr(driver, name):
            monkeypatch.setattr(
                driver,
                name,
                lambda *a, _n=name, **k: pytest.fail(f"resolver 触发了仪器 I/O：{_n}"),
            )


# ----------------------------------------------------------------------
# 门 1：合法配置 → configured，digest 稳定，零 I/O
# ----------------------------------------------------------------------


def test_real_binding_resolves_configured_with_stable_digest_and_zero_io(db, monkeypatch):
    _, model, connection, lab = _configured(db)
    driver = _f64()
    _forbid_io(monkeypatch, driver)

    first = resolve_channel_emulator_binding(db, _hal(driver), lab)
    second = resolve_channel_emulator_binding(db, _hal(driver), lab)

    assert first.status == "configured"
    assert first.execution_mode == "real"
    assert first.manifest is not None
    assert first.manifest.adapter_id == "propsim_f64"
    assert first.instrument_model_id == str(model.id)
    assert first.instrument_connection_id == str(connection.id)
    assert first.lab_profile_id == str(lab.id)
    assert first.expected_driver_module == RealPropsimF64Driver.__module__
    assert first.expected_driver_name == "RealPropsimF64Driver"
    assert first.expected_transport == {"host": "192.0.2.10", "port": None, "resource": None}
    assert first.runtime_driver.simulated is False
    assert first.runtime_driver.adapter_id == "propsim_f64"
    assert first.runtime_driver.transport == first.expected_transport
    assert first.binding_digest
    assert first.binding_digest == second.binding_digest
    assert first.stable_projection() == second.stable_projection()
    assert first.stable_projection()["binding_digest"] == first.binding_digest
    with pytest.raises(Exception):
        first.status = "changed"  # type: ignore[misc]
    with pytest.raises(Exception):
        first.runtime_driver.simulated = True  # type: ignore[misc]


# ----------------------------------------------------------------------
# 门 2：runtime_driver 变化不改 digest
# ----------------------------------------------------------------------


def test_runtime_driver_change_does_not_change_digest(db):
    _, _, _, lab = _configured(db, driver_mode="auto")

    real_one = resolve_channel_emulator_binding(db, _hal(_f64(instrument_id="ce-1")), lab)
    real_two = resolve_channel_emulator_binding(db, _hal(_f64(instrument_id="ce-2")), lab)
    simulated = resolve_channel_emulator_binding(db, _hal(_mock()), lab)

    assert real_one.binding_digest == real_two.binding_digest
    # 同一份持久化真值，装 mock 还是装真驱动，digest 必须一样 —— 运行期身份不进 digest
    assert simulated.binding_digest == real_one.binding_digest
    assert simulated.stable_projection() == real_one.stable_projection()
    assert simulated.execution_mode == "simulated"
    assert real_one.execution_mode == "real"
    assert simulated.runtime_driver != real_one.runtime_driver
    assert simulated.runtime_driver.adapter_id == "mock_channel_emulator"
    assert simulated.runtime_driver.transport is None


# ----------------------------------------------------------------------
# 门 3：品类未配置 / binding 缺失 / binding 多条 → ValueError，消息可读
# ----------------------------------------------------------------------


def test_missing_category_is_rejected_with_readable_reason(db):
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(uuid4()),
                "instrument_model_id": None,
                "connection_endpoint": None,
                "driver_mode": "mock",
                "role": "primary_channel_emulator",
            }
        ],
    )
    db.add(lab)
    db.commit()

    with pytest.raises(ValueError, match="'channelEmulator'.*未配置"):
        resolve_channel_emulator_binding(db, _hal(_mock()), lab)


@pytest.mark.parametrize(
    ("bindings_mutation", "expected"),
    [
        ("missing", r"恰好包含一条 channelEmulator binding（当前 0 条）"),
        ("duplicate", r"恰好包含一条 channelEmulator binding（当前 2 条）"),
        ("not_a_list", r"instrument_bindings 必须是列表"),
    ],
)
def test_binding_count_other_than_one_is_rejected(db, bindings_mutation, expected):
    _, _, _, lab = _configured(db)
    if bindings_mutation == "missing":
        lab.instrument_bindings = []
    elif bindings_mutation == "duplicate":
        lab.instrument_bindings = [
            *lab.instrument_bindings,
            deepcopy(lab.instrument_bindings[0]),
        ]
    else:
        lab.instrument_bindings = {"category_id": "x"}
    db.commit()

    with pytest.raises(ValueError, match=expected):
        resolve_channel_emulator_binding(db, _hal(_f64()), lab)


# ----------------------------------------------------------------------
# 门 4：driver_mode 三方一致性（category / binding / loaded driver）
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("category_mode", "loaded"),
    [("real", "mock"), ("mock", "real")],
)
def test_loaded_driver_violating_explicit_category_mode_is_rejected(db, category_mode, loaded):
    _, _, _, lab = _configured(db, driver_mode=category_mode)
    driver = _mock() if loaded == "mock" else _f64()

    with pytest.raises(ValueError, match=rf"装载的驱动模式（{loaded}）与品类显式的 {category_mode} 驱动模式不一致"):
        resolve_channel_emulator_binding(db, _hal(driver), lab)


@pytest.mark.parametrize(
    ("category_mode", "stale_binding_mode"),
    [
        ("real", "mock"),
        ("real", "auto"),
        ("mock", "real"),
        ("mock", "auto"),
        ("auto", "real"),
        ("auto", "mock"),
    ],
)
def test_stale_lab_profile_driver_mode_is_rejected(db, category_mode, stale_binding_mode):
    _, _, _, lab = _configured(db, driver_mode=category_mode)
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["driver_mode"] = stale_binding_mode
    lab.instrument_bindings = bindings
    db.commit()
    driver = _mock() if category_mode == "mock" else _f64()

    with pytest.raises(ValueError, match="驱动模式.*与品类当前驱动模式.*不一致"):
        resolve_channel_emulator_binding(db, _hal(driver), lab)


def test_invalid_driver_mode_literals_are_rejected(db):
    category, _, _, lab = _configured(db)
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["driver_mode"] = "hardware"
    lab.instrument_bindings = bindings
    db.commit()
    with pytest.raises(ValueError, match="binding 的驱动模式 'hardware' 非法"):
        resolve_channel_emulator_binding(db, _hal(_f64()), lab)

    bindings[0]["driver_mode"] = "real"
    lab.instrument_bindings = deepcopy(bindings)
    category.driver_mode = "hardware"
    db.commit()
    with pytest.raises(ValueError, match="品类的驱动模式 'hardware' 非法"):
        resolve_channel_emulator_binding(db, _hal(_f64()), lab)


# ----------------------------------------------------------------------
# 门 5：manifest fail-closed；Mock 有 manifest → simulated
# ----------------------------------------------------------------------


def test_real_driver_without_manifest_is_rejected(db):
    _, _, _, lab = _configured(db)
    driver = _f64()
    driver.adapter_manifest = None  # 实例级遮掉类级声明 → channel_emulator_manifest_of → None

    with pytest.raises(ValueError, match="RealPropsimF64Driver 没有声明 channel emulator manifest（fail-closed）"):
        resolve_channel_emulator_binding(db, _hal(driver), lab)


def test_registered_class_without_manifest_is_rejected(db, monkeypatch):
    _, _, _, lab = _configured(db)
    manifest = RealPropsimF64Driver.adapter_manifest
    monkeypatch.delattr(RealPropsimF64Driver, "adapter_manifest")
    driver = _f64()
    driver.adapter_manifest = manifest  # 装载实例有、注册类没有 → 注册侧 fail-closed

    with pytest.raises(ValueError, match="注册的驱动 RealPropsimF64Driver 没有声明 channel emulator manifest"):
        resolve_channel_emulator_binding(db, _hal(driver), lab)


def test_test_double_without_manifest_never_passes_as_a_driver(db):
    _, _, _, lab = _configured(db, driver_mode="auto")

    with pytest.raises(ValueError, match="SimpleNamespace 没有声明 channel emulator manifest"):
        resolve_channel_emulator_binding(db, _hal(SimpleNamespace()), lab)


def test_mock_with_manifest_resolves_simulated(db, monkeypatch):
    _, model, connection, lab = _configured(db, driver_mode="mock")
    mock = _mock()
    _forbid_io(monkeypatch, mock)

    resolved = resolve_channel_emulator_binding(db, _hal(mock), lab)

    assert resolved.status == "configured"
    assert resolved.execution_mode == "simulated"
    assert resolved.runtime_driver.simulated is True
    assert resolved.runtime_driver.driver_name == "MockChannelEmulator"
    assert resolved.runtime_driver.adapter_id == "mock_channel_emulator"
    assert resolved.runtime_driver.transport is None
    # binding 说的是配置的型号（F64），runtime 说的是装载的 mock —— 两句都是真话
    assert resolved.manifest is not None
    assert resolved.manifest.adapter_id == "propsim_f64"
    assert resolved.instrument_model_id == str(model.id)
    assert resolved.instrument_connection_id == str(connection.id)
    assert resolved.expected_driver_name == "RealPropsimF64Driver"


# ----------------------------------------------------------------------
# 门 6：零仪器 I/O 结构门（AST）+ 判定器自测
# ----------------------------------------------------------------------

#: 对**任何**接收者都算仪器 I/O 的方法名。
_IO_METHOD_NAMES = frozenset(
    {"_query", "_write", "_do_query", "_do_write", "connect", "disconnect"}
)
#: 只有接收者是 `db`（SQLAlchemy Session 形参）时才放行的方法名。
_DB_OR_IO_METHOD_NAMES = frozenset({"query", "write"})
_IO_MODULES = frozenset({"asyncio", "socket", "pyvisa", "ftplib", "telnetlib", "serial"})


def _io_offenders(source: str) -> list[str]:
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)):
            offenders.append(f"L{node.lineno} {type(node).__name__}")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name.split(".")[0] for alias in node.names]
                if isinstance(node, ast.Import)
                else [(node.module or "").split(".")[0]]
            )
            for name in names:
                if name in _IO_MODULES:
                    offenders.append(f"L{node.lineno} import {name}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                receiver_is_db = isinstance(func.value, ast.Name) and func.value.id == "db"
                if func.attr in _IO_METHOD_NAMES or (
                    func.attr in _DB_OR_IO_METHOD_NAMES and not receiver_is_db
                ):
                    offenders.append(f"L{node.lineno} call .{func.attr}()")
            elif isinstance(func, ast.Name) and func.id in _IO_METHOD_NAMES:
                offenders.append(f"L{node.lineno} call {func.id}()")
    return offenders


def test_resolver_source_has_zero_instrument_io():
    source = inspect.getsource(ceb)
    assert _io_offenders(source) == [], "resolver 里出现了仪器 I/O 形态"


@pytest.mark.parametrize(
    ("snippet", "expected_fragment"),
    [
        ("async def f(driver):\n    await driver.get_channel_state()\n", "Await"),
        ("def f(driver):\n    return driver._query('*IDN?')\n", "._query()"),
        ("def f(driver):\n    driver._write('DIAG:SIMU:GO')\n", "._write()"),
        ("def f(driver):\n    return driver.query('*IDN?')\n", ".query()"),
        ("def f(driver):\n    return driver.connect()\n", ".connect()"),
        ("import socket\n", "import socket"),
        ("from pyvisa import ResourceManager\n", "import pyvisa"),
    ],
)
def test_io_detector_flags_every_io_shape(snippet, expected_fragment):
    offenders = _io_offenders(snippet)
    assert any(expected_fragment in item for item in offenders), offenders


def test_io_detector_allows_db_query_and_attribute_reads():
    clean = (
        "def f(db, driver):\n"
        "    rows = db.query(Thing).filter(Thing.x == 1).one_or_none()\n"
        "    host = getattr(driver, '_connection_host', None)\n"
        "    return rows, host\n"
    )
    assert _io_offenders(clean) == []


# ----------------------------------------------------------------------
# 门 7：preview 对 ValueError 返回 invalid + detail，不抛
# ----------------------------------------------------------------------


def test_preview_returns_invalid_with_reason_instead_of_raising(db):
    _, _, _, lab = _configured(db)
    lab.instrument_bindings = []
    db.commit()

    preview = build_channel_emulator_binding_preview(db, _hal(_f64()), lab)

    assert preview.status == "invalid"
    assert preview.binding_digest is None
    assert preview.execution_mode is None
    assert preview.resolved_binding is None
    assert preview.runtime_driver is None
    assert preview.lab_profile_id == str(lab.id)
    assert "恰好包含一条 channelEmulator binding（当前 0 条）" in preview.detail


def test_preview_mirrors_resolved_binding(db):
    _, model, connection, lab = _configured(db)
    hal = _hal(_f64())

    resolved = resolve_channel_emulator_binding(db, hal, lab)
    preview = build_channel_emulator_binding_preview(db, hal, lab)

    assert preview.status == "configured"
    assert preview.binding_digest == resolved.binding_digest
    assert preview.execution_mode == "real"
    assert preview.adapter_id == "propsim_f64"
    assert preview.model_name == "PROPSIM F64"
    assert preview.category_id == resolved.category_id
    assert preview.instrument_model_id == str(model.id)
    assert preview.instrument_connection_id == str(connection.id)
    assert preview.resolved_binding == resolved.stable_projection()
    assert preview.runtime_driver == resolved.runtime_driver.model_dump(mode="json")
    assert preview.detail


# ----------------------------------------------------------------------
# 门 8：品类键只认 "channelEmulator"
# ----------------------------------------------------------------------


def test_snake_case_category_key_is_not_silently_accepted(db):
    _, _, _, lab = _configured(db, category_key="channel_emulator")

    with pytest.raises(ValueError, match="'channelEmulator'.*未配置.*只认这一种拼写"):
        resolve_channel_emulator_binding(db, _hal(_f64()), lab)


def test_hal_snake_case_driver_key_is_not_silently_accepted(db):
    _, _, _, lab = _configured(db)
    hal = SimpleNamespace(drivers={"channel_emulator": _f64()})

    with pytest.raises(ValueError, match="HAL 未装载 channelEmulator 驱动"):
        resolve_channel_emulator_binding(db, hal, lab)


# ----------------------------------------------------------------------
# 门 9：digest 忽略 manifest 文案、跟踪 support
# ----------------------------------------------------------------------


def _with_operation(manifest: ChannelEmulatorManifest, operation: str, **update):
    return manifest.model_copy(
        update={
            "operations": tuple(
                item.model_copy(update=update) if item.operation == operation else item
                for item in manifest.operations
            )
        }
    )


def test_digest_ignores_manifest_prose_but_tracks_support(db, monkeypatch):
    _, _, _, lab = _configured(db)
    baseline = resolve_channel_emulator_binding(db, _hal(_f64()), lab)
    original = RealPropsimF64Driver.adapter_manifest
    assert original.implements("set_doppler")

    monkeypatch.setattr(
        RealPropsimF64Driver,
        "adapter_manifest",
        _with_operation(original, "set_doppler", reason="改了一句解释文案"),
    )
    prose_changed = resolve_channel_emulator_binding(db, _hal(_f64()), lab)
    assert prose_changed.binding_digest == baseline.binding_digest

    monkeypatch.setattr(
        RealPropsimF64Driver,
        "adapter_manifest",
        _with_operation(original, "set_doppler", support="not_implemented"),
    )
    support_flipped = resolve_channel_emulator_binding(db, _hal(_f64()), lab)
    assert support_flipped.binding_digest != baseline.binding_digest


def test_digest_changes_for_each_persisted_truth(db):
    category, _, connection, lab = _configured(db)
    hal = _hal(_f64())
    baseline = resolve_channel_emulator_binding(db, hal, lab).binding_digest

    connection.endpoint = "192.0.2.20"
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["connection_endpoint"] = "192.0.2.20"
    lab.instrument_bindings = bindings
    hal.drivers["channelEmulator"] = _f64("192.0.2.20")
    db.commit()
    endpoint_changed = resolve_channel_emulator_binding(db, hal, lab).binding_digest
    assert endpoint_changed != baseline

    other = InstrumentModel(
        category_id=category.id, vendor="Keysight", model="PROPSIM FS16", capabilities={}
    )
    db.add(other)
    db.flush()
    category.selected_model_id = other.id
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["instrument_model_id"] = str(other.id)
    lab.instrument_bindings = bindings
    hal.drivers["channelEmulator"] = _fs16("192.0.2.20")
    db.commit()
    model_changed = resolve_channel_emulator_binding(db, hal, lab)
    assert model_changed.binding_digest != endpoint_changed
    assert model_changed.manifest is not None
    assert model_changed.manifest.adapter_id == "propsim_fs16"
    assert model_changed.expected_driver_name == "RealPropsimFs16Driver"


# ----------------------------------------------------------------------
# 门 10：每一种真值分裂都 fail-loud
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("binding_model_missing", "同时配置或同时为空"),
        ("selected_model_missing", "同时配置或同时为空"),
        ("binding_model_mismatch", "instrument_model_id 与品类 selected_model_id 不一致"),
        ("binding_endpoint", "connection_endpoint 与所选连接的 endpoint 不一致"),
        ("connection_missing", "没有连接配置"),
        ("connection_endpoint_invalid", "连接配置无效"),
        ("model_unregistered", "'Unknown CE 9000' 没有注册真驱动"),
        ("driver_missing", "HAL 未装载 channelEmulator 驱动"),
        ("driver_class", "RealPropsimFs16Driver 与所选型号注册的驱动类 RealPropsimF64Driver 不一致"),
        ("driver_endpoint", "transport 与所选连接不一致"),
        ("driver_instance_manifest_drift", "manifest 与所选型号注册的 manifest 不一致"),
    ],
)
def test_resolver_fails_loud_for_every_split_truth(db, mutation, message):
    category, model, connection, lab = _configured(db)
    driver = _f64()
    if mutation == "binding_model_missing":
        bindings = deepcopy(lab.instrument_bindings)
        bindings[0]["instrument_model_id"] = None
        lab.instrument_bindings = bindings
    elif mutation == "selected_model_missing":
        category.selected_model_id = None
    elif mutation == "binding_model_mismatch":
        other = InstrumentModel(
            category_id=category.id, vendor="Keysight", model="PROPSIM FS16", capabilities={}
        )
        db.add(other)
        db.flush()
        bindings = deepcopy(lab.instrument_bindings)
        bindings[0]["instrument_model_id"] = str(other.id)
        lab.instrument_bindings = bindings
    elif mutation == "binding_endpoint":
        bindings = deepcopy(lab.instrument_bindings)
        bindings[0]["connection_endpoint"] = "192.0.2.99"
        lab.instrument_bindings = bindings
    elif mutation == "connection_missing":
        db.delete(connection)
    elif mutation == "connection_endpoint_invalid":
        connection.endpoint = "TCPIP0::192.0.2.10::SOCKET"  # 不完整的 SOCKET resource
        bindings = deepcopy(lab.instrument_bindings)
        bindings[0]["connection_endpoint"] = "TCPIP0::192.0.2.10::SOCKET"
        lab.instrument_bindings = bindings
    elif mutation == "model_unregistered":
        model.model = "Unknown CE 9000"
    elif mutation == "driver_missing":
        driver = None
    elif mutation == "driver_class":
        driver = _fs16()
    elif mutation == "driver_endpoint":
        driver = _f64("192.0.2.99")
    elif mutation == "driver_instance_manifest_drift":
        driver.adapter_manifest = RealPropsimFs16Driver.adapter_manifest
    db.commit()

    with pytest.raises(ValueError, match=message):
        resolve_channel_emulator_binding(db, _hal(driver), lab)


# ----------------------------------------------------------------------
# 门 11：diagnostic_unbound 只允许权威 mock
# ----------------------------------------------------------------------


def _unbound(db, *, driver_mode: str = "mock"):
    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        driver_mode=driver_mode,
    )
    db.add(category)
    db.flush()
    connection = InstrumentConnection(category_id=category.id, endpoint=None)
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
    db.add_all([connection, lab])
    db.commit()
    return category, lab


def test_only_authoritative_mock_may_resolve_diagnostic_unbound(db):
    category, lab = _unbound(db)

    resolved = resolve_channel_emulator_binding(db, _hal(_mock()), lab)
    assert resolved.status == "diagnostic_unbound"
    assert resolved.execution_mode == "simulated"
    assert resolved.manifest is None
    assert resolved.instrument_model_id is None
    assert resolved.instrument_connection_id is None
    assert resolved.expected_driver_module is None
    assert resolved.expected_driver_name is None
    assert resolved.expected_transport is None
    assert resolved.runtime_driver.adapter_id == "mock_channel_emulator"
    again = resolve_channel_emulator_binding(db, _hal(_mock("ce-other")), lab)
    assert again.binding_digest == resolved.binding_digest

    with pytest.raises(ValueError, match="只允许权威 mock 驱动"):
        resolve_channel_emulator_binding(db, _hal(_f64()), lab)

    category.driver_mode = "real"
    bindings = deepcopy(lab.instrument_bindings)
    bindings[0]["driver_mode"] = "real"
    lab.instrument_bindings = bindings
    db.commit()
    with pytest.raises(ValueError, match="装载的驱动模式（mock）与品类显式的 real 驱动模式不一致"):
        resolve_channel_emulator_binding(db, _hal(_mock()), lab)


def test_unbound_digest_differs_from_configured_digest(db):
    _, unbound_lab = _unbound(db)
    unbound = resolve_channel_emulator_binding(db, _hal(_mock()), unbound_lab)
    preview = build_channel_emulator_binding_preview(db, _hal(_mock()), unbound_lab)
    assert preview.status == "diagnostic_unbound"
    assert preview.adapter_id is None
    assert preview.model_name is None
    assert preview.binding_digest == unbound.binding_digest


# ----------------------------------------------------------------------
# 门 12：lock=True 从库里刷新，不吃 identity map 的旧值
# ----------------------------------------------------------------------


def test_locked_resolver_refreshes_cached_binding_and_connection_from_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ce-binding-refresh.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    writer = session_factory()
    try:
        _, _, connection, lab = _configured(db)

        writer_connection = writer.get(InstrumentConnection, connection.id)
        writer_lab = writer.get(LabProfile, lab.id)
        assert writer_connection is not None
        assert writer_lab is not None
        writer_connection.endpoint = "192.0.2.20"
        bindings = deepcopy(writer_lab.instrument_bindings)
        bindings[0]["connection_endpoint"] = "192.0.2.20"
        writer_lab.instrument_bindings = bindings
        writer.commit()

        resolved = resolve_channel_emulator_binding(
            db, _hal(_f64("192.0.2.20")), lab, lock=True
        )

        assert resolved.expected_transport is not None
        assert resolved.expected_transport["host"] == "192.0.2.20"
    finally:
        writer.close()
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


# ----------------------------------------------------------------------
# 门 13 / 14：schema 与 §8 契约形状
# ----------------------------------------------------------------------


def test_response_schema_is_preview_fields_plus_selected_asset_id(db):
    _, _, _, lab = _configured(db)
    preview = build_channel_emulator_binding_preview(db, _hal(_f64()), lab)

    assert set(ChannelEmulatorBindingPreviewResponse.model_fields) == (
        set(ChannelEmulatorBindingPreview.model_fields) | {"selected_asset_id"}
    )
    response = ChannelEmulatorBindingPreviewResponse(
        **preview.model_dump(mode="json"), selected_asset_id=None
    )
    assert response.binding_digest == preview.binding_digest
    assert response.selected_asset_id is None
    with pytest.raises(ValidationError):
        ChannelEmulatorBindingPreviewResponse(
            **preview.model_dump(mode="json"), selected_asset_id=None, extra_field=1
        )


def test_contract_field_sets_match_design_section_8(db):
    assert set(ResolvedChannelEmulatorBinding.model_fields) == {
        "schema_version",
        "status",
        "execution_mode",
        "category_id",
        "instrument_model_id",
        "instrument_connection_id",
        "lab_profile_id",
        "manifest",
        "expected_driver_module",
        "expected_driver_name",
        "expected_transport",
        "binding_digest",
        "runtime_driver",
    }
    assert set(ChannelEmulatorRuntimeDriverIdentity.model_fields) == {
        "driver_module",
        "driver_name",
        "adapter_id",
        "simulated",
        "transport",
    }
    _, _, _, lab = _configured(db)
    resolved = resolve_channel_emulator_binding(db, _hal(_f64()), lab)
    assert set(resolved.stable_projection()) == (
        set(ResolvedChannelEmulatorBinding.model_fields) - {"execution_mode", "runtime_driver"}
    )
    with pytest.raises(ValidationError):
        ChannelEmulatorRuntimeDriverIdentity(
            driver_module="m", driver_name="n", adapter_id=None, simulated=True,
            transport=None, instrument_id="x",
        )
