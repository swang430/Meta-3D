"""P2-32A 多频路损真实入口闭环回归。"""

from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.chamber import (
    ChamberConfiguration,
    ChamberType,
    create_chamber_from_preset,
)
from app.models.probe_calibration import MultiFrequencyPathLoss
from app.schemas.probe_calibration import (
    CalibrationJobResponse,
    CalibrationJobStatus,
    MultiFrequencyPathLossResponse,
    PolarizationType,
)
from app.services.path_loss_calibration_service import MultiFrequencyPathLossService
from app.services.calibration.rf_chain_resolver import (
    RFChainResolution,
    RFChainSpec,
)


def _multi_frequency_row(*, warnings=None) -> MultiFrequencyPathLoss:
    now = datetime.utcnow()
    return MultiFrequencyPathLoss(
        chamber_id=uuid4(),
        use_mock=False,
        probe_id=1,
        polarization="V",
        freq_start_mhz=3400.0,
        freq_stop_mhz=3500.0,
        freq_step_mhz=100.0,
        num_points=2,
        frequency_points_mhz=[3400.0, 3500.0],
        path_loss_db=[42.1, 42.4],
        uncertainty_db=[0.3, 0.3],
        calibrated_at=now,
        calibrated_by="p2-32a",
        valid_until=now + timedelta(days=30),
        status="valid",
        warnings=warnings,
    )


def test_multi_frequency_warnings_round_trip_and_preserve_historical_null():
    """删除 warnings 列或把历史 NULL 默认为 [] 时必须失败。"""
    engine = create_engine("sqlite:///:memory:")
    MultiFrequencyPathLoss.__table__.create(engine)

    with Session(engine) as db:
        current = _multi_frequency_row(warnings=["SA cleanup failed"])
        historical = _multi_frequency_row(warnings=None)
        historical.probe_id = 2
        db.add_all([current, historical])
        db.commit()
        db.expire_all()

        rows = {
            row.probe_id: row
            for row in db.query(MultiFrequencyPathLoss).order_by(
                MultiFrequencyPathLoss.probe_id
            )
        }

        assert rows[1].warnings == ["SA cleanup failed"]
        assert rows[2].warnings is None


@pytest.mark.asyncio
async def test_multi_frequency_persists_warnings_per_probe(monkeypatch):
    """一个探头的清理告警不得污染同一作业中另一探头的证书。"""
    engine = create_engine("sqlite:///:memory:")
    ChamberConfiguration.__table__.create(engine)
    MultiFrequencyPathLoss.__table__.create(engine)

    @asynccontextmanager
    async def _lease(*args, **kwargs):
        yield

    monkeypatch.setattr(
        "app.services.instrument_test_lease.instrument_test_lease",
        _lease,
    )

    async def _sweep(self, *, probe_id, warnings, frequency_points, **kwargs):
        warnings.append(f"probe {probe_id} cleanup warning")
        return (
            [40.0 + probe_id for _ in frequency_points],
            [0.3 for _ in frequency_points],
        )

    monkeypatch.setattr(
        MultiFrequencyPathLossService,
        "_real_frequency_sweep_via_ce_sa",
        _sweep,
    )

    with Session(engine) as db:
        chamber = create_chamber_from_preset(
            ChamberType.TYPE_C.value,
            name="p2-32a warning isolation",
        )
        chamber.cable_sgh_to_sa_loss_db = 1.5
        db.add(chamber)
        db.commit()
        db.refresh(chamber)
        lab_profile_id = uuid4()
        monkeypatch.setattr(
            "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
            lambda *_args, **_kwargs: RFChainResolution(
                lab_profile_id=lab_profile_id,
                chamber_id=chamber.id,
                topology_id="topology-1",
                topology_name="P2-32A",
                operating_mode="mimo_ota",
                chains=[
                    RFChainSpec(
                        chain_id=f"chain-{probe_id}",
                        ce_port=f"B{probe_id + 1}.1",
                        probe_id=probe_id,
                        polarization="V",
                    )
                    for probe_id in (1, 2)
                ],
            ),
        )

        result = await MultiFrequencyPathLossService(
            db,
            use_mock=False,
        ).calibrate_frequency_sweep(
            chamber_id=chamber.id,
            lab_profile_id=lab_profile_id,
            probe_ids=[1, 2],
            polarization=PolarizationType.V,
            freq_start_mhz=3400.0,
            freq_stop_mhz=3500.0,
            freq_step_mhz=100.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
            calibrated_by="p2-32a",
        )

        assert result.success
        assert result.warnings == [
            "probe 1 cleanup warning",
            "probe 2 cleanup warning",
        ]
        rows = {
            row.probe_id: row
            for row in db.query(MultiFrequencyPathLoss).order_by(
                MultiFrequencyPathLoss.probe_id
            )
        }
        assert rows[1].warnings == ["probe 1 cleanup warning"]
        assert rows[2].warnings == ["probe 2 cleanup warning"]


@pytest.mark.asyncio
async def test_real_multi_frequency_routes_each_probe_through_resolved_chain(monkeypatch):
    """多探头真实扫频必须逐探头使用 LabProfile 冻结拓扑，不能复用当前物理通路。"""
    engine = create_engine("sqlite:///:memory:")
    ChamberConfiguration.__table__.create(engine)
    MultiFrequencyPathLoss.__table__.create(engine)

    @asynccontextmanager
    async def _lease(*args, **kwargs):
        yield

    monkeypatch.setattr(
        "app.services.instrument_test_lease.instrument_test_lease",
        _lease,
    )

    calls = []

    async def _sweep(self, **kwargs):
        calls.append(kwargs)
        return ([41.0 for _ in kwargs["frequency_points"]], [0.3])

    monkeypatch.setattr(
        MultiFrequencyPathLossService,
        "_real_frequency_sweep_via_ce_sa",
        _sweep,
    )

    with Session(engine) as db:
        chamber = create_chamber_from_preset(
            ChamberType.TYPE_C.value,
            name="p2-32a routed sweep",
        )
        chamber.cable_sgh_to_sa_loss_db = 1.5
        db.add(chamber)
        db.commit()
        db.refresh(chamber)
        lab_profile_id = uuid4()
        monkeypatch.setattr(
            "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
            lambda *_args, **_kwargs: RFChainResolution(
                lab_profile_id=lab_profile_id,
                chamber_id=chamber.id,
                topology_id="topology-routed",
                topology_name="P2-32A routed",
                operating_mode="mimo_ota",
                chains=[
                    RFChainSpec("chain-1", "B1.1", 1, "V"),
                    RFChainSpec("chain-2", "B2.1", 2, "V"),
                ],
            ),
        )

        result = await MultiFrequencyPathLossService(
            db, use_mock=False,
        ).calibrate_frequency_sweep(
            chamber_id=chamber.id,
            lab_profile_id=lab_profile_id,
            operating_mode="mimo_ota",
            probe_ids=[1, 2],
            polarization=PolarizationType.V,
            freq_start_mhz=3400.0,
            freq_stop_mhz=3500.0,
            freq_step_mhz=100.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )

        assert result.success
        assert [
            (call["probe_id"], call["ce_port"], call["route_target"])
            for call in calls
        ] == [(1, "B1.1", "chain-1"), (2, "B2.1", "chain-2")]


@pytest.mark.asyncio
async def test_real_multi_frequency_rejects_missing_chain_before_hardware(monkeypatch):
    """请求探头未出现在活动拓扑时必须在任何扫频 I/O 前失败。"""
    engine = create_engine("sqlite:///:memory:")
    ChamberConfiguration.__table__.create(engine)
    MultiFrequencyPathLoss.__table__.create(engine)
    sweep = AsyncMock()
    monkeypatch.setattr(
        MultiFrequencyPathLossService,
        "_real_frequency_sweep_via_ce_sa",
        sweep,
    )

    with Session(engine) as db:
        chamber = create_chamber_from_preset(
            ChamberType.TYPE_C.value,
            name="p2-32a missing route",
        )
        chamber.cable_sgh_to_sa_loss_db = 1.5
        db.add(chamber)
        db.commit()
        db.refresh(chamber)
        lab_profile_id = uuid4()
        monkeypatch.setattr(
            "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
            lambda *_args, **_kwargs: RFChainResolution(
                lab_profile_id=lab_profile_id,
                chamber_id=chamber.id,
                topology_id="topology-missing",
                topology_name="P2-32A missing",
                operating_mode="mimo_ota",
                chains=[RFChainSpec("chain-1", "B1.1", 1, "V")],
            ),
        )

        result = await MultiFrequencyPathLossService(
            db, use_mock=False,
        ).calibrate_frequency_sweep(
            chamber_id=chamber.id,
            lab_profile_id=lab_profile_id,
            probe_ids=[1, 2],
            polarization=PolarizationType.V,
            freq_start_mhz=3400.0,
            freq_stop_mhz=3500.0,
            freq_step_mhz=100.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )

        assert result.success is False
        assert "probe 2" in result.message
        sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_multi_frequency_rejects_ambiguous_chain_before_hardware(
    monkeypatch,
):
    """同一 probe/polarization 多条活动链时不得静默选择第一条。"""
    engine = create_engine("sqlite:///:memory:")
    ChamberConfiguration.__table__.create(engine)
    MultiFrequencyPathLoss.__table__.create(engine)
    sweep = AsyncMock()
    monkeypatch.setattr(
        MultiFrequencyPathLossService,
        "_real_frequency_sweep_via_ce_sa",
        sweep,
    )

    with Session(engine) as db:
        chamber = create_chamber_from_preset(
            ChamberType.TYPE_C.value,
            name="p2-32a ambiguous route",
        )
        chamber.cable_sgh_to_sa_loss_db = 1.5
        db.add(chamber)
        db.commit()
        db.refresh(chamber)
        lab_profile_id = uuid4()
        monkeypatch.setattr(
            "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
            lambda *_args, **_kwargs: RFChainResolution(
                lab_profile_id=lab_profile_id,
                chamber_id=chamber.id,
                topology_id="topology-ambiguous",
                topology_name="P2-32A ambiguous",
                operating_mode="mimo_ota",
                chains=[
                    RFChainSpec("chain-1", "B1.1", 1, "V"),
                    RFChainSpec("chain-2", "B1.2", 1, "V"),
                ],
            ),
        )

        result = await MultiFrequencyPathLossService(
            db, use_mock=False,
        ).calibrate_frequency_sweep(
            chamber_id=chamber.id,
            lab_profile_id=lab_profile_id,
            probe_ids=[1],
            polarization=PolarizationType.V,
            freq_start_mhz=3400.0,
            freq_stop_mhz=3500.0,
            freq_step_mhz=100.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )

        assert result.success is False
        assert "found 2" in result.message
        sweep.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_multi_frequency_rejects_unresolved_ce_port_before_hardware(
    monkeypatch,
):
    """拓扑只解析出占位端口时不得把问号下发给 CE。"""
    engine = create_engine("sqlite:///:memory:")
    ChamberConfiguration.__table__.create(engine)
    MultiFrequencyPathLoss.__table__.create(engine)
    sweep = AsyncMock()
    monkeypatch.setattr(
        MultiFrequencyPathLossService,
        "_real_frequency_sweep_via_ce_sa",
        sweep,
    )

    with Session(engine) as db:
        chamber = create_chamber_from_preset(
            ChamberType.TYPE_C.value,
            name="p2-32a unresolved CE port",
        )
        chamber.cable_sgh_to_sa_loss_db = 1.5
        db.add(chamber)
        db.commit()
        db.refresh(chamber)
        lab_profile_id = uuid4()
        monkeypatch.setattr(
            "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
            lambda *_args, **_kwargs: RFChainResolution(
                lab_profile_id=lab_profile_id,
                chamber_id=chamber.id,
                topology_id="topology-unresolved-port",
                topology_name="P2-32A unresolved port",
                operating_mode="mimo_ota",
                chains=[RFChainSpec("chain-1", "?", 1, "V")],
            ),
        )

        result = await MultiFrequencyPathLossService(
            db, use_mock=False,
        ).calibrate_frequency_sweep(
            chamber_id=chamber.id,
            lab_profile_id=lab_profile_id,
            probe_ids=[1],
            polarization=PolarizationType.V,
            freq_start_mhz=3400.0,
            freq_stop_mhz=3500.0,
            freq_step_mhz=100.0,
            sgh_model="SGH-01",
            sgh_gain_dbi=10.0,
        )

        assert result.success is False
        assert "no resolved CE port" in result.message
        sweep.assert_not_awaited()


def test_calibration_job_response_carries_requested_mode():
    """wire 响应必须让 GUI 区分真实校准与诊断模拟。"""
    response = CalibrationJobResponse(
        calibration_job_id=uuid4(),
        status=CalibrationJobStatus.COMPLETED,
        use_mock=False,
    )

    assert response.model_dump()["use_mock"] is False


def test_multi_frequency_row_response_exposes_persisted_warnings():
    """读取 schema 不能丢掉数据库行的告警留痕。"""
    assert "warnings" in MultiFrequencyPathLossResponse.model_fields


def test_legacy_synthetic_multi_frequency_route_is_not_published():
    """旧随机 TRP/TIS 入口不得继续伪装成校准生产路径。"""
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/v1/calibration/multi-frequency" not in paths
    assert "/api/v1/calibration/path-loss/multi-frequency/start" in paths


def test_multi_frequency_checked_contract_matches_live_topology_scope():
    """LabProfile/运行模式不得只出现在 live schema 或某一份镜像。"""
    from app.main import app

    live = app.openapi()["components"]["schemas"]["StartMultiFrequencyPathLossRequest"]
    checked = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "api" / "openapi.yaml").read_text(
            encoding="utf-8"
        )
    )["components"]["schemas"]["StartMultiFrequencyPathLossRequest"]

    for field in ("lab_profile_id", "chamber_id", "operating_mode"):
        assert field in live["properties"]
        assert field in checked["properties"]
    assert "lab_profile_id" in live["required"]
    assert "lab_profile_id" in checked["required"]
    assert live["properties"]["operating_mode"]["default"] == "mimo_ota"
    assert checked["properties"]["operating_mode"]["default"] == "mimo_ota"
