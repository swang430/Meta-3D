"""Idempotency + correctness tests for the 6 bootstrap seeders.

Companion to ``test_bootstrap_and_duplicate.py`` (which covers the
framework + chamber_presets seeder + duplicate workflow). This file
covers the 5 seeders added in the seed-script consolidation:

  - probes
  - instruments
  - sequences
  - report_templates
  - test_case_templates

Each test exercises a fresh in-memory DB, runs the seeder, asserts the
expected rows landed, then runs it again and asserts no duplicates.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberConfiguration
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.probe import Probe
from app.models.report import ReportTemplate
from app.models.test_plan import TestCase
from app.services.bootstrap import run_all
from app.services.bootstrap.chamber_presets import chamber_presets_seeder
from app.services.bootstrap.instruments import instruments_seeder
from app.services.bootstrap.probes import probes_seeder
from app.services.bootstrap.report_templates import report_templates_seeder
from app.services.bootstrap.test_case_templates import test_case_templates_seeder


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


# ============================================================================
# Probes seeder
# ============================================================================

class TestProbesSeeder:

    def test_probes_attach_to_type_c_preset(self, db_session):
        # probes depends on chamber_presets
        run_all(db_session, [chamber_presets_seeder, probes_seeder])

        type_c = (
            db_session.query(ChamberConfiguration)
            .filter(
                ChamberConfiguration.chamber_type == "type_c",
                ChamberConfiguration.is_system_preset.is_(True),
            )
            .first()
        )
        assert type_c is not None
        probes = db_session.query(Probe).filter(
            Probe.chamber_config_id == type_c.id
        ).all()
        assert len(probes) == 32
        # Each numbered probe has V + H
        nums = [p.probe_number for p in probes]
        assert max(nums) == 32
        assert {p.polarization for p in probes} == {"V", "H"}

    def test_probes_idempotent(self, db_session):
        run_all(db_session, [chamber_presets_seeder, probes_seeder])
        run_all(db_session, [chamber_presets_seeder, probes_seeder], force=True)
        assert db_session.query(Probe).count() == 32

    def test_probes_skips_when_no_chamber(self, db_session):
        # Don't run chamber_presets first — probes should soft-skip
        report = run_all(db_session, [probes_seeder])
        _, result, status = report[0]
        assert status == "ran"
        assert result.inserted == 0
        assert db_session.query(Probe).count() == 0


# ============================================================================
# Instruments seeder
# ============================================================================

class TestInstrumentsSeeder:

    def test_seeds_seven_categories_with_models(self, db_session):
        run_all(db_session, [instruments_seeder])

        cats = db_session.query(InstrumentCategory).all()
        assert len(cats) == 7
        keys = {c.category_key for c in cats}
        assert keys == {
            "channelEmulator", "baseStation", "signalAnalyzer", "positioner",
            "vna", "rfSwitch", "vectorSignalGenerator",
        }

        # Each category should have at least one model + a default connection
        for cat in cats:
            models = db_session.query(InstrumentModel).filter(
                InstrumentModel.category_id == cat.id
            ).count()
            assert models > 0, f"category {cat.category_key} has no models"
            conn = db_session.query(InstrumentConnection).filter(
                InstrumentConnection.category_id == cat.id
            ).first()
            assert conn is not None, f"category {cat.category_key} has no connection"

    def test_idempotent_force_rerun(self, db_session):
        run_all(db_session, [instruments_seeder])
        cat_count_first = db_session.query(InstrumentCategory).count()
        model_count_first = db_session.query(InstrumentModel).count()

        run_all(db_session, [instruments_seeder], force=True)
        assert db_session.query(InstrumentCategory).count() == cat_count_first
        assert db_session.query(InstrumentModel).count() == model_count_first

    def test_default_model_selected(self, db_session):
        run_all(db_session, [instruments_seeder])
        # channelEmulator default is PROPSIM F64
        ce = db_session.query(InstrumentCategory).filter(
            InstrumentCategory.category_key == "channelEmulator"
        ).first()
        assert ce.selected_model_id is not None
        selected = db_session.query(InstrumentModel).filter(
            InstrumentModel.id == ce.selected_model_id
        ).first()
        assert selected.model == "PROPSIM F64"


# ============================================================================
# Sequences seeder
# ============================================================================

# ARCH-1 S4c: TestSequencesSeeder 随 sequences_seeder 删除 ——
# 它给 TestSequence 表播种, 而 /test-sequences 四条路由 S4b 已删,
# TestStep.sequence_library_id 那条引用链也随计划链封存, 播出来的行
# 无人可读。

# ============================================================================
# Report templates seeder
# ============================================================================

class TestReportTemplatesSeeder:

    def test_seeds_six_templates(self, db_session):
        run_all(db_session, [report_templates_seeder])
        templates = db_session.query(ReportTemplate).all()
        names = {t.name for t in templates}
        assert names == {
            "Standard Test Report",
            "Comparison Analysis Report",
            "3GPP Regulatory Compliance Report",
            "Performance Analysis Report",
            "Executive Summary Report",
            "Virtual Road Test Report",
        }
        # One should be marked default
        defaults = [t for t in templates if t.is_default]
        assert len(defaults) == 1
        assert defaults[0].name == "Standard Test Report"

    def test_idempotent(self, db_session):
        run_all(db_session, [report_templates_seeder])
        run_all(db_session, [report_templates_seeder], force=True)
        assert db_session.query(ReportTemplate).count() == 6


# ============================================================================
# Test-case templates seeder
# ============================================================================

class TestTestCaseTemplatesSeeder:

    def test_templates_have_null_lab_profile(self, db_session):
        run_all(db_session, [test_case_templates_seeder])
        cases = db_session.query(TestCase).filter(
            TestCase.is_template.is_(True)
        ).all()
        assert len(cases) > 0
        # Per Option A: every template must have lab_profile_id=None,
        # regardless of any "active LabProfile" in the DB.
        for tc in cases:
            assert tc.lab_profile_id is None, (
                f"template '{tc.name}' has lab_profile_id={tc.lab_profile_id} "
                f"— expected None (templates are deployment-agnostic)"
            )

    def test_mimo_ota_upgrade(self, db_session):
        run_all(db_session, [test_case_templates_seeder])
        # MIMO OTA category templates should have test_type='MIMO_OTA' after upgrade
        from app.schemas.mimo_ota.config import MIMO_OTA_TEST_TYPE
        mimo_cases = db_session.query(TestCase).filter(
            TestCase.template_category == "MIMO OTA 吞吐量"
        ).all()
        assert len(mimo_cases) > 0
        assert all(tc.test_type == MIMO_OTA_TEST_TYPE for tc in mimo_cases)

    def test_idempotent_per_name(self, db_session):
        run_all(db_session, [test_case_templates_seeder])
        n1 = db_session.query(TestCase).count()
        run_all(db_session, [test_case_templates_seeder], force=True)
        assert db_session.query(TestCase).count() == n1
