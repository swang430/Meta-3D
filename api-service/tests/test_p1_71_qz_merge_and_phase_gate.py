# -*- coding: utf-8 -*-
"""P1-71 门：QZ 并轨（probe 侧表封存）+ workflow phase 口关闭。

设计出处：docs/plans/2026-08-24-p1-69-calibration-design.md §2（R6 定向：保留
channel 侧、封存 probe 侧）与 §4（workflow phase 步骤 fail-loud，PWS 复活时恢复）。

门清单（④ 每门配变异，见 PR 记录）：
  G-A  不变量门：封存表 QuietZoneCalibration 全仓零构造点、引用仅限白名单
  G-B  行为门：quiet_zone_validation_service 落库换源 channel 表（含 provenance）
  G-C  行为门：workflow phase 步骤 fail-loud，不产生任何落库
  G-D  不变量门：五个内置模板零 phase 步骤，且依赖图经真实 parser 全通过
  G-E  存在性粗筛：封存 banner 在（旁边有 G-A/G-B 行为与不变量门配套）
"""
import asyncio
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# 封存表引用白名单：模型定义 / 包导出。
# chamber_resolution 的 orphan 巡检名单用的是表名字符串（不含类名），
# 不需要豁免 —— 内审 F4 实证：列进来会让该文件的类名引用静默复活。
SEALED_REF_ALLOWLIST = {
    APP_DIR / "models" / "calibration.py",
    APP_DIR / "models" / "__init__.py",
}

# 匹配 probe 侧类名，排除 ChannelQuietZoneCalibration 的子串命中；
# 构造点门额外排除 `class QuietZoneCalibration(Base)` 定义行本身
_SEALED_NAME = re.compile(r"(?<![A-Za-z])QuietZoneCalibration\b")
_SEALED_CTOR = re.compile(r"(?<!class )(?<![A-Za-z])QuietZoneCalibration\s*\(")


def _iter_app_py():
    return sorted(APP_DIR.rglob("*.py"))


class TestSealedProbeQzTable:
    """G-A：封存表零写点 / 引用白名单。"""

    def test_no_constructor_calls_anywhere(self):
        offenders = []
        for path in _iter_app_py():
            text = path.read_text(encoding="utf-8")
            for m in _SEALED_CTOR.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                offenders.append(f"{path.relative_to(APP_DIR.parent)}:{line_no}")
        assert offenders == [], (
            "封存表 QuietZoneCalibration 出现构造调用（业务写点）: "
            f"{offenders} —— P1-71 起唯一活载体是 ChannelQuietZoneCalibration"
        )

    def test_references_only_in_allowlist(self):
        offenders = []
        for path in _iter_app_py():
            if path in SEALED_REF_ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8")
            for m in _SEALED_NAME.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                offenders.append(f"{path.relative_to(APP_DIR.parent)}:{line_no}")
        assert offenders == [], (
            f"封存表 QuietZoneCalibration 在白名单外仍被引用: {offenders}"
        )

    def test_allowlist_paths_exist(self):
        # 判定器自测：白名单路径漂移（文件改名/删除）时门要红，不许静默变宽
        for path in SEALED_REF_ALLOWLIST:
            assert path.exists(), f"白名单路径不存在（门取数源漂移）: {path}"

    def test_detector_catches_bad_and_passes_good(self):
        # 判定器自测：正反两向
        assert _SEALED_CTOR.search("cal = QuietZoneCalibration(chamber_id=1)")
        assert _SEALED_NAME.search("from x import QuietZoneCalibration")
        assert not _SEALED_CTOR.search("ChannelQuietZoneCalibration(session_id=None)")
        assert not _SEALED_NAME.search("ChannelQuietZoneCalibration")
        assert not _SEALED_CTOR.search("class QuietZoneCalibration(Base):")


class TestQzPersistRetargeted:
    """G-B：field_uniformity 落库换源 channel 表（行为门）。"""

    @pytest.fixture()
    def db(self, tmp_path):
        from app.db.database import Base
        from app.models.chamber import ChamberConfiguration

        engine = create_engine(
            f"sqlite:///{tmp_path / 'p1_71_qz.db'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = Session()
        self.chamber_id = uuid.uuid4()
        session.add(
            ChamberConfiguration(
                id=self.chamber_id,
                name="P1-71 QZ gate chamber",
                chamber_type="custom",
                chamber_radius_m=4.0,
                num_probes=64,
                quiet_zone_diameter_m=0.5,
            )
        )
        session.commit()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()

    def _run(self, db, monkeypatch, powers_dbm=None):
        from app.services.quiet_zone_validation_service import (
            QuietZoneValidationService,
        )

        async def fake_grid(self, offsets_cm, **kwargs):
            values = powers_dbm or [-85.0 + 0.1 * i for i in range(len(offsets_cm))]
            return [
                {"x": float(x), "y": float(y), "z": float(z),
                 "measured_value": values[i]}
                for i, (x, y, z) in enumerate(offsets_cm)
            ]

        monkeypatch.setattr(
            QuietZoneValidationService, "_real_grid_powers_via_ce_sa", fake_grid
        )
        svc = QuietZoneValidationService(db, use_mock=False)
        return asyncio.run(
            svc.run_field_uniformity_validation(
                chamber_id=self.chamber_id,
                frequency_mhz=3550.0,
                sgh_model="SGH-2600",
                sgh_gain_dbi=15.0,
                calibrated_by="p1-71-gate",
            )
        )

    def test_row_lands_in_channel_table_with_provenance(self, db, monkeypatch):
        from app.models.calibration import QuietZoneCalibration
        from app.models.channel_calibration import ChannelQuietZoneCalibration

        result = self._run(db, monkeypatch)
        assert result.success, result.message

        rows = db.query(ChannelQuietZoneCalibration).all()
        assert len(rows) == 1, "field_uniformity 应落且仅落一行 channel 侧 QZ 表"
        row = rows[0]
        assert str(row.id) == result.data["calibration_id"]
        assert row.num_points == 5
        assert row.quiet_zone_diameter_m == pytest.approx(0.5)
        prov = row.measurement_grid["provenance"]
        # probe 侧独有字段必须如实进 provenance，不许静默丢失
        for key in ("chamber_id", "sgh_model", "sgh_gain_dbi",
                    "measurement_method", "field_mean_dbm", "units_note"):
            assert key in prov, f"provenance 缺 {key}"
        assert prov["chamber_id"] == str(self.chamber_id)
        assert prov["sgh_model"] == "SGH-2600"
        # 激活批分流锚点锁到值级（轻量复核 F-A：存在性门可被错值绕过）
        assert prov["measurement_method"] == "ce_sa"
        # 统计列必须与判决同源（轻量复核 F-B：列值造假不影响判决无门可抓）
        assert row.amplitude_std_db == pytest.approx(result.data["field_std_db"])
        assert row.validation_pass is True

        # 封存表必须零行
        assert db.query(QuietZoneCalibration).count() == 0, (
            "封存的 probe 侧 quiet_zone_calibrations 不许再进新行"
        )

    def test_grid_samples_persist_verbatim(self, db, monkeypatch):
        # 内审 F2（MY-2 揭穿）：样本本体不许被改写 —— points 的 power_dbm
        # 必须逐点等于测得值
        from app.models.channel_calibration import ChannelQuietZoneCalibration

        # 含两位小数——防落库端偷偷 round(,1) 时门在不动点上失明（轻量复核 F-C）
        fed = [-85.27, -84.53, -85.51, -85.19, -84.86]
        result = self._run(db, monkeypatch, powers_dbm=fed)
        assert result.success, result.message
        row = db.query(ChannelQuietZoneCalibration).one()
        persisted = [p["power_dbm"] for p in row.measurement_grid["points"]]
        assert persisted == pytest.approx(fed)

    def test_fail_verdict_persists_as_fail(self, db, monkeypatch):
        # 内审 F2（MY-1 揭穿）：判决列不是常量 —— 超差网格必须 FAIL 落库
        # （范围 10 dB、std ≈ 3.9 dB，远超 ±1 dB 阈值）
        from app.models.channel_calibration import ChannelQuietZoneCalibration

        result = self._run(
            db, monkeypatch, powers_dbm=[-90.0, -80.0, -90.0, -80.0, -85.0]
        )
        assert result.success, "测量完成即 success；判决走 validation_pass"
        row = db.query(ChannelQuietZoneCalibration).one()
        assert row.validation_pass is False
        assert row.amplitude_uniformity_pass is False
        assert result.data["field_uniformity_pass"] is False
        assert result.warnings, "FAIL 必须带告警说明超差"

    def test_mock_still_refuses_to_persist(self, db):
        from app.models.channel_calibration import ChannelQuietZoneCalibration
        from app.services.quiet_zone_validation_service import (
            QuietZoneValidationService,
        )

        svc = QuietZoneValidationService(db, use_mock=True)
        result = asyncio.run(
            svc.run_field_uniformity_validation(
                chamber_id=self.chamber_id,
                frequency_mhz=3550.0,
                sgh_model="SGH-2600",
                sgh_gain_dbi=15.0,
            )
        )
        assert result.success is False
        assert "静区校准未判定" in result.message
        assert db.query(ChannelQuietZoneCalibration).count() == 0


class _RecorderDB:
    """记录 add/rollback 的桩 —— phase fail-loud 断言零落库用。"""

    def __init__(self):
        self.added = []
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    def rollback(self):
        self.rollbacks += 1


class TestWorkflowPhaseStepClosed:
    """G-C：workflow phase 步骤 fail-loud（行为门）。"""

    def _make(self):
        from app.services.workflow_engine import (
            StepResult,
            StepStatus,
            StepType,
            WorkflowDefinition,
            WorkflowExecutor,
            WorkflowStep,
        )

        step = WorkflowStep(
            id="phase_step",
            type=StepType.PROBE_CALIBRATION,
            calibration_type="phase",
            parameters={"frequency_mhz": 3550, "probe_ids": [0]},
        )
        workflow = WorkflowDefinition(
            name="p1-71-phase-gate", version="1.0", steps=[step]
        )
        recorder = _RecorderDB()
        executor = WorkflowExecutor(recorder)
        execution = executor.create_execution(workflow)
        result = StepResult(step_id="phase_step", status=StepStatus.RUNNING)
        return executor, execution, step, result, recorder

    def test_phase_step_raises_and_writes_nothing(self, monkeypatch):
        import app.services.chamber_resolution as chamber_resolution

        monkeypatch.setattr(
            chamber_resolution,
            "resolve_current_chamber",
            lambda db, lab_profile_id=None: SimpleNamespace(
                id=uuid.uuid4(), num_probes=64
            ),
        )
        executor, execution, step, result, recorder = self._make()
        with pytest.raises(RuntimeError, match="P1-71 关闭"):
            executor._execute_probe_calibration(execution, step, result)
        assert recorder.added == [], "phase 步骤不许有任何落库"
        assert recorder.rollbacks == 1, "异常路径必须回滚（既有约定）"

    def test_amplitude_branch_not_collaterally_blocked(self, monkeypatch):
        # 判定器自测反向：关的是 phase，amplitude 分支必须仍可走到其服务调用
        import app.services.chamber_resolution as chamber_resolution
        from app.services import probe_calibration_service

        monkeypatch.setattr(
            chamber_resolution,
            "resolve_current_chamber",
            lambda db, lab_profile_id=None: SimpleNamespace(
                id=uuid.uuid4(), num_probes=64
            ),
        )
        called = {}

        class _FakeAmpService:
            async def execute_amplitude_calibration(self, **kwargs):
                called["amplitude"] = True
                return SimpleNamespace(
                    success=True, message="ok", warnings=[],
                    data={"calibration_ids": []},
                )

        monkeypatch.setattr(
            probe_calibration_service, "AmplitudeCalibrationService", _FakeAmpService
        )
        executor, execution, step, result, recorder = self._make()
        step.calibration_type = "amplitude"
        executor._execute_probe_calibration(execution, step, result)
        assert called.get("amplitude") is True


class TestBuiltinTemplatesPhaseFree:
    """G-D：内置模板零 phase 步骤 + 依赖图过真实 parser（不变量门）。"""

    def _all_templates(self):
        from app.services import workflow_engine as we

        names = [
            "FULL_CHANNEL_CALIBRATION_WORKFLOW",
            "QUICK_VALIDATION_WORKFLOW",
            "FULL_SYSTEM_CALIBRATION_WORKFLOW",
            "FREQUENCY_CHANGE_WORKFLOW",
            "PATH_LOSS_ONLY_WORKFLOW",
        ]
        found = {n: getattr(we, n) for n in names if hasattr(we, n)}
        # 名单完整性：模板常量增删时本门要红，不许静默漏审
        module_consts = {
            n for n in dir(we)
            if n.endswith("_WORKFLOW") and isinstance(getattr(we, n), str)
        }
        assert module_consts == set(names), (
            f"内置模板常量集变了：{module_consts ^ set(names)} —— 更新本门名单"
        )
        return found

    def test_no_phase_steps_and_graph_parses(self):
        from app.services.workflow_engine import WorkflowParser

        for name, yaml_text in self._all_templates().items():
            workflow = WorkflowParser.parse_string(yaml_text)  # 依赖图校验在 parser 内
            phase_steps = [
                s.id for s in workflow.steps if s.calibration_type == "phase"
            ]
            assert phase_steps == [], (
                f"{name} 仍含 phase 步骤 {phase_steps} —— P1-71 已关闭该步骤类型"
            )


class TestSealBannerPresent:
    """G-E：封存 banner 存在性粗筛（行为/不变量门在上面几类）。"""

    def test_banner_mentions_seal_and_successor(self):
        from app.models.calibration import QuietZoneCalibration

        doc = QuietZoneCalibration.__doc__ or ""
        # 锚定计划链五表同款规范短语，防「提到封存但 banner 主句被改掉」绕过
        # （首版只查子串"封存"，被 MU5 变异揭穿——"封存前原始说明"也含它）
        assert "**封存 (deprecated)**" in doc
        assert "channel_quiet_zone_calibrations" in doc
        assert "新代码不要引用本表" in doc

    def test_service_module_doc_updated(self):
        import app.services.quiet_zone_validation_service as m

        doc = m.__doc__ or ""
        assert "ChannelQuietZoneCalibration" in doc
        assert "run_xpd_validation" in doc  # 移除申报必须留痕
        # 移除的两个方法确实不在了
        from app.services.quiet_zone_validation_service import (
            QuietZoneValidationService,
        )
        assert not hasattr(QuietZoneValidationService, "run_xpd_validation")
        assert not hasattr(QuietZoneValidationService, "get_latest_validation")
