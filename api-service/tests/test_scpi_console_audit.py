"""P3.5: SCPI Console (旧, EquipmentManager 入口) 也接入 diagnostic_runs 审计。

L1 (单条命令) 和 L1-batch (probe = 5 条常用命令) 现在都写 diagnostic_runs.
跟 L2 (SequenceRunnerPanel = SCPI_SEQUENCE) 统一在同一审计表, 闭合 workshop tier
的 "昨天打通的命令是什么" 承诺。

These tests do NOT need a real instrument — most paths exercise the audit
wiring via no-IP / invalid-IP / unreachable-port branches that exit before
or shortly after the socket layer. The wiring itself (build context →
record_run with right kind/target/params) is what's under test.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.diagnostic_run import DiagnosticKind, DiagnosticRun
from app.models.instrument import (
    InstrumentCategory as InstrumentCategoryModel,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
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
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def category(db):
    """A minimal InstrumentCategory — needed for the endpoints to find a target."""
    cat = InstrumentCategoryModel(
        id=uuid.uuid4(),
        category_key="vna",
        category_name="Vector Network Analyzer",
        description="P3.5 test fixture",
        is_active=True,
        usage_phase=["calibration"],
        driver_mode="auto",
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


class TestScpiCommandAudit:
    """POST /instruments/{category_key}/scpi-command writes diagnostic_runs row."""

    def test_records_row_when_no_ip_configured(self, category, db):
        # No InstrumentConnection row + no body.ip → "未配置 IP 地址" path.
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={"command": "*IDN?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "未配置" in body["error"]

        # Audit row should exist and carry the operator's intent (the command),
        # even though the command never reached the wire.
        rows = db.query(DiagnosticRun).filter(
            DiagnosticRun.kind == DiagnosticKind.SCPI_COMMAND.value
        ).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.success is False
        assert "*IDN?" in row.target_name
        assert row.target_name.startswith("vna:")
        assert row.error_message and "未配置" in row.error_message
        assert row.params is not None
        assert row.params.get("command") == "*IDN?"
        assert row.params.get("category_key") == "vna"

    def test_records_row_when_ip_invalid(self, category, db):
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={"command": "*IDN?", "ip": "not-an-ip", "port": 5025},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

        rows = db.query(DiagnosticRun).all()
        assert len(rows) == 1
        assert rows[0].success is False
        assert rows[0].error_message and "格式无效" in rows[0].error_message
        assert rows[0].params.get("ip") == "not-an-ip"

    def test_records_row_with_run_by(self, category, db):
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={"command": "SYST:ERR?", "run_by": "ops-debug"},
        )
        assert resp.status_code == 200

        row = db.query(DiagnosticRun).first()
        assert row is not None
        assert row.run_by == "ops-debug"
        assert row.duration_ms is not None and row.duration_ms >= 0

    def test_records_row_on_socket_failure(self, category, db):
        # 127.0.0.1:1 → ConnectionRefusedError immediately (no real listener).
        # Exercises the except-Exception branch in send_scpi_command.
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={
                "command": "*IDN?",
                "ip": "127.0.0.1",
                "port": 1,
                "timeout_ms": 500,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

        rows = db.query(DiagnosticRun).all()
        assert len(rows) == 1
        assert rows[0].success is False
        assert rows[0].params.get("ip") == "127.0.0.1"
        assert rows[0].params.get("port") == 1

    def test_404_category_does_not_audit(self, db):
        resp = client.post(
            "/api/v1/instruments/no-such-category/scpi-command",
            json={"command": "*IDN?"},
        )
        assert resp.status_code == 404
        # No audit when target doesn't exist — there's nothing to point at.
        assert db.query(DiagnosticRun).count() == 0

    def test_auth_write_secret_is_redacted_in_audit_copy(self, category, db):
        secret = "0123456789ABCDEF0123456789ABCDEF"
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={"command": f"BSE:AUTH:KI {secret}"},
        )
        assert resp.status_code == 200
        assert secret in resp.json()["command"], "API 返回值保持原始操作员输入"

        row = db.query(DiagnosticRun).one()
        persisted = f"{row.target_name} {row.params} {row.output_excerpt} {row.error_message}"
        assert secret not in persisted
        assert "[REDACTED]" in persisted

    def test_auth_query_response_is_redacted_only_in_audit_copy(
        self, category, db, monkeypatch
    ):
        secret = "FEDCBA9876543210FEDCBA9876543210"

        class RealAuthDriver:
            def _query(self, _cmd: str) -> str:
                return secret

            def _write(self, _cmd: str) -> None:
                return None

        monkeypatch.setattr(
            "app.api.instrument._get_loaded_hal_driver",
            lambda _category_key: RealAuthDriver(),
        )
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={"command": "BSE:AUTH:OPC?"},
        )
        assert resp.status_code == 200
        assert resp.json()["response"] == secret

        row = db.query(DiagnosticRun).one()
        persisted = f"{row.target_name} {row.params} {row.output_excerpt} {row.error_message}"
        assert secret not in persisted
        assert "[REDACTED]" in persisted


class TestScpiProbeAudit:
    """POST /instruments/{category_key}/scpi-probe writes ONE row, not five."""

    def test_single_row_for_batch_probe(self, category, db):
        # Connection refused → all 5 commands fail, but operator cognition is
        # "one health check" — verify we record exactly 1 row.
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-probe",
            json={"ip": "127.0.0.1", "port": 1},
        )
        assert resp.status_code == 200

        rows = db.query(DiagnosticRun).filter(
            DiagnosticRun.kind == DiagnosticKind.SCPI_COMMAND.value
        ).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.target_name == "probe:vna"
        assert row.success is False
        # All 5 common commands recorded in params for traceability.
        assert row.params.get("commands") == ["*IDN?", "*OPC?", "*STB?", "SYST:ERR?", "SYST:VERS?"]
        # Output summary should mention multiple commands.
        assert row.output_excerpt is not None
        assert "*IDN?" in row.output_excerpt

    def test_probe_no_ip_does_not_audit(self, category, db):
        # No connection row + no body.ip → 400, caller-bug path. We don't
        # audit caller bugs (unlike scpi-command, where the same path returns
        # HTTP 200 + success=False, and DOES audit).
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-probe",
            json={},
        )
        assert resp.status_code == 400
        assert db.query(DiagnosticRun).count() == 0

    def test_probe_run_by_threaded_through(self, category, db):
        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-probe",
            json={"ip": "127.0.0.1", "port": 1, "run_by": "field-engineer"},
        )
        assert resp.status_code == 200

        row = db.query(DiagnosticRun).first()
        assert row is not None
        assert row.run_by == "field-engineer"


class TestAuditListIntegration:
    """SCPI Console rows show up in GET /diagnostic-runs alongside L2 sequence runs."""

    def test_scpi_command_listed_under_kind_filter(self, category):
        client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={"command": "*IDN?"},
        )
        resp = client.get(
            "/api/v1/diagnostic-runs",
            params={"kind": DiagnosticKind.SCPI_COMMAND.value},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["kind"] == DiagnosticKind.SCPI_COMMAND.value
        assert items[0]["target_name"].startswith("vna:")
        # Summary now carries output_excerpt so EquipmentManager history can
        # render the response inline without a per-row detail roundtrip.
        assert "output_excerpt" in items[0]

    def test_target_contains_filters_to_one_category(self, db):
        """EquipmentManager pulls per-instrument history with target_contains=key."""
        # Two categories, two scpi-command runs each.
        for key in ("vna", "baseStation"):
            cat = InstrumentCategoryModel(
                id=uuid.uuid4(),
                category_key=key,
                category_name=f"{key} fixture",
                description="",
                is_active=True,
                usage_phase=["test"],
                driver_mode="auto",
            )
            db.add(cat)
        db.commit()

        for key in ("vna", "baseStation"):
            client.post(
                f"/api/v1/instruments/{key}/scpi-command",
                json={"command": "*IDN?"},
            )
            client.post(
                f"/api/v1/instruments/{key}/scpi-probe",
                json={"ip": "127.0.0.1", "port": 1},
            )

        # No filter: 4 rows total (2 single + 2 probe).
        all_rows = client.get(
            "/api/v1/diagnostic-runs",
            params={"kind": "scpi_command"},
        ).json()["items"]
        assert len(all_rows) == 4

        # target_contains=vna: 2 rows (vna single + probe:vna).
        vna_rows = client.get(
            "/api/v1/diagnostic-runs",
            params={"kind": "scpi_command", "target_contains": "vna"},
        ).json()["items"]
        assert len(vna_rows) == 2
        for r in vna_rows:
            assert "vna" in r["target_name"]
            assert "baseStation" not in r["target_name"]

        # target_contains=baseStation: 2 rows.
        bs_rows = client.get(
            "/api/v1/diagnostic-runs",
            params={"kind": "scpi_command", "target_contains": "baseStation"},
        ).json()["items"]
        assert len(bs_rows) == 2
        for r in bs_rows:
            assert "baseStation" in r["target_name"]

    def test_target_contains_escapes_like_wildcards(self, category):
        """A literal '%' in target_contains shouldn't match everything."""
        client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-command",
            json={"command": "*IDN?"},
        )
        # Search for "%" — should match nothing because target names contain
        # no literal % character. Without escaping this would match everything.
        resp = client.get(
            "/api/v1/diagnostic-runs",
            params={"kind": "scpi_command", "target_contains": "%"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []


class TestHalDriverGate:
    """``_get_loaded_hal_driver()`` is the gate that picks "talk through the
    live HAL session" vs "open a fresh TCP socket" for ``/scpi-probe`` and
    ``/scpi-command``. It must exclude Mock drivers — Mock drivers inherit
    the base ``_do_query`` that returns ``""``, so routing through them
    yields silent 1–2 ms empty responses instead of probing the configured
    IP. Hit live at CAICT 2026-05-13.
    """

    def test_excludes_mock_driver(self, monkeypatch):
        from app.api.instrument import _get_loaded_hal_driver

        class MockBaseStation:
            def _query(self, cmd: str) -> str: return ""
            def _write(self, cmd: str) -> None: pass

        class FakeHal:
            drivers = {"baseStation": MockBaseStation()}

        # _get_loaded_hal_driver does `from app.services.instrument_hal_service
        # import get_hal_service` inside the function, so we patch the source.
        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: FakeHal(),
        )
        # Even though the driver has _query/_write callables, gate returns
        # None because the class name starts with "Mock".
        assert _get_loaded_hal_driver("baseStation") is None

    def test_accepts_real_driver(self, monkeypatch):
        from app.api.instrument import _get_loaded_hal_driver

        class RealUxmDriver:
            def _query(self, cmd: str) -> str: return "Keysight,UXM,SN,FW"
            def _write(self, cmd: str) -> None: pass

        real = RealUxmDriver()
        class FakeHal:
            drivers = {"baseStation": real}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: FakeHal(),
        )
        assert _get_loaded_hal_driver("baseStation") is real

    def test_returns_none_when_hal_empty(self, monkeypatch):
        from app.api.instrument import _get_loaded_hal_driver

        class FakeHal:
            drivers: dict = {}

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: FakeHal(),
        )
        assert _get_loaded_hal_driver("baseStation") is None

    def test_scpi_probe_uses_socket_when_only_mock_loaded(self, category, monkeypatch):
        """End-to-end: /scpi-probe with Mock loaded falls back to socket
        path (port 1 is the canary unreachable port) instead of routing
        through Mock — the audit row's output should reflect socket-layer
        failure, not "empty response from live HAL"."""

        class MockBaseStation:
            def _query(self, cmd: str) -> str: return ""
            def _write(self, cmd: str) -> None: pass

        class FakeHal:
            drivers = {"vna": MockBaseStation()}  # category from fixture

        monkeypatch.setattr(
            "app.services.instrument_hal_service.get_hal_service",
            lambda: FakeHal(),
        )

        resp = client.post(
            f"/api/v1/instruments/{category.category_key}/scpi-probe",
            json={"ip": "127.0.0.1", "port": 1},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Socket path was taken — port 1 connection refused / per-cmd error.
        # Each result should report a socket-layer error, not an empty
        # "no response" from the Mock path which would have 1–2 ms latency.
        results = body.get("results", [])
        assert len(results) == 5
        for r in results:
            # Socket fallback: success=False with a socket-style error,
            # NOT the HAL-empty-response path which says "(empty)".
            assert r["success"] is False
            assert "(empty)" not in (r.get("error") or "")
