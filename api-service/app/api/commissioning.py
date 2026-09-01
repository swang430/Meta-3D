"""3GPP Static MIMO OTA Commissioning REST endpoints — TestCase-backed.

Public surface is unchanged from the legacy in-memory service so existing
GUI/clients keep working. Internally every session is now a TestCase row
(test_type='MIMO_OTA') + a TestExecution row, and each phase is dispatched
through the ExecutorRegistry. The `_sessions` in-memory dict is gone.

Phase name compatibility map (old string -> step.type):
  precheck   -> MIMO_OTA_PRECHECK
  reference  -> MIMO_OTA_REFERENCE
  mimo_test  -> MIMO_OTA_MEASURE
  analysis   -> MIMO_OTA_ANALYSIS
  report     -> MIMO_OTA_REPORT
"""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.logging_config import current_execution_id
from app.db.database import SessionLocal, get_db
from app.hal.positioner import retain_positioner_stop_generation
from app.models.calibration import CalibrationCertificate
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.schemas.mimo_ota.config import MIMO_OTA_TEST_TYPE, MIMOOTAStepType
from app.services.lab_resolution import LabResolutionError
from app.services.mimo_ota import build_mimo_ota_test_case
from app.hal.base_station import LteTransmissionMode
from app.services.test_execution import (
    StepDescriptor,
    StepExecutionContext,
    dispatch_step,
)
from app.services.instrument_test_lease import (
    InstrumentTestLeaseError,
    InstrumentTestLeaseReleaseError,
    instrument_test_lease,
)
from app.services.base_station_execution_session import (
    BaseStationSessionOperationResult,
    run_base_station_execution_session,
)
from app.services.execution_failure_alerts import emit_execution_failed_alert
from app.services.execution_qualification import (
    EXECUTION_QUALIFICATION_KEY,
    ExecutionQualification,
    TestCaseExecutionPolicy,
)
from app.services.execution_evidence_outcome import (
    execution_evidence_blocks_formal_outputs,
    project_execution_evidence_outcome,
)
from app.services.mimo_ota.base_station_execution_evidence import (
    BASE_STATION_EXECUTION_EVIDENCE_FIELD,
    base_station_expected_scope_from_evidence,
    base_station_metric_projection_required,
    project_base_station_metrics_by_position,
)
from app.services.base_station_adapter_profile import (
    build_frozen_base_station_validator,
    freeze_execution_base_station_adapter_profile,
)
from app.services.positioner_coordinate_profile import (
    build_frozen_positioner_validator,
    freeze_execution_positioner_coordinate_profile,
)
from app.utils.human_time import format_human_local_timestamp


COMMISSIONING_CHAINS = ("commissioning_api", "commissioning_adhoc")

# 本模块建行时写的 marker (create_session / run_adhoc_phase) —— 与
# COMMISSIONING_CHAINS 同源, 单列是为了让 _resolve_execution 的收窄谓词
# 有名字可读。


def _current_positioner_driver():
    """Read the current HAL positioner without importing HAL during module load."""
    from app.services.instrument_hal_service import get_hal_service

    return get_hal_service().drivers.get("positioner")


def reset_stale_running_commissioning_executions() -> None:
    """启动复位 (lifespan 调用): 本链的 stale running 行 → failed。

    ARCH-1 S3 的配套 —— 本模块现在会把跑相位的行标 ``running`` 让 HAL
    reload 闸门看得见, 那么进程重启留下的僵尸 running 行就会**永久拦死
    reload**。相位是同步跑在请求线程上的, 进程一没它必然中断, 所以启动
    时刻的 running 行一定是僵尸。

    谓词收窄到本链两个 marker —— 各链自管各的复位语义
    (``test_case_runner.reset_stale_running_case_executions`` 的既定约定),
    不碰用例执行 / 计划链 / VRT 的行。

    ⚠️ **单 worker 前提**（Codex #242 C1）: "启动时刻的 running 行必是僵尸"
    只在单进程下成立。多 worker 时新 worker 启动会误杀**别的 worker 正在
    跑的硬件执行** —— 行被标 failed 后 HAL 闸门随之停止保护那条仍在跑的
    链，比不复位更危险。部署契约见 ``README.md`` 的 Deployment 一节
    （已钉死 ``--workers 1`` 并写明理由）；容器入口
    ``docker-entrypoint.sh`` 也是单进程 uvicorn。
    本仓另两处复位（case-runner / plan-runner）依赖同一前提。
    多 worker 化需要把判据换成 owner/lease 或进程代次 —— 架构级改动，
    在 ARCH-1 backlog（"runner 体系整体 multi-worker 化"，#238 裁定）。
    """
    db = SessionLocal()
    try:
        stale = (
            db.query(TestExecution)
            .filter(TestExecution.status == "running")
            .filter(TestExecution.executed_by.in_(COMMISSIONING_CHAINS))
            .all()
        )
        for ex in stale:
            ex.status = "failed"
            ex.completed_at = datetime.utcnow()
            ex.error_message = "相位执行被进程重启中断 — 可重跑"
            logger.warning(
                "[commissioning] 启动复位 stale running 执行 %s → failed", ex.id
            )
        if stale:
            db.commit()
            for ex in stale:
                emit_execution_failed_alert(ex.id)
    except Exception:  # noqa: BLE001
        logger.exception("[commissioning] stale running 复位失败 (不阻塞启动)")
        db.rollback()
    finally:
        db.close()


@contextmanager
def _execution_marked_running(db: Session, execution: TestExecution):
    """ARCH-1 S3: 相位跑起来期间把行标成 ``running``，结束落终态。

    **为什么必须有**：HAL reload 闸门认的是"占着驱动的活跃执行行"
    （``hal_reload_policy.find_execution_blockers``）。commissioning 的三个
    入口原来建行 ``pending`` 后全程不改（只有 report executor 顺手置
    completed），闸门看不见它们 —— 暗室首测跑着时点重载会静默拆掉驱动，
    而这正是现场最常用的链。

    **本 contextmanager 只拥有 running 这一半，不发明终态**（内审 F1）：
    退出时把行**恢复成进入前的状态**。理由：

    - ``dispatch_step`` 把 executor 异常统一转成 FAILED result **从不上抛**
      （``registry.py``），所以"有没有抛异常"根本不是成败信号 —— 拿它当
      判据会把中止的链记成 completed，进而混进待归档报告列表、被算进
      成功率统计；
    - 跑完**一个**相位不等于会话结束，run_phase 更没有资格写终态。

    终态归"谁知道结果谁写"：全成功由 REPORT executor 写 completed
    （``executors/report.py``），中止由 run_all 自己按相位结果写
    （与 ``test_plan_runner`` / ``test_case_runner`` / adhoc 三处同构）。

    退出用 ``finally`` 而不是 ``except Exception``：``CancelledError`` 是
    BaseException（uvicorn 优雅停机会 cancel 在飞请求），走 finally 才能
    把行从 running 摘下来 —— 否则留下的僵尸行**永久拦死 reload**。

    抽成 contextmanager 而不是在三处各写一遍：第四个入口将来接进来时
    照抄这一行即可，漏一个 = 那条链继续裸奔，而且是静默的。
    """
    if execution.status == "running":
        # 拒绝并发 (Codex #242 C2): 两个相位请求打同一 session 时, 第一个
        # 退出会把行恢复成它进来时的 pending —— 而第二个还在用 HAL,
        # reload 保护就此提前失效。而且这两个请求本来就在并发操作同一套
        # 驱动, 本身是错误用法。用 DB 状态当判据 (跨 worker 可见), 不引
        # 进程内锁。
        raise HTTPException(
            status_code=409,
            detail=(
                f"会话 {execution.id} 已有相位在执行中 —— "
                f"等它结束再跑下一个 (并发操作同一套驱动会互相踩)"
            ),
        )
    prior_status = execution.status
    execution.status = "running"
    if execution.started_at is None:
        execution.started_at = datetime.utcnow()
    db.commit()
    try:
        yield
    finally:
        # 执行器可能已把行推到终态 (report executor 写 completed) —— 那是
        # 有依据的判决, 不许踩。只有还停在 running 的才由这里摘下来,
        # 恢复进入前的状态 (不发明终态)。
        db.refresh(execution)
        if execution.status == "running":
            execution.status = prior_status
            db.commit()


def _record_local_handoff_failure(
    db: Session,
    execution: TestExecution,
    error: InstrumentTestLeaseReleaseError,
    *,
    previous_error: Optional[str] = None,
) -> str:
    """把 commissioning 的 Local 交接失败发布为可见且不可重跑的终态。"""
    db.refresh(execution)
    previous_status = execution.status
    cfg = dict(execution.config or {})
    persisted_error = execution.error_message or cfg.get("error_message")
    previous_errors = []
    for candidate in (previous_error, persisted_error):
        if candidate and candidate not in previous_errors:
            previous_errors.append(candidate)
    previous_error = "；".join(previous_errors) or None
    cfg["local_control_handoff_failed"] = True
    cfg["local_control_handoff_previous_status"] = previous_status
    cfg["local_control_handoff_error"] = str(error)
    if previous_error:
        cfg["local_control_handoff_previous_error"] = previous_error
    message = f"仪表 Local 交接失败: {error}"
    if previous_error:
        message += f"；此前业务结果: {previous_error}"
    cfg["error_message"] = message
    completed_at = datetime.utcnow()
    execution.status = "failed"
    execution.completed_at = completed_at
    execution.duration_sec = (
        max(0.0, (completed_at - execution.started_at).total_seconds())
        if execution.started_at is not None
        else None
    )
    execution.error_message = message
    execution.config = cfg
    db.commit()
    emit_execution_failed_alert(execution.id)
    return message


def _lab_resolution_to_422(err: LabResolutionError) -> HTTPException:
    """Translate a ``LabResolutionError`` into an actionable 422 the
    GUI can render directly.

    Detail shape (so the GUI can build a picker without re-fetching):
        {
          "kind": "none" | "ambiguous",
          "message": "<human-readable>",
          "active_labs": [{"id": str, "name": str}, ...],
        }

    Pre-this-fix the underlying ValueError propagated uncaught and
    FastAPI returned 500 — surfaced in the GUI's commissioning
    sandbox as "初始化失败 错误代码500" with no recovery path.
    """
    return HTTPException(
        status_code=422,
        detail={
            "kind": err.kind,
            "message": str(err),
            "active_labs": [
                {"id": str(lab.id), "name": lab.name}
                for lab in err.active_labs
            ],
        },
    )
from app.models.diagnostic_run import DiagnosticKind
from app.services.diagnostic_context import build_diagnostic_context

router = APIRouter(prefix="/commissioning", tags=["暗室首测"])
logger = logging.getLogger(__name__)


# Map old phase-name strings to canonical step.type values
_PHASE_NAME_TO_STEP_TYPE: Dict[str, str] = {
    "precheck": MIMOOTAStepType.PRECHECK.value,
    "reference": MIMOOTAStepType.REFERENCE.value,
    # legacy "wait for antenna" stage is not separately modeled in MIMO_OTA;
    # treat the wait endpoint as a no-op that just reports current status.
    "reference_wait": MIMOOTAStepType.REFERENCE.value,
    "mimo_test": MIMOOTAStepType.MEASURE.value,
    "analysis": MIMOOTAStepType.ANALYSIS.value,
    "report": MIMOOTAStepType.REPORT.value,
}

# Map step.type -> the key under measurements['phases'] each executor writes
_STEP_TYPE_TO_PHASES_KEY: Dict[str, str] = {
    MIMOOTAStepType.PRECHECK.value: "precheck",
    MIMOOTAStepType.REFERENCE.value: "reference",
    MIMOOTAStepType.MEASURE.value: "measure",
    MIMOOTAStepType.ANALYSIS.value: "analysis",
    MIMOOTAStepType.REPORT.value: "report",
}

# Old SessionResponse-side phase keys (kept for backward compat with old GUI)
_LEGACY_PHASE_ORDER = ["precheck", "reference", "mimo_test", "analysis", "report"]


# ==================== Pydantic models (unchanged shape) ====================


class CreateSessionRequest(BaseModel):
    cdl_model_name: str = "UMa CDL-C NLOS"
    radio_technology: Literal["nr5g", "lte"] = "nr5g"
    # 2026-08-07 现场实证的坑：这两个原来是 `float = 3.5e9 / 100`，**同一个默认值
    # 活在两个地方**（这里 + MIMOOTAConfiguration），而 `_request_overrides` 把它们
    # **无条件**塞进 overrides —— 于是改了 schema 默认根本不生效，建出来的会话
    # 仍是 3500 MHz / 100 MHz。改成 `Optional = None`：**None = 不覆盖，用 schema
    # 默认**，跟下面 8 个 `precheck_strict_*` 同一套语义。
    # 这是"去掉重复"而不是"同步重复" —— 同步要靠人记得，去掉之后记不记得都对。
    # G14 门（test_rule_gates.py）盯着这件事：本类里任何跟 MIMOOTAConfiguration
    # 同名的字段，要么默认值相等，要么就是 None（不覆盖）。
    frequency_hz: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    band: Optional[str] = None
    duplex: Optional[Literal["fdd", "tdd"]] = None
    subcarrier_spacing_khz: Optional[int] = None
    nr_arfcn: Optional[int] = None
    lte_dl_earfcn: Optional[int] = None
    lte_transmission_mode: Optional[LteTransmissionMode] = None
    theoretical_peak_throughput_mbps: Optional[float] = None
    mimo_layers: int = 2
    azimuths_deg: List[float] = [0.0, 90.0, 180.0, 270.0]
    measurement_duration_s: float = 10.0
    # ⚠ 与 MIMOOTAConfiguration.engine_mode 保持一致（G16 门守着）。
    #   一度双双改成 keysight_gcm（2026-08-07 现场），外审 #304 P1 指出：
    #   GCM 路必须配 `.smu`，而 emulation_file / channel_asset_id 都是 None，
    #   默认会话会被 strict emulation-file 门全部拒掉。两侧一起撤回 ASC。
    #   现场那条路显式传 engine_mode="keysight_gcm" + emulation_file=<.smu 路径>。
    engine_mode: str = "mimo_first_asc"
    # 2026-05-18 P0-7: engine_mode='external_asc' 时必填 (本机绝对路径,
    # 操作员手工产 .asc 的目录). 其他 engine_mode 该字段被忽略.
    asc_source_path: Optional[str] = None
    min_throughput_ratio: float = 0.70
    max_rsrp_variance_db: float = 3.0
    # New optional field — pin a specific lab; falls back to the unique active one.
    lab_profile_id: Optional[UUID] = None
    # P3-14: 统一信道资产 (P2-16) 进会话创建 — 此前只能建完会话再 PATCH
    # configuration 绕道 (scripts/onsite-run-channel-throughput.sh 固化的临时路)。
    # None = 不带资产, 走 cdl_model_name 等显式参数 (兼容不变)。
    channel_asset_id: Optional[UUID] = None
    # Lab-smoke opt-outs for strict safety gates：cal 在 PRECHECK；managed
    # execution 的 DUT / SIM 动态门在 MEASURE 完成本次 RF 初始化和 attach 后执行。
    # Default None = don't override → config schema default (True, strict) applies,
    # so on-site real first-call keeps the fail-loud protection. The GUI's
    # "Lab smoke" toggle sends False to rehearse locally without a real DUT /
    # calibration (same path the e2e/smoke tests use). Optional[bool] not bool:
    # a literal False must override, but None must leave the default untouched
    # (passing None into the config would falsy-bypass the gate for everyone).
    precheck_strict_dut: Optional[bool] = None
    # Deprecated authority surface.  It remains in the request schema only so
    # old clients receive a precise validation error instead of silently
    # changing qualification.  Diagnostic calibration bypass is derived from
    # the audited TestCase execution policy below.
    precheck_strict_cal: Optional[bool] = None
    execution_policy_mode: Optional[Literal["formal", "diagnostic"]] = None
    execution_policy_reason: Optional[str] = None
    execution_policy_updated_by: Optional[str] = None
    # P2-11: 暗室首测 (路径 A) 的 "强制跳过严格门" 还要覆盖 Phase 1/2/3 新加的门, 否则
    # 真仪表空跑会撞上它们而无法绕过 (cal/dut 之外的捷径缺口)。同 Optional[bool] 语义:
    # 显式 False = real-mode operator override; None = 留 schema 默认 (strict)。
    precheck_strict_frequency: Optional[bool] = None
    precheck_strict_emulation_file: Optional[bool] = None
    precheck_strict_switch_mode: Optional[bool] = None
    # P2-11 Phase 6 (#114/#124/#126): DL layers/调制/MCS 一致性门也是暗室首测 (路径 A) 要跳的 ——
    # 此前漏接 → 真硬件 bring-up 撞 cell_config 门 (DUT 协商能力 < 默认请求 / MCS clamp) 挡住快速
    # first-call (feedback_strict_gate_extend_bypass_toggle 母题又踩)。同 Optional[bool] 语义。
    precheck_strict_cell_config: Optional[bool] = None
    # DUTProfile 声明能力门 (规划期, attach 前): 暗室首测 bring-up 也要可跳 (快速跑不关心 DUT
    # 声明)。新 strict 门同步 bypass (feedback_strict_gate_extend_bypass_toggle, 这次提前补)。
    precheck_strict_dut_capability: Optional[bool] = None
    # P2-13 Phase 2: SIM 身份核对门 (防插错卡)。bring-up 也要可跳 (快速跑可能不绑 SIMProfile /
    # 用临时卡)。新 strict 门同步 bypass (feedback_strict_gate_extend_bypass_toggle)。
    precheck_strict_sim_identity: Optional[bool] = None

    # === 仪表工作点（暗室首测这一条路专用）===
    #
    # ⭐ 这些**不放进 `MIMOOTAConfiguration` 的默认值**（2026-08-07 撤回后的定案）：
    #   共享 schema 的默认会流进每一条新建用例，也会被填进数据库里**已经存在**、
    #   JSON 里没有这些键的老用例 —— 实测既有 MIMO_OTA 用例的 configuration 里
    #   这几个键全都缺，所以改 schema 默认 = 改全库既有用例的行为。
    #   放在请求侧就只影响"这次建的这个会话"，跟上面 8 个 `precheck_strict_*`
    #   和 `engine_mode` 同一套路数。
    #
    # None = 不覆盖，用 schema 默认。给了值才下发。
    # 2026-08-07 CAICT 现场实测过的一组（下次现场可直接照填）：
    #   frequency_hz=3.54999e9 (ARFCN 636666) / bandwidth_mhz=40
    #   uxm_dl_power_dbm_per_bw=-15  ← 整带宽口径，已下发并回读确认
    #   f64_input_ref_dbm=-17（UXM→F64 路损按 2 dB 估，⚠ 尚未实测）
    #   f64_crest_db=15 / f64_output_level_dbm=-52
    #   ⚠ -50 会被 F64 拒（该机口 1 实测上限 `OUTP:LEV:AMP:LIM?` = -51.61）
    uxm_dl_power_dbm_per_bw: Optional[float] = None
    f64_input_ref_dbm: Optional[float] = None
    f64_crest_db: Optional[float] = None
    f64_output_level_dbm: Optional[float] = None
    emulation_file: Optional[str] = None
    # 「扶一把」开关：None = 关（正常流程）。有的 DUT 在衰落打开时挂不上，
    # 设成 2（Butler 直通）可先用直通扶它 attach，挂上后自动撤掉再开衰落。
    # attach 超时的错误消息会主动提示这个开关，不需要谁记住它。
    f64_bypass_mode: Optional[int] = None
    base_station_config_mode: Optional[Literal["dispatch", "inherit"]] = Field(
        default=None,
        description=(
            "Vendor-neutral base-station configuration mode; inherit is "
            "diagnostic-only."
        ),
    )

    @model_validator(mode="after")
    def require_explicit_lte_working_point(self) -> "CreateSessionRequest":
        if self.radio_technology != "lte":
            if (
                self.subcarrier_spacing_khz is not None
                and self.subcarrier_spacing_khz not in (15, 30, 60, 120)
            ):
                raise ValueError(
                    "subcarrier_spacing_khz must be one of 15, 30, 60, 120"
                )
            if self.lte_dl_earfcn is not None:
                raise ValueError("NR commissioning request must not set lte_dl_earfcn")
            if self.duplex is not None:
                raise ValueError("NR commissioning request must not set LTE duplex")
            if any(
                value is not None
                for value in (self.band, self.nr_arfcn, self.subcarrier_spacing_khz)
            ):
                for field_name in (
                    "frequency_hz", "bandwidth_mhz", "band",
                    "nr_arfcn", "subcarrier_spacing_khz",
                ):
                    if getattr(self, field_name) is None:
                        raise ValueError(
                            f"explicit NR commissioning PCell requires {field_name}"
                        )
            return self
        if self.nr_arfcn is not None or self.subcarrier_spacing_khz is not None:
            raise ValueError("LTE commissioning request must not set NR channel fields")
        for field_name in (
            "frequency_hz", "bandwidth_mhz", "band", "duplex",
            "lte_dl_earfcn", "lte_transmission_mode",
        ):
            if getattr(self, field_name) is None:
                raise ValueError(
                    f"LTE commissioning request requires explicit {field_name}"
                )
        return self

    @model_validator(mode="after")
    def require_current_gcm_model_source(self) -> "CreateSessionRequest":
        """正式 GCM 会话必须声明本次要加载的模型来源。

        ``precheck_strict_emulation_file=False`` 是既有 lab-smoke 明确降级，
        仍允许 mock/诊断空跑；默认严格路径不得依赖 F64 上一轮遗留 ``.smu``。
        """
        if (
            self.engine_mode == "keysight_gcm"
            and self.precheck_strict_emulation_file is not False
            and self.channel_asset_id is None
            and not (self.emulation_file or "").strip()
        ):
            raise ValueError(
                "engine_mode=keysight_gcm 的正式暗室首测必须提供 "
                "channel_asset_id 或 emulation_file；不能依赖 F64 遗留场景。"
            )
        return self

    @model_validator(mode="after")
    def require_audited_execution_policy(self) -> "CreateSessionRequest":
        if self.precheck_strict_cal is not None:
            raise ValueError(
                "precheck_strict_cal no longer grants qualification; use "
                "execution_policy_mode with reason and updated_by"
            )
        audit_values = (
            self.execution_policy_reason,
            self.execution_policy_updated_by,
        )
        if self.execution_policy_mode is None:
            if any(value is not None for value in audit_values):
                raise ValueError(
                    "execution_policy_reason/updated_by require execution_policy_mode"
                )
            return self
        if any(value is None or not value.strip() for value in audit_values):
            raise ValueError(
                "execution_policy_mode requires non-blank reason and updated_by"
            )
        return self


class SessionResponse(BaseModel):
    session_id: str
    phase: str
    phase_statuses: Dict[str, str]
    overall_progress: float
    config: Dict[str, Any]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    precheck: Optional[Dict[str, Any]] = None
    reference: Optional[Dict[str, Any]] = None
    mimo_test: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    report_id: Optional[str] = None
    execution_qualification: Optional[ExecutionQualification] = None


class PhaseResultResponse(BaseModel):
    phase: str
    status: str
    result: Dict[str, Any]


# ==================== Helpers ====================


def _request_overrides(req: CreateSessionRequest) -> Dict[str, Any]:
    """Translate CreateSessionRequest fields into MIMOOTAConfiguration overrides."""
    overrides: Dict[str, Any] = {
        "cdl_model_name": req.cdl_model_name,
        "mimo_layers": req.mimo_layers,
        "azimuths_deg": req.azimuths_deg,
        "measurement_duration_s": req.measurement_duration_s,
        "engine_mode": req.engine_mode,
        "asc_source_path": req.asc_source_path,
        "pass_criteria": {
            "min_throughput_ratio": req.min_throughput_ratio,
            "max_rsrp_variance_db": req.max_rsrp_variance_db,
        },
    }
    # 频率/带宽: None = 不覆盖 → 用 MIMOOTAConfiguration 的通用默认
    # （3.5 GHz / 100 MHz）。现场工作点由调用方显式给。见类定义上的注释。
    if req.frequency_hz is not None:
        overrides["frequency_hz"] = req.frequency_hz
    if req.bandwidth_mhz is not None:
        overrides["bandwidth_mhz"] = req.bandwidth_mhz
    if req.radio_technology == "lte":
        overrides["component_carriers"] = [
            {
                "radio_technology": "lte",
                "frequency_hz": req.frequency_hz,
                "bandwidth_mhz": req.bandwidth_mhz,
                "band": req.band,
                "duplex": req.duplex,
                "lte_dl_earfcn": req.lte_dl_earfcn,
                "lte_transmission_mode": req.lte_transmission_mode,
                "role": "pcell",
            }
        ]
        if req.theoretical_peak_throughput_mbps is not None:
            overrides["theoretical_peak_throughput_mbps"] = (
                req.theoretical_peak_throughput_mbps
            )
    elif any(
        value is not None
        for value in (req.band, req.nr_arfcn, req.subcarrier_spacing_khz)
    ):
        if req.frequency_hz is None or req.bandwidth_mhz is None:
            raise ValueError("explicit NR commissioning PCell requires frequency and bandwidth")
        overrides["component_carriers"] = [
            {
                "radio_technology": "nr5g",
                "frequency_hz": req.frequency_hz,
                "bandwidth_mhz": req.bandwidth_mhz,
                "subcarrier_spacing_khz": (
                    30
                    if req.subcarrier_spacing_khz is None
                    else req.subcarrier_spacing_khz
                ),
                "band": req.band,
                "nr_arfcn": req.nr_arfcn,
                "role": "pcell",
            }
        ]
    # 仪表工作点（暗室首测专用）—— 同样 None = 不覆盖。这些**不放共享 schema
    # 默认**：那会流进每条新建用例、也会被填进 JSON 里缺这些键的既有用例
    # （2026-08-07 实证：既有 MIMO_OTA 用例的 configuration 里这几个键全缺）。
    for _f in (
        "base_station_config_mode",
        "uxm_dl_power_dbm_per_bw",
        "f64_input_ref_dbm",
        "f64_crest_db",
        "f64_output_level_dbm",
        "emulation_file",
        "f64_bypass_mode",
    ):
        _v = getattr(req, _f)
        if _v is not None:
            overrides[_f] = _v
    # P3-14: 资产引用透传 (MIMOOTAConfiguration.channel_asset_id 已存在, S3 起
    # measure resolver 按它派生 engine_mode / .smu 源)。None 不发 — 不覆盖默认。
    if req.channel_asset_id is not None:
        overrides["channel_asset_id"] = str(req.channel_asset_id)
    # Only emit the strict-gate flags when the caller set them explicitly.
    # Omitting them keeps the config schema default (True / strict). The
    # mock/real auto-skip is NOT applied here — it's evaluated live at precheck
    # time (precheck.py sections 5 / 5b: `strict = config_flag AND hardware_real`)
    # so a session created in mock but run on real hardware still gets the gate
    # (Codex on PR #75). An explicit False here is the real-mode operator
    # override (Lab-smoke toggle); None leaks nothing.
    if req.precheck_strict_dut is not None:
        overrides["precheck_strict_dut"] = req.precheck_strict_dut
    # P2-11: Phase 1/2/3 新门同样的 explicit-False-override / None-leaves-default 语义。
    if req.precheck_strict_frequency is not None:
        overrides["precheck_strict_frequency"] = req.precheck_strict_frequency
    if req.precheck_strict_emulation_file is not None:
        overrides["precheck_strict_emulation_file"] = req.precheck_strict_emulation_file
    if req.precheck_strict_switch_mode is not None:
        overrides["precheck_strict_switch_mode"] = req.precheck_strict_switch_mode
    if req.precheck_strict_cell_config is not None:
        overrides["precheck_strict_cell_config"] = req.precheck_strict_cell_config
    if req.precheck_strict_dut_capability is not None:
        overrides["precheck_strict_dut_capability"] = req.precheck_strict_dut_capability
    if req.precheck_strict_sim_identity is not None:
        overrides["precheck_strict_sim_identity"] = req.precheck_strict_sim_identity
    return overrides


def _request_execution_policy(req: CreateSessionRequest) -> Dict[str, Any] | None:
    """Build the server-owned TestCase policy from complete request audit."""

    if req.execution_policy_mode is None:
        return None
    policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode=req.execution_policy_mode,
        reason=req.execution_policy_reason,
        updated_by=req.execution_policy_updated_by,
        updated_at=datetime.now(timezone.utc),
    )
    return policy.model_dump(mode="json")


def _phase_status_from_payload(
    payload: Dict[str, Any],
    *,
    require_operational_truth: bool = False,
) -> str:
    """Map a phase payload to old PhaseStatus string."""
    if not payload:
        return "pending"
    if payload.get("overall_pass") is False:
        if require_operational_truth and payload.get("operational_ready") is not False:
            return "completed"
        return "failed"
    return "completed"


def _commissioning_measure_projection(
    execution: TestExecution,
    test_case: TestCase,
    measure: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """Expose raw rows only beside a server-owned formal metric projection."""

    if measure is None:
        return None
    execution_config = execution.config if isinstance(execution.config, dict) else {}
    outcome = project_execution_evidence_outcome(execution)
    diagnostic = execution_evidence_blocks_formal_outputs(execution)
    classification = outcome.qualification_classification
    evidence = execution_config.get(BASE_STATION_EXECUTION_EVIDENCE_FIELD)
    evidence_required = base_station_metric_projection_required(
        execution_config
    )
    if not evidence_required:
        projected = deepcopy(measure)
        projected["execution_classification"] = classification
        return projected

    expected_config, expected_positions = base_station_expected_scope_from_evidence(
        evidence
    )
    rows = (
        project_base_station_metrics_by_position(
            evidence,
            expected_config=expected_config,
            expected_positions=expected_positions,
            execution_config=execution_config,
        )
        if expected_config is not None
        else []
    )
    projected = deepcopy(measure)
    projected["execution_classification"] = classification
    if diagnostic:
        rows = [
            {
                **row,
                "metrics": {
                    key: metric.model_copy(
                        update={
                            "status": "diagnostic"
                            if metric.diagnostic_value is not None
                            or metric.formal_value is not None
                            else "unknown",
                            "formal_value": None,
                            "diagnostic_value": metric.diagnostic_value
                            if metric.diagnostic_value is not None
                            else metric.formal_value,
                            "reason": "execution_qualification_diagnostic",
                        }
                    )
                    for key, metric in row["metrics"].items()
                },
            }
            for row in rows
        ]
        for row in rows:
            row["dl_throughput_mbps"] = row["metrics"].get(
                "dl_throughput_mbps", row["dl_throughput_mbps"]
            )
            row["dl_bler_percent"] = row["metrics"].get(
                "dl_bler_percent", row["dl_bler_percent"]
            )
    projected["base_station_metric_projection"] = [
        {
            "position": row["position"],
            "metrics": {
                key: metric.model_dump(mode="json")
                for key, metric in row["metrics"].items()
            },
            "dl_throughput_mbps": row["dl_throughput_mbps"].model_dump(mode="json"),
            "dl_bler_percent": row["dl_bler_percent"].model_dump(mode="json"),
        }
        for row in rows
    ]
    return projected


def _execution_to_session_response(
    execution: TestExecution, test_case: TestCase
) -> SessionResponse:
    """Reconstruct the legacy SessionResponse shape from TestExecution + TestCase."""
    measurements = execution.measurements or {}
    phases: Dict[str, Dict[str, Any]] = (measurements or {}).get("phases", {})

    # phase_statuses keyed by old phase strings
    phase_statuses: Dict[str, str] = {}
    completed_count = 0
    for legacy_name in _LEGACY_PHASE_ORDER:
        # legacy_name -> internal phases key (mimo_test -> measure, others same)
        internal_key = (
            "measure" if legacy_name == "mimo_test" else legacy_name
        )
        payload = phases.get(internal_key, {}) or {}
        status = _phase_status_from_payload(
            payload,
            require_operational_truth=internal_key == "precheck",
        )
        phase_statuses[legacy_name] = status
        if status == "completed":
            completed_count += 1

    overall_progress = completed_count / len(_LEGACY_PHASE_ORDER) * 100.0

    # current "phase" — pick the latest one with data, else first pending
    current_phase = "precheck"
    for legacy_name in _LEGACY_PHASE_ORDER:
        if phase_statuses[legacy_name] == "completed":
            current_phase = legacy_name
        else:
            current_phase = legacy_name
            break

    cfg = test_case.configuration or {}
    config_view = {
        "cdl_model_name": cfg.get("cdl_model_name"),
        "frequency_ghz": (cfg.get("frequency_hz") or 0.0) / 1e9,
        "bandwidth_mhz": cfg.get("bandwidth_mhz"),
        "mimo_config": f"{cfg.get('mimo_layers', 2)}x{cfg.get('mimo_layers', 2)}",
        "azimuths_deg": cfg.get("azimuths_deg"),
        "measurement_duration_s": cfg.get("measurement_duration_s"),
        "total_estimated_time_s": (
            (cfg.get("measurement_duration_s", 0) + cfg.get("settling_time_s", 0))
            * len(cfg.get("azimuths_deg", []) or [])
        ),
        "engine_mode": cfg.get("engine_mode"),
    }

    report_payload = phases.get("report") or {}

    return SessionResponse(
        session_id=str(execution.id),
        phase=current_phase,
        phase_statuses=phase_statuses,
        overall_progress=overall_progress,
        config=config_view,
        started_at=(
            execution.started_at.isoformat() + "Z" if execution.started_at else None
        ),
        completed_at=(
            execution.completed_at.isoformat() + "Z" if execution.completed_at else None
        ),
        precheck=phases.get("precheck"),
        reference=phases.get("reference"),
        mimo_test=_commissioning_measure_projection(
            execution,
            test_case,
            phases.get("measure"),
        ),
        analysis=phases.get("analysis"),
        report_id=report_payload.get("report_id"),
        execution_qualification=(
            ExecutionQualification.model_validate(
                (execution.config or {}).get(EXECUTION_QUALIFICATION_KEY)
            )
            if isinstance(execution.config, dict)
            and isinstance(execution.config.get(EXECUTION_QUALIFICATION_KEY), dict)
            else None
        ),
    )


def _resolve_execution(
    db: Session, session_id: str
) -> tuple[TestExecution, TestCase, list[StepDescriptor]]:
    """Look up TestExecution + TestCase by session_id (= execution UUID).

    Step descriptors are reconstructed from TestExecution.config JSON, which
    the create_session endpoint stores at session creation time.
    """
    try:
        exec_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid session_id: {session_id}")

    execution = db.query(TestExecution).filter(TestExecution.id == exec_uuid).first()
    if execution is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if execution.executed_by not in COMMISSIONING_CHAINS:
        # 收窄到本链 (内审 F5): 用例执行的快照用例同样是 MIMO_OTA, 拿它的
        # execution id 打 run-all 会两条链并发同一套 HAL, 且退出时改写它的
        # 状态 → case-runner 下个相位边界看到非 running 就静默 return,
        # 正式测试无声中断。各链自管各的行 (与复位 / cancel 同一刀)。
        raise HTTPException(
            status_code=404,
            detail=(
                f"Session {session_id} 不属于暗室首测链 "
                f"(executed_by={execution.executed_by!r})"
            ),
        )

    # P1-36（内审 F1）：**这里**才是暗室首测的执行身份落点。
    #
    # 早前 set 在 `create_session` 里 —— 但那个端点**根本不跑相位**（只建行
    # 返回），而真正 dispatch 的 `run_phase` / `run_all_phases` 一处都没有。
    # 内审探针实证：`run-all` 产生 **51 条日志、0 条带 execution_id**；
    # 唯一被标上的那行是 `create_session` 那条，而它自己早就把 id 写进了
    # 消息文本 —— 我拿它当证据，正是「验证打在看起来的那一端」。
    #
    # `_resolve_execution` 是 `run_phase` / `run_all_phases` / `get_session`
    # 三者的**唯一解析点**，跟 VRT 选 `get()` 是同一个理由。
    current_execution_id.set(str(execution.id))
    if execution.test_case_id is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session {session_id}: no test_case bound (corrupted state)",
        )
    test_case = (
        db.query(TestCase).filter(TestCase.id == execution.test_case_id).first()
    )
    if test_case is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session {session_id}: TestCase {execution.test_case_id} missing",
        )
    if test_case.test_type != MIMO_OTA_TEST_TYPE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Session {session_id}: TestCase test_type='{test_case.test_type}' is "
                f"not {MIMO_OTA_TEST_TYPE}"
            ),
        )

    raw_steps = (execution.config or {}).get("step_descriptors") or []
    descriptors = [
        StepDescriptor(
            id=s["id"], type=s["type"], parameters=s.get("parameters") or {}
        )
        for s in raw_steps
    ]
    return execution, test_case, descriptors


def _build_context(
    db: Session,
    execution: TestExecution,
    test_case: TestCase,
    step: StepDescriptor,
) -> StepExecutionContext:
    """开关 3: 提升到 services/test_execution/hydrate.py 与计划 runner 共用。"""
    from app.services.test_execution.hydrate import build_step_context

    return build_step_context(db, execution, test_case, step)


# ==================== Endpoints ====================


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest, db: Session = Depends(get_db)):
    """Create a new MIMO_OTA session (TestCase + TestExecution + 5 step descriptors)."""
    # P3-14 (内审 F2): 资产悬空引用在创建期就 422 — 否则 precheck/reference 两个
    # 阶段 (真仪器时间) 跑完才在 measure 撞 ChannelAssetResolveError, 现场时间贵。
    # 对称先例: 同函数里 lab_profile_id 创建期解析失败即 422。
    if req.channel_asset_id is not None:
        from app.services.channel_asset_service import (
            ChannelAssetNotFound,
            get_channel_asset,
        )
        from app.services.mimo_ota.channel_asset_resolver import (
            ChannelAssetResolveError,
            engine_mode_for_channel_asset,
        )
        try:
            asset = get_channel_asset(db, req.channel_asset_id)
        except ChannelAssetNotFound as err:
            raise HTTPException(status_code=422, detail=str(err)) from err
        if asset.is_active is not True:
            raise HTTPException(
                status_code=422,
                detail=f"ChannelAsset {asset.id} 已退役，不能用于创建新会话。",
            )
        try:
            resolved_engine = engine_mode_for_channel_asset(asset)
        except ChannelAssetResolveError as err:
            raise HTTPException(status_code=422, detail=str(err)) from err

        # ChannelAsset resolver is authoritative and otherwise overwrites
        # config.engine_mode at measure time. Reject the contradiction here,
        # before the operator spends instrument time on earlier phases.
        if resolved_engine != req.engine_mode:
            required_target = {
                "keysight_gcm": "gcm_native",
                "mimo_first_asc": "asc_baked",
                "b2_parametric_tdl": "b2_parametric",
            }.get(req.engine_mode, "no_channel_asset_target")
            raise HTTPException(
                status_code=422,
                detail=(
                    f"engine_mode={req.engine_mode} requires ChannelAsset target "
                    f"{required_target}; asset {asset.id} source_type={asset.source_type} "
                    f"resolves to engine_mode={resolved_engine} "
                    f"(allowed_targets={asset.allowed_targets})."
                ),
            )

        # A vendor declaration without an associated .smu is useful metadata,
        # but it is not an executable GCM cold-start source. The explicit
        # lab-smoke downgrade remains the only exception.
        if (
            req.engine_mode == "keysight_gcm"
            and req.precheck_strict_emulation_file is not False
            and not str(asset.associated_file_path or "").strip().lower().endswith(".smu")
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"ChannelAsset {asset.id} is declared_only and has no usable "
                    "associated .smu file; strict keysight_gcm commissioning "
                    "cannot depend on the F64's previous model."
                ),
            )
    overrides = _request_overrides(req)
    try:
        test_case, descriptors = build_mimo_ota_test_case(
            db,
            name=(
                "MIMO_OTA Session "
                + format_human_local_timestamp(datetime.now(timezone.utc))
            ),
            description="Created by /commissioning/sessions REST endpoint",
            lab_profile_id=req.lab_profile_id,
            config_overrides=overrides,
            created_by="commissioning_api",
            tags=["mimo_ota_session", "commissioning"],
            execution_policy=_request_execution_policy(req),
        )
    except LabResolutionError as err:
        raise _lab_resolution_to_422(err) from err
    except ValueError as err:
        # explicit lab_profile_id that's missing/inactive — caller bug,
        # but a clean 422 is more useful than a 500 traceback
        raise HTTPException(status_code=422, detail=str(err)) from err

    execution = TestExecution(
        test_case_id=test_case.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={
            "step_descriptors": [
                {"id": d.id, "type": d.type, "parameters": d.parameters}
                for d in descriptors
            ],
            # 与测试管理正门同一语义：静态 PRECHECK 后，由 MEASURE 按本次
            # TestCase 初始化完整 RF 链、受控 attach，再做动态门和正式采样。
            "managed_rf_attach": True,
        },
        executed_by="commissioning_api",
    )
    db.add(execution)
    db.flush()
    try:
        # Commissioning phases share one TestExecution. Freeze both instrument
        # contracts before any phase progress exists; waiting until MEASURE
        # would make a preceding PRECHECK an unsafe backfill boundary.
        _freeze_instrument_lease(
            db, execution, test_case, include_positioner=True
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=f"仪表执行配置无法冻结: {error}",
        ) from error
    db.commit()
    db.refresh(execution)

    # P1-36: 暗室首测的相位**同步跑在这个请求线程上**，所以在这里 set 一次，
    # 本次请求内后续的全部日志 (executor / HAL / SCPI) 自动带上执行身份。
    # 与 test_case_runner 那条是同一个机制，只是作用域从"后台任务"换成
    # "这次请求"。⚠ 全仓 4 种执行里这是其中两种，别只instrument一处。
    current_execution_id.set(str(execution.id))

    logger.info(
        "Created MIMO_OTA session: execution_id=%s test_case_id=%s",
        execution.id,
        test_case.id,
    )
    return _execution_to_session_response(execution, test_case)


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    include_ad_hoc: bool = False,
    db: Session = Depends(get_db),
):
    """List MIMO_OTA sessions (TestExecutions whose TestCase.test_type=MIMO_OTA).

    Phase 3 introduced 'diagnostic_ad_hoc' single-phase runs that *must* live
    in test_executions (executors need a row to write measurements into) but
    aren't actual commissioning sessions. Default behaviour hides them so
    the regular list view stays clean; pass include_ad_hoc=true to see them.
    """
    rows = (
        db.query(TestExecution, TestCase)
        .join(TestCase, TestExecution.test_case_id == TestCase.id)
        .filter(TestCase.test_type == MIMO_OTA_TEST_TYPE)
        # Codex #242 C3: 与 _resolve_execution 同一条链谓词 —— 否则
        # case-runner 的行 (快照用例同为 MIMO_OTA, 且不带
        # diagnostic_ad_hoc / test_step_id 标记) 会列在这里, 用户点进去
        # 却拿 404: "列得出、点不动"。列表与详情/执行路由必须同源。
        .filter(TestExecution.executed_by.in_(COMMISSIONING_CHAINS))
        .order_by(TestExecution.executed_at.desc())
        .limit(200)
        .all()
    )
    if not include_ad_hoc:
        # 门审 #217 F9: 计划 runner 的步骤执行 (config 带 test_step_id) 与
        # diagnostic_ad_hoc 同理隐藏 — 反复调试计划会每步一行, 淹没 bring-up
        # 会话列表; 计划执行明细走测试管理页/历史 Tab, 不占会话视图。
        rows = [
            (ex, tc) for ex, tc in rows
            if not (ex.config or {}).get("diagnostic_ad_hoc")
            and not (ex.config or {}).get("test_step_id")
        ]
    return [_execution_to_session_response(ex, tc) for ex, tc in rows]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: Session = Depends(get_db)):
    execution, test_case, _ = _resolve_execution(db, session_id)
    return _execution_to_session_response(execution, test_case)


@router.post(
    "/sessions/{session_id}/phase/{phase_name}",
    response_model=PhaseResultResponse,
)
async def run_phase(
    session_id: str, phase_name: str, db: Session = Depends(get_db)
):
    if phase_name not in _PHASE_NAME_TO_STEP_TYPE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown phase: {phase_name}. "
                f"Valid: {list(_PHASE_NAME_TO_STEP_TYPE.keys())}"
            ),
        )
    target_step_type = _PHASE_NAME_TO_STEP_TYPE[phase_name]
    execution, test_case, descriptors = _resolve_execution(db, session_id)

    # Find the descriptor for this step type
    step = next((d for d in descriptors if d.type == target_step_type), None)
    if step is None:
        raise HTTPException(
            status_code=500,
            detail=f"Session {session_id} has no step descriptor for {target_step_type}",
        )

    # ARCH-1 S3: 相位期间行标 running, 让 HAL reload 闸门看得见 (这条
    # 链 GUI 可点、跑真硬件, 之前全程 pending 所以闸门看不见它)
    ctx = _build_context(db, execution, test_case, step)
    try:
        validate_adapter = _freeze_instrument_lease(
            db,
            execution,
            test_case,
            include_positioner=target_step_type == "MIMO_OTA_MEASURE",
        )
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    result = None
    try:
        with _execution_marked_running(db, execution):
            with retain_positioner_stop_generation(_current_positioner_driver()):
                if target_step_type in {
                    "MIMO_OTA_ANALYSIS",
                    "MIMO_OTA_REPORT",
                }:
                    result = await dispatch_step(ctx)
                else:
                    async def _run_phase_operation():
                        phase_result = await dispatch_step(ctx)
                        return BaseStationSessionOperationResult(
                            value=phase_result,
                            succeeded=phase_result.status.value == "success",
                        )

                    result = await run_base_station_execution_session(
                        db,
                        execution,
                        test_case,
                        purpose=f"commissioning-phase:{session_id}:{phase_name}",
                        step_type=target_step_type,
                        validate_before_remote=validate_adapter,
                        operation=_run_phase_operation,
                    )
    except asyncio.CancelledError:
        raise
    except InstrumentTestLeaseReleaseError as error:
        if result is None:
            result = getattr(error, "operation_value", None)
        combined_error = _record_local_handoff_failure(
            db,
            execution,
            error,
            previous_error=(
                result.error_message if result is not None else None
            ),
        )
        raise InstrumentTestLeaseReleaseError(combined_error) from error
    except InstrumentTestLeaseError:
        raise

    db.refresh(execution)  # pick up measurements written by executor
    phases_key = _STEP_TYPE_TO_PHASES_KEY[target_step_type]
    phase_payload = (execution.measurements or {}).get("phases", {}).get(phases_key) or {}

    return PhaseResultResponse(
        phase=phase_name,
        status=result.status.value,
        result=phase_payload or {"_executor_status": result.status.value},
    )


# ==================== P3 Phase 3: ad-hoc single-phase (workshop tier) ====================


class AdhocPhaseRequest(BaseModel):
    """One-shot run of a single MIMO_OTA executor against a synthetic session.

    Differs from /sessions + /sessions/{id}/phase/{name} in that:
      - The created TestCase + TestExecution are tagged 'diagnostic_ad_hoc'
        so the regular commissioning list view can hide them.
      - A diagnostic_run audit row is written (kind=COMMISSIONING_PHASE) so
        ops history is searchable across SCPI sequences + ad-hoc phases.
      - phase_overrides override the descriptor.parameters dict for this
        phase (e.g. skip a precheck assertion that's known broken-but-
        irrelevant for the current debug goal).
      - config_overrides override MIMOOTAConfiguration before descriptor build,
        same shape as CreateSessionRequest fields.
    """

    lab_profile_id: Optional[UUID] = None
    phase_name: str  # one of _PHASE_NAME_TO_STEP_TYPE keys
    config_overrides: Optional[Dict[str, Any]] = None
    phase_overrides: Optional[Dict[str, Any]] = None
    run_by: Optional[str] = None


class AdhocPhaseResponse(BaseModel):
    diagnostic_run_id: UUID
    test_execution_id: UUID
    phase: str
    status: str
    duration_ms: int
    result: Dict[str, Any]
    error_message: Optional[str] = None


@router.post("/diagnostic/run-phase", response_model=AdhocPhaseResponse)
async def run_adhoc_phase(req: AdhocPhaseRequest, db: Session = Depends(get_db)):
    """Run ONE MIMO_OTA executor as a debug probe.

    Creates a tagged TestCase + TestExecution (the executors need a row to
    write measurements into), runs the requested phase, persists a
    diagnostic_run audit row, returns the executor's payload + status.
    """
    import time

    if req.phase_name not in _PHASE_NAME_TO_STEP_TYPE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown phase: {req.phase_name}. "
                f"Valid: {list(_PHASE_NAME_TO_STEP_TYPE.keys())}"
            ),
        )
    target_step_type = _PHASE_NAME_TO_STEP_TYPE[req.phase_name]

    # Build a regular MIMO_OTA TestCase but tag it so the commissioning list
    # view can filter these out.
    overrides = req.config_overrides or {}
    adhoc_policy = TestCaseExecutionPolicy(
        schema_version=1,
        mode="diagnostic",
        reason=f"Commissioning ad-hoc phase: {req.phase_name}",
        updated_by=(req.run_by or "commissioning_adhoc"),
        updated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    try:
        test_case, descriptors = build_mimo_ota_test_case(
            db,
            name=(
                f"ADHOC {req.phase_name} "
                + format_human_local_timestamp(datetime.now(timezone.utc))
            ),
            description=f"Ad-hoc workshop run of phase '{req.phase_name}'",
            lab_profile_id=req.lab_profile_id,
            config_overrides=overrides,
            created_by="commissioning_adhoc",
            tags=["diagnostic_ad_hoc", f"phase:{req.phase_name}"],
            execution_policy=adhoc_policy,
        )
    except LabResolutionError as err:
        raise _lab_resolution_to_422(err) from err
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    step = next((d for d in descriptors if d.type == target_step_type), None)
    if step is None:
        raise HTTPException(
            status_code=500,
            detail=f"No step descriptor for {target_step_type} (factory bug)",
        )

    # Apply per-phase parameter overrides on the in-memory descriptor only.
    if req.phase_overrides:
        step.parameters = {**(step.parameters or {}), **req.phase_overrides}

    execution = TestExecution(
        test_case_id=test_case.id,
        status="pending",
        started_at=datetime.utcnow(),
        config={
            "step_descriptors": [
                {"id": step.id, "type": step.type, "parameters": step.parameters},
            ],
            "diagnostic_ad_hoc": True,
            "phase_overrides": req.phase_overrides or {},
        },
        executed_by="commissioning_adhoc",
    )
    db.add(execution)
    db.flush()
    try:
        validate_adapter = _freeze_instrument_lease(
            db,
            execution,
            test_case,
            include_positioner=target_step_type == "MIMO_OTA_MEASURE",
        )
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    db.commit()
    db.refresh(execution)

    # P1-36: 暗室首测的相位**同步跑在这个请求线程上**，所以在这里 set 一次，
    # 本次请求内后续的全部日志 (executor / HAL / SCPI) 自动带上执行身份。
    # 与 test_case_runner 那条是同一个机制，只是作用域从"后台任务"换成
    # "这次请求"。⚠ 全仓 4 种执行里这是其中两种，别只instrument一处。
    current_execution_id.set(str(execution.id))

    # ARCH-1 S3: 开跑置 running, 让 HAL reload 闸门看得见这条链。
    # 不套 _execution_marked_running: 本入口下面已有更精细的收尾
    # (四态映射, skipped 不记成 failed), 两套收尾会打架。
    execution.status = "running"
    db.commit()

    started = time.monotonic()
    error_message: Optional[str] = None
    status_value = "failed"
    result = None
    try:
        ctx = _build_context(db, execution, test_case, step)
        with retain_positioner_stop_generation(_current_positioner_driver()):
            if target_step_type in {
                "MIMO_OTA_ANALYSIS",
                "MIMO_OTA_REPORT",
            }:
                result = await dispatch_step(ctx)
            else:
                async def _run_adhoc_operation():
                    phase_result = await dispatch_step(ctx)
                    return BaseStationSessionOperationResult(
                        value=phase_result,
                        succeeded=phase_result.status.value == "success",
                    )

                result = await run_base_station_execution_session(
                    db,
                    execution,
                    test_case,
                    purpose=f"commissioning-adhoc:{req.phase_name}",
                    step_type=target_step_type,
                    validate_before_remote=validate_adapter,
                    operation=_run_adhoc_operation,
                )
        status_value = result.status.value
        error_message = result.error_message
    except asyncio.CancelledError:
        raise
    except InstrumentTestLeaseReleaseError as e:
        logger.exception("[adhoc] phase=%s Local 交接失败", req.phase_name)
        if result is None:
            result = getattr(e, "operation_value", None)
        error_message = _record_local_handoff_failure(
            db,
            execution,
            e,
            previous_error=(
                result.error_message if result is not None else None
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("[adhoc] phase=%s aborted", req.phase_name)
        error_message = str(e)
    duration_ms = int((time.monotonic() - started) * 1000)

    db.refresh(execution)

    # Codex #238 迟到 C-2: 单相位诊断行也要收尾 — 建行时是 pending,
    # 不回写的话执行历史/仪表盘里它永远显示"待执行" (实际早跑完了)。
    # REPORT executor 会把成功链置 completed, 但 adhoc 多数相位不含
    # REPORT, 这里统一按实际结果落终态。
    # 相位状态有四种 (StepExecutionStatus: success/failed/skipped/running),
    # 二分成 completed/failed 会把"跳过"记成"失败" — skipped 是
    # TestExecution.status 的合法值, 原样保留 (自查发现, 见提交说明)。
    if execution.status == "running":
        _PHASE_TO_ROW_STATUS = {"success": "completed", "skipped": "skipped"}
        execution.status = _PHASE_TO_ROW_STATUS.get(status_value, "failed")
        execution.completed_at = datetime.utcnow()
        execution.duration_sec = duration_ms / 1000.0
        if error_message:
            execution.error_message = error_message
        db.commit()

    phases_key = _STEP_TYPE_TO_PHASES_KEY[target_step_type]
    phase_payload = (execution.measurements or {}).get("phases", {}).get(phases_key) or {}

    # Workshop audit row — keyed by phase_name so list views can filter.
    ctx_for_audit = build_diagnostic_context(
        db,
        lab_profile_id=req.lab_profile_id,
        resolve_rf_chains_too=False,  # speed: this is debug, not measurement
    )
    summary_text = (
        f"phase={req.phase_name} status={status_value} "
        f"test_execution_id={execution.id} "
        f"phase_overrides={req.phase_overrides or {}}"
    )
    if error_message:
        summary_text += f"\nerror: {error_message}"
    audit_row = ctx_for_audit.record_run(
        db,
        kind=DiagnosticKind.COMMISSIONING_PHASE,
        target_name=req.phase_name,
        success=status_value == "success",
        params={
            "phase_name": req.phase_name,
            "config_overrides": overrides,
            "phase_overrides": req.phase_overrides or {},
            "test_execution_id": str(execution.id),
        },
        output=summary_text,
        error_message=error_message,
        duration_ms=duration_ms,
        run_by=req.run_by,
    )

    return AdhocPhaseResponse(
        diagnostic_run_id=audit_row.id,
        test_execution_id=execution.id,
        phase=req.phase_name,
        status=status_value,
        duration_ms=duration_ms,
        result=phase_payload or {"_executor_status": status_value},
        error_message=error_message,
    )


# ==================== HAL trace tail (workshop tier) ====================


class HALTraceTailResponse(BaseModel):
    """Last N lines from the HAL/SCPI log file."""

    log_path: str
    lines: List[str]
    total_lines_returned: int


@router.get("/diagnostic/hal-trace-tail", response_model=HALTraceTailResponse)
async def hal_trace_tail(lines: int = 200):
    """Return the tail of the SCPI / HAL log so the GUI can render a live console.

    Workshop tier debugging hinges on "what did the box send back". Right
    now operators have to ssh and tail; this surfaces the same lines next
    to the ad-hoc result so debug stays in one window.
    """
    from pathlib import Path

    # The logging config writes SCPI traffic to ./logs/calibration.log
    # (for calibration paths) and ./logs/app.log catches general HAL events.
    # Workshop tools mostly want the SCPI/measurement stream — start with
    # measurement.log, fall back to app.log.
    candidates = [
        Path("logs/measurement.log"),
        Path("logs/calibration.log"),
        Path("logs/app.log"),
    ]
    chosen = next((p for p in candidates if p.exists()), None)
    if chosen is None:
        raise HTTPException(
            status_code=404,
            detail=f"No log file found in {candidates}; check logging config",
        )

    n = max(1, min(2000, lines))  # cap so a malformed query doesn't OOM
    # Cheap-and-correct tail for typical log sizes (< 100MB). The "right"
    # answer is seek-from-end + read-back, but log files here are small.
    with chosen.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    tail = [line.rstrip("\n") for line in all_lines[-n:]]

    return HALTraceTailResponse(
        log_path=str(chosen),
        lines=tail,
        total_lines_returned=len(tail),
    )


@router.post("/sessions/{session_id}/run-all", response_model=SessionResponse)
async def run_all_phases(session_id: str, db: Session = Depends(get_db)):
    """Sequentially dispatch all 5 phases. Aborts early if a phase fails."""
    execution, test_case, descriptors = _resolve_execution(db, session_id)
    try:
        validate_adapter = _freeze_instrument_lease(
            db, execution, test_case, include_positioner=True
        )
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error

    # ARCH-1 S3: 整条链期间行标 running (闸门要看得见暗室首测 —— 现场
    # 最常用的链)。终态由本函数按相位结果写, 不交给 contextmanager:
    # dispatch_step 从不上抛, "没异常"≠"成功" (内审 F1)。
    aborted_at: Optional[str] = None
    abort_message: Optional[str] = None
    started_at = datetime.utcnow()
    try:
        with _execution_marked_running(db, execution):
            with retain_positioner_stop_generation(_current_positioner_driver()):
                deferred_formalization = None

                async def _run_hardware_phases():
                    nonlocal aborted_at, abort_message
                    hardware_deferred = None
                    for index, step in enumerate(descriptors):
                        if step.type in {
                            "MIMO_OTA_ANALYSIS",
                            "MIMO_OTA_REPORT",
                        }:
                            remaining = descriptors[index:]
                            if [item.type for item in remaining] != [
                                "MIMO_OTA_ANALYSIS",
                                "MIMO_OTA_REPORT",
                            ]:
                                raise RuntimeError(
                                    "run-all 末尾必须是连续 ANALYSIS → REPORT"
                                )
                            hardware_deferred = remaining
                            break
                        ctx = _build_context(db, execution, test_case, step)
                        result = await dispatch_step(ctx)
                        if result.status.value == "failed":
                            aborted_at = step.type
                            abort_message = result.error_message
                            logger.warning(
                                "[%s] run-all aborted at %s: %s",
                                session_id,
                                step.type,
                                result.error_message,
                            )
                            break
                    return BaseStationSessionOperationResult(
                        value=hardware_deferred,
                        succeeded=aborted_at is None,
                    )

                deferred_formalization = await run_base_station_execution_session(
                    db,
                    execution,
                    test_case,
                    purpose=f"commissioning-run-all:{session_id}",
                    step_type="MIMO_OTA_MEASURE",
                    validate_before_remote=validate_adapter,
                    operation=_run_hardware_phases,
                )
                if aborted_at is None and deferred_formalization is not None:
                    for step in deferred_formalization:
                        ctx = _build_context(db, execution, test_case, step)
                        result = await dispatch_step(ctx)
                        if result.status.value == "failed":
                            aborted_at = step.type
                            abort_message = result.error_message
                            break
    except asyncio.CancelledError:
        raise
    except InstrumentTestLeaseReleaseError as error:
        previous_error = None
        if aborted_at is not None:
            previous_error = (
                f"链在相位 {aborted_at} 中止: "
                f"{abort_message or '明细见相位结果'}"
            )
        combined_error = _record_local_handoff_failure(
            db,
            execution,
            error,
            previous_error=previous_error,
        )
        raise InstrumentTestLeaseReleaseError(combined_error) from error
    except InstrumentTestLeaseError:
        raise

    if aborted_at is not None:
        # 中止的链是 failed —— 记成 completed 会让它混进待归档报告列表
        # 并被算进成功率 (内审 F1 实证)
        db.refresh(execution)
        execution.status = "failed"
        execution.completed_at = datetime.utcnow()
        execution.duration_sec = (
            execution.completed_at - started_at
        ).total_seconds()
        execution.error_message = (
            f"链在相位 {aborted_at} 中止: {abort_message or '明细见相位结果'}"
        )
        db.commit()
        emit_execution_failed_alert(execution.id)

    db.refresh(execution)
    db.refresh(test_case)
    return _execution_to_session_response(execution, test_case)


# ============================================================
# 暗室首测前逐设备快速自检 (借鉴转台 #132 / EMCenter standalone 验证理念)
#
# 暗室首测目的是快速 first-call 验整体思路, 不在细节调试上耗。但首测中途撞设备问题 (某仪表
# 没连上 / 不响应) 会打断这个目的。本端点在跑首测前对每个 HAL driver 主动探测 "连接 + 响应"
# (get_metrics 轻量查询), 让操作员先确认各设备单独通再开始首测 —— 把 "首测中途撞设备细节"
# 前移成 "首测前先单独验设备"。深度单设备控制验证去调试维护页 (转台控制 Tab / 调试序列)。
# ============================================================

class DeviceSelfcheckItem(BaseModel):
    category: str
    connected: bool
    responsive: bool  # get_metrics 不抛 = driver 能响应
    detail: Optional[str] = None


class DeviceSelfcheckResult(BaseModel):
    all_ready: bool
    devices: List[DeviceSelfcheckItem]
    message: str


@router.post("/device-selfcheck", response_model=DeviceSelfcheckResult)
async def device_selfcheck() -> DeviceSelfcheckResult:
    """暗室首测前逐设备快速自检 (连接 + 响应性主动探测)。"""
    items: List[DeviceSelfcheckItem] = []
    async with instrument_test_lease(
        "commissioning-device-selfcheck",
        enable_monitoring=False,
    ):
        try:
            from app.services.instrument_hal_service import get_hal_service
            hal = get_hal_service()
        except Exception:  # noqa: BLE001
            return DeviceSelfcheckResult(
                all_ready=False, devices=[], message="HAL 服务不可用"
            )
        drivers = (hal.drivers or {}) if hal else {}
        if not drivers:
            return DeviceSelfcheckResult(
                all_ready=False, devices=[],
                message="无 HAL 驱动加载 — 检查仪器已选 + 连接 IP 已填, 或重载 HAL 驱动",
            )
        for category, driver in sorted(drivers.items()):
            status = getattr(driver, "status", None)
            status_str = str(getattr(status, "value", status) or "").lower()
            connected = status_str in ("connected", "ready", "busy")
            responsive = False
            detail: Optional[str] = None
            try:
                await driver.get_metrics()  # 主动轻量探测 driver 是否响应
                responsive = True
            except Exception as e:  # noqa: BLE001
                detail = str(e)
            items.append(DeviceSelfcheckItem(
                category=category, connected=connected, responsive=responsive, detail=detail,
            ))
    all_ready = all(d.connected and d.responsive for d in items)
    return DeviceSelfcheckResult(
        all_ready=all_ready,
        devices=items,
        message=("各设备已连接且响应, 可开始暗室首测" if all_ready
                 else "部分设备未就绪 — 去调试维护页单独验证 (转台控制 / 调试序列) 后重试"),
    )


def _freeze_instrument_lease(
    db: Session,
    execution: TestExecution,
    test_case: TestCase,
    *,
    include_positioner: bool,
):
    """Freeze once, then return the lock-time pure validator callback."""
    from app.services.instrument_hal_service import get_hal_service

    hal = get_hal_service()
    frozen_base_station = freeze_execution_base_station_adapter_profile(
        db,
        hal,
        execution,
        test_case,
        force_diagnostic=execution.executed_by == "commissioning_adhoc",
    )
    validate_base_station = build_frozen_base_station_validator(
        frozen_base_station
    )
    frozen_positioner = None
    validate_positioner = None
    if include_positioner:
        frozen_positioner = freeze_execution_positioner_coordinate_profile(
            db,
            hal,
            execution,
            test_case,
        )
        validate_positioner = build_frozen_positioner_validator(
            frozen_positioner
        )

    def _validate(locked_hal):
        validators = [("baseStation", validate_base_station)]
        if validate_positioner is not None:
            validators.append(("positioner", validate_positioner))
        for label, validator in validators:
            error = validator(locked_hal)
            if error:
                return f"{label} frozen execution profile mismatch: {error}"
        return None

    _validate.validation_identity = ":".join(
        digest
        for digest in (
            frozen_base_station.get("digest"),
            frozen_positioner.get("digest") if frozen_positioner else None,
        )
        if digest
    )
    return _validate
