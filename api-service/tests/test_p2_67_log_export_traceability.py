"""P2-67：BaseStation 公共租约日志与执行导出的独立可追溯性。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import settings
from app.core.logging_config import current_execution_id
from app.hal.base_station import (
    BaseStationControlReleaseResult,
    BaseStationRemoteSessionResult,
)
from app.hal.base_station_compatibility import (
    build_frozen_compatibility_payload,
    build_measure_execution_requirements,
    canonical_payload_digest,
    evaluate_base_station_compatibility,
)
from app.hal.uxm_base_station import RealUxmDriver
from app.main import app
from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY


class _BaseStation:
    adapter_id = "cmw500"

    async def acquire_remote_control(self) -> BaseStationRemoteSessionResult:
        return BaseStationRemoteSessionResult(
            adapter_id=self.adapter_id,
            session_token="cmw-session",
            acquired_confirmed=True,
            warnings=(),
        )

    async def release_remote_session(
        self,
        expected_session_token: str,
        *,
        measurement_attempt_id: str | None = None,
        lease_id: str = "",
    ) -> BaseStationControlReleaseResult:
        return BaseStationControlReleaseResult(
            measurement_attempt_id=measurement_attempt_id,
            lease_id=lease_id,
            adapter_id=self.adapter_id,
            session_token=expected_session_token,
            remote_session_acquired_confirmed=True,
            transport_session_released_confirmed=True,
            front_panel_local_confirmed=None,
            warnings=(),
        )

    async def release_to_local_control(self) -> bool:
        return True


class _HAL:
    def __init__(self):
        self.drivers = {"baseStation": _BaseStation()}

    async def clear_metrics_cache(self) -> None:
        return None


def test_frozen_validator_projects_minimal_lease_audit_context():
    from app.services.base_station_adapter_profile import (
        build_frozen_base_station_validator,
    )
    from app.services.instrument_test_lease import BaseStationLeaseAuditContext

    validator = build_frozen_base_station_validator(
        {
            "digest": "freeze-digest",
            "binding_digest": "binding-digest",
            "resolution": {
                "adapter": "cmw500",
                "status": "configured",
                "execution_mode": "real",
                "profile": {},
            },
        }
    )

    assert validator.validation_identity == "freeze-digest"
    assert validator.lease_audit_context == BaseStationLeaseAuditContext(
        adapter_id="cmw500",
        binding_digest="binding-digest",
    )


@pytest.mark.asyncio
async def test_public_lease_logs_are_vendor_neutral_and_structurally_identified(
    caplog,
):
    from app.services.instrument_test_lease import (
        BaseStationLeaseAuditContext,
        InstrumentTestLease,
    )

    class _Validator:
        validation_identity = "freeze-digest"
        lease_audit_context = BaseStationLeaseAuditContext(
            adapter_id="cmw500",
            binding_digest="binding-digest",
        )

        def __call__(self, _hal):
            return None

    lease = InstrumentTestLease(_HAL)
    token = current_execution_id.set(
        "31d3e29d-3b0f-4e5c-b391-0b629824e72d"
    )
    try:
        with caplog.at_level(
            logging.INFO,
            logger="app.services.instrument_test_lease",
        ):
            async with lease.hold(
                "formal-case",
                control_f64=False,
                control_uxm=True,
                validate_before_remote=_Validator(),
            ):
                pass
    finally:
        current_execution_id.reset(token)

    public = [
        record
        for record in caplog.records
        if "instrument-lease" in record.getMessage()
    ]
    assert len(public) == 2
    assert all("F64/UXM" not in record.getMessage() for record in public)
    assert all("UXM" not in record.getMessage() for record in public)
    assert [record.lease_event for record in public] == [
        "control_acquired",
        "control_released",
    ]
    assert all(
        record.controlled_instruments == ("baseStation",)
        for record in public
    )
    assert all(record.base_station_adapter_id == "cmw500" for record in public)
    assert all(
        record.base_station_binding_digest == "binding-digest"
        for record in public
    )
    assert all(
        record.execution_id == "31d3e29d-3b0f-4e5c-b391-0b629824e72d"
        for record in public
    )


@pytest.mark.asyncio
async def test_idle_park_log_does_not_claim_specific_vendor(caplog):
    from app.services.instrument_test_lease import InstrumentTestLease

    lease = InstrumentTestLease(_HAL)
    with caplog.at_level(
        logging.INFO,
        logger="app.services.instrument_test_lease",
    ):
        assert await lease.park_idle_instruments() is True

    message = caplog.records[-1].getMessage()
    assert "F64/UXM" not in message
    assert "UXM" not in message
    assert caplog.records[-1].lease_event == "idle_parked"


def _execution(execution_id: str):
    requirements = build_measure_execution_requirements("nr5g")
    verdict = evaluate_base_station_compatibility(
        requirements,
        RealUxmDriver.adapter_manifest,
    )
    compatibility = build_frozen_compatibility_payload(requirements, verdict)
    identity = {
        "schema_version": 1,
        "lab_profile_id": "lab-a",
        "instrument_connection_id": "connection-a",
        "resolution": {
            "schema_version": 1,
            "adapter": "uxm",
            "status": "not_applicable",
            "execution_mode": "real",
            "profile": None,
        },
        "binding_digest": "b" * 64,
        "resolved_binding": {
            "status": "not_applicable",
            "binding_digest": "b" * 64,
            "manifest": RealUxmDriver.adapter_manifest.model_dump(mode="json"),
        },
        "compatibility": compatibility,
    }
    frozen = {**identity, "digest": canonical_payload_digest(identity)}
    return SimpleNamespace(
        id=UUID(execution_id),
        status="completed",
        config={FREEZE_CONFIG_KEY: frozen},
    )


def _log_line(execution_id: str, message: str) -> str:
    return json.dumps(
        {
            "ts": "2026-09-02T01:00:00.000+08:00",
            "level": "INFO",
            "logger": "app.services.test_case_runner",
            "hal_mode": "real",
            "session_id": "request-a",
            "execution_id": execution_id,
            "instrument_id": "-",
            "msg": message,
        },
        ensure_ascii=False,
    )


class _Query:
    def __init__(self, row):
        self.row = row

    def filter(self, *_args):
        return self

    def one_or_none(self):
        return self.row


class _DB:
    def __init__(self, row):
        self.row = row

    def query(self, _model):
        return _Query(self.row)

    def close(self):
        return None


def test_execution_filtered_export_has_frozen_metadata_and_independent_name(
    tmp_path,
    monkeypatch,
):
    import app.api.system_logs as system_logs

    execution_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    execution_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    (tmp_path / "app.log").write_text(
        "\n".join(
            [
                _log_line(execution_a, "execution A"),
                _log_line(execution_b, "execution B first"),
                _log_line(execution_a, "execution A later"),
                _log_line(execution_b, "execution B done"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    monkeypatch.setattr(
        system_logs,
        "SessionLocal",
        lambda: _DB(_execution(execution_b)),
        raising=False,
    )

    response = TestClient(app).get(
        f"{settings.api_v1_prefix}/system-logs/export/app.log",
        params={"execution_id": execution_b},
    )

    assert response.status_code == 200
    assert execution_b in response.headers["content-disposition"]
    records = [json.loads(line) for line in response.text.splitlines()]
    metadata = records[0]
    assert metadata["record_type"] == "export_metadata"
    assert metadata["source_filename"] == "app.log"
    assert metadata["filters"]["execution_id"] == execution_b
    assert metadata["execution_id"] == execution_b
    assert metadata["base_station_adapter_id"] == "uxm"
    assert metadata["base_station_binding_digest"] == "b" * 64
    assert metadata["test_case_rat"] == "nr5g"
    assert metadata["execution_evidence_outcome"][
        "compatibility_classification"
    ] == "compatible"
    assert metadata["exported_at"].endswith("+00:00")
    assert [record["msg"] for record in records[1:]] == [
        "execution B first",
        "execution B done",
    ]
    assert {record["execution_id"] for record in records[1:]} == {execution_b}


def test_export_metadata_uses_only_frozen_execution_not_current_state(monkeypatch):
    import app.api.system_logs as system_logs

    execution_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    execution = _execution(execution_id)
    db = _DB(execution)

    metadata = system_logs._load_execution_export_metadata(execution_id, db)

    assert metadata["base_station_adapter_id"] == "uxm"
    assert metadata["test_case_rat"] == "nr5g"
    assert db.row is execution


def test_malformed_frozen_execution_exports_invalid_without_backfill():
    import app.api.system_logs as system_logs

    execution_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    execution = _execution(execution_id)
    execution.config[FREEZE_CONFIG_KEY]["digest"] = "tampered"

    metadata = system_logs._load_execution_export_metadata(
        execution_id,
        _DB(execution),
    )

    assert metadata["base_station_adapter_id"] is None
    assert metadata["base_station_binding_digest"] is None
    assert metadata["test_case_rat"] is None
    assert metadata["execution_evidence_outcome"][
        "compatibility_classification"
    ] == "invalid"
    assert metadata["execution_evidence_outcome"]["formal_eligible"] is False


def test_unknown_or_invalid_execution_filter_is_rejected(tmp_path, monkeypatch):
    import app.api.system_logs as system_logs

    (tmp_path / "app.log").write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    monkeypatch.setattr(
        system_logs,
        "SessionLocal",
        lambda: _DB(None),
        raising=False,
    )
    client = TestClient(app)

    malformed = client.get(
        f"{settings.api_v1_prefix}/system-logs/export/app.log",
        params={"execution_id": "not-a-uuid"},
    )
    missing = client.get(
        f"{settings.api_v1_prefix}/system-logs/export/app.log",
        params={
            "execution_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        },
    )

    assert malformed.status_code == 400
    assert missing.status_code == 404


def test_unfiltered_export_and_raw_download_remain_byte_compatible(
    tmp_path,
    monkeypatch,
):
    raw = _log_line("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "unchanged") + "\n"
    (tmp_path / "app.log").write_text(raw, encoding="utf-8")
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    client = TestClient(app)

    filtered = client.get(
        f"{settings.api_v1_prefix}/system-logs/export/app.log"
    )
    downloaded = client.get(
        f"{settings.api_v1_prefix}/system-logs/download/app.log"
    )

    assert filtered.text == raw
    assert filtered.headers["content-disposition"].endswith(
        'filename="app_export.jsonl"'
    )
    assert downloaded.content == raw.encode("utf-8")
    assert downloaded.headers["content-disposition"].endswith(
        'filename="app.log"'
    )


def test_execution_export_canonicalizes_uuid_before_filtering(
    tmp_path,
    monkeypatch,
):
    import app.api.system_logs as system_logs

    execution_id = "abcdefab-cdef-4abc-8def-abcdefabcdef"
    (tmp_path / "app.log").write_text(
        _log_line(execution_id, "canonical execution") + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "log_dir", str(tmp_path))
    monkeypatch.setattr(
        system_logs,
        "SessionLocal",
        lambda: _DB(_execution(execution_id)),
        raising=False,
    )

    response = TestClient(app).get(
        f"{settings.api_v1_prefix}/system-logs/export/app.log",
        params={"execution_id": execution_id.upper()},
    )

    assert response.status_code == 200
    records = [json.loads(line) for line in response.text.splitlines()]
    assert records[0]["filters"]["execution_id"] == execution_id
    assert [record["msg"] for record in records[1:]] == [
        "canonical execution"
    ]


def test_execution_export_contract_is_mirrored_and_gui_query_is_single_source():
    live_operation = app.openapi()["paths"][
        "/api/v1/system-logs/export/{filename}"
    ]["get"]
    checked_operation = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2]
            / "api/openapi.yaml"
        ).read_text(encoding="utf-8")
    )["paths"]["/api/v1/system-logs/export/{filename}"]["get"]

    for operation in (live_operation, checked_operation):
        assert "export_metadata" in operation["description"]
        assert "完整 execution UUID" in operation["description"]
        assert {"400", "404"} <= set(operation["responses"])
        parameters = {
            parameter["name"]: parameter
            for parameter in operation["parameters"]
        }
        assert "execution_id" in parameters
        assert not {
            "adapter_id",
            "requested_rat",
            "compatibility_verdict",
        }.intersection(parameters)

    viewer = (
        Path(__file__).resolve().parents[2]
        / "gui/src/features/Reports/components/SystemLogViewer.tsx"
    ).read_text(encoding="utf-8")
    assert len(re.findall(r"buildLogQuery\(\{", viewer)) == 3
    assert (
        "if (opts.executionFilter) q.execution_id = opts.executionFilter"
        in viewer
    )
