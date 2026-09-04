"""P2-58 ②（API 接线 + 契约前两步）：信道仿真器分型号 preset 经 ``PUT /instruments/channelEmulator``
落库、响应序列化、四级回退、不双写、channel-models 增删回写 preset、契约三面镜像。

镜像 ``test_base_station_atomic_model_save.py`` 与 ``test_base_station_model_preset_openapi.py``
（后者去掉手写 ``gui/src/types/api.ts`` 那一面 —— 归前端片）。每条门都配过让它变红的变异，
门↔变异↔结果表见 PR 描述。
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.instrument as instrument_api
import app.services.channel_emulator_model_preset as preset_module
from app.db.database import Base, get_db
from app.main import app
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CE_URL = "/api/v1/instruments/channelEmulator"
F64_ENDPOINT = "192.168.100.21:3334"
FS16_ENDPOINT = "TCPIP0::192.168.100.22::inst0::INSTR"
PRESET_FIELDS = {
    "schema_version",
    "model_id",
    "endpoint",
    "controller",
    "notes",
    "connection_params",
}
NEW_MODEL = "3GPP_5GNR_TDLC300.smu"
OLD_MODEL = "3GPP_5GNR_1x1_TDLA30-5.smu"


def _f64_params() -> dict:
    """活动 F64 连接的参数：全是操作员 / 同步维护的型号配置资产，一个都不能丢。"""

    return {
        "timeout_sec": 30,
        "alignment_name": "CAICT_2026-08_n78",
        "available_channel_models": [
            {"filename": OLD_MODEL, "radio_technology": "nr5g"},
            "New GCM Model 5.smu",
        ],
        "default_emulation_file": "New GCM Model 5.smu",
    }


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _filenames(entries) -> list[str]:
    return [e["filename"] if isinstance(e, dict) else e for e in entries]


@pytest.fixture
def ce_api_db():
    """内存 SQLite + ``get_db`` 覆盖：channelEmulator 品类、F64 / FS16 两型号、活动为 F64 的连接，
    ``channel_emulator_model_presets`` 不设（= SQL NULL，与生产建行同形）。"""

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()
    category = InstrumentCategory(
        id=uuid4(),
        category_key="channelEmulator",
        category_name="信道仿真器",
        driver_mode="mock",
        is_active=True,
    )
    f64 = InstrumentModel(
        id=uuid4(),
        category_id=category.id,
        vendor="Keysight",
        model="PROPSIM F64",
        capabilities={},
        is_available=True,
    )
    fs16 = InstrumentModel(
        id=uuid4(),
        category_id=category.id,
        vendor="Keysight",
        model="PROPSIM FS16",
        capabilities={},
        is_available=True,
    )
    category.selected_model_id = f64.id
    connection = InstrumentConnection(
        id=uuid4(),
        category_id=category.id,
        endpoint=F64_ENDPOINT,
        controller_ip="192.168.100.21",
        port=3334,
        protocol="socket",
        notes="现场 F64",
        connection_params=_f64_params(),
        created_by="test",
    )
    db.add_all([category, f64, fs16, connection])
    db.commit()
    ids = {
        "category": category.id,
        "connection": connection.id,
        "f64": f64.id,
        "fs16": fs16.id,
    }
    db.close()

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield Session, ids
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        Base.metadata.drop_all(engine)
        engine.dispose()


def _load(db, ids):
    category = db.get(InstrumentCategory, ids["category"])
    connection = (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.category_id == ids["category"])
        .one()
    )
    return category, connection


def _f64_body(ids) -> dict:
    return {
        "modelId": str(ids["f64"]),
        "connection": {
            "endpoint": F64_ENDPOINT,
            "controller": "socket",
            "notes": "保存时的 F64",
            "connection_params": _f64_params(),
        },
    }


def _fs16_body(ids) -> dict:
    return {
        "modelId": str(ids["fs16"]),
        "connection": {
            "endpoint": FS16_ENDPOINT,
            "controller": "visa",
            "notes": "FS16",
            "connection_params": {"timeout_sec": 10},
        },
    }


def _nr_model_payload(filename: str) -> dict:
    return {
        "filename": filename,
        "radio_technology": "nr5g",
        "channel_kind": "nr_arfcn",
        "band": "N78",
        "nr_arfcn": 640000,
    }


# ---------------------------------------------------------------------------
# 门 1：PUT 落库 + 响应序列化 + 响应路径 fail-loud
# ---------------------------------------------------------------------------


def test_put_persists_presets_and_response_carries_serialized_map(ce_api_db):
    """PUT 带 model + connection → 200；响应 ``connection.channel_emulator_model_presets[model_id]``
    是六字段 JSON dict（``model_id`` 为 str）；``GET /instruments/catalog`` 同样带出；库里存坏的 map
    经 ``_convert_connection`` 大声失败（``parse_*`` 接在响应路径上），不静默放行。
    变异：``_convert_connection`` 不接该字段 → 响应恒 ``{}`` → 红；跳过 ``parse_*`` 直传库里原值 →
    坏 map 不再抛 → 红。
    """

    Session, ids = ce_api_db
    with TestClient(app) as client:
        response = client.put(CE_URL, json=_f64_body(ids))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["selectedModelId"] == str(ids["f64"])
        presets = body["connection"]["channel_emulator_model_presets"]
        assert set(presets) == {str(ids["f64"])}
        preset = presets[str(ids["f64"])]
        assert set(preset) == PRESET_FIELDS
        assert preset["schema_version"] == 1
        assert preset["model_id"] == str(ids["f64"])
        assert preset["endpoint"] == F64_ENDPOINT
        assert preset["controller"] == "socket"
        assert preset["notes"] == "保存时的 F64"
        assert _canonical(preset["connection_params"]) == _canonical(_f64_params())

        catalog = client.get("/api/v1/instruments/catalog")
        assert catalog.status_code == 200, catalog.text
        ce = next(
            c for c in catalog.json()["categories"] if c["key"] == "channelEmulator"
        )
        assert ce["connection"]["channel_emulator_model_presets"] == presets

    with Session() as db:
        _category, connection = _load(db, ids)
        assert _canonical(connection.channel_emulator_model_presets) == _canonical(presets)
        # 库里键与 model_id 不一致 → 响应路径必须大声失败（中文 ValueError），不能带着坏 map 200
        connection.channel_emulator_model_presets = {"not-the-id": preset}
        with pytest.raises(ValueError, match="信道仿真器"):
            instrument_api._convert_connection(connection)


# ---------------------------------------------------------------------------
# 门 2：切型号保存不覆盖另一型号
# ---------------------------------------------------------------------------


def test_switch_save_keeps_other_model_bytes_and_projects_target(ce_api_db):
    """F64 存后切 FS16 存 → F64 项逐字节不变、FS16 项出现、活动字段投影成 FS16。

    额外钉死「已存过就不重新快照」（镜像 H 的服务层门 2）：存完 F64 后直接把库里活动连接的
    notes 改掉（模拟一个带外写方），切到 FS16 时 F64 preset 仍是保存时那份，不是活动侧现值。
    没有这一步，「整张 map 重写」的变异会被 ``save_*`` 的快照分支掩盖 —— 它把恰好等于已存
    preset 的活动连接重新快照回来，字节相同、门恒绿（首版实跑就是这样）。
    变异：CE 块调 ``save_*`` 前把整张 map 置空（整张重写）→ F64 项变成活动侧快照 → 红。"""

    Session, ids = ce_api_db
    with TestClient(app) as client:
        assert client.put(CE_URL, json=_f64_body(ids)).status_code == 200
        with Session() as db:
            _category, connection = _load(db, ids)
            f64_saved = _canonical(
                connection.channel_emulator_model_presets[str(ids["f64"])]
            )
            connection.notes = "活动侧未保存的改动"
            db.commit()
        response = client.put(CE_URL, json=_fs16_body(ids))
        assert response.status_code == 200, response.text

    with Session() as db:
        category, connection = _load(db, ids)
        presets = connection.channel_emulator_model_presets
        assert set(presets) == {str(ids["f64"]), str(ids["fs16"])}
        assert _canonical(presets[str(ids["f64"])]) == f64_saved
        assert presets[str(ids["f64"])]["notes"] == "保存时的 F64"
        assert category.selected_model_id == ids["fs16"]
        assert connection.endpoint == FS16_ENDPOINT
        assert connection.controller_ip == "192.168.100.22"
        assert connection.port is None
        assert connection.protocol == "visa"
        assert connection.notes == "FS16"
        assert connection.connection_params == {"timeout_sec": 10}


# ---------------------------------------------------------------------------
# 门 3：四级回退（请求 → 目标 preset → 活动连接 → 空）
# ---------------------------------------------------------------------------


def test_missing_request_fields_fall_back_to_saved_preset_then_active_connection(ce_api_db):
    """(b) 从未存过 preset，只发 ``{connection: {notes}}`` → 目标 = 活动 F64，endpoint / controller /
    params 取活动连接（第三级），并由此建出 F64 的首个 preset；
    (a) F64 / FS16 都存过后，只发 ``{modelId: F64, connection: {}}`` → 活动字段 = F64 保存时那份（第二级）。
    变异：删 endpoint 的「有 preset 用 preset」级 → (a) endpoint 落空 → 422 → 红；
    删「活动型号用活动连接」级 → (b) 422 → 红。"""

    Session, ids = ce_api_db
    with TestClient(app) as client:
        # (b)：此刻 presets 还是 NULL
        response = client.put(CE_URL, json={"connection": {"notes": "改备注"}})
        assert response.status_code == 200, response.text
        with Session() as db:
            category, connection = _load(db, ids)
            assert category.selected_model_id == ids["f64"]
            assert connection.endpoint == F64_ENDPOINT
            assert connection.controller_ip == "192.168.100.21"
            assert connection.port == 3334
            assert connection.protocol == "socket"
            assert connection.notes == "改备注"
            assert _canonical(connection.connection_params) == _canonical(_f64_params())
            first = connection.channel_emulator_model_presets[str(ids["f64"])]
            assert first["endpoint"] == F64_ENDPOINT
            assert first["controller"] == "socket"
            assert first["notes"] == "改备注"
            assert _canonical(first["connection_params"]) == _canonical(_f64_params())

        # (a)
        assert client.put(CE_URL, json=_f64_body(ids)).status_code == 200
        assert client.put(CE_URL, json=_fs16_body(ids)).status_code == 200
        response = client.put(
            CE_URL, json={"modelId": str(ids["f64"]), "connection": {}}
        )
        assert response.status_code == 200, response.text

    with Session() as db:
        category, connection = _load(db, ids)
        assert category.selected_model_id == ids["f64"]
        assert connection.endpoint == F64_ENDPOINT
        assert connection.controller_ip == "192.168.100.21"
        assert connection.port == 3334
        assert connection.protocol == "socket"
        assert connection.notes == "保存时的 F64"
        assert _canonical(connection.connection_params) == _canonical(_f64_params())
        assert set(connection.channel_emulator_model_presets) == {
            str(ids["f64"]),
            str(ids["fs16"]),
        }


# ---------------------------------------------------------------------------
# 门 4：不双写 —— CE 块以 return 结尾，通用路径不再跑
# ---------------------------------------------------------------------------


def test_channel_emulator_save_runs_once_and_never_falls_through_to_generic_path(
    ce_api_db, monkeypatch
):
    """CE PUT 后 ``save_channel_emulator_model_preset`` 恰被调 1 次，``_parse_endpoint_to_ip_port``
    恰 1 次（通用路径没再解析 / 再写一遍连接字段）。
    变异：删掉 CE 块末尾的 ``return`` → 落回通用路径再解析一次 → 计数 2 → 红。"""

    _Session, ids = ce_api_db
    calls = {"save": 0, "parse": 0}
    real_save = preset_module.save_channel_emulator_model_preset
    real_parse = instrument_api._parse_endpoint_to_ip_port

    def counting_save(**kwargs):
        calls["save"] += 1
        return real_save(**kwargs)

    def counting_parse(endpoint):
        calls["parse"] += 1
        return real_parse(endpoint)

    monkeypatch.setattr(
        preset_module, "save_channel_emulator_model_preset", counting_save
    )
    monkeypatch.setattr(instrument_api, "_parse_endpoint_to_ip_port", counting_parse)

    with TestClient(app) as client:
        response = client.put(CE_URL, json=_fs16_body(ids))
    assert response.status_code == 200, response.text
    assert calls == {"save": 1, "parse": 1}


# ---------------------------------------------------------------------------
# 门 5：契约三面镜像（live / checked-in yaml / 生成 TS；手写 api.ts 归前端片）
# ---------------------------------------------------------------------------


def test_channel_emulator_presets_are_typed_in_live_yaml_and_generated_mirrors():
    """live ``FEInstrumentConnection`` / checked-in ``InstrumentConnection`` / 生成 TS 三面都带
    ``channel_emulator_model_presets`` 且 required；``ChannelEmulatorModelPreset`` 恰六字段、
    ``additionalProperties: false``、无 adapter_profile 槽。
    变异：yaml ``InstrumentConnection.required`` 删掉该项 → 红。"""

    live = app.openapi()["components"]["schemas"]
    live_connection = live["FEInstrumentConnection"]
    assert live_connection["properties"]["channel_emulator_model_presets"][
        "additionalProperties"
    ] == {"$ref": "#/components/schemas/ChannelEmulatorModelPreset"}
    assert "channel_emulator_model_presets" in live_connection["required"]
    assert set(live["ChannelEmulatorModelPreset"]["properties"]) == PRESET_FIELDS

    checked = yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())[
        "components"
    ]["schemas"]
    checked_connection = checked["InstrumentConnection"]
    assert checked_connection["properties"]["channel_emulator_model_presets"][
        "additionalProperties"
    ] == {"$ref": "#/components/schemas/ChannelEmulatorModelPreset"}
    assert "channel_emulator_model_presets" in checked_connection["required"]
    assert checked["ChannelEmulatorModelPreset"]["additionalProperties"] is False
    assert set(checked["ChannelEmulatorModelPreset"]["required"]) == PRESET_FIELDS
    assert set(checked["ChannelEmulatorModelPreset"]["properties"]) == PRESET_FIELDS

    generated = (REPO_ROOT / "gui/src/types/api.generated.ts").read_text()
    assert (
        'channel_emulator_model_presets: {\n'
        '                [key: string]: components["schemas"]["ChannelEmulatorModelPreset"]'
    ) in generated
    assert "ChannelEmulatorModelPreset: {" in generated


# ---------------------------------------------------------------------------
# 门 6 / 7：PUT 之外的活动 connection_params 写点（channel-models 增删）回写 preset
# ---------------------------------------------------------------------------


def test_channel_model_add_and_remove_mirror_into_the_saved_active_preset(ce_api_db):
    """F64 存过 preset 后，POST 增一条 / DELETE 删一条 channel-model → F64 preset 的
    ``connection_params`` 与活动连接逐字节相等（增删都到，``alignment_name`` 等其它键原样）。
    变异：删增端点里的 ``synchronize_*`` 调用 → 增后 preset 仍是旧清单 → 红；删删端点里的 → 红。"""

    Session, ids = ce_api_db
    with TestClient(app) as client:
        assert client.put(CE_URL, json=_f64_body(ids)).status_code == 200
        added = client.post(
            f"{CE_URL}/channel-models", json=_nr_model_payload(NEW_MODEL)
        )
        assert added.status_code == 200, added.text
        with Session() as db:
            _category, connection = _load(db, ids)
            saved = connection.channel_emulator_model_presets[str(ids["f64"])]
            assert NEW_MODEL in _filenames(
                saved["connection_params"]["available_channel_models"]
            )
            assert saved["connection_params"]["alignment_name"] == "CAICT_2026-08_n78"
            assert _canonical(saved["connection_params"]) == _canonical(
                connection.connection_params
            )
            assert saved["endpoint"] == F64_ENDPOINT and saved["notes"] == "保存时的 F64"

        removed = client.delete(f"{CE_URL}/channel-models/{OLD_MODEL}")
        assert removed.status_code == 200, removed.text

    with Session() as db:
        _category, connection = _load(db, ids)
        saved = connection.channel_emulator_model_presets[str(ids["f64"])]
        filenames = _filenames(saved["connection_params"]["available_channel_models"])
        assert OLD_MODEL not in filenames
        assert NEW_MODEL in filenames
        assert _canonical(saved["connection_params"]) == _canonical(
            connection.connection_params
        )


def test_channel_model_edit_without_saved_preset_is_a_no_op_and_first_switch_snapshots_it(
    ce_api_db,
):
    """没有 preset 时增 channel-model 照常 200、不凭空建 preset（建 preset 只走 ``save_*``）；
    随后首次切型号保存，F64 的快照带着刚加的条目 —— 说明 no-op 不是漏洞。
    有意与 BS topology-profile 的「无 preset → 422」不同：channel-models 增删今天没有「先保存」
    前置（甚至会自建连接行），这里 422 会把既有流程弄坏。
    变异：``synchronize_*`` 在无 preset 时凭活动连接建 preset → presets 不再是 None → 红。"""

    Session, ids = ce_api_db
    with TestClient(app) as client:
        added = client.post(
            f"{CE_URL}/channel-models", json=_nr_model_payload(NEW_MODEL)
        )
        assert added.status_code == 200, added.text
        with Session() as db:
            _category, connection = _load(db, ids)
            assert connection.channel_emulator_model_presets is None
            assert NEW_MODEL in _filenames(
                connection.connection_params["available_channel_models"]
            )
        assert client.put(CE_URL, json=_fs16_body(ids)).status_code == 200

    with Session() as db:
        _category, connection = _load(db, ids)
        snapshot = connection.channel_emulator_model_presets[str(ids["f64"])]
        assert NEW_MODEL in _filenames(
            snapshot["connection_params"]["available_channel_models"]
        )
        assert snapshot["connection_params"]["alignment_name"] == "CAICT_2026-08_n78"


# ---------------------------------------------------------------------------
# 门 8：fail-closed 三态（只发 modelId / 带 BS profile 字段 / 空白 endpoint）
# ---------------------------------------------------------------------------


def test_channel_emulator_put_rejects_model_only_bs_profile_field_and_blank_endpoint(
    ce_api_db,
):
    """(a) 只发 ``modelId`` → 422（型号必须与连接一起保存，镜像 BS）；
    (b) 带 ``base_station_adapter_profile`` → 422（通用路径今天对非 BS 品类也是 422，CE 块不得静默吞掉）；
    (c) 目标 endpoint 空白 → 422 且状态不变（selected 仍 F64、presets 仍 NULL、endpoint 不变）。
    变异：删 (a) 的检查 → 200 → 红；删 (b) → 200 → 红；删 ``save_*`` 的 except → 异常穿出 → 红。"""

    Session, ids = ce_api_db
    with TestClient(app) as client:
        a = client.put(CE_URL, json={"modelId": str(ids["fs16"])})
        assert a.status_code == 422, a.text
        b = client.put(
            CE_URL,
            json={
                "modelId": str(ids["fs16"]),
                "connection": {
                    "endpoint": FS16_ENDPOINT,
                    "base_station_adapter_profile": None,
                },
            },
        )
        assert b.status_code == 422, b.text
        c = client.put(
            CE_URL,
            json={
                "modelId": str(ids["fs16"]),
                "connection": {"endpoint": "   ", "controller": "visa"},
            },
        )
        assert c.status_code == 422, c.text

    with Session() as db:
        category, connection = _load(db, ids)
        assert category.selected_model_id == ids["f64"]
        assert connection.endpoint == F64_ENDPOINT
        assert connection.channel_emulator_model_presets is None
