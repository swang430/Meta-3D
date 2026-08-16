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

import asyncio
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
import app.api.instrument as instrument_api
from app.models.diagnostic_run import DiagnosticKind, DiagnosticRun
from app.models.instrument import (
    InstrumentCategory as InstrumentCategoryModel,
    InstrumentConnection as InstrumentConnectionDB,
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


@pytest.mark.parametrize(
    "operation",
    [
        "test-connection",
        "scpi-command",
        "scpi-probe",
    ],
)
def test_manual_socket_fallback_rejects_conflicting_merged_config_before_io(
    category,
    db,
    monkeypatch,
    operation,
):
    conn = InstrumentConnectionDB(
        id=uuid.uuid4(),
        category_id=category.id,
        controller_ip="192.0.2.10",
        endpoint="TCPIP0::192.0.2.10::5025::SOCKET",
        port=5025,
        protocol="SCPI",
        connection_params={
            "visa_resource": "TCPIP0::192.0.2.99::5025::SOCKET"
        },
    )
    db.add(conn)
    db.commit()
    monkeypatch.setattr(instrument_api, "_get_loaded_hal_driver", lambda _key: None)

    @asynccontextmanager
    async def _lease(*_args, **_kwargs):
        yield

    monkeypatch.setattr(instrument_api, "instrument_test_lease", _lease)

    with patch("socket.socket.connect") as socket_connect:
        if operation == "test-connection":
            result = asyncio.run(instrument_api.test_instrument_connection(
                category.category_key,
                body=instrument_api.TestConnectionRequest(),
                db=db,
            ))
            error_text = result.message
        elif operation == "scpi-command":
            result = asyncio.run(instrument_api.send_scpi_command(
                category.category_key,
                request=instrument_api.ScpiCommandRequest(command="*IDN?"),
                db=db,
            ))
            error_text = result.error or ""
        else:
            with pytest.raises(instrument_api.HTTPException) as exc_info:
                asyncio.run(instrument_api.probe_scpi_commands(
                    category.category_key,
                    body=instrument_api.TestConnectionRequest(),
                    db=db,
                ))
            error_text = str(exc_info.value.detail)

    socket_connect.assert_not_called()
    assert "冲突" in error_text


@pytest.mark.parametrize(
    "operation",
    [
        "test-connection",
        "scpi-command",
        "scpi-probe",
    ],
)
def test_manual_override_must_match_loaded_hal_target_before_scpi(
    category,
    db,
    monkeypatch,
    operation,
):
    """请求目标 B 不能借用已经连接到目标 A 的 HAL 会话。"""

    class RealInstrumentDriver:
        config = {"ip": "192.0.2.10", "port": 5025}
        _query = AsyncMock(return_value="VENDOR,MODEL,SN,FW")
        _write = AsyncMock()

    driver = RealInstrumentDriver()
    monkeypatch.setattr(
        instrument_api, "_get_loaded_hal_driver", lambda _key: driver
    )

    @asynccontextmanager
    async def _lease(*_args, **_kwargs):
        yield

    monkeypatch.setattr(instrument_api, "instrument_test_lease", _lease)
    override = instrument_api.TestConnectionRequest(
        ip="192.0.2.99", port=5025
    )

    if operation == "test-connection":
        result = asyncio.run(instrument_api.test_instrument_connection(
            category.category_key,
            body=override,
            db=db,
        ))
        error_text = result.message
    elif operation == "scpi-command":
        result = asyncio.run(instrument_api.send_scpi_command(
            category.category_key,
            request=instrument_api.ScpiCommandRequest(
                command="*IDN?",
                ip=override.ip,
                port=override.port,
            ),
            db=db,
        ))
        error_text = result.error or ""
    else:
        with pytest.raises(instrument_api.HTTPException) as exc_info:
            asyncio.run(instrument_api.probe_scpi_commands(
                category.category_key,
                body=override,
                db=db,
            ))
        error_text = str(exc_info.value.detail)

    assert "活动 HAL 会话" in error_text
    driver._query.assert_not_awaited()
    driver._write.assert_not_awaited()


@pytest.mark.parametrize(
    "operation",
    [
        "test-connection",
        "scpi-command",
        "scpi-probe",
    ],
)
def test_hal_removed_during_lease_restores_raw_target_error(
    category,
    db,
    monkeypatch,
    operation,
):
    """活动 driver 在租约内消失时，不能把旧目标 A 当作 raw fallback。"""
    conn = InstrumentConnectionDB(
        id=uuid.uuid4(),
        category_id=category.id,
        controller_ip="192.0.2.20",
        endpoint="TCPIP0::192.0.2.20::5025::SOCKET",
        port=5025,
        protocol="SCPI",
        connection_params={
            "visa_resource": "TCPIP0::192.0.2.99::5025::SOCKET"
        },
    )
    db.add(conn)
    db.commit()

    class RealInstrumentDriver:
        config = {"ip": "192.0.2.10", "port": 5025}
        _query = AsyncMock(return_value="VENDOR,MODEL,SN,FW")
        _write = AsyncMock()

    loaded_drivers = iter([RealInstrumentDriver(), None])
    monkeypatch.setattr(
        instrument_api,
        "_get_loaded_hal_driver",
        lambda _key: next(loaded_drivers),
    )

    @asynccontextmanager
    async def _lease(*_args, **_kwargs):
        yield

    monkeypatch.setattr(instrument_api, "instrument_test_lease", _lease)

    with patch("socket.socket.connect") as socket_connect:
        if operation == "test-connection":
            result = asyncio.run(instrument_api.test_instrument_connection(
                category.category_key,
                body=instrument_api.TestConnectionRequest(),
                db=db,
            ))
            error_text = result.message
        elif operation == "scpi-command":
            result = asyncio.run(instrument_api.send_scpi_command(
                category.category_key,
                request=instrument_api.ScpiCommandRequest(command="*IDN?"),
                db=db,
            ))
            error_text = result.error or ""
        else:
            with pytest.raises(instrument_api.HTTPException) as exc_info:
                asyncio.run(instrument_api.probe_scpi_commands(
                    category.category_key,
                    body=instrument_api.TestConnectionRequest(),
                    db=db,
                ))
            error_text = str(exc_info.value.detail)

    socket_connect.assert_not_called()
    assert "冲突" in error_text


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
            json={"command": f"CONF:AUTH:KEY:VALUE {secret}"},
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

    def test_connection_reuses_loaded_uxm_session_without_second_socket(
        self, db, monkeypatch
    ):
        cat = InstrumentCategoryModel(
            id=uuid.uuid4(),
            category_key="baseStation",
            category_name="UXM",
            is_active=True,
            usage_phase=["testing"],
            driver_mode="real",
        )
        db.add(cat)
        db.commit()

        class RealUxmDriver:
            config = {"ip": "192.0.2.20", "port": 5125}
            _query = AsyncMock(return_value="Keysight,E7515B,SN,FW")
            _write = AsyncMock()

        driver = RealUxmDriver()

        @asynccontextmanager
        async def _lease(*_args, **_kwargs):
            yield

        monkeypatch.setattr(
            instrument_api, "_get_loaded_hal_driver", lambda _key: driver
        )
        monkeypatch.setattr(instrument_api, "instrument_test_lease", _lease)

        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("已加载 UXM 时不得另开 raw socket"),
        ):
            resp = client.post(
                "/api/v1/instruments/baseStation/test-connection",
                json={"ip": "192.0.2.20", "port": 5125, "protocol": "SCPI"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["idn"] == "Keysight,E7515B,SN,FW"
        driver._query.assert_awaited_once_with("*IDN?")

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
