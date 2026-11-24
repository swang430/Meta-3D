"""
Virtual Road Test API

REST API endpoints for virtual road test scenarios, topologies, and executions
"""

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional, Any
import logging
import traceback
from datetime import datetime

from app.db.database import get_db
from app.models.report import TestReport, ReportType, ReportStatus, ReportFormat

from app.schemas.road_test import (
    RoadTestScenario,
    ScenarioCreate,
    ScenarioUpdate,
    ScenarioSummary,
    ScenarioCategory,
    ScenarioSource,
    NetworkTopology,
    TopologyCreate,
    TopologyUpdate,
    TopologySummary,
    TopologyValidationResult,
    TestExecution,
    ExecutionCreate,
    ExecutionControl,
    ExecutionSummary,
    TestStatus,
    TestMetrics,
    KPIMetrics,
    MetricsStreamMessage,
    StreamSubscription,
    TestMode,
    ExecutionStatus,
    # Report models
    ExecutionReport,
    ScenarioInfo,
    NetworkInfo,
    EnvironmentInfo,
    RouteInfo,
    BaseStationInfo,
    StepConfigInfo,
    # Metrics submission models
    ExecutionMetricsSubmit,
    # Detailed config models
    NetworkConfigDetail,
    BaseStationConfigDetail,
    DigitalTwinConfig,
    CustomConfigHighlight,
    TrajectoryPoint,
)
from app.schemas.road_test.execution import TwinTimeline, TwinComparison, ExecutionArchiveReceipt, ExecutionControlReceipt, RoadTestAvailability
from app.data.scenario_library import (
    get_all_scenarios,
    get_scenario_by_id,
    get_scenarios_by_category,
)
from app.services.road_test.measurement_evidence import real_driver_pair, throughput_summary
from app.services.road_test import twin_playback
from app.services.road_test.vrt_execution_service import _utcnow
from app.services.road_test.vrt_service import vrt_service
from app.services.road_test.network_topology_service import network_topology_service
from app.services.road_test.vrt_execution_service import vrt_execution_service

from pydantic import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/road-test", tags=["Virtual Road Test"])


# ──────────────────────────────────────────────────────────────────────────
# Custom scenarios are persisted as TestCase rows with test_type='VirtualRoadTest'.
# These helpers convert TestCase rows to/from the legacy RoadTestScenario shape
# so the existing endpoint contracts remain unchanged for clients during the
# VRT-into-TestCase consolidation (Phase 2).
# ──────────────────────────────────────────────────────────────────────────

def _env_channel_model_str(env) -> str:
    """P2-20 (内审 F2): 信道模型摘要串 — 快照真值, 双形态兼容 (pydantic 对象 /
    model_dump dict 都走 get_attr_or_item, 与本函数族其余字段同契约)。
    无快照 / Custom 快照 → 空串 (报告显示空, 不编造模型名)。"""
    snaps = get_attr_or_item(env, 'channel_snapshots', []) or []
    if not snaps:
        return ''
    model = get_attr_or_item(snaps[0], 'standard_model', None)
    if model is None:
        return ''
    return model.value if hasattr(model, 'value') else str(model)


def _list_custom_scenarios(db: Session) -> List[RoadTestScenario]:
    """Read all VRT TestCases from the DB and project them as RoadTestScenarios.

    P2-20: 逐行投影 + 降级 — 单行坏 configuration (旧 schema 遗留 / 手改脏数据)
    过不了 model_validate 时跳过该行并 logger.error 报数, 不再让 ValidationError
    冒泡把整个 /road-test/scenarios 打成 500 (单行坏数据不许有全库爆炸半径)。
    跳行是**响的** (ERROR 级 + 计数), 不是静默丢。
    """
    out: List[RoadTestScenario] = []
    bad = 0
    for tc in vrt_service.list_vrt_test_cases(db, limit=10_000):
        try:
            out.append(vrt_service.vrt_test_case_to_scenario(tc))
        except Exception as e:  # noqa: BLE001 — 单行降级, 不吞聚合错误
            bad += 1
            logger.error(
                "[vrt] TestCase %s 投影场景失败, 跳过该行 (P2-20 单行降级): %s",
                tc.id, e,
            )
    if bad:
        logger.error("[vrt] 场景列表本次跳过 %d 行坏配置 — 请排查上方逐行日志", bad)
    return out


def _get_custom_scenario(db: Session, scenario_id: str) -> Optional[RoadTestScenario]:
    """Fetch a single VRT TestCase by id (UUID string) and convert.

    Companion TestCases (FK-target placeholders auto-created by
    legacy scenario-based TestPlan flow) are not real VRT scenarios
    and are reported as not-found here — `vrt_test_case_to_scenario`
    would otherwise raise a clear ValueError on them; this layer
    just maps that to a 404 / None for the GET endpoint (P3-8).
    """
    from app.services.road_test.vrt_service import is_companion_test_case

    try:
        from uuid import UUID
        tc = vrt_service.get_vrt_test_case(db, UUID(scenario_id))
    except (ValueError, AttributeError):
        return None
    if tc is None or is_companion_test_case(tc):
        return None
    return vrt_service.vrt_test_case_to_scenario(tc)


# Phase 2.4 complete: VRT runtime state lives in the database
# (test_executions + vrt_kpi_samples), accessed via vrt_execution_service.

def _log_event(
    db: Session,
    execution_id: str,
    message: str,
    level: str = "INFO",
    source: str = "System",
):
    """Internal helper to log execution events (DB-backed via vrt_execution_service)."""
    vrt_execution_service.append_log(db, execution_id, level=level, message=message, source=source)
    logger.info(f"[{execution_id}] {message}")


# ===== Scenario Management =====

def compute_overall_result(kpi_summary, execution_status):
    """算合格率与总结论。抽成纯函数是为了让它能被直接测到（P1-48）。

    ⚠️ **一条 KPI 都没有真判决时，结论恒为「未判定」** —— 不能掉进 failed。
    那等于把「编造的通过」换成「编造的不通过」，只是换了个方向说谎，半径没收敛。

    只有正式测量且具备适用判据时才能形成合格结论。客户端提交的判决不采信。
    """
    judged = [k for k in kpi_summary if getattr(k, "passed", None) is not None]
    passed_kpis = sum(1 for k in judged if k.passed)

    if not judged:
        # ⚠️ 合格率返回 None 而不是 0.0（外审 P1）：0.0 会被界面无条件
        #    显示成「通过率 0%」，读者以为一条都没过 —— 实际是**一条都没判**。
        #
        # ⚠️ 结论用 undetermined 而不是 incomplete（外审 P2）：
        #    incomplete 原本表示「执行没跑完」（还在跑 / 被停止），
        #    把它拿来兼表「跑完了但没有可信判决」会让真正没跑完的执行
        #    也显示成「未判定」—— 那是新的假信息。两者必须分开。
        # ⚠️ 执行**本身失败**这个信息不能丢（外审 P2）：原来这个早退分支
        #    在 FAILED 那一格之前就返回 incomplete，于是真正失败的执行
        #    被显示成「未完成」。
        if execution_status == ExecutionStatus.FAILED:
            return None, "failed"
        if execution_status == ExecutionStatus.COMPLETED:
            return None, "undetermined"
        return None, "incomplete"

    pass_rate = (passed_kpis / len(judged)) * 100
    if execution_status == ExecutionStatus.COMPLETED:
        return pass_rate, ("passed" if pass_rate >= 80 else "failed")
    if execution_status == ExecutionStatus.FAILED:
        return pass_rate, "failed"
    return pass_rate, "incomplete"


@router.get("/scenarios", response_model=List[ScenarioSummary])
async def list_scenarios(
    category: Optional[ScenarioCategory] = None,
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    source: Optional[str] = Query(None, description="standard or custom"),
    db: Session = Depends(get_db),
):
    """
    List all available road test scenarios

    Filter by category, tags, or source (standard/custom)
    """
    # Get standard scenarios
    if category:
        scenarios = get_scenarios_by_category(category)
    else:
        scenarios = get_all_scenarios()

    # Add custom scenarios (DB-backed via vrt_service)
    scenarios.extend(_list_custom_scenarios(db))

    # Filter by source
    if source:
        scenarios = [s for s in scenarios if s.source.value == source]

    # Filter by tags
    if tags and isinstance(tags, str):
        tag_list = [t.strip() for t in tags.split(",")]
        scenarios = [
            s for s in scenarios
            if any(tag in s.tags for tag in tag_list)
        ]

    # Convert to summaries with extended fields for editing
    summaries = []
    for s in scenarios:
        # 衍生字段算不出来只让这组字段缺省（缺谁补默认谁），行本身必须
        # 出现在列表里 —— 场景不允许因摘要构造失败而静默消失
        base = dict(
            id=s.id,
            name=s.name,
            category=s.category,
            source=s.source,
            tags=s.tags or [],
            description=s.description,
            created_at=s.created_at,
            author=s.author,
        )
        try:
            # Calculate average speed from route
            avg_speed = None
            if s.route and s.route.duration_s > 0:
                avg_speed = (s.route.total_distance_m / 1000) / (s.route.duration_s / 3600)  # km/h

            # Handle step_configuration - ensure it's serializable
            step_config = s.step_configuration
            if step_config is not None and not isinstance(step_config, dict):
                # If it's a Pydantic model, convert to dict
                if hasattr(step_config, 'model_dump'):
                    step_config = step_config.model_dump()

            # 信道模型真值在 channel_snapshots（Environment 已无 channel_model
            # 字段）；摘要取首个快照的 standard_model 作代表值，Custom 快照
            # 或无快照时为 None
            first_snapshot = (
                s.environment.channel_snapshots[0]
                if s.environment and s.environment.channel_snapshots
                else None
            )
            summaries.append(ScenarioSummary(
                **base,
                duration_s=s.route.duration_s if s.route else 0,
                distance_m=s.route.total_distance_m if s.route else 0,
                step_configuration=step_config,
                # Extended fields
                network_type=s.network.type.value if s.network else None,
                band=s.network.band if s.network else None,
                bandwidth_mhz=s.network.bandwidth_mhz if s.network else None,
                channel_model=(
                    first_snapshot.standard_model.value
                    if first_snapshot and first_snapshot.standard_model
                    else None
                ),
                avg_speed_kmh=avg_speed,
            ))
        except Exception as e:
            logger.error(f"Error computing summary fields for scenario {s.id}: {e}")
            summaries.append(ScenarioSummary(**base, duration_s=0, distance_m=0))

    return summaries


@router.get("/scenarios/{scenario_id}", response_model=RoadTestScenario)
async def get_scenario(scenario_id: str, db: Session = Depends(get_db)):
    """
    Get detailed scenario configuration
    """
    # Check standard scenarios
    scenario = get_scenario_by_id(scenario_id)
    if scenario:
        return scenario

    # Check custom scenarios (DB-backed)
    custom = _get_custom_scenario(db, scenario_id)
    if custom is not None:
        return custom

    raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")


@router.post("/scenarios", response_model=RoadTestScenario, status_code=201)
async def create_scenario(
    scenario_create: ScenarioCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new custom scenario (persisted as a VRT TestCase row).
    """
    # Build a transient RoadTestScenario from the create payload — only used
    # to feed the conversion helper. The real ID is the TestCase UUID.
    transient = RoadTestScenario(
        id="pending",
        source=ScenarioSource.CUSTOM,
        **scenario_create.model_dump(),
    )
    config = vrt_service.scenario_to_vrt_config(transient, mode=TestMode.DIGITAL_TWIN)
    test_case = vrt_service.create_vrt_test_case(
        db,
        name=scenario_create.name,
        configuration=config,
        created_by="api",  # TODO Phase 4: derive from auth context
        description=scenario_create.description,
        tags=scenario_create.tags,
    )
    logger.info("Created custom scenario %s as TestCase %s", scenario_create.name, test_case.id)
    return vrt_service.vrt_test_case_to_scenario(test_case)


@router.put("/scenarios/{scenario_id}", response_model=RoadTestScenario)
async def update_scenario(
    scenario_id: str,
    scenario_update: ScenarioUpdate,
    db: Session = Depends(get_db),
):
    """
    Update a scenario. For standard scenarios, creates a custom copy.
    """
    # Try custom scenario first (DB-backed)
    from uuid import UUID
    try:
        case_uuid = UUID(scenario_id)
        existing_tc = vrt_service.get_vrt_test_case(db, case_uuid)
    except ValueError:
        existing_tc = None

    if existing_tc is not None:
        existing_scenario = vrt_service.vrt_test_case_to_scenario(existing_tc)
        # Apply partial update onto the existing scenario shape
        update_data = scenario_update.model_dump(exclude_unset=True)
        merged = existing_scenario.model_dump()
        for field, value in update_data.items():
            if value is not None:
                merged[field] = value
        merged_scenario = RoadTestScenario.model_validate(merged)
        new_config = vrt_service.scenario_to_vrt_config(
            merged_scenario, mode=TestMode.DIGITAL_TWIN
        )
        updated = vrt_service.update_vrt_test_case(
            db,
            case_uuid,
            name=merged_scenario.name,
            description=merged_scenario.description,
            configuration=new_config,
            tags=merged_scenario.tags,
        )
        logger.info("Updated custom scenario %s", scenario_id)
        return vrt_service.vrt_test_case_to_scenario(updated)

    # Standard scenario: create a custom copy with the updates applied.
    standard_scenario = get_scenario_by_id(scenario_id)
    if standard_scenario:
        scenario_data = standard_scenario.model_dump()
        scenario_data["source"] = ScenarioSource.CUSTOM
        update_data = scenario_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                scenario_data[field] = value
        # Drop fields owned by the new TestCase row
        scenario_data.pop("id", None)
        scenario_data.pop("created_at", None)
        scenario_data.pop("updated_at", None)
        new_scenario = RoadTestScenario(id="pending", **scenario_data)
        config = vrt_service.scenario_to_vrt_config(new_scenario, mode=TestMode.DIGITAL_TWIN)
        test_case = vrt_service.create_vrt_test_case(
            db,
            name=new_scenario.name,
            configuration=config,
            created_by="api",
            description=new_scenario.description,
            tags=new_scenario.tags,
        )
        logger.info(
            "Created custom scenario %s from standard scenario %s",
            test_case.id,
            scenario_id,
        )
        return vrt_service.vrt_test_case_to_scenario(test_case)

    raise HTTPException(
        status_code=404,
        detail=f"Scenario '{scenario_id}' not found",
    )


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(scenario_id: str, db: Session = Depends(get_db)):
    """
    Delete a custom scenario (standard scenarios cannot be deleted)
    """
    from uuid import UUID
    try:
        case_uuid = UUID(scenario_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Custom scenario '{scenario_id}' not found or is a standard scenario",
        )

    if not vrt_service.delete_vrt_test_case(db, case_uuid):
        raise HTTPException(
            status_code=404,
            detail=f"Custom scenario '{scenario_id}' not found or is a standard scenario",
        )

    logger.info("Deleted custom scenario %s", scenario_id)
    return JSONResponse(status_code=204, content=None)


# ===== Topology Management =====

@router.get("/topologies", response_model=List[TopologySummary])
async def list_topologies(db: Session = Depends(get_db)):
    """
    List all network topologies (DB-backed via the `topologies` table).
    """
    topologies = network_topology_service.list(db)
    return [
        TopologySummary(
            id=t.id,
            name=t.name,
            topology_type=t.topology_type,
            description=t.description,
            is_validated=t.is_validated,
            devices_count=3,  # BS + CE + DUT
            connections_count=len(t.connections),
            created_at=t.created_at,
            author=t.author,
        )
        for t in topologies
    ]


@router.get("/topologies/{topology_id}", response_model=NetworkTopology)
async def get_topology(topology_id: str, db: Session = Depends(get_db)):
    """
    Get detailed topology configuration
    """
    topology = network_topology_service.get(db, topology_id)
    if topology is None:
        raise HTTPException(status_code=404, detail=f"Topology '{topology_id}' not found")
    return topology


@router.post("/topologies", response_model=NetworkTopology, status_code=201)
async def create_topology(
    topology_create: TopologyCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new network topology (persisted in the `topologies` table).
    """
    topology = network_topology_service.create(db, topology_create, author="api")
    logger.info("Created topology %s", topology.id)
    return topology


@router.post("/topologies/{topology_id}/validate", response_model=TopologyValidationResult)
async def validate_topology(topology_id: str, db: Session = Depends(get_db)):
    """
    Validate topology configuration

    Checks:
    - Port conflicts
    - Connection validity
    - Device compatibility
    - RF link budget
    """
    topology = network_topology_service.get(db, topology_id)
    if topology is None:
        raise HTTPException(status_code=404, detail=f"Topology '{topology_id}' not found")

    # Validation logic (simplified)
    errors = []
    warnings = []

    # Check port conflicts
    used_ports = set()
    for conn in topology.connections:
        port_key = f"{conn.source_device_id}:{conn.source_port}"
        if port_key in used_ports:
            errors.append(f"Port conflict: {port_key} is used multiple times")
        used_ports.add(port_key)

    # Check connection validity
    for conn in topology.connections:
        if conn.cable_length_m > 10:
            warnings.append(f"Long cable ({conn.cable_length_m}m) may introduce significant loss")

    # Persist validation outcome back to the topology row
    network_topology_service.set_validation_result(
        db, topology_id, is_validated=len(errors) == 0, errors=errors
    )

    result = TopologyValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        details={
            "total_connections": len(topology.connections),
            "total_loss_db": sum(conn.loss_db for conn in topology.connections),
        },
    )

    logger.info("Validated topology %s: %s", topology_id, "PASS" if result.is_valid else "FAIL")
    return result


# ===== Test Execution =====

def _execution_scenario(db: Session, row):
    if row.mode == TestMode.CONDUCTED.value:
        # 旧传导记录没有可信快照，只能显示当时保存的场景标识。
        return (row.vrt_conducted_setup or {}).get("scenario_snapshot")
    if row.mode == "digital_twin" and row.vrt_twin_input:
        return row.vrt_twin_input["scenario_snapshot"]
    if row.scenario_id:
        return get_scenario_by_id(row.scenario_id) or _get_custom_scenario(db, row.scenario_id)
    return None


@router.get("/executions", response_model=List[ExecutionSummary])
async def list_executions(
    mode: Optional[TestMode] = None,
    status: Optional[ExecutionStatus] = None,
    db: Session = Depends(get_db),
):
    """
    List all test executions (DB-backed via test_executions table).
    """
    rows = vrt_execution_service.list(db, mode=mode, status=status)
    summaries = []
    for row in rows:
        scenario = _execution_scenario(db, row)
        scenario_name = get_attr_or_item(scenario, "name", row.scenario_id or "")
        summaries.append(vrt_execution_service.to_summary(row, scenario_name))
    return summaries


@router.post("/executions", response_model=TestExecution, status_code=201)
async def create_execution(
    execution_create: ExecutionCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new test execution

    Initializes the test executor based on the selected mode:
    - digital_twin: Fully simulated
    - conducted: Requires topology_id
    - ota: Uses MPAC chamber
    """
    # Validate scenario exists (standard library or custom DB-backed)
    scenario = get_scenario_by_id(execution_create.scenario_id)
    if not scenario:
        scenario = _get_custom_scenario(db, execution_create.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{execution_create.scenario_id}' not found")

    if "conducted" in execution_create.config:
        raise HTTPException(400, "请通过传导建档接口保存服务端核对的准备资料。")

    # Validate topology for conducted mode
    if execution_create.mode == TestMode.CONDUCTED:
        if not execution_create.topology_id:
            raise HTTPException(status_code=400, detail="Topology ID required for conducted mode")
        if not network_topology_service.exists(db, execution_create.topology_id):
            raise HTTPException(status_code=404, detail=f"Topology '{execution_create.topology_id}' not found")

    # Persist via service (initial state IDLE, log entry written automatically)
    row = vrt_execution_service.create(
        db,
        mode=execution_create.mode,
        scenario_id=execution_create.scenario_id,
        topology_id=execution_create.topology_id,
        config=execution_create.config,
        twin_input=twin_playback.freeze(scenario, execution_create.config) if execution_create.mode == TestMode.DIGITAL_TWIN else None,
        notes=execution_create.notes,
        created_by="api",
    )
    return vrt_execution_service.to_test_execution(row)


@router.get("/executions/{execution_id}", response_model=TestExecution)
async def get_execution(execution_id: str, db: Session = Depends(get_db)):
    """
    Get execution details
    """
    row = vrt_execution_service.get(db, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return vrt_execution_service.to_test_execution(row)


@router.post("/executions/{execution_id}/control", response_model=ExecutionControlReceipt,
             responses={409: {"description": "本次执行的设备、校准或状态不允许该操作。"}})
async def control_execution(
    execution_id: str,
    control: ExecutionControl,
    db: Session = Depends(get_db),
):
    """
    Control execution (start/pause/resume/stop/complete) — DB-backed state machine.
    """
    row = vrt_execution_service.get(db, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    current = ExecutionStatus(row.status)
    action = control.action.value if hasattr(control.action, "value") else control.action
    logger.info("[Control] %s requested for %s (current=%s)", action, execution_id, current.value)

    if row.mode == TestMode.CONDUCTED.value:
        from app.services.road_test.conducted_runner import control as control_conducted

        await control_conducted(db, row, action)
        if action == "stop":
            db.expire_all()
            await _archive_execution_report(execution_id, db)
        return {"status": "success", "execution_id": execution_id, "action": action}

    if action == "start":
        if current != ExecutionStatus.IDLE:
            raise HTTPException(status_code=400, detail="Execution already started")
        transitioned = vrt_execution_service.start(
            db,
            execution_id,
            expected_status=current,
        )
        if transitioned is None:
            raise HTTPException(
                status_code=409,
                detail="Execution state changed before start; refresh and retry.",
            )

    elif action == "pause":
        if current != ExecutionStatus.RUNNING:
            raise HTTPException(status_code=400, detail="Execution not running")
        transitioned = vrt_execution_service.pause(
            db,
            execution_id,
            expected_status=current,
        )
        if transitioned is None:
            raise HTTPException(
                status_code=409,
                detail="Execution state changed before pause; refresh and retry.",
            )

    elif action == "resume":
        if current != ExecutionStatus.PAUSED:
            raise HTTPException(status_code=400, detail="Execution not paused")
        transitioned = vrt_execution_service.resume(
            db,
            execution_id,
            expected_status=current,
        )
        if transitioned is None:
            raise HTTPException(
                status_code=409,
                detail="Execution state changed before resume; refresh and retry.",
            )

    elif action == "stop":
        if current in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
            raise HTTPException(status_code=400, detail="Execution already finished")
        terminal_row = vrt_execution_service.stop(
            db,
            execution_id,
            expected_status=current,
        )
        if terminal_row is None:
            raise HTTPException(
                status_code=409,
                detail="Execution state changed before stop; refresh and retry.",
            )
        await _archive_execution_report(execution_id, db)

    elif action == "complete":
        if current in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
            raise HTTPException(status_code=400, detail="Execution already finished")
        terminal_row = vrt_execution_service.complete(
            db,
            execution_id,
            expected_status=current,
        )
        if terminal_row is None:
            raise HTTPException(
                status_code=409,
                detail="Execution state changed before completion; refresh and retry.",
            )
        await _archive_execution_report(execution_id, db)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    return {"status": "success", "execution_id": execution_id, "action": action}


@router.get("/executions/{execution_id}/timeline", response_model=TwinTimeline)
async def get_twin_timeline(execution_id: str, db: Session = Depends(get_db)):
    row = vrt_execution_service.get(db, execution_id)
    if row is None:
        raise HTTPException(404, "找不到本次执行。")
    return twin_playback.timeline(row, _utcnow())


@router.get("/executions/{execution_id}/comparison", response_model=TwinComparison)
async def compare_twin(execution_id: str, conducted_execution_id: str, db: Session = Depends(get_db)):
    row = vrt_execution_service.get(db, execution_id)
    conducted = vrt_execution_service.get(db, conducted_execution_id)
    if row is None or conducted is None:
        raise HTTPException(404, "找不到所选执行。")
    if conducted.mode != "conducted":
        raise HTTPException(422, "请选择传导执行作为对照。")
    points = twin_playback.timeline(row, _utcnow())["points"]
    samples = vrt_execution_service.query_kpi_samples(db, conducted_execution_id)
    observations = vrt_execution_service.to_test_metrics(conducted, samples).observations
    return twin_playback.compare(row.vrt_twin_input, conducted.vrt_conducted_setup or {}, points, observations)


@router.get("/executions/{execution_id}/status", response_model=TestStatus)
async def get_execution_status(execution_id: str, db: Session = Depends(get_db)):
    """
    Get real-time execution status (derived from test_executions row).
    """
    row = vrt_execution_service.get(db, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return vrt_execution_service.to_test_status(row)


@router.get("/executions/{execution_id}/metrics", response_model=TestMetrics)
async def get_execution_metrics(execution_id: str, db: Session = Depends(get_db)):
    """
    Get execution metrics (KPI time series) from vrt_kpi_samples + JSONB summary.
    """
    row = vrt_execution_service.get(db, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    samples = vrt_execution_service.query_kpi_samples(db, execution_id)
    return vrt_execution_service.to_test_metrics(row, samples)


@router.post("/executions/{execution_id}/metrics")
async def submit_execution_metrics(
    execution_id: str,
    metrics: ExecutionMetricsSubmit,
    db: Session = Depends(get_db),
):
    """
    Submit execution metrics collected during test run.

    Receives time series + phase results + events + KPI summary, persists to
    vrt_kpi_samples table and JSONB columns on test_executions.
    """
    row = vrt_execution_service.get(db, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    if row.mode == TestMode.CONDUCTED.value:
        raise HTTPException(status_code=409, detail="传导测试的采样和进度由服务器记录。")

    # 1. Convert TimeSeriesPoint → KPIMetrics for the KPI samples table
    kpi_samples = [
        KPIMetrics(
            time_s=p.time_s,
            rsrp_dbm=p.rsrp_dbm,
            rsrq_db=p.rsrq_db,
            sinr_db=p.sinr_db,
            dl_throughput_mbps=p.dl_throughput_mbps,
            ul_throughput_mbps=p.ul_throughput_mbps,
            latency_ms=p.latency_ms,
            position=p.position,
            event_occurred=p.event,
        )
        for p in metrics.time_series
    ]

    # 2. Build summary from kpi_summary
    # ⚠️ 这个入口收到的**就是浏览器提交的数据**，
    #    所以后端**无条件**把这批标成模拟、不读请求里的任何标记 —— 被检查的一方
    #    不能自己声明自己是真是假。
    #    上一版只丢掉了 passed，而 mean/min/max/std **照样落库、照样印进报告**
    #    （外审 P1）—— 判决不采信了，数值还是编的，等于只挡了一半。
    summary = {
        kpi.name: {
            "mean": kpi.mean, "min": kpi.min, "max": kpi.max,
            "std": kpi.std, "target": kpi.target,
            "passed": None,          # 客户端的判决一律不采信
            "provenance": "client_simulated",   # 这批数的来源，报告据此决定印不印
        }
        for kpi in metrics.kpi_summary
    }

    # 3. Persist (frontend sends full history each call → simplest is replace; for now we append).
    try:
        n = vrt_execution_service.insert_kpi_samples(db, execution_id, kpi_samples)
        vrt_execution_service.set_summary(db, execution_id, summary)
        vrt_execution_service.append_events(db, execution_id, metrics.events)
        vrt_execution_service.set_phase_results(
            db, execution_id, [p.model_dump(mode="json") for p in metrics.phases]
        )
        logger.info(
            "Stored metrics for %s: %d samples, %d phases", execution_id, n, len(metrics.phases)
        )
    except Exception as e:
        logger.error(f"Error storing metrics: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error storing metrics: {str(e)}")

    return {
        "status": "success",
        "points_received": len(metrics.time_series),
        "phases_received": len(metrics.phases),
    }


@router.get("/executions/{execution_id}/report", response_model=ExecutionReport)
async def get_execution_report(execution_id: str, db: Session = Depends(get_db)):
    """
    Generate execution report for completed test

    Returns detailed report with scenario info, step configs, phase results, KPI summary, and events.
    """
    import traceback
    try:
        return await _generate_execution_report(execution_id, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report for {execution_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.post("/executions/{execution_id}/archive-report", response_model=ExecutionArchiveReceipt,
             responses={409: {"description": "执行尚未到达终态，或尚未取得可信的归档文件。"}})
async def archive_execution_report(execution_id: str, db: Session = Depends(get_db)):
    """Create/reuse the server-owned archive for a terminal VRT execution."""
    row = vrt_execution_service.get(db, execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    if row.status not in {
        ExecutionStatus.COMPLETED.value,
        ExecutionStatus.STOPPED.value,
        ExecutionStatus.FAILED.value,
    }:
        raise HTTPException(
            status_code=409,
            detail="VRT report archival is available only after the execution is terminal.",
        )

    await _archive_execution_report(execution_id, db)
    db.expire_all()
    report = db.query(TestReport).filter(
        TestReport.road_test_execution_id == execution_id
    ).first()
    if report is None:
        raise HTTPException(
            status_code=500,
            detail="VRT report archival failed before a recoverable report was created.",
        )
    payload = {"id": str(report.id), "title": report.title, "status": report.status}
    if report.status == ReportStatus.COMPLETED.value:
        from app.services.report_service import report_has_vrt_archive_trust

        if not report_has_vrt_archive_trust(report.content_data):
            raise HTTPException(status_code=409, detail="旧报告的测量来源未核实，归档尚未重建。")
        return payload
    if report.status == ReportStatus.GENERATING.value:
        raise HTTPException(
            status_code=409,
            detail=(
                "VRT archive remains generating, but writer liveness cannot be proven. "
                "Automatic retry is blocked; inspect the existing claim before recovery."
            ),
        )
    raise HTTPException(
        status_code=409,
        detail=(
            f"VRT archive remains {report.status}; writer liveness cannot be proven. "
            f"Use /reports/{report.id}/generate to retry."
        ),
    )


async def _archive_execution_report(execution_id: str, db: Session):
    """
    Helper to generate and save execution report to database (Option B+)
    """
    try:
        # DEBUG ENTRY
        logger.info(f"Archiving execution report for {execution_id}")

        # A terminal execution owns one immutable automatic archive.  Only a
        # strict server-written trust marker proves that an existing row was
        # produced by this path; pre-upgrade GUI rows used client-owned KPI
        # payloads and must be rebuilt from the execution instead of reused.
        existing_report = db.query(TestReport).filter(
            TestReport.road_test_execution_id == execution_id
        ).first()
        from app.services.report_service import (
            VRT_ARCHIVE_TRUST_FIELD,
            VRT_ARCHIVE_TRUST_SCHEMA_VERSION,
            report_has_vrt_archive_trust,
        )
        if (
            existing_report is not None
            and report_has_vrt_archive_trust(existing_report.content_data)
        ):
            logger.info(
                "Skipped duplicate VRT archive for execution %s; report %s already exists",
                execution_id,
                existing_report.id,
            )
            return

        # 1. Generate full report (Pydantic model)
        # Note: We temporarily allow report generation even if status is just changed
        report_data: ExecutionReport = await _generate_execution_report(execution_id, db)
        
        # 2. Convert to JSON dict
        content_data = report_data.model_dump(mode="json")
        content_data[VRT_ARCHIVE_TRUST_FIELD] = VRT_ARCHIVE_TRUST_SCHEMA_VERSION
        
        # 3. Create TestReport entry
        from datetime import datetime, timezone
        import uuid
        
        report_kind = "数字孪生模拟报告" if report_data.mode == TestMode.DIGITAL_TWIN else "虚拟路测报告"
        report_title = f"{report_kind}: {report_data.scenario_name}"
        legacy_content_snapshot = None
        if existing_report is not None:
            from copy import deepcopy

            # Do not mutate the legacy row before acquiring ReportService's
            # writer claim.  The authoritative payload is supplied only to
            # the claim winner, which then replaces the old content/file.
            target_report = existing_report
            legacy_content_snapshot = deepcopy(existing_report.content_data)
            logger.info(
                "Rebuilding untrusted historical VRT report %s for execution %s",
                target_report.id,
                execution_id,
            )
        else:
            logger.info(f"Creating new archived report for execution {execution_id}")
            new_report = TestReport(
                id=uuid.uuid4(),
                title=report_title,
                description=f"Mode: {report_data.mode}, Result: {report_data.overall_result}",
                report_type=ReportType.SINGLE_EXECUTION,
                format=ReportFormat.PDF,
                # This is only a recoverable input snapshot until ReportService
                # atomically owns the writer claim and publishes the PDF.  A
                # crash before that claim must not leave a completed report with
                # no artifact.
                status=ReportStatus.PENDING,
                generated_by="System (Auto-Archive)",
                generated_at=datetime.now(timezone.utc),
                content_data=content_data,
                road_test_execution_id=execution_id,
                # Metadata
                notes=report_data.notes,
                tags=["VRT", report_data.mode.value, report_data.overall_result]
            )
            db.add(new_report)
            try:
                db.commit()
                target_report = new_report
            except IntegrityError:
                # A concurrent first archive inserted the unique execution row
                # while this request prepared its local snapshot.  This request
                # is the insert loser and must exit: retrying the generation claim
                # could overwrite the winner after it has already completed.
                db.rollback()
                target_report = db.query(TestReport).filter(
                    TestReport.road_test_execution_id == execution_id
                ).first()
                if target_report is None:
                    raise
                logger.info(
                    "Skipped duplicate first VRT archive; report %s already owns execution %s",
                    target_report.id,
                    execution_id,
                )
                return

        logger.info("Prepared VRT report archive for %s", execution_id)

        # Trigger PDF generation immediately (for user convenience)
        from app.services.report_service import (
            ReportGenerationConflict,
            ReportService,
        )
        try:
            target_report_id = target_report.id if target_report else None
            logger.info(f"Triggering auto-generation of PDF for report {target_report_id}")
            service = ReportService()
            if target_report_id:
                # Pass content_data directly to bypass DB read lag/issues
                generation_kwargs = {
                    "content_data_override": content_data,
                    "vrt_archive_metadata_override": {
                        "title": report_title,
                        "description": (
                            f"Mode: {report_data.mode}, "
                            f"Result: {report_data.overall_result}"
                        ),
                        "notes": report_data.notes,
                        "tags": [
                            "VRT",
                            report_data.mode.value,
                            report_data.overall_result,
                        ],
                    },
                }
                if existing_report is not None:
                    generation_kwargs["expected_content_data"] = (
                        legacy_content_snapshot
                    )
                service.generate_report(db, target_report_id, **generation_kwargs)
        except ReportGenerationConflict as pdf_err:
            # This request never owned the writer claim.  Do not race a later
            # winner state (including completed/failed) with any retry reset.
            db.rollback()
            logger.warning(
                "Skipped VRT archive generation for report %s: %s",
                target_report.id if target_report else None,
                pdf_err,
            )
        except Exception as pdf_err:
            logger.error(f"Failed to auto-generate PDF: {pdf_err}")
            # Preserve another request's active generation claim.  For an
            # ordinary generation failure ReportService has already moved the
            # row out of generating, so this conditional update retains the
            # existing retryable pending behavior.
            if target_report:
                reset = db.query(TestReport).filter(
                    TestReport.id == target_report.id,
                    TestReport.status != ReportStatus.GENERATING.value,
                ).update(
                    {
                        TestReport.status: ReportStatus.PENDING.value,
                        TestReport.error_message: f"PDF generation failed: {str(pdf_err)}",
                    },
                    synchronize_session=False,
                )
                if reset == 1:
                    db.commit()
                    logger.info(
                        "Report %s marked as PENDING due to PDF generation failure",
                        target_report.id,
                    )
                else:
                    db.rollback()
                    logger.warning(
                        "Preserved active generation claim for report %s after "
                        "archive generation conflict",
                        target_report.id,
                    )
        
        
    except Exception as e:
        logger.error(f"Failed to archive VRT report for {execution_id}: {e}")
        logger.error(traceback.format_exc())
        # Don't raise exception to client, just log error (background task style)

def get_attr_or_item(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to get value from object or dict safely"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

async def _generate_execution_report(execution_id: str, db: Session) -> ExecutionReport:
    """Internal function to generate report"""
    try:
        row = vrt_execution_service.get(db, execution_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

        execution = vrt_execution_service.to_test_execution(row)

        if execution.status not in [ExecutionStatus.COMPLETED, ExecutionStatus.STOPPED, ExecutionStatus.FAILED]:
            raise HTTPException(
                status_code=400,
                detail=f"Report only available for completed executions. Current status: {execution.status}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking execution status: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking status: {str(e)}")

    try:
        scenario = _execution_scenario(db, row)
        scenario_name = get_attr_or_item(scenario, 'name', execution.scenario_id)
    except Exception as e:
        logger.error(f"Error retrieving scenario: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving scenario: {str(e)}")

    # Build scenario info
    scenario_info = None
    network_info = None
    environment_info = None
    route_info = None
    base_stations_info = []
    step_configs = []

    try:
        if scenario:
            # Scenario basic info
            scenario_info = ScenarioInfo(
                id=get_attr_or_item(scenario, 'id', ''),
                name=get_attr_or_item(scenario, 'name', ''),
                category=str(get_attr_or_item(scenario, 'category', '')),
                description=get_attr_or_item(scenario, 'description'),
                tags=get_attr_or_item(scenario, 'tags', [])
            )

            # Network configuration
            net = get_attr_or_item(scenario, 'network')
            if net:
                network_info = NetworkInfo(
                    type=str(get_attr_or_item(net, 'type', '')),
                    band=get_attr_or_item(net, 'band', ''),
                    bandwidth_mhz=get_attr_or_item(net, 'bandwidth_mhz', 0.0),
                    duplex_mode=get_attr_or_item(net, 'duplex_mode', ''),
                    scs_khz=get_attr_or_item(net, 'scs_khz')
                )

            # Environment info
            env = get_attr_or_item(scenario, 'environment')
            if env:
                environment_info = EnvironmentInfo(
                    type=str(get_attr_or_item(env, 'type', '')),
                    channel_model=str(_env_channel_model_str(env)),
                    weather=str(get_attr_or_item(env, 'weather', '')),
                    traffic_density=str(get_attr_or_item(env, 'traffic_density', ''))
                )

            # Route info
            rt = get_attr_or_item(scenario, 'route')
            if rt:
                duration = get_attr_or_item(rt, 'duration_s', 0)
                distance = get_attr_or_item(rt, 'total_distance_m', 0)
                waypoints = get_attr_or_item(rt, 'waypoints', [])
                
                avg_speed = None
                if duration and duration > 0 and distance:
                    avg_speed = round((distance / 1000) / (duration / 3600), 1)
                    
                route_info = RouteInfo(
                    duration_s=duration,
                    distance_m=distance,
                    waypoint_count=len(waypoints) if waypoints else 0,
                    avg_speed_kmh=avg_speed
                )

            # Base stations
            base_stations = get_attr_or_item(scenario, 'base_stations')
            if base_stations:
                for bs in base_stations:
                    base_stations_info.append(BaseStationInfo(
                        bs_id=get_attr_or_item(bs, 'bs_id', ''),
                        name=get_attr_or_item(bs, 'name', ''),
                        tx_power_dbm=get_attr_or_item(bs, 'tx_power_dbm', 0.0),
                        antenna_config=get_attr_or_item(bs, 'antenna_config', ''),
                        antenna_height_m=get_attr_or_item(bs, 'antenna_height_m', 0.0)
                    ))

            # Step configurations
            step_cfg = get_attr_or_item(scenario, 'step_configuration')
            if step_cfg:
                step_mapping = {
                    'chamber_init': ('暗室初始化', get_attr_or_item(step_cfg, 'chamber_init')),
                    'network_config': ('网络配置', get_attr_or_item(step_cfg, 'network_config')),
                    'base_station_setup': ('基站配置', get_attr_or_item(step_cfg, 'base_station_setup')),
                    'ota_mapper': ('OTA映射器', get_attr_or_item(step_cfg, 'ota_mapper')),
                    'route_execution': ('路径执行', get_attr_or_item(step_cfg, 'route_execution')),
                    'kpi_validation': ('KPI验证', get_attr_or_item(step_cfg, 'kpi_validation')),
                    'report_generation': ('报告生成', get_attr_or_item(step_cfg, 'report_generation')),
                }
                for step_key, (step_name, step_data) in step_mapping.items():
                    if step_data:
                        # Safe conversion to dict
                        if hasattr(step_data, 'model_dump'):
                            params = step_data.model_dump()
                        elif hasattr(step_data, 'dict'):
                            params = step_data.dict()
                        elif isinstance(step_data, dict):
                            params = step_data
                        else:
                            try:
                                params = dict(step_data)
                            except:
                                params = {}
                                
                        step_configs.append(StepConfigInfo(
                            step_name=step_name,
                            enabled=True,
                            parameters=params
                        ))
    except Exception as e:
        logger.error(f"Error processing scenario details: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing scenario details: {str(e)}")


    # Pull real metrics + phases from DB (Phase 2.4c)
    kpi_samples_orm = vrt_execution_service.query_kpi_samples(db, execution_id)
    metrics_obj = vrt_execution_service.to_test_metrics(row, kpi_samples_orm)
    observations = metrics_obj.observations
    time_series_data = []
    trajectory_data = []
    network_config_detail = None
    base_station_config_detail = None
    digital_twin_config = None
    custom_config_highlights = []

    try:
        phases = []
        events = []
        kpi_summary = throughput_summary([item.model_dump() for item in observations])

    except Exception as e:
        logger.error(f"Error generating metrics/phases: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error generating metrics: {str(e)}")

    try:
        # Extract detailed configurations from scenario
        if scenario:
            step_cfg = get_attr_or_item(scenario, 'step_configuration')
            if step_cfg:
                # Network config detail
                nc = get_attr_or_item(step_cfg, 'network_config')
                if nc:
                    auth = get_attr_or_item(nc, 'authentication')
                    qos = get_attr_or_item(nc, 'qos')
                    pdu = get_attr_or_item(nc, 'pdu_session')
                    apps = get_attr_or_item(nc, 'applications')
                    app_tests = get_attr_or_item(apps, 'tests') if apps else None
                    
                    network_config_detail = NetworkConfigDetail(
                        authentication=auth.model_dump() if hasattr(auth, 'model_dump') else (auth if isinstance(auth, dict) else None),
                        qos=qos.model_dump() if hasattr(qos, 'model_dump') else (qos if isinstance(qos, dict) else None),
                        pdu_session=pdu.model_dump() if hasattr(pdu, 'model_dump') else (pdu if isinstance(pdu, dict) else None),
                        applications=[getattr(app, 'type', app.get('type') if isinstance(app, dict) else str(app)) for app in app_tests] if app_tests else None
                    )

                # Base station config detail
                bs_cfg = get_attr_or_item(step_cfg, 'base_station_setup')
                if bs_cfg:
                    rf = get_attr_or_item(bs_cfg, 'rf')
                    ant = get_attr_or_item(bs_cfg, 'antenna')
                    beam = get_attr_or_item(bs_cfg, 'beamforming')
                    ho = get_attr_or_item(bs_cfg, 'handover')
                    
                    base_station_config_detail = BaseStationConfigDetail(
                        rf=rf.model_dump() if hasattr(rf, 'model_dump') else (rf if isinstance(rf, dict) else None),
                        antenna=ant.model_dump() if hasattr(ant, 'model_dump') else (ant if isinstance(ant, dict) else None),
                        beamforming=beam.model_dump() if hasattr(beam, 'model_dump') else (beam if isinstance(beam, dict) else None),
                        handover=ho.model_dump() if hasattr(ho, 'model_dump') else (ho if isinstance(ho, dict) else None)
                    )

                # Digital twin config
                env_cfg = get_attr_or_item(step_cfg, 'environment_setup')
                if env_cfg:
                    cm = get_attr_or_item(env_cfg, 'channel_model')
                    rt = get_attr_or_item(env_cfg, 'ray_tracing')
                    wx = get_attr_or_item(env_cfg, 'weather')
                    inf = get_attr_or_item(env_cfg, 'interference')
                    
                    digital_twin_config = DigitalTwinConfig(
                        channel_model=cm.model_dump() if hasattr(cm, 'model_dump') else (cm if isinstance(cm, dict) else None),
                        ray_tracing=rt.model_dump() if hasattr(rt, 'model_dump') else (rt if isinstance(rt, dict) else None),
                        weather=wx.model_dump() if hasattr(wx, 'model_dump') else (wx if isinstance(wx, dict) else None),
                        interference=inf.model_dump() if hasattr(inf, 'model_dump') else (inf if isinstance(inf, dict) else None)
                    )

        # Identify custom scenario highlights
        if scenario:
            src = get_attr_or_item(scenario, 'source')
            if str(src) == 'custom':
                custom_config_highlights.append(CustomConfigHighlight(
                    category="场景来源",
                    label="定制场景",
                    value=get_attr_or_item(scenario, 'name', 'Custom'),
                    description="用户自定义的测试场景"
                ))

            # Check for special configurations
            step_cfg = get_attr_or_item(scenario, 'step_configuration')
            if step_cfg:
                env_cfg = get_attr_or_item(step_cfg, 'environment_setup')
                if env_cfg:
                    inf = get_attr_or_item(env_cfg, 'interference')
                    if inf and get_attr_or_item(inf, 'enabled', False):
                        custom_config_highlights.append(CustomConfigHighlight(
                            category="干扰配置",
                            label="干扰源",
                            value="已启用",
                            description="场景包含自定义干扰源"
                        ))
                    
                    rt = get_attr_or_item(env_cfg, 'ray_tracing')
                    if rt and get_attr_or_item(rt, 'enabled', False):
                        custom_config_highlights.append(CustomConfigHighlight(
                            category="信道模型",
                            label="射线追踪",
                            value="已启用",
                            description="使用确定性射线追踪信道模型"
                        ))

        # Build trajectory from route waypoints if no real trajectory
        if execution.mode != TestMode.CONDUCTED and not trajectory_data and scenario:
            route = get_attr_or_item(scenario, 'route')
            if route:
                waypoints = get_attr_or_item(route, 'waypoints', [])
                for wp in waypoints:
                    # Handle wp.position whether it's a dict (Pydantic V2 dump) or object
                    pos = get_attr_or_item(wp, 'position')
                    if pos:
                        # Try dict access first, then attribute access
                        lat = pos.get('lat') if isinstance(pos, dict) else getattr(pos, 'lat', None)
                        lon = pos.get('lon') if isinstance(pos, dict) else getattr(pos, 'lon', None)
                        alt = pos.get('alt') if isinstance(pos, dict) else getattr(pos, 'alt', getattr(pos, 'altitude_m', None))
                        
                        if lat is not None and lon is not None:
                            trajectory_data.append(TrajectoryPoint(
                                lat=lat,
                                lon=lon,
                                alt=alt,
                                time_s=get_attr_or_item(wp, 'time_s')
                            ))
    except Exception as e:
        logger.error(f"Error processing detailed configs: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing details: {str(e)}")

    try:
        pass_rate, overall_result = compute_overall_result(kpi_summary, execution.status)

        report = ExecutionReport(
            execution_id=execution_id,
            scenario_name=scenario_name,
            mode=execution.mode,
            status=execution.status,
            # Scenario details
            scenario=scenario_info,
            network=network_info,
            environment=environment_info,
            route=route_info,
            base_stations=base_stations_info,
            step_configs=step_configs,
            # Timing
            start_time=execution.start_time,
            end_time=execution.end_time,
            duration_s=execution.duration_s,
            # Results
            conducted_setup=row.vrt_conducted_setup if row.mode == "conducted" else None,
            simulation_input=row.vrt_twin_input,
            simulation_timeline=twin_playback.timeline(row, _utcnow()) if row.vrt_twin_input else None,
            observations=observations,
            phases=phases,
            kpi_summary=kpi_summary,
            overall_result=overall_result,
            # ⚠️ 合格率可能是 None（一条 KPI 都没有可信判决时）——
            #    `round(None, 1)` 会 TypeError。上一轮我查了 pdf_generator 与
            #    report_service 两处下游，**漏了本文件自己这一处**（外审 P1）。
            pass_rate=None if pass_rate is None else round(pass_rate, 1),
            events=events,
            # NEW: Time series and trajectory
            time_series=time_series_data,
            trajectory=trajectory_data,
            # NEW: Detailed configs
            network_config_detail=network_config_detail,
            base_station_config_detail=base_station_config_detail,
            digital_twin_config=digital_twin_config,
            custom_config_highlights=custom_config_highlights,
            # NEW: Logs (from execution_logs JSONB column)
            logs=row.execution_logs or [],
            # Metadata
            generated_at=datetime.now(),
            notes=execution.notes
        )

        logger.info(f"Generated report for execution: {execution_id}")
        return report
    except ValidationError as e:
        logger.error(f"Report validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Report validation failed: {str(e)}")
    except Exception as e:
        logger.error(f"Final report assembly error: {e}")
        raise HTTPException(status_code=500, detail=f"Final report assembly error: {str(e)}")


@router.websocket("/executions/{execution_id}/stream")
async def stream_execution_metrics(websocket: WebSocket, execution_id: str):
    """
    WebSocket stream for real-time metrics

    Client sends: {"subscribe": ["metrics", "events", "logs"]}
    Server sends: {"type": "metrics", "data": {...}}
    """
    # Validate execution_id exists before accepting connection.
    # FastAPI's Depends(get_db) doesn't apply to WebSockets, so we create a
    # short-lived session manually for the validation + initial log write.
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        if vrt_execution_service.get(db, execution_id) is None:
            await websocket.close(code=4004, reason=f"Execution {execution_id} not found")
            logger.warning(f"WebSocket connection rejected: Execution {execution_id} not found")
            return
        _log_event(db, execution_id, "Frontend monitor connected", "INFO")
    finally:
        db.close()

    await websocket.accept()
    logger.info(f"WebSocket connected for execution: {execution_id}")

    try:
        # Receive subscription request
        data = await websocket.receive_json()
        subscription = StreamSubscription(**data)

        logger.info(f"Subscription: {subscription.channels}")

        import asyncio

        while True:
            with SessionLocal() as session:
                row = vrt_execution_service.get(session, execution_id)
                if row is None:
                    await websocket.close(code=4004)
                    return
                status = vrt_execution_service.to_test_status(row).model_dump(mode="json")
                messages = []
                if "metrics" in subscription.channels:
                    samples = vrt_execution_service.query_kpi_samples(session, execution_id)
                    metrics = vrt_execution_service.to_test_metrics(row, samples)
                    messages.append(("metrics", metrics.model_dump(mode="json")))
                if "events" in subscription.channels or "logs" in subscription.channels:
                    messages.append(("status", {"status": status, "logs": row.execution_logs or []}))
            for kind, payload in messages:
                message = MetricsStreamMessage(execution_id=execution_id, timestamp=datetime.now(),
                                               message_type=kind, data=payload)
                await websocket.send_json(message.model_dump(mode="json"))

            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for execution: {execution_id}")
    except Exception as e:
        logger.error(f"WebSocket error for execution {execution_id}: {e}")
        await websocket.close()


# ===== System Information =====

@router.get("/capabilities", response_model=RoadTestAvailability)
async def get_capabilities():
    """
    Get system capabilities for each test mode
    """
    from app.services.instrument_hal_service import get_hal_service, is_mock_driver

    drivers = get_hal_service().drivers
    simulated = all(is_mock_driver(drivers.get(key)) for key in ("baseStation", "channelEmulator"))
    real = real_driver_pair(drivers)
    return {
        "digital_twin": {
            "available": True,
            "max_bandwidth_mhz": 100,
            "max_mimo_order": "4x4",
            "acceleration_factor": 10.0
        },
        "conducted": {
            "available": simulated or real,
            "simulated_available": simulated,
            "real_available": real,
            "requires_preparation": True,
            "max_bandwidth_mhz": None,
            "max_mimo_order": "4x2",
            "requires_topology": True
        },
        "ota": {
            "available": False,  # Requires MPAC
            "max_bandwidth_mhz": 100,
            "max_mimo_order": "4x4",
            "requires_mpac": True
        }
    }
