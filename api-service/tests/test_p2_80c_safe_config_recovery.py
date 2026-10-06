"""P2-80C：合法显式替代值只修目标，无法无损保留时原子拒绝。"""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.instrument import InstrumentCategory, InstrumentConnection
from tests.test_base_station_atomic_model_save import atomic_db, _cmw_profile
from tests.test_p2_58_2_channel_emulator_preset_api import ce_api_db


@pytest.fixture(params=["baseStation", "channelEmulator"])
def recovery(request):
    kind = request.param
    if kind == "baseStation":
        Session, category_id, target_id, other_id = request.getfixturevalue("atomic_db")
        field = "base_station_model_presets"
    else:
        Session, ids = request.getfixturevalue("ce_api_db")
        category_id, target_id, other_id = ids["category"], ids["f64"], ids["fs16"]
        field = "channel_emulator_model_presets"
    payload = {"modelId": str(target_id), "connection": {
        "endpoint": "192.0.2.55:3334", "controller": "socket", "notes": "操作员重存",
        "connection_params": {"timeout_sec": 25},
    }}
    if kind == "baseStation":
        payload["connection"]["base_station_adapter_profile"] = _cmw_profile()
    return Session, category_id, str(target_id), str(other_id), field, kind, payload


def store(case, *, presets=None, params=None):
    Session, category_id, _, _, field, _, _ = case
    with Session() as db:
        connection = db.query(InstrumentConnection).filter_by(category_id=category_id).one()
        setattr(connection, field, presets)
        if params is not None:
            connection.connection_params = params
        db.commit()
        return snapshot(case)


def snapshot(case):
    Session, category_id, _, _, field, _, _ = case
    with Session() as db:
        connection = db.query(InstrumentConnection).filter_by(category_id=category_id).one()
        return (getattr(connection, field), connection.connection_params,
                connection.endpoint, db.get(InstrumentCategory, category_id).selected_model_id)


@pytest.mark.parametrize("bad", [["bad"], "broken", False])
def test_explicit_params_replace_bad_active_params(recovery, bad):
    store(recovery, params=bad)
    response = TestClient(app).put(f"/api/v1/instruments/{recovery[5]}", json=recovery[6])
    assert response.status_code == 200, response.text
    assert snapshot(recovery)[1]["timeout_sec"] == 25


def test_complete_request_replaces_only_bad_target_preset(recovery):
    target, other = recovery[2:4]
    untouched = {"model_id": other, "endpoint": "192.0.2.77", "notes": "  原样保留  "}
    store(recovery, presets={target: {"broken": True}, other: untouched})
    response = TestClient(app).put(f"/api/v1/instruments/{recovery[5]}", json=recovery[6])
    assert response.status_code == 200, response.text
    saved = snapshot(recovery)[0]
    assert saved[other] == untouched
    assert saved[target]["endpoint"] == "192.0.2.55:3334"


@pytest.mark.parametrize("failure", ["whole_map", "other_entry", "partial", "invalid_replacement", "switch_bad_old"])
def test_unsafe_recovery_is_422_and_leaves_all_saved_truth_unchanged(recovery, failure):
    target, other = recovery[2:4]
    payload = deepcopy(recovery[6])
    presets = {target: {"broken": True}}
    params = None
    if failure == "whole_map":
        presets = ["not a map"]
    elif failure == "other_entry":
        presets[other] = {"broken": True}
    elif failure == "partial":
        payload["connection"].pop("notes")
    elif failure == "invalid_replacement":
        payload["connection"]["endpoint"] = ""
    elif failure == "switch_bad_old":
        presets = None
        params = ["bad old params"]
        payload["modelId"] = other
        if recovery[5] == "baseStation":
            payload["connection"]["base_station_adapter_profile"] = None
    before = store(recovery, presets=presets, params=params)
    response = TestClient(app, raise_server_exceptions=False).put(
        f"/api/v1/instruments/{recovery[5]}", json=payload)
    assert response.status_code == 422, response.text
    assert snapshot(recovery) == before
