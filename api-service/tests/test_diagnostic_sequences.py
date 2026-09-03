"""P3 Phase 2: sequence loader + run endpoint.

The two example sequences (instrument_idn_sweep, baseStation_attach_check)
exercise both branches: parameter-less + parameterised, no required
categories + required categories. We mock the HAL drivers since these
tests run against in-memory SQLite without real instruments.
"""
from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.diagnostics import loader
from app.main import app
from app.models.chamber import (
    ChamberType,
    create_chamber_from_preset,
)
from app.models.diagnostic_run import DiagnosticRun
from app.models.lab_profile import LabProfile


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
def chamber(db):
    c = create_chamber_from_preset(ChamberType.TYPE_C.value, name="Phase 2 Chamber")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lab_with_bs(db, chamber):
    """Lab with a baseStation binding so attach_check sequence can run."""
    from app.models.instrument import InstrumentCategory

    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="baseStation",
        category_name="Base Station",
        is_active=True,
    )
    db.add(cat)
    db.commit()
    lp = LabProfile(
        name="P3-Phase2-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(cat.id),
                "connection_endpoint": "192.168.1.5:5025",
                "driver_mode": "real",
                "role": "primary_base_station",
            },
        ],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def lab_with_bs_and_ce(db, chamber):
    """Lab 同时绑 baseStation + channelEmulator (P2-17 直通编排的 CE 配置判定用)。"""
    from app.models.instrument import InstrumentCategory

    bs_cat = InstrumentCategory(
        id=uuid.uuid4(), category_key="baseStation",
        category_name="Base Station", is_active=True,
    )
    ce_cat = InstrumentCategory(
        id=uuid.uuid4(), category_key="channelEmulator",
        category_name="Channel Emulator", is_active=True,
    )
    db.add_all([bs_cat, ce_cat])
    db.commit()
    lp = LabProfile(
        name="P2-17-Lab-BS-CE",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(bs_cat.id),
                "connection_endpoint": "192.168.1.5:5025",
                "driver_mode": "real",
                "role": "primary_base_station",
            },
            {
                "category_id": str(ce_cat.id),
                "connection_endpoint": "192.168.100.21:3334",
                "driver_mode": "real",
                "role": "primary_channel_emulator",
            },
        ],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def lab_with_ce(db, chamber):
    """Lab with a channelEmulator binding so PROPSIM probe can run."""
    from app.models.instrument import InstrumentCategory

    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="channelEmulator",
        category_name="Channel Emulator",
        is_active=True,
    )
    db.add(cat)
    db.commit()
    lp = LabProfile(
        name="P3-Phase2-CE-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(cat.id),
                "connection_endpoint": "TCPIP0::192.168.0.100::5025::SOCKET",
                "driver_mode": "real",
                "role": "primary_channel_emulator",
            },
        ],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


@pytest.fixture
def lab_with_vna(db, chamber):
    """Lab with a vna binding so VNA health probe can run."""
    from app.models.instrument import InstrumentCategory

    cat = InstrumentCategory(
        id=uuid.uuid4(),
        category_key="vna",
        category_name="Vector Network Analyzer",
        is_active=True,
    )
    db.add(cat)
    db.commit()
    lp = LabProfile(
        name="P3-Phase2-VNA-Lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(cat.id),
                "connection_endpoint": "TCPIP::192.168.0.10::INSTR",
                "driver_mode": "real",
                "role": "calibration_vna",
            },
        ],
        is_active=True,
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _patched_hal(monkeypatch, drivers: dict):
    """Replace get_hal_service() with a stub returning the given drivers dict."""
    fake_hal = MagicMock()
    fake_hal.drivers = drivers
    monkeypatch.setattr(
        "app.api.diagnostic_sequence.get_hal_service", lambda: fake_hal
    )
    return fake_hal


class TestListSequences:
    def test_lists_both_examples(self):
        # Reset cache so that any earlier test that didn't import the
        # sequences package doesn't leave a stale entry.
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "instrument_idn_sweep" in keys
        assert "baseStation_attach_check" in keys

    def test_metadata_shape_includes_required_categories(self):
        resp = client.get("/api/v1/diagnostic-sequences")
        body = resp.json()
        attach = next(s for s in body if s["key"] == "baseStation_attach_check")
        assert attach["required_categories"] == ["baseStation"]
        assert any(p["name"] == "frequency_mhz" for p in attach["params_schema"])
        assert attach["safe_during_test"] is False


class TestRunSequence:
    def test_404_on_unknown_sequence(self):
        resp = client.post("/api/v1/diagnostic-sequences/no_such/run", json={})
        assert resp.status_code == 404

    def test_422_when_required_category_not_bound(self, db, chamber):
        """Lab has no baseStation binding — 422 with the offending category."""
        # Empty bindings to trigger the missing-category guard.
        lp = LabProfile(
            name="empty-lab",
            chamber_config_id=chamber.id,
            instrument_bindings=[],
            is_active=True,
        )
        db.add(lp)
        db.commit()

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={"lab_profile_id": str(lp.id)},
        )
        assert resp.status_code == 422
        assert "baseStation" in resp.json()["detail"]

    def test_idn_sweep_records_audit_row_when_no_drivers(self, db, lab_with_bs, monkeypatch):
        """No HAL drivers loaded → sequence runs, marks failure, audit row exists."""
        _patched_hal(monkeypatch, drivers={})
        resp = client.post(
            "/api/v1/diagnostic-sequences/instrument_idn_sweep/run",
            json={"lab_profile_id": str(lab_with_bs.id), "run_by": "pytest"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        # One step (the lab has one binding), and it should report driver missing.
        assert len(body["steps"]) == 1
        assert "未加载" in body["steps"][0]["detail"]
        # Audit row written
        audit = db.query(DiagnosticRun).filter(
            DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"])
        ).first()
        assert audit is not None
        assert audit.success is False
        assert audit.run_by == "pytest"
        assert "driver not loaded" in (audit.output_excerpt or "")

    def test_idn_sweep_succeeds_with_mock_driver(self, db, lab_with_bs, monkeypatch):
        bs_driver = MagicMock()
        bs_driver.get_identity = AsyncMock(return_value="VENDOR,MODEL,SN12345")
        _patched_hal(monkeypatch, drivers={"baseStation": bs_driver})

        resp = client.post(
            "/api/v1/diagnostic-sequences/instrument_idn_sweep/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["steps"]) == 1
        assert "VENDOR" in body["steps"][0]["detail"]

    def test_attach_check_sequence_runs_with_mock_bs(self, db, lab_with_bs, monkeypatch):
        """The sequence does mutate state — verify it walks through cleanly when
        the fake driver returns a happy path."""
        bs = MagicMock()
        bs.connect = AsyncMock(return_value=True)
        bs.set_cell_config = AsyncMock(return_value=True)
        bs.start_signaling = AsyncMock(return_value=True)
        bs.get_ue_info = AsyncMock(return_value={"connected": True, "imsi": "001010..."})
        bs.query_ue_capability = AsyncMock(return_value={"max_layers": 4})
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 2, "frequency_mhz": 3500},
            },
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        labels = [s["label"] for s in body["steps"]]
        assert "connect" in labels
        assert any("set_cell_config" in label for label in labels)
        assert "start_signaling" in labels
        assert body["extra"]["ue_info"]["connected"] is True

    def test_attach_check_aborts_when_set_cell_config_returns_false(
        self, db, lab_with_bs, monkeypatch
    ):
        """Codex #195 R5 P1 同族: HAL 布尔契约 False 不得被记成 success 继续跑。"""
        bs = MagicMock()
        bs.connect = AsyncMock(return_value=True)
        bs.set_cell_config = AsyncMock(return_value=False)
        bs.start_signaling = AsyncMock(return_value=True)
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 1, "frequency_mhz": 3500},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "returned False" in body["summary"]
        failed = [s for s in body["steps"] if not s["success"]]
        assert any("set_cell_config" in s["label"] for s in failed), body["steps"]
        # Codex #199 P3: 同一失败 step 只记一条 (False 分支记录后哨兵异常
        # 不得再被通用 except 二次 append)
        cell_cfg_failures = [s for s in failed if "set_cell_config" in s["label"]]
        assert len(cell_cfg_failures) == 1, body["steps"]
        # False 中止序列 — 后续 start_signaling 不应执行
        bs.start_signaling.assert_not_awaited()

    def _happy_bs(self):
        bs = MagicMock()
        bs.connect = AsyncMock(return_value=True)
        bs.set_cell_config = AsyncMock(return_value=True)
        bs.start_signaling = AsyncMock(return_value=True)
        bs.get_ue_info = AsyncMock(return_value={"connected": True, "imsi": "001010..."})
        bs.query_ue_capability = AsyncMock(return_value={"max_layers": 4})
        return bs

    def test_attach_check_defaults_dispatch_onsite_baseline(
        self, db, lab_with_bs, monkeypatch
    ):
        """agent R6 F2: 默认参数必须下发 2026-07-03 现场实证 attach 基线 —
        显式 arfcn 636666 (3549.99 MHz 换算, 与 measure 链同模式, 不靠 band
        fallback) + BW40 + RS EPRE -46。此前无 arfcn 恒落 632628 错频且 SSB
        永不自动补, 下次现场开跑主角会被误诊成 DUT/RF 问题。"""
        bs = self._happy_bs()
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 1},  # 其余全默认
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        cfg = bs.set_cell_config.await_args.args[0]
        assert cfg["arfcn"] == 636666
        assert cfg["frequency_mhz"] == pytest.approx(3549.99)
        assert cfg["bandwidth_mhz"] == 40
        assert cfg["dl_power_dbm"] == -46
        assert cfg["band"] == "n78"

    def test_attach_schema_and_runtime_defaults_have_one_declared_source(self):
        """GUI schema 与 run() fallback 必须引用同一份 attach 默认配置。"""
        from app.diagnostics.sequences import baseStation_attach_check as sequence

        defaults = getattr(sequence, "ATTACH_CONFIG_DEFAULTS", None)
        assert defaults is not None, "attach defaults must have one declared source"
        schema_defaults = {
            item["name"]: item.get("default") for item in sequence.metadata.params_schema
        }
        for name, expected in defaults.items():
            assert schema_defaults[name] == expected

    def test_attach_check_custom_freq_converts_arfcn(
        self, db, lab_with_bs, monkeypatch
    ):
        """自定义频率显式换算 ARFCN — 不落 band fallback 静默错频。"""
        bs = self._happy_bs()
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 1, "frequency_mhz": 3600.0},
            },
        )
        assert resp.status_code == 200
        cfg = bs.set_cell_config.await_args.args[0]
        assert cfg["arfcn"] == 640000  # 3600 MHz 全局栅格

    def test_attach_check_establishes_f64_passthrough(self, db, lab_with_bs_and_ce, monkeypatch):
        """P2-17 ②: 有 F64 直通能力的 CE 时 attach 前建立直通稳态 (STOPPED + STATIC 3)。"""
        bs = self._happy_bs()
        ce = MagicMock()
        ce.SUPPORTS_STATIC_PASSTHROUGH = True  # Codex #201 P2: 能力标志 gate
        ce.stop_emulation = AsyncMock(return_value=True)
        ce.set_passthrough_mode = AsyncMock(return_value=True)
        _patched_hal(monkeypatch, drivers={"baseStation": bs, "channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs_and_ce.id),
                "params": {"attach_timeout_s": 2, "frequency_mhz": 3500},
            },
        )
        body = resp.json()
        assert body["success"] is True
        labels = [s["label"] for s in body["steps"]]
        assert any("stop_emulation" in lbl for lbl in labels), labels
        assert any("passthrough" in lbl.lower() for lbl in labels), labels
        ce.stop_emulation.assert_awaited_once()
        ce.set_passthrough_mode.assert_awaited_once()
        # 开关 2 默认档: 不传参数时 mode=3 (CALIBRATION) 透传到驱动
        assert ce.set_passthrough_mode.await_args.kwargs.get("mode") == 3

    def test_attach_check_bypass_mode_param_forwarded(
        self, db, lab_with_bs_and_ce, monkeypatch
    ):
        """开关 2 (门审 #216 F6): f64_bypass_mode 参数经序列透传到驱动 —
        拨 2 (Butler) 时驱动收到 mode=2, step label 显示实际档位。"""
        bs = self._happy_bs()
        ce = MagicMock()
        ce.SUPPORTS_STATIC_PASSTHROUGH = True
        ce.stop_emulation = AsyncMock(return_value=True)
        ce.set_passthrough_mode = AsyncMock(return_value=True)
        _patched_hal(monkeypatch, drivers={"baseStation": bs, "channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs_and_ce.id),
                "params": {"attach_timeout_s": 2, "f64_bypass_mode": 2},
            },
        )
        body = resp.json()
        assert body["success"] is True
        assert ce.set_passthrough_mode.await_args.kwargs.get("mode") == 2
        labels = [s["label"] for s in body["steps"]]
        assert any("STATIC 2" in lbl for lbl in labels), labels

    def test_attach_check_bypass_mode_bool_not_coerced(
        self, db, lab_with_bs_and_ce, monkeypatch
    ):
        """Codex #216 P2: 序列层不得 int() 强转 — JSON true 必须以原始 True
        到达驱动 (由驱动的 isinstance(bool) 守门拒绝), 不能被强转成 1 绕过
        (静默切 STATIC 1)。"""
        bs = self._happy_bs()
        ce = MagicMock()
        ce.SUPPORTS_STATIC_PASSTHROUGH = True
        ce.stop_emulation = AsyncMock(return_value=True)
        # 模拟真驱动契约: bool → False (拒绝)
        ce.set_passthrough_mode = AsyncMock(return_value=False)
        _patched_hal(monkeypatch, drivers={"baseStation": bs, "channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs_and_ce.id),
                "params": {"attach_timeout_s": 2, "f64_bypass_mode": True},
            },
        )
        body = resp.json()
        # 关键契约 1: 驱动收到的是原始 True, 不是被强转的 1
        got = ce.set_passthrough_mode.await_args.kwargs.get("mode")
        assert got is True, f"mode 被上游强转: {got!r}"
        # 关键契约 2: 驱动拒绝 (False) → 序列 fail-loud, 不带错误模式继续
        assert body["success"] is False
        bs.set_cell_config.assert_not_awaited()

    def test_attach_check_passthrough_skipped_without_ce(self, db, lab_with_bs, monkeypatch):
        """无 CE (线缆直连场景) → 跳过 step 记录, 序列继续。"""
        bs = self._happy_bs()
        _patched_hal(monkeypatch, drivers={"baseStation": bs})
        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={"lab_profile_id": str(lab_with_bs.id), "params": {"attach_timeout_s": 2}},
        )
        body = resp.json()
        assert body["success"] is True
        skipped = [s for s in body["steps"] if "skipped" in s["label"]]
        assert len(skipped) == 1 and skipped[0]["success"] is True, body["steps"]

    def test_attach_check_passthrough_failure_aborts(self, db, lab_with_bs_and_ce, monkeypatch):
        """CE 在场但直通失败 → fail-loud (衰落在跑 attach 大概率失败, 不硬闯)。"""
        bs = self._happy_bs()
        ce = MagicMock()
        ce.SUPPORTS_STATIC_PASSTHROUGH = True
        ce.stop_emulation = AsyncMock(return_value=True)
        ce.set_passthrough_mode = AsyncMock(return_value=False)
        _patched_hal(monkeypatch, drivers={"baseStation": bs, "channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={"lab_profile_id": str(lab_with_bs_and_ce.id), "params": {"attach_timeout_s": 2}},
        )
        body = resp.json()
        assert body["success"] is False
        bs.set_cell_config.assert_not_awaited()  # 直通失败即中止, 不继续配小区

    def test_attach_check_skips_non_f64_ce(self, db, lab_with_bs_and_ce, monkeypatch):
        """Codex #201 P2: 无 STATIC 直通能力标志的 CE (FS16 等) → 跳过不硬闯。"""
        bs = self._happy_bs()
        ce = MagicMock()
        ce.SUPPORTS_STATIC_PASSTHROUGH = False  # 基类都有 set_passthrough_mode 方法名
        ce.set_passthrough_mode = AsyncMock(return_value=True)
        _patched_hal(monkeypatch, drivers={"baseStation": bs, "channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={"lab_profile_id": str(lab_with_bs_and_ce.id), "params": {"attach_timeout_s": 2}},
        )
        body = resp.json()
        assert body["success"] is True
        skipped = [s for s in body["steps"] if "skipped" in s["label"]]
        assert len(skipped) == 1, body["steps"]
        ce.set_passthrough_mode.assert_not_awaited()

    def test_attach_check_ignores_stray_global_ce_when_lab_unbound(
        self, db, lab_with_bs, monkeypatch
    ):
        """Codex #201 R2 P2: 本 lab 未绑 CE 时, 全局 HAL 残留的 F64 (别的 setup)
        不得被停/切 — binding 是第一道门。"""
        bs = self._happy_bs()
        stray_ce = MagicMock()
        stray_ce.SUPPORTS_STATIC_PASSTHROUGH = True
        stray_ce.stop_emulation = AsyncMock(return_value=True)
        stray_ce.set_passthrough_mode = AsyncMock(return_value=True)
        _patched_hal(monkeypatch, drivers={"baseStation": bs, "channelEmulator": stray_ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={"lab_profile_id": str(lab_with_bs.id), "params": {"attach_timeout_s": 2}},
        )
        body = resp.json()
        assert body["success"] is True
        assert any("skipped" in s["label"] for s in body["steps"]), body["steps"]
        stray_ce.stop_emulation.assert_not_awaited()
        stray_ce.set_passthrough_mode.assert_not_awaited()

    def test_attach_check_fails_when_configured_ce_not_loaded(
        self, db, lab_with_bs_and_ce, monkeypatch
    ):
        """Codex #201 P2: lab 配置了 CE 但驱动没加载 ≠ 线缆直连 — fail-loud,
        否则 F64 停在任意模式, attach 失败被误诊成 DUT/RF 问题。"""
        bs = self._happy_bs()
        _patched_hal(monkeypatch, drivers={"baseStation": bs})  # CE 驱动缺席
        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={"lab_profile_id": str(lab_with_bs_and_ce.id), "params": {"attach_timeout_s": 2}},
        )
        body = resp.json()
        assert body["success"] is False
        assert "channelEmulator" in body["summary"]
        bs.set_cell_config.assert_not_awaited()

    def test_attach_check_passthrough_opt_out(self, db, lab_with_bs, monkeypatch):
        """explicit 关闭开关 → 不碰 CE。"""
        bs = self._happy_bs()
        ce = MagicMock()
        ce.SUPPORTS_STATIC_PASSTHROUGH = True
        ce.stop_emulation = AsyncMock(return_value=True)
        ce.set_passthrough_mode = AsyncMock(return_value=True)
        _patched_hal(monkeypatch, drivers={"baseStation": bs, "channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 2, "establish_f64_passthrough": False},
            },
        )
        assert resp.json()["success"] is True
        ce.set_passthrough_mode.assert_not_awaited()

    def test_attach_check_marks_failure_on_no_attach(self, db, lab_with_bs, monkeypatch):
        """DUT never attaches within timeout → success=False, but HTTP 200."""
        bs = MagicMock()
        bs.connect = AsyncMock(return_value=True)
        bs.set_cell_config = AsyncMock(return_value=True)
        bs.start_signaling = AsyncMock(return_value=True)
        bs.get_ue_info = AsyncMock(return_value={"connected": False})
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/baseStation_attach_check/run",
            json={
                "lab_profile_id": str(lab_with_bs.id),
                "params": {"attach_timeout_s": 1},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "did not attach" in body["summary"]
        # Audit row written with success=False
        audit = db.query(DiagnosticRun).filter(
            DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"])
        ).first()
        assert audit.success is False


class TestUxmScpiCompatibilitySequence:
    """Probe sequence that walks every UxmScpiCommands constant and reports
    which are supported by the connected firmware.

    The sequence calls bs._query() for each command + once more for
    SYSTem:ERRor?. We mock _query with a programmable side_effect so each
    test can simulate a specific firmware-error-queue scenario.
    """

    def test_registered_in_loader(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "uxm_scpi_compatibility" in keys

    def test_metadata_requires_base_station(self):
        resp = client.get("/api/v1/diagnostic-sequences")
        entry = next(s for s in resp.json() if s["key"] == "uxm_scpi_compatibility")
        assert entry["required_categories"] == ["baseStation"]
        assert entry["safe_during_test"] is False
        assert any(p["name"] == "include_supported" for p in entry["params_schema"])

    def _build_bs(self, err_for_cmd):
        """Build a fake baseStation driver whose _query returns canned errs.

        err_for_cmd: callable(last_probed_cmd_str) -> error_queue_response.
        """
        bs = MagicMock()
        bs._write = MagicMock(return_value=None)
        state = {"last_probe": None}

        def fake_query(cmd):
            if cmd == "SYSTem:ERRor?":
                last = state["last_probe"]
                return err_for_cmd(last) if last else '0,"No error"'
            state["last_probe"] = cmd
            return ""

        bs._query = fake_query
        return bs

    def test_all_supported_when_firmware_responds_clean(self, lab_with_bs, monkeypatch):
        bs = self._build_bs(lambda cmd: '0,"No error"')
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id), "params": {"include_supported": False}},
        )
        assert resp.status_code == 200
        body = resp.json()
        # 固件对**已定义**的命令全部回 clean → 零 UNSUPPORTED
        assert body["extra"]["counts"]["UNSUPPORTED"] == 0
        # With include_supported=False and zero unsupported, steps stay empty.
        assert body["steps"] == []
        # ⚠ P1-58: 本用例跑在 **5G_NR_Test 方言**上（探测命令是
        # `CONFig:NR5G:CELL0:BAND?` —— 无前缀 + CELL0），该方言 profile 里
        # 有一批 critical 能力未定义（手册只给了 BSE: 变体，按禁盲试不猜）。
        # 判定集改按当前方言 profile 派生后：固件对已定义命令全 clean、且
        # 该方言无 mandatory ACTION → 零实测失败因子，**不是 BLOCKER**；
        # 但未定义 = 未经查证、从未探测 → 判 **UNDETERMINED**，success 仍 False
        # （Codex #358 R1 P1：不能把没探测过的报成健康；GUI 拿 success 画绿牌）。
        assert body["success"] is False
        assert body["extra"]["verdict"] == "UNDETERMINED"
        assert body["extra"]["critical_unsupported"] == []
        assert body["extra"]["critical_not_in_profile"], (
            "本用例前提：5G 方言里确实有 critical 能力未在 profile 定义"
        )
        # 总结如实：applicable 口径 + 披露未定义能力，不冒充全局清单全绿，也不报 BLOCKER
        assert body["summary"].startswith("UNDETERMINED")
        assert "applicable" in body["summary"]
        assert "未在本方言 profile 定义" in body["summary"]
        assert "BLOCKER" not in body["summary"]

    def test_critical_not_in_profile_is_disclosed_not_failed(
        self, lab_with_bs, monkeypatch
    ):
        """⭐ P1-58：critical 清单里在本方言为 None 的命令**如实披露、不报成仪器拒绝**。

        `_all_commands()` 按"该 Test App 不暴露此命令"的契约过滤掉 None ——
        这类命令没被探测。Codex #275 P2 的防线（不把没探测过的报成已验证）
        保留并升级成四态：未定义 ≠ BLOCKER（不是仪器拒绝），但也 ≠ 健康 ——
        判 UNDETERMINED、success=False（Codex #358 R1 P1）；全局 critical 清单
        是跨方言并集，单一方言不可能全部定义，所以披露必须逐条、口径必须如实。

        变异：披露归零（extra 不放 critical_not_in_profile）→ 红；
        判定集回退全局清单（applicable=_CRITICAL_NAMES）→ 披露断言红。
        """
        from app.diagnostics.sequences import uxm_scpi_compatibility as seq
        from app.hal.uxm_command_profiles import Uxm5GNRTestAppProfile

        undefined = sorted(
            n for n in seq._CRITICAL_NAMES
            if not isinstance(getattr(Uxm5GNRTestAppProfile, n, None), str))
        assert undefined, "本用例前提：5G 方言里确实有 critical 命令未定义"

        bs = self._build_bs(lambda cmd: '0,"No error"')
        _patched_hal(monkeypatch, drivers={"baseStation": bs})
        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        # 未定义 ≠ 仪器拒绝（不是 BLOCKER），但也 ≠ 健康：UNDETERMINED
        assert body["success"] is False
        assert body["extra"]["verdict"] == "UNDETERMINED"
        assert body["extra"]["critical_unsupported"] == []
        # 但必须逐条披露，且总结不得冒充全局清单全绿
        assert body["extra"]["critical_not_in_profile"] == undefined
        assert str(len(undefined)) in body["summary"]
        assert f"All {len(seq._CRITICAL_NAMES)} " not in body["summary"]

    def test_critical_unsupported_fails_with_blocker(self, lab_with_bs, monkeypatch):
        broken = "CONFig:NR5G:CELL0:BAND?"  # _to_probe_command(CELL_BAND)

        def err_for(probe_cmd):
            if probe_cmd == broken:
                return '-113,"Undefined header"'
            return '0,"No error"'

        bs = self._build_bs(err_for)
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "BLOCKER" in body["summary"]
        assert "CELL_BAND" in body["summary"]
        cell_band_steps = [s for s in body["steps"] if s["label"].startswith("CELL_BAND ")]
        assert len(cell_band_steps) == 1
        assert cell_band_steps[0]["success"] is False
        assert "UNSUPPORTED" in cell_band_steps[0]["detail"]
        assert body["extra"]["critical_unsupported"] == ["CELL_BAND"]

    def test_state_error_categorized_as_ok(self, lab_with_bs, monkeypatch):
        """-200..-299 = header exists, wrong state — not a blocker."""
        bs = self._build_bs(lambda cmd: '-220,"Parameter error;current state"')
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        # 本用例的题眼：-220 归到 SUPPORTED_BUT_STATE，不算 blocker
        assert body["extra"]["counts"]["SUPPORTED_BUT_STATE"] > 0
        assert body["extra"]["counts"]["UNSUPPORTED"] == 0
        # （P1-58 后 success 不再被「方言未定义」压成恒 False；本用例只守
        # "-220 不是 blocker"，success 的完整判定见
        # test_critical_not_in_profile_is_disclosed_not_failed。）

    def test_fails_clean_when_no_driver_loaded(self, lab_with_bs, monkeypatch):
        """HAL has the binding but the driver class failed to init."""
        _patched_hal(monkeypatch, drivers={})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "baseStation" in body["summary"] and "scpi-probe" in body["summary"]

    def test_refuses_mock_driver(self, lab_with_bs, monkeypatch):
        """P1-14: mock BS loads in mock mode → probe gets past the no-driver
        check, but an SCPI-compat sweep against a mock is meaningless. Refuse
        with the actionable mock summary."""
        from app.hal import MockBaseStation

        _patched_hal(monkeypatch, drivers={
            "baseStation": registered_mock_base_station("mock-bs", {"model": "UXM 5G E7515B"}),
        })
        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "mock 驱动" in body["summary"]
        assert "real 模式" in body["summary"]

    def test_irat_profile_walks_smaller_command_set(self, lab_with_bs, monkeypatch):
        """LTE_NR_IRAT app exposes ~32 BSE-prefixed commands (vs ~76 in
        5G_NR_Test). Driver must expose its _cmds for the probe to pick
        the right profile. Verified live at CAICT 2026-05-13 against
        E7515B firmware 28.21.0.32."""
        from app.hal.uxm_command_profiles import UxmLteNrIratProfile

        bs = self._build_bs(lambda cmd: '0,"No error"')
        bs._cmds = UxmLteNrIratProfile  # type: ignore[attr-defined]
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id), "params": {"include_supported": True}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["extra"]["profile"] == "LTE_NR_IRAT"
        # ⚠ P1-33（2026-08-04）：**旧判据「IRAT 一定比 5G 少」不再成立** ——
        #   按手册给 IRAT 补了 14 条 MAC 配置命令（TDD 六条 / APPLY / BWP PRB 查询），
        #   同期 5G profile 那 11 条**本来是编的**（手册 0 命中）已置 `None`。
        #   **去掉**这个大小断言，不换新魔数 —— 本门真正要守的是
        #   「普查确实遍历到了当前方言的命令集」，方言名 + 非空即可。
        total = body["extra"]["total_probed"]
        assert total > 0, "普查一条都没遍历到"
        # All emitted steps should use the BSE: prefix and CELL1.
        non_bse = [s for s in body["steps"] if "CONFig:NR5G:CELL1" in s["label"] and "BSE:" not in s["label"]]
        assert non_bse == [], f"IRAT profile emitted non-BSE NR commands: {non_bse}"

    def test_fail_fast_aborts_after_consecutive_timeouts(self, lab_with_bs, monkeypatch):
        """If 3 commands in a row hit VI_ERROR_TMO (stuck SCPI channel),
        probe aborts early instead of grinding through all 76. Same
        pattern as the FS16/F64 probes; saves the operator from a
        5-minute hang when HAL session goes half-closed."""
        bs = MagicMock()
        bs._write = MagicMock(return_value=None)

        # Every query raises a VISA timeout exception.
        def fake_query(cmd):
            if cmd == "SYSTem:ERRor?":
                raise Exception("VisaIOError: VI_ERROR_TMO (-1073807339)")
            raise Exception("VisaIOError: VI_ERROR_TMO (-1073807339)")
        bs._query = fake_query
        _patched_hal(monkeypatch, drivers={"baseStation": bs})

        resp = client.post(
            "/api/v1/diagnostic-sequences/uxm_scpi_compatibility/run",
            json={"lab_profile_id": str(lab_with_bs.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["extra"]["aborted_early"] is True
        # Should NOT have probed all 76 — bail-out triggered early.
        # Be generous on the upper bound to avoid flake (timeout-detection
        # streak resets if SYST:ERR? happens to return, etc.).
        assert body["extra"]["total_probed"] >= 5, "total_probed reports the full set size, not progress; sanity"
        assert "ABORTED" in body["summary"]
        assert "/api/v1/instruments/hal/reload" in body["summary"]


class TestProfileForDriverHelper:
    """Codex P2 on PR #44 follow-up: ``_profile_for_driver`` must accept
    BOTH instance (current ``RealUxmDriver._cmds``) AND class (legacy
    test fixtures still doing ``mock._cmds = SomeProfileClass``). Pre-fix
    the helper gated on ``isinstance(profile, type)``, so an IRAT driver
    with ``_cmds = UxmLteNrIratProfile()`` fell through to the 5G
    fallback and the diagnostic probed CELL0 / wrong SCPI tree.
    """

    def test_returns_instance_when_cmds_is_instance(self):
        from app.diagnostics.sequences.uxm_scpi_compatibility import (
            _profile_for_driver,
        )
        from app.hal.uxm_command_profiles import UxmLteNrIratProfile

        bs = MagicMock()
        bs._cmds = UxmLteNrIratProfile()  # PR #44 storage shape
        result = _profile_for_driver(bs)
        # Returns the instance itself, not the class — downstream helpers
        # use getattr / inspect.getmembers, which work on both.
        assert isinstance(result, UxmLteNrIratProfile)
        assert result is bs._cmds
        # Pin the field that would have been wrong if fallback kicked in:
        # IRAT uses CELL1, 5G default uses CELL0.
        assert result.PRIMARY_CELL == "CELL1"

    def test_returns_class_when_cmds_is_class_legacy(self):
        from app.diagnostics.sequences.uxm_scpi_compatibility import (
            _profile_for_driver,
        )
        from app.hal.uxm_command_profiles import UxmLteNrIratProfile

        bs = MagicMock()
        bs._cmds = UxmLteNrIratProfile  # legacy fixture shape
        result = _profile_for_driver(bs)
        assert result is UxmLteNrIratProfile
        assert result.PRIMARY_CELL == "CELL1"

    def test_falls_back_to_5g_when_cmds_is_magicmock_auto(self):
        from app.diagnostics.sequences.uxm_scpi_compatibility import (
            _profile_for_driver,
        )
        from app.hal.uxm_command_profiles import Uxm5GNRTestAppProfile

        # MagicMock auto-fabricates _cmds as another Mock — neither
        # an instance nor a class subclassing UxmTestApp. Must fall back.
        bs = MagicMock()
        result = _profile_for_driver(bs)
        assert result is Uxm5GNRTestAppProfile

    def test_falls_back_to_5g_when_cmds_missing(self):
        from app.diagnostics.sequences.uxm_scpi_compatibility import (
            _profile_for_driver,
        )
        from app.hal.uxm_command_profiles import Uxm5GNRTestAppProfile

        class BareBS:
            pass

        result = _profile_for_driver(BareBS())
        assert result is Uxm5GNRTestAppProfile


class TestVnaEnaHealthSequence:
    """Four-step pre-calibration health probe for Keysight E5071C ENA.

    The sequence drives ``vna.get_identity()``, ``vna.setup_sweep()``,
    ``vna.measure_s_param()``, ``vna.get_trace_data()`` — we mock each with
    AsyncMock so tests stay decoupled from a live VISA session.
    """

    def test_registered_in_loader(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "vna_ena_health" in keys

    def test_metadata_requires_vna(self):
        resp = client.get("/api/v1/diagnostic-sequences")
        entry = next(s for s in resp.json() if s["key"] == "vna_ena_health")
        assert entry["required_categories"] == ["vna"]
        assert entry["safe_during_test"] is False
        param_names = {p["name"] for p in entry["params_schema"]}
        assert {"center_freq_mhz", "span_mhz", "points"}.issubset(param_names)

    def _build_vna(
        self,
        idn: str = "Keysight Technologies,E5071C,MY12345678,A.12.34",
        setup_ok: bool = True,
        measure_ok: bool = True,
        trace=None,
    ):
        """Build a fake VNA driver with the four methods the sequence needs."""
        if trace is None:
            # 101 points of plausible S21 around -40 dB.
            trace = [complex(0.01 * (i + 1), 0.001 * i) for i in range(101)]
        vna = MagicMock()
        vna.get_identity = AsyncMock(return_value=idn)
        vna.setup_sweep = AsyncMock(return_value=setup_ok)
        vna.measure_s_param = AsyncMock(return_value=measure_ok)
        vna.get_trace_data = AsyncMock(return_value=trace)
        return vna

    def test_happy_path_returns_trace(self, lab_with_vna, monkeypatch):
        vna = self._build_vna()
        _patched_hal(monkeypatch, drivers={"vna": vna})

        resp = client.post(
            "/api/v1/diagnostic-sequences/vna_ena_health/run",
            json={"lab_profile_id": str(lab_with_vna.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True, body
        assert "E5071C health OK" in body["summary"]
        labels = [s["label"] for s in body["steps"]]
        assert "*IDN?" in labels
        assert any("setup_sweep" in lb for lb in labels)
        assert "measure_s_param('S21')" in labels
        assert "get_trace_data()" in labels
        assert body["extra"]["trace_stats"]["len"] == 101
        assert body["extra"]["trace_stats"]["nan_count"] == 0
        # setup_sweep was called with sweep around center 2450 MHz ± 50 MHz.
        start_hz, stop_hz, pts = vna.setup_sweep.call_args.args
        assert pts == 101
        assert abs(start_hz - 2.4e9) < 1e3
        assert abs(stop_hz - 2.5e9) < 1e3

    def test_idn_wrong_model_fails(self, lab_with_vna, monkeypatch):
        """IP points at a different instrument — IDN check guards us."""
        vna = self._build_vna(idn="Keysight Technologies,N5227B,SOMEONE_ELSES_PNA,A.1.0")
        _patched_hal(monkeypatch, drivers={"vna": vna})

        resp = client.post(
            "/api/v1/diagnostic-sequences/vna_ena_health/run",
            json={"lab_profile_id": str(lab_with_vna.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "N5227B" in body["summary"]
        assert "not an E5071-family ENA" in body["summary"]
        # We bail after IDN — setup_sweep must not have been called.
        vna.setup_sweep.assert_not_called()

    def test_setup_sweep_failure_fails_clean(self, lab_with_vna, monkeypatch):
        vna = self._build_vna(setup_ok=False)
        _patched_hal(monkeypatch, drivers={"vna": vna})

        resp = client.post(
            "/api/v1/diagnostic-sequences/vna_ena_health/run",
            json={"lab_profile_id": str(lab_with_vna.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "setup_sweep failed" in body["summary"]
        # measure_s_param must not have been called once setup failed.
        vna.measure_s_param.assert_not_called()

    def test_trace_with_nan_fails(self, lab_with_vna, monkeypatch):
        bad_trace = [complex(1.0, 1.0)] * 50 + [complex(float("nan"), 0.0)] * 51
        vna = self._build_vna(trace=bad_trace)
        _patched_hal(monkeypatch, drivers={"vna": vna})

        resp = client.post(
            "/api/v1/diagnostic-sequences/vna_ena_health/run",
            json={"lab_profile_id": str(lab_with_vna.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert body["extra"]["trace_stats"]["nan_count"] == 51
        assert "NaN" in body["steps"][-1]["detail"]

    def test_all_zero_trace_passes_with_note(self, lab_with_vna, monkeypatch):
        """Open port → S21 ~ 0 — legit operator scenario, must not fail."""
        zero_trace = [complex(0.0, 0.0)] * 101
        vna = self._build_vna(trace=zero_trace)
        _patched_hal(monkeypatch, drivers={"vna": vna})

        resp = client.post(
            "/api/v1/diagnostic-sequences/vna_ena_health/run",
            json={"lab_profile_id": str(lab_with_vna.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert "ALL-ZERO" in body["steps"][-1]["detail"]
        assert "trace all-zero" in body["summary"]

    def test_fails_clean_when_no_driver_loaded(self, lab_with_vna, monkeypatch):
        _patched_hal(monkeypatch, drivers={})

        resp = client.post(
            "/api/v1/diagnostic-sequences/vna_ena_health/run",
            json={"lab_profile_id": str(lab_with_vna.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "vna" in body["summary"] and "scpi-probe" in body["summary"]


class TestPropsimF64HealthSequence:
    """Two-phase PROPSIM F64 health probe.

    Phase A walks ~24 SCPI headers, classifying each by SYST:ERR? response.
    Phase B exercises 5 read-only driver APIs to catch parser/timeout
    failures that header probes miss.

    Tests mock the CE driver: ``_query`` is set to a callable with a
    programmable side_effect; ``_write`` is a MagicMock; the high-level
    methods (``query_runtime_environment`` etc.) are AsyncMock'd.
    """

    DEFAULT_IDN = "PROPSIM,F64,SN12345,FW1.4.0"

    def test_registered_in_loader(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "propsim_f64_health" in keys

    def test_metadata_requires_channel_emulator(self):
        resp = client.get("/api/v1/diagnostic-sequences")
        entry = next(s for s in resp.json() if s["key"] == "propsim_f64_health")
        assert entry["required_categories"] == ["channelEmulator"]
        assert entry["safe_during_test"] is False
        param_names = {p["name"] for p in entry["params_schema"]}
        assert {"include_supported", "functional_checks"}.issubset(param_names)

    def _build_ce(
        self,
        *,
        idn: str = DEFAULT_IDN,
        sys_info: str = "",
        err_for_probe=lambda probed_cmd: '0,"No error"',
        runtime_env=None,
        alignment=None,
        external_units=None,
        output_cal=None,
        metrics_obj=None,
    ):
        """Build a fake PROPSIM driver.

        `err_for_probe(last_cmd_str)` decides what SYST:ERR? returns
        after the last probed command. Default: clean queue.
        `sys_info` lets a test simulate a rebranded firmware where IDN
        doesn't say PROPSIM but SYST:INFO? does (or vice versa).
        """
        from datetime import datetime
        from app.hal.base import InstrumentMetrics

        ce = MagicMock()
        ce._write = MagicMock(return_value=None)
        state = {"last_probe": None}

        def fake_query(cmd, *_args, **_kw):
            if cmd == "*IDN?":
                return idn
            if cmd == "SYST:INFO?":
                return sys_info
            if cmd == "SYST:ERR?":
                last = state["last_probe"]
                return err_for_probe(last) if last else '0,"No error"'
            state["last_probe"] = cmd
            return ""

        ce._query = fake_query
        ce.query_runtime_environment = AsyncMock(
            return_value=runtime_env if runtime_env is not None
            else {1: {"channel_count": 64, "running": False}}
        )
        ce.get_user_alignment_status = AsyncMock(return_value=alignment)
        ce.list_external_units = AsyncMock(
            return_value=external_units if external_units is not None else []
        )
        ce.get_output_calibration = AsyncMock(return_value=output_cal)
        ce.get_metrics = AsyncMock(
            return_value=metrics_obj if metrics_obj is not None
            else InstrumentMetrics(timestamp=datetime.utcnow(), metrics={})
        )
        return ce

    def test_happy_path_all_supported(self, lab_with_ce, monkeypatch):
        ce = self._build_ce()
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True, body
        assert "PROPSIM F64 health OK" in body["summary"]
        assert body["extra"]["counts"]["UNSUPPORTED"] == 0
        assert body["extra"]["critical_unsupported"] == []
        assert body["extra"]["functional_failures"] == 0
        # Phase B steps are emitted as a group at the end.
        labels = [s["label"] for s in body["steps"]]
        assert "get_metrics()" in labels
        assert any("query_runtime_environment" in lb for lb in labels)

    def test_f64_opt_unsupported_is_expected_and_not_a_blocker(self, lab_with_ce, monkeypatch):
        """Real F64 ATE firmware does not implement ``*OPT?``.

        License discovery reads the SYSTem:INFO? reply instead (手册
        §20.4.2.4), so this legacy IEEE-488 query may remain visible as
        unsupported but must not fail the health sequence.
        """
        broken = "*OPT?"

        def err_for(probe_cmd):
            if probe_cmd == broken:
                return '-113,"Undefined header"'
            return '0,"No error"'

        ce = self._build_ce(err_for_probe=err_for)
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert "BLOCKER" not in body["summary"]
        assert "OPT" not in body["extra"]["critical_unsupported"]
        opt_step = next(step for step in body["steps"] if step["label"].startswith("OPT "))
        assert opt_step["success"] is False
        assert "UNSUPPORTED" in opt_step["detail"]

    def test_state_error_categorized_as_ok(self, lab_with_ce, monkeypatch):
        """-200..-299 = header exists, state rejects query — not a blocker."""
        ce = self._build_ce(
            err_for_probe=lambda cmd: '-220,"Parameter error;not ready"',
        )
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["extra"]["counts"]["SUPPORTED_BUT_STATE"] > 0
        assert body["extra"]["counts"]["UNSUPPORTED"] == 0

    def test_idn_wrong_model_fails_before_surface(self, lab_with_ce, monkeypatch):
        """Wrong IDN → bail before walking 24 commands against the
        wrong instrument."""
        ce = self._build_ce(idn="VENDOR_X,SomethingElse,SN0,FW0")
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "PROPSIM" in body["summary"]
        assert "expected any of" in body["summary"]
        # Only the IDN step should appear — Phase A didn't run.
        assert len(body["steps"]) == 1

    def test_functional_failure_fails_overall(self, lab_with_ce, monkeypatch):
        ce = self._build_ce()
        # Make query_runtime_environment raise — proves Phase B catches
        # crashes that Phase A header-probing can't.
        ce.query_runtime_environment = AsyncMock(
            side_effect=RuntimeError("CH:MOD:CONT:ENV parser exploded")
        )
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "functional check" in body["summary"]
        assert body["extra"]["functional_failures"] >= 1
        runtime_step = next(
            s for s in body["steps"] if s["label"].startswith("query_runtime_environment")
        )
        assert runtime_step["success"] is False
        assert "RuntimeError" in runtime_step["detail"]

    def test_functional_checks_can_be_disabled(self, lab_with_ce, monkeypatch):
        ce = self._build_ce()
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={
                "lab_profile_id": str(lab_with_ce.id),
                "params": {"functional_checks": False},
            },
        )
        body = resp.json()
        assert body["success"] is True
        # No Phase B step labels present.
        assert not any(
            lb in {s["label"] for s in body["steps"]}
            for lb in (
                "query_runtime_environment([1])",
                "get_user_alignment_status()",
                "list_external_units()",
                "get_output_calibration(1)",
                "get_metrics()",
            )
        )
        assert body["extra"]["functional_failures"] == 0
        assert body["extra"]["functional_checks"] is False

    def test_soft_pass_when_license_returns_none(self, lab_with_ce, monkeypatch):
        """User alignment / output cal returning None = license absent,
        no SGH attached — soft pass, not a failure."""
        ce = self._build_ce(alignment=None, output_cal=None)
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is True
        align_step = next(
            s for s in body["steps"] if s["label"] == "get_user_alignment_status()"
        )
        assert align_step["success"] is True
        assert "None" in align_step["detail"]

    def test_fails_clean_when_no_driver_loaded(self, lab_with_ce, monkeypatch):
        _patched_hal(monkeypatch, drivers={})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "channelEmulator" in body["summary"] and "scpi-probe" in body["summary"]

    def test_refuses_mock_driver(self, lab_with_ce, monkeypatch):
        """P1-14: in mock mode the mock CE loads, so the probe gets PAST the
        no-driver check — but a hardware identity probe against a mock returns
        empty IDN ("Identity check failed: IDN=''"). The probe must refuse the
        mock with an actionable summary instead of that cryptic failure."""
        from app.hal import MockChannelEmulator

        _patched_hal(monkeypatch, drivers={
            "channelEmulator": MockChannelEmulator("mock-ce", {"model": "UXM 5G E7515B"}),
        })
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "mock 驱动" in body["summary"]      # names it as mock
        assert "real 模式" in body["summary"]       # actionable: switch to real
        assert "Identity check failed" not in body["summary"]  # not the cryptic path

    def test_identity_falls_back_to_sys_info(self, lab_with_ce, monkeypatch):
        """Backported from FS16 probe: if IDN doesn't carry the PROPSIM
        tag but SYST:INFO? does, we still pass the identity gate. Future-
        proofs against firmware rebrands."""
        ce = self._build_ce(
            idn="Keysight Technologies,GenericFW,SN0,1.0",  # no PROPSIM
            sys_info="PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz",
        )
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is True, body
        assert body["extra"]["sys_info"] is not None

    def test_phase_a_aborts_on_consecutive_timeouts(self, lab_with_ce, monkeypatch):
        """Backported circuit breaker: 3 consecutive VISA timeouts on
        SYST:ERR? short-circuits the rest of Phase A. Without this, a
        stuck SCPI channel would eat ~10 s per remaining command."""
        # Every probe gets a VISA timeout response in the error queue.
        ce = self._build_ce(
            err_for_probe=lambda cmd: 'err-read raised: VI_ERROR_TMO timeout',
        )
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_f64_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "ABORTED" in body["summary"]
        assert "3 consecutive VISA timeouts" in body["summary"]
        assert body["extra"]["phase_a_aborted"] is True
        # Phase B must NOT have run (would have eaten more time)
        labels = [s["label"] for s in body["steps"]]
        assert "get_metrics()" not in labels
        assert any(lb == "ABORTED" for lb in labels)


class TestPropsimFs16HealthSequence:
    """PROPSIM FS16 (F8820A) health probe — different SCPI dialect from F64.

    The mock CE here mimics FS16's empirically-observed behaviour:
    *IDN? returns F8820A, SYST:INFO? returns "PROPSIM FS16,...", *OPT?
    returns ``-100,"ATE command not supported"``, channel-indexed
    queries return ``-200,"Channel not found"`` (state error), and
    everything else returns 0,"No error".
    """

    DEFAULT_IDN = "Keysight Technologies,F8820A,MY62500170,10.2"
    DEFAULT_INFO = "PROPSIM FS16,4,RF,v2.0,4,Band: 3MHz - 6000MHz,Main license,Bandwidth:100.000MHz"

    def test_registered_in_loader(self):
        loader.reset_cache()
        resp = client.get("/api/v1/diagnostic-sequences")
        assert resp.status_code == 200
        keys = [s["key"] for s in resp.json()]
        assert "propsim_fs16_health" in keys

    def test_metadata_requires_channel_emulator(self):
        resp = client.get("/api/v1/diagnostic-sequences")
        entry = next(s for s in resp.json() if s["key"] == "propsim_fs16_health")
        assert entry["required_categories"] == ["channelEmulator"]
        assert entry["safe_during_test"] is False

    def _build_ce(
        self,
        *,
        idn: str = DEFAULT_IDN,
        sys_info: str = DEFAULT_INFO,
        # Function mapping last_probed_cmd -> SYST:ERR? response text.
        # The default mimics real FS16: *OPT? UNSUPPORTED, channel-indexed
        # queries STATE-rejected, everything else clean.
        err_for_probe=None,
        sim_state: str = "CLOSED",
        playback_dir: str = "01.smu,02.smu",
        alignment_name=None,
    ):
        from datetime import datetime
        from app.hal.base import InstrumentMetrics

        ce = MagicMock()
        ce._write = MagicMock(return_value=None)
        state = {"last_probe": None}

        def default_err_for_probe(cmd):
            if cmd == "*OPT?":
                return '-100,"Command error;ATE command not supported"'
            # Channel-indexed queries on a CLOSED simulation return -200
            if cmd and ":CH " in cmd or (cmd and cmd.endswith(":CH? 1")):
                return '-200,"Execution error;Channel not found"'
            if cmd in ("DIAG:SIMU:MODEL:STATIC?", "OUTP:CALIB:GET? 1",
                       "OUTP:MEAS:RES:GET? 1", "ROUT:PATH:CONN? 1"):
                return '-200,"Execution error;Wrong device state for command"'
            return '0,"No error"'

        eff_err = err_for_probe or default_err_for_probe

        def fake_query(cmd, *_a, **_kw):
            if cmd == "*IDN?":
                return idn
            if cmd == "SYST:INFO?":
                return sys_info
            if cmd == "SYST:ERR?":
                last = state["last_probe"]
                resp = eff_err(last) if last else '0,"No error"'
                state["last_probe"] = None  # consume
                return resp
            state["last_probe"] = cmd
            return ""

        ce._query = fake_query
        ce.query_simulation_state = AsyncMock(return_value=sim_state)
        ce.list_playback_directory = AsyncMock(return_value=playback_dir)
        ce.query_user_alignment_name = AsyncMock(return_value=alignment_name)
        ce.get_metrics = AsyncMock(
            return_value=InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics={"product": "PROPSIM FS16", "simulation_state": sim_state},
            )
        )
        return ce

    def test_happy_path_with_real_fs16_shape(self, lab_with_ce, monkeypatch):
        """Default mock = real FS16 behaviour. Should succeed: *OPT?
        UNSUPPORTED is expected; channel-indexed STATE-rejects are fine
        (no sim open)."""
        ce = self._build_ce()
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})

        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_fs16_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True, body
        assert "PROPSIM FS16 health OK" in body["summary"]
        assert body["extra"]["critical_unsupported"] == []
        assert body["extra"]["functional_failures"] == 0
        # *OPT? row should be present + marked as expected, success=True
        opt_step = next(s for s in body["steps"] if s["label"].startswith("OPT "))
        assert "(expected)" in opt_step["detail"]
        assert opt_step["success"] is True

    def test_identity_falls_back_to_sys_info(self, lab_with_ce, monkeypatch):
        """If IDN doesn't carry an F8820/FS16 tag but SYST:INFO? does,
        we still pass the gate."""
        ce = self._build_ce(
            idn="Keysight Technologies,GenericFW,SN0,1.0",  # no F8820 / FS16
            sys_info="PROPSIM FS16,4,RF,...",
        )
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_fs16_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is True, body

    def test_identity_fails_when_neither_matches(self, lab_with_ce, monkeypatch):
        ce = self._build_ce(
            idn="VENDOR_X,SomethingElse,SN0,FW0",
            sys_info="SomethingElse,1,RF",
        )
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_fs16_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "Identity check failed" in body["summary"]
        # Bailed before Phase A — only the IDN step row.
        assert len(body["steps"]) == 1

    def test_critical_simulation_state_unsupported_blocks(self, lab_with_ce, monkeypatch):
        """If DIAG:SIMU:STATe? itself is UNSUPPORTED, that's a real
        blocker — we can't tell whether the box is healthy."""

        def err_for(cmd):
            if cmd == "DIAG:SIMU:STATe?":
                return '-113,"Undefined header"'
            if cmd == "*OPT?":
                return '-100,"ATE command not supported"'
            return '0,"No error"'

        ce = self._build_ce(err_for_probe=err_for)
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_fs16_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "BLOCKER" in body["summary"]
        assert "SIMU_STATE" in body["extra"]["critical_unsupported"]

    def test_state_rejected_channel_queries_pass_overall(self, lab_with_ce, monkeypatch):
        """Default mock has channel-indexed queries STATE-rejected — the
        expected reality when no simulation is OPEN. Should NOT fail
        overall; counts.SUPPORTED_BUT_STATE > 0."""
        ce = self._build_ce()
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_fs16_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["extra"]["counts"]["SUPPORTED_BUT_STATE"] > 0

    def test_functional_failure_fails_overall(self, lab_with_ce, monkeypatch):
        ce = self._build_ce()
        ce.get_metrics = AsyncMock(side_effect=RuntimeError("VISA timeout"))
        _patched_hal(monkeypatch, drivers={"channelEmulator": ce})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_fs16_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "functional check" in body["summary"]
        metrics_step = next(s for s in body["steps"] if s["label"] == "get_metrics()")
        assert metrics_step["success"] is False
        assert "RuntimeError" in metrics_step["detail"]

    def test_fails_clean_when_no_driver_loaded(self, lab_with_ce, monkeypatch):
        _patched_hal(monkeypatch, drivers={})
        resp = client.post(
            "/api/v1/diagnostic-sequences/propsim_fs16_health/run",
            json={"lab_profile_id": str(lab_with_ce.id)},
        )
        body = resp.json()
        assert body["success"] is False
        assert "channelEmulator" in body["summary"] and "scpi-probe" in body["summary"]


class TestRealPropsimFs16Driver:
    """Unit tests for the FS16 driver itself (no real instrument)."""

    def _make_driver(self, **overrides):
        from app.hal.propsim_fs16 import RealPropsimFs16Driver
        config = {"ip": "192.168.0.100", "port": 5025, **overrides}
        return RealPropsimFs16Driver("fs16-test", config)

    def test_load_modes_are_empty_until_playback_is_really_implemented(self):
        """FS16 **不宣称任何加载模式** —— P2-57 把一个假声明换成了真拒绝。

        ⚠️ 本用例原名 `test_load_modes_external_waveform_only`，断言
        `modes == [EXTERNAL_WAVEFORM]`，理由写的是「FS16 只做文件播放」。
        实况是：`upload_asc_files` / `start_emulation` **从未实现**，调用会抛
        不受控的 `AttributeError`（那 14 个抽象方法当时整段掉在类体之外）。
        也就是说这条断言守住的是一个**假承诺**。

        P2-57 起 load modes 由 manifest 派生，FS16 的三种模式全部
        `not_implemented` → 空。真实实现落地时，改 manifest 即可，本门随之变红
        提醒同步。
        """
        d = self._make_driver()
        assert d.get_supported_load_modes() == []
        assert d.adapter_manifest.supported_load_modes() == ()

    def test_calibration_tone_capabilities_empty_in_mvp(self):
        d = self._make_driver()
        assert d.get_calibration_tone_capabilities() == []

    def test_parse_sys_info_extracts_fs16_fields(self):
        d = self._make_driver()
        d._parse_sys_info(
            "PROPSIM FS16,4,RF,v2.0,4,Band: 3MHz - 6000MHz,Main license,Bandwidth:100.000MHz"
        )
        assert d._product_family == "PROPSIM FS16"
        assert d._channel_count == 4
        assert d._bandwidth_mhz == 100.0
        assert "3MHz" in d._band_label
        assert "license" in d._license_label.lower()

    def test_parse_sys_info_resilient_to_empty(self):
        d = self._make_driver()
        d._parse_sys_info("")
        # Stays at constructor defaults
        assert d._channel_count == 4

    def test_parse_sys_info_resilient_to_garbage(self):
        d = self._make_driver()
        d._parse_sys_info("not-a-valid-info-string")
        assert d._product_family == "not-a-valid-info-string"
        # Bandwidth label absent → stays default
        assert d._bandwidth_mhz == 100.0


class TestStepRawFieldPlumbing:
    """`SequenceStepResult.raw` —— 仪器原始回复必须一路通到响应与**归档**。

    动机 (2026-07-26): 现场验证问题分两类, "通不通" 和 "返回什么字面值"。后者是
    F64R-7 一整类问题的问法, 回复混在自由文本 ``detail`` 里就不可比对、不可归档
    —— 而归档 (``DiagnosticRun.output_excerpt``) 正是下次现场用来跟本次对照的东西。
    """

    def _run_with_steps(self, db, lab, monkeypatch, steps, *, extra=None):
        """借 idn_sweep 的路由跑一个返回指定 steps 的假序列。"""
        from app.diagnostics import loader
        from app.diagnostics.protocol import SequenceMetadata, SequenceRunResult

        class _StubSequence:
            metadata = SequenceMetadata(
                name="raw-plumbing-stub", description="test only",
            )

            @staticmethod
            async def run(ctx, hal, params, *, log):
                log("stub ran")
                return SequenceRunResult(
                    success=True,
                    summary="ok",
                    steps=steps,
                    extra=extra or {},
                )

        monkeypatch.setattr(loader, "get_sequence", lambda key: _StubSequence)
        _patched_hal(monkeypatch, drivers={})
        resp = client.post(
            "/api/v1/diagnostic-sequences/raw_stub/run",
            json={"lab_profile_id": str(lab.id), "run_by": "pytest"},
        )
        assert resp.status_code == 200
        body = resp.json()
        audit = db.query(DiagnosticRun).filter(
            DiagnosticRun.id == uuid.UUID(body["diagnostic_run_id"])
        ).first()
        return body, audit

    def test_raw_reaches_response_and_archive_verbatim(self, db, lab_with_bs, monkeypatch):
        from app.diagnostics.protocol import SequenceStepResult

        body, audit = self._run_with_steps(db, lab_with_bs, monkeypatch, [
            SequenceStepResult(label="STATE?", success=True, detail="RUNNING",
                               raw='  "RunNing"  '),
        ])
        assert body["steps"][0]["raw"] == '  "RunNing"  ', "响应里必须原样"
        # 归档用 repr 存 —— 前后空白与引号本身就是结论的一部分, 不能被行首行尾吃掉。
        assert '\'  "RunNing"  \'' in (audit.output_excerpt or ""), (
            f"归档缺原始回复: {audit.output_excerpt!r}"
        )

    def test_empty_string_reply_is_archived_not_dropped(self, db, lab_with_bs, monkeypatch):
        """空串回复**是一条结论**("仪器回了个空"), 不能被真值判断当成"没有回复"丢掉。"""
        from app.diagnostics.protocol import SequenceStepResult

        body, audit = self._run_with_steps(db, lab_with_bs, monkeypatch, [
            SequenceStepResult(label="STATE?", success=False, detail="空回复", raw=""),
        ])
        assert body["steps"][0]["raw"] == ""
        assert "raw: ''" in (audit.output_excerpt or "")

    def test_steps_without_reply_stay_none(self, db, lab_with_bs, monkeypatch):
        """纯写命令 / 驱动 API 调用没有仪器回复 → None, 归档不应凭空多一行 raw。"""
        from app.diagnostics.protocol import SequenceStepResult

        body, audit = self._run_with_steps(db, lab_with_bs, monkeypatch, [
            SequenceStepResult(label="connect", success=True, detail="ok"),
        ])
        assert body["steps"][0]["raw"] is None
        assert "raw:" not in (audit.output_excerpt or "")

    def test_structured_result_survives_excerpt_truncation(
        self, db, lab_with_bs, monkeypatch,
    ):
        """后置 SCPI 证据不能只活在即时响应或 2KB 摘要的尾部。"""
        from app.diagnostics.protocol import SequenceStepResult

        decisive = {
            "observations": {
                "after_protocol_status": "CONNected",
                "after_band": "N78",
            },
            "coverage": {"band": {"covered": True}},
            "formal_verdict": "unverified",
        }
        verbose_steps = [
            SequenceStepResult(
                label=f"verbose-{index}",
                success=True,
                detail="D" * 180,
                raw=f"raw-{index}",
            )
            for index in range(30)
        ]

        body, audit = self._run_with_steps(
            db,
            lab_with_bs,
            monkeypatch,
            verbose_steps,
            extra=decisive,
        )

        assert "truncated" in (audit.output_excerpt or "")
        assert body["extra"] == decisive
        assert audit.result_extra == decisive

        expected_evidence = {
            "schema_version": 1,
            "summary": body["summary"],
            "duration_ms": body["duration_ms"],
            "log": body["log"],
            "steps": body["steps"],
            "extra": body["extra"],
        }
        assert audit.sequence_evidence == expected_evidence

        detail = client.get(f"/api/v1/diagnostic-runs/{audit.id}")
        assert detail.status_code == 200
        assert detail.json()["result_extra"] == decisive
        assert detail.json()["sequence_evidence"] == expected_evidence

        listing = client.get(
            "/api/v1/diagnostic-runs",
            params={"kind": "scpi_sequence"},
        )
        assert listing.status_code == 200
        assert "sequence_evidence" not in listing.json()["items"][0]
