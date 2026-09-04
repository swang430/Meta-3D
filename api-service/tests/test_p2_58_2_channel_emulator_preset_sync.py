# -*- coding: utf-8 -*-
"""P2-58 ②（漂移堵完）：CE saved preset 与活动连接在 PUT 之外的写点上保持相等。

活动 ``connection_params`` 在 ``PUT /instruments/channelEmulator`` 之外的写点有四个：
W2 / W3 channel-models 增删（``api/instrument.py``，I 已接、I 的门守）、
**W4** ``standard_channel_service._sync_projection_for_binding``（SCD 关联投影，associate / delete 共用）、
**W5** ``smu_project_inventory.sync_smu_project_truth``（smu-sync）。本文件守：

1. W4 / W5 都把改动 ``synchronize_*`` 回写进当前型号的 saved preset（``connection_params`` 逐字节等于活动）；
   无 preset 时 no-op、不凭空建（建 preset 只走 ``save_*``）；
2. **本片的可观察故障本身**：F64 存 preset → smu-sync 写新清单 → 切 FS16 → 切回 F64，
   活动 ``available_channel_models`` 必须是 smu-sync 后那份，不是保存时的旧快照；
3. ``require_saved_active_channel_emulator_preset``：无 preset / 四个字段任一漂移 → 中文 ValueError；相等 → 通过；
4. sync-current 的 CE 分支接上了该检测器：无 preset → 422 + 回滚；保存后一致 → 200；带外漂移 → 422 + 回滚。

脚手架复用 ``tests/test_p2_58_channel_emulator_binding_api.py``（TestClient / ``get_db`` 覆盖 /
teardown 事务快照）与 ``tests/test_smu_project_inventory.py``（tmp_path 当只读 SMB 挂载 + vendor 资产建法）。
每条门都配过让它变红的变异并实跑，门↔变异↔结果表见 PR 描述。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.hal.channel_emulator import MockChannelEmulator
from app.main import app
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.services import instrument_hal_service
from app.services import standard_channel_service as scd_svc
from app.services.channel_asset_service import create_channel_asset
from app.services.channel_emulator_model_preset import (
    require_saved_active_channel_emulator_preset,
)
from app.services.smu_project_inventory import sync_smu_project_truth


CE_URL = "/api/v1/instruments/channelEmulator"
F64_ENDPOINT = "192.168.100.21:3334"
FS16_ENDPOINT = "TCPIP0::192.168.100.22::inst0::INSTR"
LEGACY_MODEL = "New GCM Model 5.smu"
SMU_RELATIVE = "pack/truth.smu"
SMU_WINDOWS_PATH = r"D:\Scenario Packs\pack\truth.smu"
_SCD_CONFIG = {
    "radio_technology": "nr5g",
    "channel_kind": "nr_arfcn",
    "band": "N78",
    "arfcn": 640000,
    "bandwidth_mhz": 100,
    "model": "CDLC",
    "scenario": "UMa",
    "mimo": "4x4",
    "polarization": "DP",
    "version": 1,
}


# ----------------------------------------------------------------------
# 脚手架（镜像 tests/test_p2_58_channel_emulator_binding_api.py）
# ----------------------------------------------------------------------

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#: 每个请求的 ``get_db`` 会话在 teardown 时是否还开着事务。fail-closed 分支要求「422 之前自己
#: rollback」—— 只看落库结果抓不到漏掉的 rollback（StaticPool 下会话 close 时也会隐式回滚），
#: 所以多记这一格（memory：假门第六种）。
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


def _active_params(root: Path) -> dict:
    """活动 F64 连接的参数：全是操作员 / 同步维护的型号配置资产，一个都不能丢。
    ``smu_project_scan`` 把 tmp_path 当只读 SMB 挂载（镜像 test_smu_project_inventory.py）。"""

    return {
        "timeout_sec": 30,
        "alignment_name": "CAICT_2026-08_n78",
        "smu_project_scan": {
            "local_mount_root": str(root),
            "instrument_root": r"D:\Scenario Packs",
        },
        "available_channel_models": [{"filename": LEGACY_MODEL, "label": "手敲存量"}],
    }


@pytest.fixture
def ce(db, tmp_path):
    """channelEmulator 品类（mock 模式）+ F64 / FS16 两型号 + 活动为 F64 的连接 + 空 binding 的 LabProfile；
    ``channel_emulator_model_presets`` 不设（= SQL NULL，与生产建行同形）。"""

    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
        driver_mode="mock",
    )
    db.add(category)
    db.flush()
    f64 = InstrumentModel(
        category_id=category.id, vendor="Keysight", model="PROPSIM F64", capabilities={}
    )
    fs16 = InstrumentModel(
        category_id=category.id, vendor="Keysight", model="PROPSIM FS16", capabilities={}
    )
    db.add_all([f64, fs16])
    db.flush()
    category.selected_model_id = f64.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint=F64_ENDPOINT,
        controller_ip="192.168.100.21",
        port=3334,
        protocol="socket",
        notes="现场 F64",
        connection_params=_active_params(tmp_path),
        created_by="test",
    )
    lab = LabProfile(name=f"lab-{uuid.uuid4()}", instrument_bindings=[])
    db.add_all([connection, lab])
    db.commit()
    return SimpleNamespace(
        category_id=category.id,
        connection_id=connection.id,
        f64_id=f64.id,
        fs16_id=fs16.id,
        lab_id=lab.id,
        root=tmp_path,
    )


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _filenames(entries) -> list[str]:
    return [e["filename"] if isinstance(e, dict) else e for e in entries]


def _load(db, ce):
    """每次都先 expire：TestClient 走的是另一个会话，identity map 里的旧值不是真值。"""

    db.expire_all()
    category = db.get(InstrumentCategory, ce.category_id)
    connection = db.get(InstrumentConnection, ce.connection_id)
    return category, connection


def _saved_preset(connection, model_id):
    return (connection.channel_emulator_model_presets or {}).get(str(model_id))


def _save_active_as_preset() -> None:
    """经正门 PUT 把活动连接原样存成当前型号的 preset（空 ``connection`` = 四级回退第三级）。"""

    saved = client.put(CE_URL, json={"connection": {}})
    assert saved.status_code == 200, saved.text


def _switch_model(model_id, connection_body: dict) -> None:
    switched = client.put(
        CE_URL, json={"modelId": str(model_id), "connection": connection_body}
    )
    assert switched.status_code == 200, switched.text


def _write_smu(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _register_vendor_asset(db):
    """一条 vendor_file 资产，完整 F64 路径精确等于扫描到的工程（smu-sync 唯一会写的形态）。"""

    return create_channel_asset(
        db,
        name="truth",
        source_type="vendor_file",
        payload={"scd_config": {**_SCD_CONFIG, "version": 7}},
        associated_file_path=SMU_WINDOWS_PATH,
        center_frequency_hz=3_600_000_000,
        bandwidth_mhz=100,
        instrument_connection_id=None,
    )


def _create_scd(db, connection_id):
    return scd_svc.create_scd(
        db,
        instrument_connection_id=connection_id,
        radio_technology="nr5g",
        channel_kind="nr_arfcn",
        band="N78",
        arfcn=640000,
        lte_dl_earfcn=None,
        bandwidth_mhz=100,
        model="CDLC",
        scenario="UMa",
        mimo="4x4",
        polarization="DP",
        version=3,
    )


def _scd_ids(entries) -> list[str]:
    return [e["scd_id"] for e in entries if isinstance(e, dict) and e.get("scd_id")]


def _sync_url(lab_id) -> str:
    return f"/api/v1/lab-profiles/{lab_id}/instrument-bindings/channelEmulator/sync-current"


def _patch_mock_hal(monkeypatch) -> None:
    """端点内部是延迟 ``from app.services.instrument_hal_service import get_hal_service``，
    改模块属性即生效；品类是 mock 模式，装 Mock 驱动即可让 resolver 走 simulated 分支。"""

    hal = SimpleNamespace(drivers={"channelEmulator": MockChannelEmulator("ce", {})})
    monkeypatch.setattr(instrument_hal_service, "get_hal_service", lambda: hal)


# ----------------------------------------------------------------------
# 门 1：W4 —— SCD 关联 / 删除的投影写活动清单，preset 同步；无 preset 则 no-op
# ----------------------------------------------------------------------


def test_scd_projection_mirrors_into_saved_active_preset_on_associate_and_delete(db, ce):
    """有 F64 preset → associate 把 SCD 派生条目写进活动 ``available_channel_models``，
    preset 的 ``connection_params`` 与活动逐字节相等（endpoint / notes 不动）；
    delete 走同一个 W4 写点，派生条目从两边一起消失、存量手敲条目两边都在。
    变异：删 ``_sync_projection_for_binding`` 里的 ``synchronize_*`` 调用 → preset 仍是保存时的清单 → 红。"""

    _save_active_as_preset()
    scd = _create_scd(db, ce.connection_id)
    scd_svc.associate_file(
        db, scd.id, file_path="customer_channel.smu", association_source="vendor_associated"
    )

    _, connection = _load(db, ce)
    active = connection.connection_params["available_channel_models"]
    assert _scd_ids(active) == [str(scd.id)]
    preset = _saved_preset(connection, ce.f64_id)
    assert preset is not None
    assert _canonical(preset["connection_params"]) == _canonical(connection.connection_params)
    assert preset["endpoint"] == F64_ENDPOINT
    assert preset["controller"] == "socket"
    assert preset["notes"] == "现场 F64"

    scd_svc.delete_scd(db, scd.id)

    _, connection = _load(db, ce)
    assert _filenames(connection.connection_params["available_channel_models"]) == [LEGACY_MODEL]
    preset = _saved_preset(connection, ce.f64_id)
    assert _scd_ids(preset["connection_params"]["available_channel_models"]) == []
    assert _canonical(preset["connection_params"]) == _canonical(connection.connection_params)


def test_scd_projection_without_saved_preset_stays_a_no_op(db, ce):
    """从未存过 preset：associate 照常写活动清单，``channel_emulator_model_presets`` 仍是 NULL ——
    不凭空建 preset（建 preset 只走 ``save_*``；首次切型号的快照分支会带上，I 的 API 门 7 钉住）。
    变异：``synchronize_*`` 在无 preset 时凭活动连接建 preset → 不再是 None → 红。"""

    scd = _create_scd(db, ce.connection_id)
    scd_svc.associate_file(
        db, scd.id, file_path="customer_channel.smu", association_source="vendor_associated"
    )

    _, connection = _load(db, ce)
    assert connection.channel_emulator_model_presets is None
    assert _scd_ids(connection.connection_params["available_channel_models"]) == [str(scd.id)]


# ----------------------------------------------------------------------
# 门 2：W5 —— smu-sync 写活动清单，preset 同步；无 preset 则 no-op
# ----------------------------------------------------------------------


def _sync_one_project(db, ce):
    _write_smu(
        ce.root / SMU_RELATIVE,
        "[Channel Group 0]\nCenterFrequency=3549990000 Hz\n",
    )
    asset = _register_vendor_asset(db)
    result = sync_smu_project_truth(db)
    assert result.updated_count == 1, result
    return asset


def test_smu_sync_mirrors_into_saved_active_preset(db, ce):
    """有 F64 preset → smu-sync 把工程真值写进活动 ``available_channel_models``（带 ``channel_asset_id``），
    preset 的 ``connection_params`` 与活动逐字节相等，``alignment_name`` 等其它键原样。
    变异：删 ``sync_smu_project_truth`` 里的 ``synchronize_*`` 调用 → preset 仍是保存时的清单 → 红。"""

    _save_active_as_preset()
    asset = _sync_one_project(db, ce)

    _, connection = _load(db, ce)
    active = connection.connection_params["available_channel_models"]
    synced = next(
        e for e in active if isinstance(e, dict) and e.get("filename") == SMU_WINDOWS_PATH
    )
    assert synced["channel_asset_id"] == str(asset.id)
    preset = _saved_preset(connection, ce.f64_id)
    assert preset is not None
    assert _canonical(preset["connection_params"]) == _canonical(connection.connection_params)
    assert preset["connection_params"]["alignment_name"] == "CAICT_2026-08_n78"
    assert preset["endpoint"] == F64_ENDPOINT and preset["notes"] == "现场 F64"


def test_smu_sync_without_saved_preset_stays_a_no_op(db, ce):
    """从未存过 preset：smu-sync 照常写活动清单，``channel_emulator_model_presets`` 仍是 NULL。
    变异：同门 1b。"""

    _sync_one_project(db, ce)

    _, connection = _load(db, ce)
    assert connection.channel_emulator_model_presets is None
    assert SMU_WINDOWS_PATH in _filenames(connection.connection_params["available_channel_models"])


# ----------------------------------------------------------------------
# 门 3：往返不丢 —— 本片的可观察故障本身
# ----------------------------------------------------------------------


def test_model_switch_round_trip_restores_post_sync_channel_models_not_the_stale_snapshot(
    db, ce
):
    """F64 存 preset（清单只有存量手敲那条）→ smu-sync 写进工程真值 → 切 FS16 保存 → 只发
    ``{modelId: F64, connection: {}}`` 切回 → 活动 ``available_channel_models`` == smu-sync 后那份
    （含 ``channel_asset_id`` 条目），不是保存时的旧快照。
    变异：W5 不回写 → 切回 F64 时 preset 把旧快照投影成活动真值 → smu-sync 结果丢失 → 红。"""

    _save_active_as_preset()
    _, connection = _load(db, ce)
    snapshot = _saved_preset(connection, ce.f64_id)["connection_params"]["available_channel_models"]
    assert _filenames(snapshot) == [LEGACY_MODEL]

    asset = _sync_one_project(db, ce)
    _, connection = _load(db, ce)
    post_sync = connection.connection_params["available_channel_models"]
    assert set(_filenames(post_sync)) == {LEGACY_MODEL, SMU_WINDOWS_PATH}
    post_sync_canonical = _canonical(post_sync)

    _switch_model(
        ce.fs16_id,
        {
            "endpoint": FS16_ENDPOINT,
            "controller": "visa",
            "notes": "FS16",
            "connection_params": {"timeout_sec": 10},
        },
    )
    category, connection = _load(db, ce)
    assert category.selected_model_id == ce.fs16_id
    assert connection.connection_params == {"timeout_sec": 10}

    _switch_model(ce.f64_id, {})
    category, connection = _load(db, ce)
    assert category.selected_model_id == ce.f64_id
    assert connection.endpoint == F64_ENDPOINT
    restored = connection.connection_params["available_channel_models"]
    assert _canonical(restored) == post_sync_canonical
    assert any(
        isinstance(e, dict) and e.get("channel_asset_id") == str(asset.id) for e in restored
    )
    assert connection.connection_params["alignment_name"] == "CAICT_2026-08_n78"


# ----------------------------------------------------------------------
# 门 4：require_saved_active_channel_emulator_preset
# ----------------------------------------------------------------------


def test_require_saved_preset_rejects_missing_then_each_drifted_field_and_accepts_equal(db, ce):
    """无 preset → ValueError（中文「没有已保存配置」）；保存后活动 == preset → 返回该 preset；
    endpoint / controller / notes / connection_params 任一在内存里漂掉 → ValueError，
    消息含「不一致」「请重新保存后再同步」且**只**点名漂移的那一个字段。
    变异：删任一字段的相等性比对 → 该字段的漂移用例不再抛 → 红。"""

    f64 = db.get(InstrumentModel, ce.f64_id)
    _, connection = _load(db, ce)
    with pytest.raises(ValueError, match="没有已保存配置"):
        require_saved_active_channel_emulator_preset(model=f64, connection=connection)

    _save_active_as_preset()
    _, connection = _load(db, ce)
    f64 = db.get(InstrumentModel, ce.f64_id)
    preset = require_saved_active_channel_emulator_preset(model=f64, connection=connection)
    assert preset.model_id == ce.f64_id
    assert preset.endpoint == F64_ENDPOINT
    assert _canonical(preset.connection_params) == _canonical(connection.connection_params)

    drifts = {
        "endpoint": lambda c: setattr(c, "endpoint", "192.168.100.99:3334"),
        "controller": lambda c: setattr(c, "protocol", "visa"),
        "notes": lambda c: setattr(c, "notes", "带外改的备注"),
        "connection_params": lambda c: setattr(
            c, "connection_params", {**c.connection_params, "alignment_name": "other"}
        ),
    }
    for field, drift in drifts.items():
        # 每次从库里的真值出发，只在内存里漂一个字段，不落库
        db.rollback()
        _, connection = _load(db, ce)
        f64 = db.get(InstrumentModel, ce.f64_id)
        drift(connection)
        with pytest.raises(ValueError) as exc:
            require_saved_active_channel_emulator_preset(model=f64, connection=connection)
        message = str(exc.value)
        assert "不一致" in message and "请重新保存后再同步" in message, message
        assert [name for name in drifts if name in message] == [field], message
    db.rollback()


# ----------------------------------------------------------------------
# 门 5：sync-current 的 CE 分支接线
# ----------------------------------------------------------------------


def test_sync_current_channel_emulator_requires_saved_preset_and_detects_out_of_band_drift(
    db, ce, monkeypatch
):
    """(1) 无 preset → 422「没有已保存配置」+ 请求会话到 teardown 已不在事务里 + binding 不落库；
    (2) 经正门保存后活动 == preset → 200，binding 落库、型号 / endpoint 取自品类真值；
    (3) 绕过 ``synchronize_*`` 直接改活动 ``connection_params``（带外写方）→ 422「不一致」
    点名 ``connection_params`` + 回滚，清空过的 binding 仍是空。
    变异：删 lab_profile.py CE 分支的 ``require_saved_*`` 调用 → (1) 变 200 → 红。"""

    _patch_mock_hal(monkeypatch)

    # (1)
    response = client.put(_sync_url(ce.lab_id))
    assert response.status_code == 422, response.text
    assert "没有已保存配置" in response.json()["detail"]
    assert _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN == [False]
    db.expire_all()
    assert db.get(LabProfile, ce.lab_id).instrument_bindings == []

    # (2)
    _save_active_as_preset()
    _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN.clear()
    response = client.put(_sync_url(ce.lab_id))
    assert response.status_code == 200, response.text
    binding = response.json()["binding"]
    assert binding["instrument_model_id"] == str(ce.f64_id)
    assert binding["connection_endpoint"] == F64_ENDPOINT
    assert binding["driver_mode"] == "mock"
    db.expire_all()
    lab = db.get(LabProfile, ce.lab_id)
    assert len(lab.instrument_bindings) == 1
    assert lab.instrument_bindings[0] == binding

    # (3) 先把 binding 清空，让「422 后 binding 仍是空」成为真断言（否则同一条 binding 重写一遍也看不出）
    _, connection = _load(db, ce)
    lab = db.get(LabProfile, ce.lab_id)
    lab.instrument_bindings = []
    connection.connection_params = {**connection.connection_params, "alignment_name": "带外改的"}
    db.commit()
    db.expire_all()
    assert db.get(LabProfile, ce.lab_id).instrument_bindings == []  # 前置：清空确实落库了
    _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN.clear()
    response = client.put(_sync_url(ce.lab_id))
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "不一致" in detail and "connection_params" in detail and "请重新保存后再同步" in detail
    assert _REQUEST_SESSION_OPEN_TX_AT_TEARDOWN == [False]
    db.expire_all()
    assert db.get(LabProfile, ce.lab_id).instrument_bindings == []
