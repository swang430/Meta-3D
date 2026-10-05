"""P2-79A：显式型号归属，不把当前选择补成历史真值。"""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.channel_asset import ChannelAsset
from app.services import standard_channel_service as scd_service
from app.services import channel_asset_service as asset_service


def save_preset(conn, model, models=None):
    conn.channel_emulator_model_presets = {str(model.id): {
        "schema_version": 1, "model_id": str(model.id), "endpoint": "test:3334",
        "controller": "SOCKET", "notes": "", "connection_params": {
            "available_channel_models": models or [],
        },
    }}


@pytest.fixture
def owner_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    category = InstrumentCategory(category_key="channelEmulator", category_name="CE")
    db.add(category)
    db.flush()
    models = [InstrumentModel(category_id=category.id, vendor="test", model=name,
                              capabilities={}) for name in ("F64", "FS16")]
    db.add_all(models)
    db.flush()
    category.selected_model_id = models[0].id
    conn = InstrumentConnection(category_id=category.id, endpoint="test:3334",
                                protocol="SOCKET", connection_params={})
    db.add(conn)
    db.commit()
    yield db, category, conn, models
    db.close()
    engine.dispose()


def make_scd(db, conn, **kwargs):
    return scd_service.create_scd(
        db, instrument_connection_id=conn.id, radio_technology="nr5g",
        channel_kind="nr_arfcn", band="N78", arfcn=640000, lte_dl_earfcn=None,
        bandwidth_mhz=100, model="CDLC", scenario="UMa", mimo="4x4",
        polarization="DP", **kwargs,
    )


def test_scd_requires_explicit_model_not_current_default(owner_db):
    db, _category, conn, _models = owner_db
    with pytest.raises(scd_service.StandardChannelError, match="型号"):
        make_scd(db, conn)
    assert scd_service.list_scds(db) == []


def test_scd_records_requested_model_and_rejects_stale_selection(owner_db):
    db, category, conn, models = owner_db
    scd = make_scd(db, conn, instrument_model_id=models[0].id)
    assert scd.instrument_model_id == models[0].id
    category.selected_model_id = models[1].id
    db.commit()
    with pytest.raises(scd_service.StandardChannelError, match="型号"):
        make_scd(db, conn, instrument_model_id=models[0].id, version=2)


def test_cross_category_model_cannot_own_channel_asset(owner_db):
    db, _category, conn, _models = owner_db
    other_category = InstrumentCategory(category_key="baseStation", category_name="BS")
    db.add(other_category)
    db.flush()
    other = InstrumentModel(category_id=other_category.id, vendor="test", model="CMW",
                            capabilities={})
    db.add(other)
    db.commit()
    with pytest.raises(scd_service.StandardChannelError, match="型号"):
        make_scd(db, conn, instrument_model_id=other.id)


def test_legacy_asset_owner_confirmation_is_explicit_and_preserves_payload(owner_db):
    db, category, conn, models = owner_db
    payload = {"scd_config": {"radio_technology": "nr5g", "channel_kind": "nr_arfcn",
        "band": "N78", "arfcn": 640000, "bandwidth_mhz": 100, "model": "CDLC",
        "scenario": "UMa", "mimo": "4x4", "polarization": "DP", "version": 1}}
    asset = ChannelAsset(name="legacy", source_type="vendor_file", payload=deepcopy(payload),
                         allowed_targets=["gcm_native"], is_active=True)
    db.add(asset)
    db.commit()
    result = asset_service.update_channel_asset(db, asset.id,
        instrument_connection_id=conn.id, instrument_model_id=models[0].id)
    assert result.instrument_model_id == models[0].id
    assert result.payload == payload
    category.selected_model_id = models[1].id
    db.commit()
    with pytest.raises(asset_service.ChannelAssetError, match="型号"):
        asset_service.update_channel_asset(db, asset.id, instrument_model_id=models[0].id)
    assert result.instrument_model_id == models[0].id


def test_vendor_creation_without_owner_is_rejected(owner_db):
    db, _category, _conn, _models = owner_db
    with pytest.raises(asset_service.ChannelAssetError, match="归属"):
        asset_service.create_channel_asset(db, name="new", source_type="vendor_file",
            payload={"scd_config": {"radio_technology": "nr5g", "channel_kind": "nr_arfcn",
                "band": "N78", "arfcn": 640000, "bandwidth_mhz": 100, "model": "CDLC",
                "scenario": "UMa", "mimo": "4x4", "polarization": "DP", "version": 1}})


def test_generated_asset_does_not_require_instrument_owner(owner_db):
    db, _category, _conn, _models = owner_db
    result = asset_service.create_channel_asset(db, name="generated", source_type="standard_3gpp",
                                              payload={"cdl_model_name": "UMa CDL-C NLOS"})
    assert result.allowed_targets == ["asc_baked"]


def test_inactive_owner_projection_does_not_pollute_current_model(owner_db):
    db, category, conn, models = owner_db
    save_preset(conn, models[0])
    db.commit()
    scd = make_scd(db, conn, instrument_model_id=models[0].id)
    category.selected_model_id = models[1].id
    conn.connection_params = {"available_channel_models": [{"filename": "fs16.dat"}]}
    db.commit()
    scd_service.associate_file(db, scd.id, file_path="f64.smu")
    assert conn.connection_params["available_channel_models"] == [{"filename": "fs16.dat"}]
    saved = conn.channel_emulator_model_presets[str(models[0].id)]
    assert saved["connection_params"]["available_channel_models"][0]["filename"] == "f64.smu"
    scd_service.delete_scd(db, scd.id)
    assert conn.connection_params["available_channel_models"] == [{"filename": "fs16.dat"}]
    assert conn.channel_emulator_model_presets[str(models[0].id)]["connection_params"]["available_channel_models"] == []


def test_same_name_can_belong_to_different_models(owner_db):
    db, category, conn, models = owner_db
    first = make_scd(db, conn, instrument_model_id=models[0].id)
    category.selected_model_id = models[1].id
    db.commit()
    second = make_scd(db, conn, instrument_model_id=models[1].id)
    assert first.standard_name == second.standard_name
    assert first.id != second.id
    listed = scd_service.list_scds(db, instrument_connection_id=conn.id,
                                  instrument_model_id=models[1].id)
    assert [s.id for s in listed] == [second.id]


def test_legacy_twin_never_republishes_over_modern_asset(owner_db):
    db, _category, conn, models = owner_db
    twin = make_scd(db, conn, instrument_model_id=models[0].id)
    modern = vendor_asset(db, conn, models[1].id)
    db.delete(modern)
    db.flush()
    modern = ChannelAsset(id=twin.id, name="modern-twin", source_type="vendor_file",
        payload={}, allowed_targets=["gcm_native"], is_active=True,
        instrument_connection_id=conn.id, instrument_model_id=models[1].id,
        associated_file_path="modern.smu")
    db.add(modern)
    twin.associated_file_path = "old.smu"
    db.commit()
    with pytest.raises(scd_service.StandardChannelError, match="信道工作台"):
        scd_service.associate_file(db, twin.id, file_path="legacy.smu", instrument_model_id=models[0].id)
    sibling = make_scd(db, conn, instrument_model_id=models[0].id, version=2)
    scd_service.associate_file(db, sibling.id, file_path="sibling.smu")
    assert [e["filename"] for e in conn.connection_params["available_channel_models"]] == ["sibling.smu"]
    assert modern.associated_file_path == "modern.smu"


def test_unknown_legacy_scd_cannot_be_associated_implicitly(owner_db):
    db, _category, conn, models = owner_db
    scd = make_scd(db, conn, instrument_model_id=models[0].id)
    scd.instrument_model_id = None
    db.commit()
    with pytest.raises(scd_service.StandardChannelError, match="归属"):
        scd_service.associate_file(db, scd.id, file_path="legacy.smu")
    assert scd.associated_file_path is None


def test_legacy_claim_name_conflict_is_controlled_and_does_not_write(owner_db):
    from app.models.standard_channel import StandardChannelDefinition
    db, _category, conn, models = owner_db
    known = make_scd(db, conn, instrument_model_id=models[0].id)
    legacy = StandardChannelDefinition(instrument_connection_id=conn.id,
        instrument_model_id=None, radio_technology=known.radio_technology,
        channel_kind=known.channel_kind, band=known.band, arfcn=known.arfcn,
        bandwidth_mhz=known.bandwidth_mhz, model=known.model, scenario=known.scenario,
        mimo=known.mimo, polarization=known.polarization, version=known.version,
        standard_name=known.standard_name, association_source="declared_only")
    db.add(legacy)
    db.commit()
    with pytest.raises(scd_service.StandardChannelError, match="同名"):
        scd_service.associate_file(db, legacy.id, file_path="legacy.smu", instrument_model_id=models[0].id)
    assert legacy.instrument_model_id is None
    assert legacy.associated_file_path is None


def test_batch_confirmation_is_all_or_nothing(owner_db):
    db, _category, conn, models = owner_db
    first = ChannelAsset(name="first", source_type="vendor_file", payload={},
                         allowed_targets=["gcm_native"], is_active=True)
    non_vendor = ChannelAsset(name="generated", source_type="standard_3gpp", payload={},
                              allowed_targets=["asc_baked"], is_active=True)
    db.add_all([first, non_vendor])
    db.commit()
    with pytest.raises(asset_service.ChannelAssetError):
        asset_service.confirm_channel_asset_ownership(db, [first.id, non_vendor.id],
                                                      conn.id, models[0].id)
    db.expire_all()
    assert first.instrument_model_id is None
    result = asset_service.confirm_channel_asset_ownership(db, [first.id], conn.id, models[0].id)
    assert [a.id for a in result] == [first.id]
    assert first.instrument_model_id == models[0].id


def test_batch_stale_selection_does_not_claim_unknown_assets(owner_db):
    db, _category, conn, models = owner_db
    first = ChannelAsset(name="first", source_type="vendor_file", payload={},
                         allowed_targets=["gcm_native"], is_active=True)
    db.add(first)
    db.commit()
    with pytest.raises(asset_service.ChannelAssetError, match="型号"):
        asset_service.confirm_channel_asset_ownership(db, [first.id], conn.id, models[1].id)
    assert first.instrument_model_id is None


def test_ownership_api_serializes_owner_and_batch_transaction(owner_db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import get_db
    db, _category, conn, models = owner_db
    asset = ChannelAsset(name="legacy", source_type="vendor_file", payload={},
                         allowed_targets=["gcm_native"], is_active=True)
    db.add(asset)
    db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        before = client.get(f"/api/v1/channel-assets/{asset.id}")
        assert before.status_code == 200
        assert before.json()["instrument_model_id"] is None
        result = client.post("/api/v1/channel-assets/vendor-files/confirm-ownership", json={
            "asset_ids": [str(asset.id)], "instrument_connection_id": str(conn.id),
            "instrument_model_id": str(models[0].id),
        })
        assert result.status_code == 200
        assert result.json()[0]["instrument_model_id"] == str(models[0].id)
    finally:
        app.dependency_overrides.pop(get_db, None)


def vendor_asset(db, conn, model):
    asset = ChannelAsset(name=f"vendor-{uuid4()}", source_type="vendor_file",
        payload={"scd_config": {"radio_technology": "nr5g", "channel_kind": "nr_arfcn",
            "band": "N78", "arfcn": 640000, "bandwidth_mhz": 100, "model": "CDLC",
            "scenario": "UMa", "mimo": "4x4", "polarization": "DP", "version": 1}},
        instrument_connection_id=conn.id, instrument_model_id=model,
        associated_file_path="channel.smu", allowed_targets=["gcm_native"], is_active=True)
    db.add(asset)
    db.commit()
    return asset


def test_derived_projection_uses_source_owner_not_client_label(owner_db):
    from app.services.channel_asset_ownership import owned_channel_model_params
    db, _category, conn, models = owner_db
    asset = vendor_asset(db, conn, models[1].id)
    params = {"available_channel_models": [
        {"filename": "channel.smu", "channel_asset_id": str(asset.id),
         "instrument_model_id": str(models[0].id)},
        {"filename": "manual.smu"},
    ]}
    result = owned_channel_model_params(db, conn.id, models[0].id, params)
    assert result["available_channel_models"] == [{"filename": "manual.smu"}]
    asset.instrument_model_id = models[0].id
    db.commit()
    assert len(owned_channel_model_params(db, conn.id, models[0].id, params)["available_channel_models"]) == 2
    asset.instrument_model_id = None
    db.commit()
    assert owned_channel_model_params(db, conn.id, None, params)["available_channel_models"] == [{"filename": "manual.smu"}]


@pytest.mark.parametrize("owner", ["unknown", "other"])
def test_new_vendor_freeze_rejects_unknown_or_wrong_owner(owner_db, owner):
    from types import SimpleNamespace
    from app.services.channel_emulator_execution_plan import freeze_channel_asset_resolution
    db, _category, conn, models = owner_db
    asset = vendor_asset(db, conn, None if owner == "unknown" else models[1].id)
    with pytest.raises(ValueError, match="归属|型号"):
        freeze_channel_asset_resolution(db, SimpleNamespace(channel_asset_id=asset.id))


def test_frozen_vendor_owner_is_digest_bound_and_drift_is_rejected(owner_db):
    from types import SimpleNamespace
    from app.services.channel_emulator_execution_plan import (
        freeze_channel_asset_resolution, validate_resolved_channel_asset_against_freeze,
    )
    db, _category, conn, models = owner_db
    asset = vendor_asset(db, conn, models[0].id)
    frozen = freeze_channel_asset_resolution(db, SimpleNamespace(channel_asset_id=asset.id))
    assert frozen["schema_version"] == 2
    assert frozen["instrument_model_id"] == str(models[0].id)
    asset.instrument_model_id = models[1].id
    with pytest.raises(ValueError, match="drifted"):
        validate_resolved_channel_asset_against_freeze(SimpleNamespace(asset=asset), frozen)


def test_old_resolution_digest_remains_readable_without_owner_backfill(owner_db):
    from types import SimpleNamespace
    from app.hal.base_station_compatibility import canonical_payload_digest
    from app.services.channel_emulator_execution_plan import (
        _channel_asset_executable_content, validate_resolved_channel_asset_against_freeze,
    )
    db, _category, conn, models = owner_db
    asset = vendor_asset(db, conn, models[0].id)
    content = _channel_asset_executable_content(asset)
    content.pop("instrument_model_id", None)
    payload = {"schema_version": 1, "channel_asset_id": str(asset.id),
        "source_type": "vendor_file", "executable_content_digest": canonical_payload_digest(content)}
    old = {**payload, "digest": canonical_payload_digest(payload)}
    assert validate_resolved_channel_asset_against_freeze(SimpleNamespace(asset=asset), old) == old


def test_owner_comparison_uses_same_execution_binding_not_current_selection(owner_db):
    from types import SimpleNamespace
    from app.services.channel_emulator_execution_plan import (
        CE_FREEZE_CONFIG_KEY, freeze_channel_asset_resolution, validate_channel_asset_frozen_owner,
    )
    db, category, conn, models = owner_db
    asset = vendor_asset(db, conn, models[0].id)
    frozen = freeze_channel_asset_resolution(db, SimpleNamespace(channel_asset_id=asset.id))
    execution_config = {CE_FREEZE_CONFIG_KEY: {"resolved_binding": {
        "instrument_connection_id": str(conn.id), "instrument_model_id": str(models[0].id)}}}
    category.selected_model_id = models[1].id
    db.commit()
    validate_channel_asset_frozen_owner(frozen, execution_config)
    execution_config[CE_FREEZE_CONFIG_KEY]["resolved_binding"]["instrument_model_id"] = str(models[1].id)
    with pytest.raises(ValueError, match="归属"):
        validate_channel_asset_frozen_owner(frozen, execution_config)


def test_legacy_only_scd_freezes_explicit_owner_and_rejects_unknown(owner_db):
    from types import SimpleNamespace
    from app.services.channel_emulator_execution_plan import freeze_legacy_channel_file_resolution
    db, _category, conn, models = owner_db
    scd = make_scd(db, conn, instrument_model_id=models[0].id)
    scd_service.associate_file(db, scd.id, file_path="legacy.smu")
    configuration = SimpleNamespace(channel_asset_id=None, scd_id=str(scd.id), engine_mode="keysight_gcm")
    frozen = freeze_legacy_channel_file_resolution(db, configuration)
    assert frozen["instrument_model_id"] == str(models[0].id)
    scd.instrument_model_id = None
    db.commit()
    with pytest.raises(ValueError, match="归属"):
        freeze_legacy_channel_file_resolution(db, configuration)


def test_saved_preset_quarantines_wrong_or_unknown_derived_files():
    from app.services.channel_emulator_model_preset import model_owned_channel_emulator_params
    target = uuid4()
    manual = {"filename": "manual.smu"}
    owned = {"filename": "owned.smu", "scd_id": "one", "instrument_model_id": str(target)}
    unknown = {"filename": "unknown.smu", "channel_asset_id": "two"}
    wrong = {"filename": "wrong.smu", "scd_id": "three", "instrument_model_id": str(uuid4())}
    params = {"available_channel_models": [manual, owned, unknown, wrong], "other": 1}
    assert model_owned_channel_emulator_params(params, target) == {
        "available_channel_models": [manual, owned], "other": 1}
    assert len(params["available_channel_models"]) == 4
