# -*- coding: utf-8 -*-
"""P2-58 ①：`api/lab_profile.py` 接 channelEmulator resolver 的 API 门。

覆盖两处接线：
- `GET /lab-profiles/{id}/instrument-bindings/channelEmulator/preview`（只读预览）
- `PUT /lab-profiles/{id}/instrument-bindings/channelEmulator/sync-current`
  的 channelEmulator 分支（保存即解析、解析不通 422 + 回滚；响应 `resolved` 刻意不扩）

脚手架：建数写法复用 `tests/test_p2_58_channel_emulator_binding.py`（resolver 门），
TestClient / `get_db` 覆盖写法复用 `tests/test_lab_profile_api.py`。
每条门在 PR 里都配了一条让它变红的变异并实跑过（见 PR 描述的变异表）。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.main import app
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase
from app.schemas.channel_emulator_binding import ChannelEmulatorBindingPreviewResponse
from app.services import instrument_hal_service


# ----------------------------------------------------------------------
# 脚手架（镜像 tests/test_lab_profile_api.py）
# ----------------------------------------------------------------------

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#: 每个请求的 `get_db` 会话在 teardown 时是否还开着事务。
#: 保存路径的 fail-closed 分支要求「422 之前自己 rollback」——只看落库结果抓不到
#: 漏掉的 rollback（会话 close 时连接归池也会隐式回滚），所以在这里多记一格。
_REQUEST_SESSION_OPEN_TX_AT_TEARDOWN: list[bool] = []


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN.append(db.in_transaction())
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN.clear()
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if prev is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = prev
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ----------------------------------------------------------------------
# 建数（复用 Agent A 的 `_configured` 写法，别另起一套）
# ----------------------------------------------------------------------


def _configured(
    db,
    *,
    model_name: str = "PROPSIM F64",
    driver_mode: str = "real",
    endpoint: str = "192.0.2.10",
    category_key: str = "channelEmulator",
    bindings=None,
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
    if bindings is None:
        bindings = [
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": endpoint,
                "driver_mode": driver_mode,
                "role": "primary_channel_emulator",
            }
        ]
    lab = LabProfile(
        name=f"lab-{uuid.uuid4()}",
        instrument_bindings=bindings,
    )
    db.add_all([connection, lab])
    db.commit()
    return category, model, connection, lab


def _f64(endpoint: str = "192.0.2.10", instrument_id: str = "ce"):
    return RealPropsimF64Driver(instrument_id, {"ip_address": endpoint})


def _mock(instrument_id: str = "ce"):
    return MockChannelEmulator(instrument_id, {})


def _hal(driver):
    return SimpleNamespace(drivers={} if driver is None else {"channelEmulator": driver})


def _patch_hal(monkeypatch, driver):
    """端点内部是延迟 `from app.services.instrument_hal_service import get_hal_service`，
    改模块属性即生效。"""

    hal = _hal(driver)
    monkeypatch.setattr(instrument_hal_service, "get_hal_service", lambda: hal)
    return hal


def _forbid_io(monkeypatch, driver):
    """任何 transport / SCPI 入口一旦被碰就 fail —— 验证打在真实生效端。"""

    for name in ("connect", "_query", "_write", "_do_query", "_do_write", "query", "write"):
        if hasattr(driver, name):
            monkeypatch.setattr(
                driver,
                name,
                lambda *a, _n=name, **k: pytest.fail(f"预览端点触发了仪器 I/O：{_n}"),
            )


def _mimo_ota_case(db, lab, configuration: dict) -> TestCase:
    case = TestCase(
        name=f"ce-preview-{uuid.uuid4()}",
        test_type="MIMO_OTA",
        configuration=configuration,
        created_by="test",
        lab_profile_id=lab.id,
    )
    db.add(case)
    db.commit()
    return case


def _preview_url(lab_id) -> str:
    return f"/api/v1/lab-profiles/{lab_id}/instrument-bindings/channelEmulator/preview"


def _sync_url(lab_id) -> str:
    return f"/api/v1/lab-profiles/{lab_id}/instrument-bindings/channelEmulator/sync-current"


def _save_active_channel_emulator_preset() -> None:
    """P2-58 ②：sync-current 的 CE 分支现在要求活动连接有当前型号的 saved preset（无则 422），
    所以两条 sync-current 用例先经正门 ``PUT /instruments/channelEmulator`` 保存一次。
    空 ``connection`` = 把活动连接原样存成当前型号的 preset（四级回退第三级，② API 门 3 钉住）。
    这个 PUT 自己也是一次请求会话，清掉它留下的 teardown 快照，让用例里的断言仍只看
    sync-current 那一个请求 —— 只改 setup，不改断言语义。"""

    saved = client.put("/api/v1/instruments/channelEmulator", json={"connection": {}})
    assert saved.status_code == 200, saved.text
    _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN.clear()


# ----------------------------------------------------------------------
# 门 1：GET 预览合法配置 → 200 configured，selected_asset_id 为 null，零仪器 I/O
# ----------------------------------------------------------------------


def test_preview_configured_binding_returns_projection_without_selected_asset(db, monkeypatch):
    _, model, connection, lab = _configured(db)
    driver = _f64()
    _forbid_io(monkeypatch, driver)
    _patch_hal(monkeypatch, driver)

    response = client.get(_preview_url(lab.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "configured"
    assert body["execution_mode"] == "real"
    assert body["adapter_id"] == "propsim_f64"
    assert body["model_name"] == "PROPSIM F64"
    assert body["instrument_model_id"] == str(model.id)
    assert body["instrument_connection_id"] == str(connection.id)
    assert body["lab_profile_id"] == str(lab.id)
    assert body["binding_digest"]
    assert body["resolved_binding"]["binding_digest"] == body["binding_digest"]
    assert body["runtime_driver"]["adapter_id"] == "propsim_f64"
    assert body["selected_asset_id"] is None
    # 响应键集合 == 公开 schema 字段集合（不多不少，extra=forbid 的另一半）
    assert set(body) == set(ChannelEmulatorBindingPreviewResponse.model_fields)


# ----------------------------------------------------------------------
# 门 2：test_case_id → selected_asset_id 附带、不进 digest；缺省 null；不存在 404
# ----------------------------------------------------------------------


def test_preview_attaches_test_case_channel_asset_without_changing_digest(db, monkeypatch):
    _, _, _, lab = _configured(db)
    _patch_hal(monkeypatch, _f64())
    with_asset = _mimo_ota_case(db, lab, {"channel_asset_id": "asset-7f3c"})
    without_asset = _mimo_ota_case(db, lab, {"component_carriers": []})

    plain = client.get(_preview_url(lab.id))
    selected = client.get(_preview_url(lab.id), params={"test_case_id": str(with_asset.id)})
    unselected = client.get(
        _preview_url(lab.id), params={"test_case_id": str(without_asset.id)}
    )

    assert selected.status_code == 200, selected.text
    assert selected.json()["selected_asset_id"] == "asset-7f3c"
    assert unselected.status_code == 200, unselected.text
    assert unselected.json()["selected_asset_id"] is None
    assert plain.status_code == 200, plain.text
    assert plain.json()["selected_asset_id"] is None
    # selected asset 是 per-TestCase 的，不是 LabProfile 真值：digest 三次必须一样
    digests = {plain.json()["binding_digest"], selected.json()["binding_digest"],
               unselected.json()["binding_digest"]}
    assert len(digests) == 1 and None not in digests
    # 除 selected_asset_id 外其余字段逐字相同
    strip = lambda body: {k: v for k, v in body.items() if k != "selected_asset_id"}  # noqa: E731
    assert strip(selected.json()) == strip(plain.json()) == strip(unselected.json())


def test_preview_unknown_test_case_is_404_not_a_swallowed_null(db, monkeypatch):
    _, _, _, lab = _configured(db)
    _patch_hal(monkeypatch, _f64())

    response = client.get(_preview_url(lab.id), params={"test_case_id": str(uuid.uuid4())})

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "TestCase not found"


# ----------------------------------------------------------------------
# 门 3：解析失败 → 200 + status=invalid + 中文 detail（不是 500）
# ----------------------------------------------------------------------


def test_preview_reports_invalid_with_reason_instead_of_500(db, monkeypatch):
    _, _, _, lab = _configured(db)
    lab.instrument_bindings = []
    db.commit()
    _patch_hal(monkeypatch, _f64())

    response = client.get(_preview_url(lab.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "invalid"
    assert body["binding_digest"] is None
    assert body["execution_mode"] is None
    assert body["resolved_binding"] is None
    assert body["runtime_driver"] is None
    assert body["lab_profile_id"] == str(lab.id)
    assert body["selected_asset_id"] is None
    assert "LabProfile 必须恰好包含一条 channelEmulator binding（当前 0 条）" in body["detail"]


# ----------------------------------------------------------------------
# 门 4：保存路径 fail-closed —— 解析不通 → 422 + 回滚，binding 不落库
# ----------------------------------------------------------------------


def _stale_bindings(category, keep_row):
    return [
        keep_row,
        {
            "category_id": str(category.id),
            "instrument_model_id": None,
            "connection_endpoint": "stale-endpoint",
            "driver_mode": "auto",
            "role": "primary_channelEmulator",
        },
    ]


_KEEP_ROW = {
    "category_id": str(uuid.uuid4()),
    "instrument_model_id": str(uuid.uuid4()),
    "connection_endpoint": "keep-me",
    "driver_mode": "auto",
    "role": "other",
}


def test_sync_current_rejects_unresolvable_channel_emulator_binding_and_rolls_back(
    db, monkeypatch
):
    category, _, _, lab = _configured(db, driver_mode="real", bindings=[])
    lab.instrument_bindings = _stale_bindings(category, _KEEP_ROW)
    db.commit()
    before = [dict(row) for row in lab.instrument_bindings]
    # 品类显式 real，HAL 里装的却是 mock → resolver 拒绝（真值不一致）
    _patch_hal(monkeypatch, _mock())

    _save_active_channel_emulator_preset()
    response = client.put(_sync_url(lab.id))

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        "装载的驱动模式（mock）与品类显式的 real 驱动模式不一致"
    )
    db.expire_all()
    db.refresh(lab)
    assert lab.instrument_bindings == before
    # 422 之前必须已经 rollback：请求会话到 teardown 时不能还开着带脏写的事务
    assert _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN == [False]


# ----------------------------------------------------------------------
# 门 5：保存路径合法 → 200，binding 落库，`resolved` 刻意保持 null（不扩契约）
# ----------------------------------------------------------------------


def test_sync_current_persists_channel_emulator_binding_and_keeps_resolved_null(
    db, monkeypatch
):
    category, model, _, lab = _configured(db, driver_mode="real", bindings=[])
    lab.instrument_bindings = _stale_bindings(category, _KEEP_ROW)
    db.commit()
    _patch_hal(monkeypatch, _f64())

    _save_active_channel_emulator_preset()
    response = client.put(_sync_url(lab.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["binding"] == {
        "category_id": str(category.id),
        "instrument_model_id": str(model.id),
        "connection_endpoint": "192.0.2.10",
        "driver_mode": "real",
        "role": "primary_channelEmulator",
    }
    # 有意收窄：`resolved` / `testcase_compatibility` 是 BaseStation 形态，CE 不往里塞
    assert body["resolved"] is None
    assert body["testcase_compatibility"] is None
    db.expire_all()
    db.refresh(lab)
    assert len(lab.instrument_bindings) == 2
    assert lab.instrument_bindings[0] == _KEEP_ROW
    assert lab.instrument_bindings[1] == body["binding"]

    # 保存出的 binding 立刻能被预览端点按同一真值解析
    preview = client.get(_preview_url(lab.id))
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "configured"
    assert preview.json()["instrument_model_id"] == str(model.id)
    assert preview.json()["binding_digest"]


# ----------------------------------------------------------------------
# 门 6：LabProfile 不存在 → 404
# ----------------------------------------------------------------------


def test_preview_unknown_lab_profile_is_404(monkeypatch):
    _patch_hal(monkeypatch, _f64())

    response = client.get(_preview_url(uuid.uuid4()))

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "LabProfile not found"
