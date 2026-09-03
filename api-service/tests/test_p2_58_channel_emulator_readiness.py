# -*- coding: utf-8 -*-
"""P2-58 ①：`GET /api/v1/instruments/hal/readiness` 接上 channelEmulator binding 预览的门。

守的是 `app/api/instrument.py::get_hal_readiness` 那一条链：

* 响应键逐字叫 `channel_emulator_binding`（openapi.yaml 已按此声明，G11 门要求 yaml ⊆ 实现）；
* readiness 是只读面：CE 真值不一致 → `status="invalid"` + 中文 detail，**不** 4xx/5xx；
* 无活动 LabProfile → 键在、值为 null；
* digest 直接复用 resolver 的，不在端点里重算；
* 两个构造点（HAL 未初始化 / 已初始化）都带这个字段 —— 站点数与 `base_station_binding=` 对等；
* 邻居 `base_station_binding` 不受影响。

脚手架：DB/HAL 替身照 `tests/test_p2_58_channel_emulator_binding.py`（A 的 resolver 门），
端点打法照 `tests/test_hal_readiness.py`（`TestClient(app)` 不进 lifespan + `get_db` 覆盖 +
monkeypatch `app.services.instrument_hal_service.get_hal_service`）。
每条门在 PR 里都配了一条让它变红的变异并实跑过。
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.instrument as instrument_api
from app.db.database import Base, get_db
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.main import app
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.services.channel_emulator_binding import (
    CHANNEL_EMULATOR_CATEGORY_KEY,
    resolve_channel_emulator_binding,
)
from app.services.readiness import (
    DutAttachReadiness,
    ReadinessReport,
    build_calibration_readiness,
    build_lab_profile_readiness,
)

READINESS_URL = "/api/v1/instruments/hal/readiness"
NOW = datetime(2026, 9, 3, 12, 0, 0)


# ----------------------------------------------------------------------
# 脚手架
# ----------------------------------------------------------------------

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# 不用 `with TestClient(app)`：不进 lifespan，就不会初始化全局 HAL —— HAL 全部由下面的替身给
client = TestClient(app)


@pytest.fixture(autouse=True)
def _db_schema():
    Base.metadata.create_all(bind=_engine)
    prior = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        if prior is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prior
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def db():
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _configured(
    db,
    *,
    model_name: str = "PROPSIM F64",
    driver_mode: str = "real",
    endpoint: str = "192.0.2.10",
):
    """一条合法的 channelEmulator 配置：品类 + 型号 + 连接 + 活动 LabProfile（镜像 A 的 fixture）。"""

    category = InstrumentCategory(
        category_key=CHANNEL_EMULATOR_CATEGORY_KEY,
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
        is_active=True,
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


def _f64(endpoint: str = "192.0.2.10"):
    return RealPropsimF64Driver("ce", {"ip_address": endpoint})


def _forbid_io(monkeypatch, driver):
    """readiness 是只读面：任何 transport / SCPI 入口一旦被碰就 fail。"""

    for name in ("connect", "_query", "_write", "_do_query", "_do_write", "query", "write"):
        if hasattr(driver, name):
            monkeypatch.setattr(
                driver,
                name,
                lambda *a, _n=name, **k: pytest.fail(f"readiness 触发了仪器 I/O：{_n}"),
            )


def _report(db) -> ReadinessReport:
    lab_section = build_lab_profile_readiness(db)
    return ReadinessReport(
        drivers=[],
        lab_profile=lab_section,
        calibration=build_calibration_readiness(db, lab_section, now=NOW),
        dut_attach=DutAttachReadiness(),
        generated_at_iso=NOW.isoformat(),
    )


def _install_hal(monkeypatch, driver, *, report):
    """HAL 替身：`drivers` 只认驼峰键；`report=None` 走「HAL 未初始化」构造点。"""

    hal = SimpleNamespace(
        drivers={} if driver is None else {CHANNEL_EMULATOR_CATEGORY_KEY: driver},
        last_readiness_report=report,
    )
    # 端点在函数体内 `from app.services.instrument_hal_service import get_hal_service`，
    # 所以要 patch 模块属性（与 tests/test_hal_readiness.py 同一打法）
    monkeypatch.setattr(
        "app.services.instrument_hal_service.get_hal_service", lambda: hal
    )
    return hal


# ----------------------------------------------------------------------
# 门 1：合法配置 → 200 / configured / digest 非空 / selected_asset_id 恒 None / 零 I/O
# ----------------------------------------------------------------------


def test_readiness_reports_configured_channel_emulator_binding(db, monkeypatch):
    _, model, connection, lab = _configured(db)
    driver = _f64()
    _forbid_io(monkeypatch, driver)
    _install_hal(monkeypatch, driver, report=_report(db))

    resp = client.get(READINESS_URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    # 键名逐字 snake_case —— openapi.yaml 就是按这个名字声明的（G11）
    assert "channel_emulator_binding" in body
    ce = body["channel_emulator_binding"]
    assert ce["status"] == "configured"
    assert ce["binding_digest"]
    assert ce["execution_mode"] == "real"
    assert ce["adapter_id"] == "propsim_f64"
    assert ce["model_name"] == "PROPSIM F64"
    assert ce["instrument_model_id"] == str(model.id)
    assert ce["instrument_connection_id"] == str(connection.id)
    assert ce["lab_profile_id"] == str(lab.id)
    assert ce["runtime_driver"]["adapter_id"] == "propsim_f64"
    # readiness 没有 TestCase 上下文：资产字段在、值恒 None
    assert "selected_asset_id" in ce
    assert ce["selected_asset_id"] is None


# ----------------------------------------------------------------------
# 门 2：CE 真值不一致 → 仍 200，status=invalid + 中文 detail（只读面不 4xx/5xx）
# ----------------------------------------------------------------------


def test_readiness_stays_200_with_invalid_preview_when_binding_missing(db, monkeypatch):
    _, _, _, lab = _configured(db)
    lab.instrument_bindings = []
    db.commit()
    _install_hal(monkeypatch, _f64(), report=_report(db))

    resp = client.get(READINESS_URL)

    assert resp.status_code == 200
    ce = resp.json()["channel_emulator_binding"]
    assert ce["status"] == "invalid"
    assert ce["binding_digest"] is None
    assert ce["execution_mode"] is None
    assert ce["resolved_binding"] is None
    assert ce["runtime_driver"] is None
    assert ce["lab_profile_id"] == str(lab.id)
    assert ce["selected_asset_id"] is None
    assert ce["detail"]
    assert "恰好包含一条 channelEmulator binding（当前 0 条）" in ce["detail"]


def test_readiness_stays_200_when_hal_has_no_channel_emulator_driver(db, monkeypatch):
    """HAL 没装 channelEmulator 驱动：resolver 报 ValueError，端点照样 200 + invalid。"""

    _, _, _, lab = _configured(db)
    _install_hal(monkeypatch, None, report=_report(db))

    resp = client.get(READINESS_URL)

    assert resp.status_code == 200
    ce = resp.json()["channel_emulator_binding"]
    assert ce["status"] == "invalid"
    assert ce["lab_profile_id"] == str(lab.id)
    assert "HAL 未装载 channelEmulator 驱动" in ce["detail"]


# ----------------------------------------------------------------------
# 门 3：无活动 LabProfile → 200，键在、值为 null
# ----------------------------------------------------------------------


@pytest.mark.parametrize("hal_initialised", [False, True])
def test_readiness_without_active_lab_profile_has_null_channel_emulator_binding(
    db, monkeypatch, hal_initialised
):
    # 有品类、有驱动，但一条 LabProfile 都没有 → lab_section.profile_id is None
    category = InstrumentCategory(
        category_key=CHANNEL_EMULATOR_CATEGORY_KEY,
        category_name="信道仿真器",
        driver_mode="real",
    )
    db.add(category)
    db.commit()
    _install_hal(monkeypatch, _f64(), report=_report(db) if hal_initialised else None)

    resp = client.get(READINESS_URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is hal_initialised
    assert body["lab_profile"]["profile_id"] is None
    # 键在（GUI 类型 `channel_emulator_binding: ... | null`），值为 null，不是缺键
    assert "channel_emulator_binding" in body
    assert body["channel_emulator_binding"] is None


# ----------------------------------------------------------------------
# 门 4：digest 一致性 —— readiness 复用 resolver 的 digest，不重算
# ----------------------------------------------------------------------


def test_readiness_digest_equals_resolver_digest(db, monkeypatch):
    _, _, _, lab = _configured(db)
    hal = _install_hal(monkeypatch, _f64(), report=_report(db))
    resolved = resolve_channel_emulator_binding(db, hal, lab)

    resp = client.get(READINESS_URL)

    assert resp.status_code == 200
    ce = resp.json()["channel_emulator_binding"]
    assert ce["binding_digest"] == resolved.binding_digest
    assert ce["resolved_binding"] == resolved.stable_projection()
    assert ce["resolved_binding"]["binding_digest"] == resolved.binding_digest


# ----------------------------------------------------------------------
# 门 5：两个构造点都带字段（HAL 未初始化 / 已初始化）+ 站点数与 BS 对等的结构不变量
# ----------------------------------------------------------------------


@pytest.mark.parametrize("hal_initialised", [False, True])
def test_channel_emulator_binding_present_on_both_construction_points(
    db, monkeypatch, hal_initialised
):
    _, _, _, lab = _configured(db)
    _install_hal(monkeypatch, _f64(), report=_report(db) if hal_initialised else None)

    resp = client.get(READINESS_URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is hal_initialised
    ce = body["channel_emulator_binding"]
    assert ce is not None, "该构造点漏传 channel_emulator_binding"
    assert ce["status"] == "configured"
    assert ce["lab_profile_id"] == str(lab.id)


def test_every_base_station_binding_construction_site_also_passes_channel_emulator_binding():
    """不变量：`HALReadinessResponse(...)` 的每个构造点，`base_station_binding=` 与
    `channel_emulator_binding=` 成对出现。新加第三个早返回支而漏传 CE 字段 → 这里红。"""

    source = inspect.getsource(instrument_api.get_hal_readiness)
    bs_sites = re.findall(r"\bbase_station_binding=", source)
    ce_sites = re.findall(r"\bchannel_emulator_binding=", source)
    assert len(bs_sites) >= 2, "readiness 端点应至少有两个响应构造点（HAL 未初始化 / 已初始化）"
    assert len(ce_sites) == len(bs_sites), (
        f"base_station_binding= 有 {len(bs_sites)} 处，channel_emulator_binding= 只有 {len(ce_sites)} 处"
    )


# ----------------------------------------------------------------------
# 门 6：邻居 base_station_binding 不受影响
# ----------------------------------------------------------------------


def test_base_station_binding_still_flows_next_to_channel_emulator_binding(db, monkeypatch):
    _, _, _, lab = _configured(db)
    _install_hal(monkeypatch, _f64(), report=_report(db))

    resp = client.get(READINESS_URL)

    assert resp.status_code == 200
    body = resp.json()
    bs = body["base_station_binding"]
    # 本测试没配 baseStation 品类 → BS 预览如实报 invalid；字段仍在同一响应里照旧流出
    assert bs is not None
    assert bs["status"] == "invalid"
    assert bs["lab_profile_id"] == str(lab.id)
    assert bs["detail"]
    assert "testcase_compatibility" in bs
    assert body["base_station_testcase_compatibility"]["lab_profile_id"] == str(lab.id)
    assert "cmw500_lte_2x2" in body
    # 两个 binding 字段并列，各说各的品类
    assert body["channel_emulator_binding"]["status"] == "configured"
