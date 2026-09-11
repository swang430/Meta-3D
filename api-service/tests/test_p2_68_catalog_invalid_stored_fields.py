"""P2-68：一条 ``InstrumentConnection`` 的某个 JSON 列损坏，不能让整张仪器目录消失。

可观察故障（#458 行内 3938243884 / 2026-09-05 triage 在 ``a0c671c4`` 复现）：
``GET /api/v1/instruments/catalog`` 把连接的 JSON 列原样塞进严格 Pydantic 模型；
一条坏认证 → ``_convert_connection`` 抛错 → 端点尾部 ``except Exception`` 把整张目录
洗成 ``categories=[]``。同一个兜底还把真实 DB 故障伪装成「零仪器」。

本文件的门（设计稿 §6）：
- G1  五个会让整目录丢失的列各自单独隔离（参数化），其余 category / connection 照常
- G2  隔离粒度是「字段」不是「连接」
- G3  DB 故障照实 5xx，不再是 200 + ``[]``
- G4  正式门对同一份坏认证仍 fail-closed —— 目录容错不能松动它
- G5  不变量：受保护字段常量 == 转换器实际保护的字段 == 契约 description 列出的键
- G7  ``PUT /instruments/{category_key}`` 的响应经同一容错投影
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.services.execution_qualification import BaseStationSiteCertification

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_URL = "/api/v1/instruments/catalog"
BS_ENDPOINT = "192.168.1.112:5125"
CE_ENDPOINT = "192.168.0.132:3334"

# 每个值都必须被对应的权威解析器判为「坏」；G1 的 ``invalid_fields`` 断言会抓出判不坏的。
BAD_VALUES = {
    "base_station_site_certification": {"schema_version": 1, "status": "bogus"},
    "channel_emulator_site_certification": {"schema_version": 1, "status": "active"},
    "base_station_model_presets": "presets-must-be-an-object",
    "channel_emulator_model_presets": ["a", "list", "is", "not", "a", "map"],
    "connection_params": ["not", "an", "object"],
}
FALLBACKS = {
    "base_station_site_certification": None,
    "channel_emulator_site_certification": None,
    "base_station_model_presets": {},
    "channel_emulator_model_presets": {},
    "connection_params": None,
}

VALID_BS_CERTIFICATION = BaseStationSiteCertification(
    schema_version=1,
    status="active",
    lab_profile_id="lab-1",
    instrument_connection_id="conn-1",
    binding_digest="a" * 64,
    adapter_id="uxm_5g_e7515b",
    model="UXM 5G E7515B",
    firmware_version="1.0",
    options=("A",),
    source_execution_id="exec-1",
    evidence_digest="b" * 64,
    required_proofs={
        "config_readback": True,
        "route_readback": True,
        "route_not_applicable": False,
        "cleanup": True,
        "transport_release": True,
    },
    certified_by="quality-owner",
    certified_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    reason="site evidence complete",
).model_dump(mode="json")


@pytest.fixture
def catalog_db():
    """两类仪器、各一条连接的真 SQLite 目录；返回 (Session, ids)。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()
    bs_cat = InstrumentCategory(
        id=uuid4(), category_key="baseStation", category_name="基站仿真器",
        driver_mode="mock", is_active=True, display_order=1,
    )
    ce_cat = InstrumentCategory(
        id=uuid4(), category_key="channelEmulator", category_name="信道仿真器",
        driver_mode="mock", is_active=True, display_order=2,
    )
    bs_model = InstrumentModel(
        id=uuid4(), category_id=bs_cat.id, vendor="Keysight", model="UXM 5G E7515B",
        capabilities={}, is_available=True,
    )
    ce_model = InstrumentModel(
        id=uuid4(), category_id=ce_cat.id, vendor="Keysight", model="PROPSIM F64",
        capabilities={}, is_available=True,
    )
    bs_cat.selected_model_id = bs_model.id
    ce_cat.selected_model_id = ce_model.id
    bs_conn = InstrumentConnection(
        id=uuid4(), category_id=bs_cat.id, endpoint=BS_ENDPOINT, protocol="hislip",
        notes="UXM", connection_params={"app": "LTE_NR_IRAT"}, created_by="test",
    )
    ce_conn = InstrumentConnection(
        id=uuid4(), category_id=ce_cat.id, endpoint=CE_ENDPOINT, protocol="socket",
        notes="F64", connection_params={"port": 3334}, created_by="test",
    )
    db.add_all([bs_cat, ce_cat, bs_model, ce_model, bs_conn, ce_conn])
    db.commit()
    ids = {"bs_conn": bs_conn.id, "ce_conn": ce_conn.id}
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


def _set(Session, connection_id, field: str, value) -> None:
    db = Session()
    try:
        conn = db.get(InstrumentConnection, connection_id)
        setattr(conn, field, value)
        db.commit()
    finally:
        db.close()


def _connection_of(body: dict, category_key: str) -> dict:
    for cat in body["categories"]:
        if cat["key"] == category_key:
            return cat["connection"]
    raise AssertionError(f"category {category_key!r} missing; got {[c['key'] for c in body['categories']]}")


# ── G1 ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("field", sorted(BAD_VALUES))
def test_one_malformed_stored_field_keeps_the_rest_of_the_catalog(catalog_db, field):
    Session, ids = catalog_db
    _set(Session, ids["ce_conn"], field, BAD_VALUES[field])

    response = TestClient(app).get(CATALOG_URL)

    assert response.status_code == 200
    body = response.json()
    assert {c["key"] for c in body["categories"]} == {"baseStation", "channelEmulator"}

    ce = _connection_of(body, "channelEmulator")
    assert ce[field] == FALLBACKS[field]
    assert set(ce["invalid_fields"]) == {field}
    reason = ce["invalid_fields"][field]
    assert isinstance(reason, str) and reason.strip() and len(reason) <= 200
    assert ce["endpoint"] == CE_ENDPOINT  # 同一连接的其余字段照常

    bs = _connection_of(body, "baseStation")
    assert bs["invalid_fields"] == {}
    assert bs["endpoint"] == BS_ENDPOINT
    assert bs["connection_params"] == {"app": "LTE_NR_IRAT"}


# ── G1b：BS preset 解析器不包一层 ValueError，直接抛 pydantic ValidationError ─────────
def test_pydantic_validation_error_inside_bs_preset_map_is_isolated_too(catalog_db):
    """``parse_base_station_model_presets`` 对单个坏 preset 直接抛 ``ValidationError``（不像 CE 那样
    包成中文 ``ValueError``）；容错投影靠「``ValidationError`` 是 ``ValueError`` 子类」接住它——
    这条假设必须有门。"""
    Session, ids = catalog_db
    bad_map = {"11111111-1111-1111-1111-111111111111": {"model_id": "not-a-uuid"}}
    _set(Session, ids["bs_conn"], "base_station_model_presets", bad_map)

    body = TestClient(app).get(CATALOG_URL).json()
    bs = _connection_of(body, "baseStation")

    assert {c["key"] for c in body["categories"]} == {"baseStation", "channelEmulator"}
    assert bs["base_station_model_presets"] == {}
    assert set(bs["invalid_fields"]) == {"base_station_model_presets"}
    assert len(bs["invalid_fields"]["base_station_model_presets"]) <= 200


# ── G2 ────────────────────────────────────────────────────────────────────
def test_isolation_is_per_field_not_per_connection(catalog_db):
    Session, ids = catalog_db
    _set(Session, ids["bs_conn"], "base_station_site_certification", VALID_BS_CERTIFICATION)
    _set(Session, ids["bs_conn"], "base_station_model_presets", BAD_VALUES["base_station_model_presets"])

    body = TestClient(app).get(CATALOG_URL).json()
    bs = _connection_of(body, "baseStation")

    assert bs["base_station_site_certification"]["status"] == "active"
    assert bs["base_station_model_presets"] == {}
    assert set(bs["invalid_fields"]) == {"base_station_model_presets"}


# ── G3 ────────────────────────────────────────────────────────────────────
def test_database_failure_is_reported_not_disguised_as_empty_catalog(catalog_db, monkeypatch):
    from sqlalchemy.orm import Session as SASession

    def _boom(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, RuntimeError("database is down"))

    monkeypatch.setattr(SASession, "query", _boom)

    response = TestClient(app, raise_server_exceptions=False).get(CATALOG_URL)

    assert response.status_code >= 500
    assert "categories" not in response.text


# ── G4 ────────────────────────────────────────────────────────────────────
def test_formal_gates_still_reject_the_same_malformed_certifications():
    from app.services.channel_emulator_certification import (
        build_channel_emulator_certification_preview,
        parse_channel_emulator_site_certification,
    )
    from app.services.execution_qualification import (
        freeze_execution_qualification,
        parse_base_station_site_certification,
    )

    bad_ce = BAD_VALUES["channel_emulator_site_certification"]
    bad_bs = BAD_VALUES["base_station_site_certification"]

    binding_preview = SimpleNamespace(
        status="configured", execution_mode="real", binding_digest="d" * 64,
        adapter_id="propsim_f64", instrument_model_id="model-1",
        instrument_connection_id="conn-1", lab_profile_id="lab-1",
    )
    projected = build_channel_emulator_certification_preview(binding_preview, bad_ce)
    assert projected.status == "invalid"
    assert "site_certification_invalid" in projected.reasons

    with pytest.raises(ValueError):
        parse_channel_emulator_site_certification(bad_ce)
    with pytest.raises(ValueError):
        parse_base_station_site_certification(bad_bs)
    # 冻结正式资格的生产函数用的就是这个解析器，且它的 ValueError 不在该函数内被吞
    source = inspect.getsource(freeze_execution_qualification)
    assert "parse_base_station_site_certification(" in source


# ── G5 ────────────────────────────────────────────────────────────────────
def test_projected_stored_fields_constant_matches_converter_and_contract():
    import yaml

    from app.api.instrument import (
        PROJECTED_STORED_FIELDS,
        FEInstrumentConnection,
        _convert_connection,
    )

    protected: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(_convert_connection))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_project"
        ):
            first = node.args[0]
            assert isinstance(first, ast.Constant) and isinstance(first.value, str)
            protected.add(first.value)
    assert protected == set(PROJECTED_STORED_FIELDS)
    assert len(set(PROJECTED_STORED_FIELDS)) == len(PROJECTED_STORED_FIELDS)
    for field in PROJECTED_STORED_FIELDS:
        assert hasattr(InstrumentConnection, field), field  # 真是 DB 列
        assert field in FEInstrumentConnection.model_fields, field  # 真有对应投影
    assert "invalid_fields" in FEInstrumentConnection.model_fields

    spec = yaml.safe_load((REPO_ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8"))
    connection_schema = spec["components"]["schemas"]["InstrumentConnection"]
    prop = connection_schema["properties"]["invalid_fields"]
    assert prop["type"] == "object"
    assert prop["additionalProperties"] == {"type": "string"}
    assert "invalid_fields" in connection_schema["required"]
    for field in PROJECTED_STORED_FIELDS:
        assert field in prop["description"], field


# ── G7 ────────────────────────────────────────────────────────────────────
def test_update_category_response_uses_the_same_tolerant_projection(catalog_db):
    Session, ids = catalog_db
    bad_ce = BAD_VALUES["channel_emulator_site_certification"]
    _set(Session, ids["ce_conn"], "channel_emulator_site_certification", bad_ce)

    response = TestClient(app).put(
        "/api/v1/instruments/channelEmulator", json={"connection": {"notes": "改备注"}}
    )

    assert response.status_code == 200
    connection = response.json()["connection"]
    assert connection["notes"] == "改备注"
    assert connection["channel_emulator_site_certification"] is None
    assert set(connection["invalid_fields"]) == {"channel_emulator_site_certification"}
