"""
Virtual Road Test API

REST API endpoints for virtual road test scenarios, topologies, and executions
"""

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from typing import List, Optional, Any
import logging
import traceback

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
    PhaseResult,
    KPISummary,
    ScenarioInfo,
    NetworkInfo,
    EnvironmentInfo,
    RouteInfo,
    BaseStationInfo,
    StepConfigInfo,
    # Metrics submission models
    TimeSeriesPoint,
    ExecutionMetricsSubmit,
    # Detailed config models
    NetworkConfigDetail,
    BaseStationConfigDetail,
    DigitalTwinConfig,
    CustomConfigHighlight,
    TrajectoryPoint,
)
from app.data.scenario_library import (
    get_all_scenarios,
    get_scenario_by_id,
    get_scenarios_by_category,
)

from pydantic import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/road-test", tags=["Virtual Road Test"])

# In-memory storage (replace with database in production)
# Persistence: Save to JSON file
import json
import os
DATA_DIR = "data"
SCENARIOS_FILE = os.path.join(DATA_DIR, "custom_scenarios.json")

def load_scenarios():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if os.path.exists(SCENARIOS_FILE):
        try:
            with open(SCENARIOS_FILE, "r") as f:
                data = json.load(f)
                return {k: RoadTestScenario(**v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"Failed to load scenarios: {e}")
    return {}

def save_scenarios():
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        data = {k: v.model_dump(mode="json") for k, v in _custom_scenarios.items()}
        with open(SCENARIOS_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to save scenarios: {e}")

_custom_scenarios: dict[str, RoadTestScenario] = load_scenarios()
_topologies: dict[str, NetworkTopology] = {}
_executions: dict[str, TestExecution] = {}
_execution_status: dict[str, TestStatus] = {}
_execution_metrics: dict[str, TestMetrics] = {}
_execution_phases: dict[str, List[PhaseResult]] = {}  # Store submitted phase results


def _compute_kpi_summary_from_samples(kpi_samples: List[KPIMetrics]) -> List[KPISummary]:
    """Compute KPI summary statistics from raw samples."""
    import statistics

    result = []

    # Helper to compute stats for a metric
    def compute_stats(values: List[float], name: str, unit: str, target: float = None) -> KPISummary:
        if not values:
            return None
        mean_val = statistics.mean(values)
        return KPISummary(
            name=name,
            unit=unit,
            mean=round(mean_val, 2),
            min=round(min(values), 2),
            max=round(max(values), 2),
            std=round(statistics.stdev(values), 2) if len(values) > 1 else 0,
            target=target,
            passed=mean_val >= target if target and name not in ["端到端延迟", "BLER"] else (mean_val <= target if target else None)
        )

    # Extract values for each metric
    dl_values = [s.dl_throughput_mbps for s in kpi_samples if s.dl_throughput_mbps is not None]
    ul_values = [s.ul_throughput_mbps for s in kpi_samples if s.ul_throughput_mbps is not None]
    latency_values = [s.latency_ms for s in kpi_samples if s.latency_ms is not None]
    rsrp_values = [s.rsrp_dbm for s in kpi_samples if s.rsrp_dbm is not None]
    sinr_values = [s.sinr_db for s in kpi_samples if s.sinr_db is not None]

    if dl_values:
        result.append(compute_stats(dl_values, "下行吞吐量", "Mbps", 100.0))
    if ul_values:
        result.append(compute_stats(ul_values, "上行吞吐量", "Mbps", 40.0))
    if latency_values:
        kpi = compute_stats(latency_values, "端到端延迟", "ms", 20.0)
        if kpi:
            kpi.passed = kpi.mean <= kpi.target if kpi.target else None
            result.append(kpi)
    if rsrp_values:
        kpi = compute_stats(rsrp_values, "RSRP", "dBm", -90.0)
        if kpi:
            kpi.passed = kpi.mean >= kpi.target if kpi.target else None
            result.append(kpi)
    if sinr_values:
        result.append(compute_stats(sinr_values, "SINR", "dB", 10.0))

    return [r for r in result if r is not None]


# ===== Scenario Management =====

@router.get("/scenarios", response_model=List[ScenarioSummary])
async def list_scenarios(
    category: Optional[ScenarioCategory] = None,
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    source: Optional[str] = Query(None, description="standard or custom")
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

    # Add custom scenarios
    scenarios.extend(_custom_scenarios.values())

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

            summaries.append(ScenarioSummary(
                id=s.id,
                name=s.name,
                category=s.category,
                source=s.source,
                tags=s.tags,
                description=s.description,
                duration_s=s.route.duration_s if s.route else 0,
                distance_m=s.route.total_distance_m if s.route else 0,
                created_at=s.created_at,
                author=s.author,
                step_configuration=step_config,
                # Extended fields
                network_type=s.network.type.value if s.network else None,
                band=s.network.band if s.network else None,
                bandwidth_mhz=s.network.bandwidth_mhz if s.network else None,
                channel_model=s.environment.channel_model.value if s.environment else None,
                avg_speed_kmh=avg_speed,
            ))
        except Exception as e:
            logger.error(f"Error creating summary for scenario {s.id}: {e}")
            # Create a minimal summary to avoid breaking the list
            summaries.append(ScenarioSummary(
                id=s.id,
                name=s.name,
                category=s.category,
                source=s.source,
                tags=s.tags or [],
                description=s.description,
                duration_s=0,
                distance_m=0,
                created_at=s.created_at,
                author=s.author,
            ))

    return summaries


@router.get("/scenarios/{scenario_id}", response_model=RoadTestScenario)
async def get_scenario(scenario_id: str):
    """
    Get detailed scenario configuration
    """
    # Check standard scenarios
    scenario = get_scenario_by_id(scenario_id)
    if scenario:
        return scenario

    # Check custom scenarios
    if scenario_id in _custom_scenarios:
        return _custom_scenarios[scenario_id]

    raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")


@router.post("/scenarios", response_model=RoadTestScenario, status_code=201)
async def create_scenario(scenario_create: ScenarioCreate):
    """
    Create a new custom scenario
    """
    # Generate scenario ID
    scenario_id = f"custom-{len(_custom_scenarios) + 1:04d}"

    # Create scenario
    from datetime import datetime
    scenario = RoadTestScenario(
        id=scenario_id,
        source=ScenarioCategory.CUSTOM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        **scenario_create.model_dump()
    )

    _custom_scenarios[scenario_id] = scenario
    save_scenarios()

    logger.info(f"Created custom scenario: {scenario_id}")
    return scenario


@router.put("/scenarios/{scenario_id}", response_model=RoadTestScenario)
async def update_scenario(scenario_id: str, scenario_update: ScenarioUpdate):
    """
    Update a scenario. For standard scenarios, creates a custom copy.
    """
    from datetime import datetime

    # Check if it's a custom scenario
    if scenario_id in _custom_scenarios:
        scenario = _custom_scenarios[scenario_id]

        # Update fields
        update_data = scenario_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(scenario, field, value)

        scenario.updated_at = datetime.now()
        save_scenarios()
        logger.info(f"Updated custom scenario: {scenario_id}")
        return scenario

    # Check if it's a standard scenario - create a custom copy
    standard_scenario = get_scenario_by_id(scenario_id)
    if standard_scenario:
        # Create a new custom scenario based on the standard one
        new_id = f"custom-{len(_custom_scenarios) + 1:04d}"

        # Copy standard scenario data
        scenario_data = standard_scenario.model_dump()
        scenario_data['id'] = new_id
        scenario_data['source'] = ScenarioSource.CUSTOM
        scenario_data['created_at'] = datetime.now()
        scenario_data['updated_at'] = datetime.now()

        # Apply updates
        update_data = scenario_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                scenario_data[field] = value

        # Create new scenario
        new_scenario = RoadTestScenario(**scenario_data)
        _custom_scenarios[new_id] = new_scenario
        save_scenarios()

        logger.info(f"Created custom scenario {new_id} from standard scenario {scenario_id}")
        return new_scenario

    raise HTTPException(
        status_code=404,
        detail=f"Scenario '{scenario_id}' not found"
    )


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(scenario_id: str):
    """
    Delete a custom scenario (standard scenarios cannot be deleted)
    """
    if scenario_id not in _custom_scenarios:
        raise HTTPException(
            status_code=404,
            detail=f"Custom scenario '{scenario_id}' not found or is a standard scenario"
        )

    del _custom_scenarios[scenario_id]
    save_scenarios()
    logger.info(f"Deleted scenario: {scenario_id}")
    return JSONResponse(status_code=204, content=None)


# ===== Topology Management =====

@router.get("/topologies", response_model=List[TopologySummary])
async def list_topologies():
    """
    List all network topologies
    """
    summaries = [
        TopologySummary(
            id=t.id,
            name=t.name,
            topology_type=t.topology_type,
            description=t.description,
            is_validated=t.is_validated,
            devices_count=3,  # BS + CE + DUT
            connections_count=len(t.connections),
            created_at=t.created_at,
            author=t.author
        )
        for t in _topologies.values()
    ]
    return summaries


@router.get("/topologies/{topology_id}", response_model=NetworkTopology)
async def get_topology(topology_id: str):
    """
    Get detailed topology configuration
    """
    if topology_id not in _topologies:
        raise HTTPException(status_code=404, detail=f"Topology '{topology_id}' not found")

    return _topologies[topology_id]


@router.post("/topologies", response_model=NetworkTopology, status_code=201)
async def create_topology(topology_create: TopologyCreate):
    """
    Create a new network topology
    """
    # Generate topology ID
    topology_id = f"topology-{len(_topologies) + 1:04d}"

    # Create topology
    from datetime import datetime
    topology = NetworkTopology(
        id=topology_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        **topology_create.model_dump()
    )

    _topologies[topology_id] = topology

    logger.info(f"Created topology: {topology_id}")
    return topology


@router.post("/topologies/{topology_id}/validate", response_model=TopologyValidationResult)
async def validate_topology(topology_id: str):
    """
    Validate topology configuration

    Checks:
    - Port conflicts
    - Connection validity
    - Device compatibility
    - RF link budget
    """
    if topology_id not in _topologies:
        raise HTTPException(status_code=404, detail=f"Topology '{topology_id}' not found")

    topology = _topologies[topology_id]

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

    # Update topology validation status
    topology.is_validated = len(errors) == 0
    topology.validation_errors = errors

    result = TopologyValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        details={
            "total_connections": len(topology.connections),
            "total_loss_db": sum(conn.loss_db for conn in topology.connections)
        }
    )

    logger.info(f"Validated topology {topology_id}: {'PASS' if result.is_valid else 'FAIL'}")
    return result


# ===== Test Execution =====

@router.get("/executions", response_model=List[ExecutionSummary])
async def list_executions(
    mode: Optional[TestMode] = None,
    status: Optional[ExecutionStatus] = None
):
    """
    List all test executions
    """
    executions = list(_executions.values())

    # Filter by mode
    if mode:
        executions = [e for e in executions if e.mode == mode]

    # Filter by status
    if status:
        executions = [e for e in executions if e.status == status]

    summaries = [
        ExecutionSummary(
            execution_id=e.execution_id,
            mode=e.mode,
            status=e.status,
            scenario_name=get_scenario_by_id(e.scenario_id).name if get_scenario_by_id(e.scenario_id) else e.scenario_id,
            start_time=e.start_time,
            duration_s=e.duration_s,
            progress_percent=_execution_status.get(e.execution_id, TestStatus(
                execution_id=e.execution_id,
                status=e.status,
                progress_percent=0,
                elapsed_time_s=0
            )).progress_percent,
            created_by=e.created_by
        )
        for e in executions
    ]

    return summaries


@router.post("/executions", response_model=TestExecution, status_code=201)
async def create_execution(execution_create: ExecutionCreate):
    """
    Create a new test execution

    Initializes the test executor based on the selected mode:
    - digital_twin: Fully simulated
    - conducted: Requires topology_id
    - ota: Uses MPAC chamber
    """
    # Validate scenario exists
    scenario = get_scenario_by_id(execution_create.scenario_id)
    if not scenario and execution_create.scenario_id not in _custom_scenarios:
        raise HTTPException(status_code=404, detail=f"Scenario '{execution_create.scenario_id}' not found")

    # Validate topology for conducted mode
    if execution_create.mode == TestMode.CONDUCTED:
        if not execution_create.topology_id:
            raise HTTPException(status_code=400, detail="Topology ID required for conducted mode")
        if execution_create.topology_id not in _topologies:
            raise HTTPException(status_code=404, detail=f"Topology '{execution_create.topology_id}' not found")

    # Generate execution ID
    import uuid
    execution_id = f"exec-{uuid.uuid4().hex[:12]}"

    # Create execution
    from datetime import datetime
    execution = TestExecution(
        execution_id=execution_id,
        mode=execution_create.mode,
        status=ExecutionStatus.IDLE,
        scenario_id=execution_create.scenario_id,
        topology_id=execution_create.topology_id,
        config=execution_create.config,
        notes=execution_create.notes
    )

    _executions[execution_id] = execution

    # Initialize status
    _execution_status[execution_id] = TestStatus(
        execution_id=execution_id,
        status=ExecutionStatus.IDLE,
        progress_percent=0,
        elapsed_time_s=0
    )

    logger.info(f"Created execution: {execution_id} (mode={execution_create.mode})")
    return execution


@router.get("/executions/{execution_id}", response_model=TestExecution)
async def get_execution(execution_id: str):
    """
    Get execution details
    """
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    return _executions[execution_id]


@router.post("/executions/{execution_id}/control")
async def control_execution(execution_id: str, control: ExecutionControl):
    """
    Control execution (start/pause/resume/stop)
    """
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    execution = _executions[execution_id]
    status = _execution_status[execution_id]

    # Handle control actions
    if control.action == "start":
        if execution.status != ExecutionStatus.IDLE:
            raise HTTPException(status_code=400, detail="Execution already started")

        execution.status = ExecutionStatus.RUNNING
        status.status = ExecutionStatus.RUNNING

        from datetime import datetime
        execution.start_time = datetime.now()

        logger.info(f"Started execution: {execution_id}")

    elif control.action == "pause":
        if execution.status != ExecutionStatus.RUNNING:
            raise HTTPException(status_code=400, detail="Execution not running")

        execution.status = ExecutionStatus.PAUSED
        status.status = ExecutionStatus.PAUSED

        logger.info(f"Paused execution: {execution_id}")

    elif control.action == "resume":
        if execution.status != ExecutionStatus.PAUSED:
            raise HTTPException(status_code=400, detail="Execution not paused")

        execution.status = ExecutionStatus.RUNNING
        status.status = ExecutionStatus.RUNNING

        logger.info(f"Resumed execution: {execution_id}")

    elif control.action == "stop":
        if execution.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.STOPPED]:
            raise HTTPException(status_code=400, detail="Execution already finished")

        execution.status = ExecutionStatus.STOPPED
        status.status = ExecutionStatus.STOPPED

        from datetime import datetime
        execution.end_time = datetime.now()
        if execution.start_time:
            execution.duration_s = (execution.end_time - execution.start_time).total_seconds()

        logger.info(f"Stopped execution: {execution_id}")

    elif control.action == "complete":
        if execution.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.STOPPED]:
            raise HTTPException(status_code=400, detail="Execution already finished")

        execution.status = ExecutionStatus.COMPLETED
        status.status = ExecutionStatus.COMPLETED
        status.progress_percent = 100

        from datetime import datetime
        execution.end_time = datetime.now()
        if execution.start_time:
            execution.duration_s = (execution.end_time - execution.start_time).total_seconds()

        logger.info(f"Completed execution: {execution_id}")

    return {"status": "success", "execution_id": execution_id, "action": control.action}


@router.get("/executions/{execution_id}/status", response_model=TestStatus)
async def get_execution_status(execution_id: str):
    """
    Get real-time execution status
    """
    if execution_id not in _execution_status:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    return _execution_status[execution_id]


@router.get("/executions/{execution_id}/metrics", response_model=TestMetrics)
async def get_execution_metrics(execution_id: str):
    """
    Get execution metrics (KPI time series)
    """
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    # Return metrics if available, otherwise empty
    if execution_id in _execution_metrics:
        return _execution_metrics[execution_id]
    else:
        return TestMetrics(
            execution_id=execution_id,
            kpi_samples=[],
            summary={},
            events=[],
            kpi_results={}
        )


@router.post("/executions/{execution_id}/metrics")
async def submit_execution_metrics(execution_id: str, metrics: ExecutionMetricsSubmit):
    """
    Submit execution metrics collected during test run.

    This endpoint receives metrics collected by the frontend during test execution,
    including time series data, phase results, events, and KPI summary.
    """
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    # Convert TimeSeriesPoint to KPIMetrics for storage
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
            event_occurred=p.event
        )
        for p in metrics.time_series
    ]

    # Compute summary statistics from KPI summary
    summary = {}
    for kpi in metrics.kpi_summary:
        summary[kpi.name] = {
            "mean": kpi.mean,
            "min": kpi.min,
            "max": kpi.max,
            "std": kpi.std,
            "target": kpi.target,
            "passed": kpi.passed
        }

    # Store metrics
    _execution_metrics[execution_id] = TestMetrics(
        execution_id=execution_id,
        kpi_samples=kpi_samples,
        summary=summary,
        events=metrics.events,
        kpi_results={}
    )

    # Store phase results
    _execution_phases[execution_id] = metrics.phases

    logger.info(f"Received metrics for execution {execution_id}: {len(metrics.time_series)} points, {len(metrics.phases)} phases")

    return {
        "status": "success",
        "points_received": len(metrics.time_series),
        "phases_received": len(metrics.phases)
    }


@router.get("/executions/{execution_id}/report", response_model=ExecutionReport)
async def get_execution_report(execution_id: str):
    """
    Generate execution report for completed test

    Returns detailed report with scenario info, step configs, phase results, KPI summary, and events.
    """
    import traceback
    try:
        return await _generate_execution_report(execution_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report for {execution_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

def get_attr_or_item(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to get value from object or dict safely"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

async def _generate_execution_report(execution_id: str) -> ExecutionReport:
    """Internal function to generate report"""
    try:
        if execution_id not in _executions:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

        execution = _executions[execution_id]

        # Check if execution is complete
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
        # Get scenario details (check both standard and custom scenarios)
        scenario = get_scenario_by_id(execution.scenario_id)
        if not scenario and execution.scenario_id in _custom_scenarios:
            scenario = _custom_scenarios[execution.scenario_id]
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
                    channel_model=str(get_attr_or_item(env, 'channel_model', '')),
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

    from datetime import datetime, timedelta
    import random

    base_time = execution.start_time or datetime.now()

    # Check if we have real metrics data
    has_real_metrics = (
        execution_id in _execution_metrics and
        len(_execution_metrics[execution_id].kpi_samples) > 0
    )

    # Initialize new fields
    time_series_data = []
    trajectory_data = []
    network_config_detail = None
    base_station_config_detail = None
    digital_twin_config = None
    custom_config_highlights = []

    try:
        if has_real_metrics:
            # ===== Use real collected data =====
            metrics = _execution_metrics[execution_id]

            # Use submitted phases if available
            if execution_id in _execution_phases:
                phases = _execution_phases[execution_id]
            else:
                # Fallback to generating phases from metrics
                phases = [
                    PhaseResult(
                        name="测试执行",
                        status="completed",
                        duration_s=execution.duration_s or 0,
                        start_time=execution.start_time or datetime.now(),
                        end_time=execution.end_time or datetime.now(),
                        notes=None
                    )
                ]

            # Build KPI summary from real metrics
            kpi_summary = []
            for name, stats in metrics.summary.items():
                kpi_summary.append(KPISummary(
                    name=name,
                    unit=stats.get("unit", ""),
                    mean=stats.get("mean", 0),
                    min=stats.get("min", 0),
                    max=stats.get("max", 0),
                    std=stats.get("std"),
                    target=stats.get("target"),
                    passed=stats.get("passed")
                ))

            # If no summary, compute from samples
            if not kpi_summary and metrics.kpi_samples:
                kpi_summary = _compute_kpi_summary_from_samples(metrics.kpi_samples)

            # Use real events
            events = metrics.events

            # Build time series data for charts
            for sample in metrics.kpi_samples:
                time_series_data.append(TimeSeriesPoint(
                    time_s=sample.time_s,
                    position=sample.position,
                    rsrp_dbm=sample.rsrp_dbm,
                    rsrq_db=sample.rsrq_db,
                    sinr_db=sample.sinr_db,
                    dl_throughput_mbps=sample.dl_throughput_mbps,
                    ul_throughput_mbps=sample.ul_throughput_mbps,
                    latency_ms=sample.latency_ms,
                    event=sample.event_occurred
                ))

                # Build trajectory from positions
                if sample.position and 'lat' in sample.position and 'lon' in sample.position:
                    trajectory_data.append(TrajectoryPoint(
                        lat=sample.position['lat'],
                        lon=sample.position['lon'],
                        alt=sample.position.get('alt'),
                        time_s=sample.time_s
                    ))

            logger.info(f"Using real metrics for report: {len(metrics.kpi_samples)} samples")

        else:
            # ===== Fallback to simulated data (backwards compatibility) =====
            phases = []
            phase_names = ["初始化", "配置网络", "启动基站", "连接DUT", "运行测试", "收集数据", "生成报告"]
            current_time = base_time

            for i, name in enumerate(phase_names):
                duration = random.uniform(3, 10)
                end_time = current_time + timedelta(seconds=duration)
                phases.append(PhaseResult(
                    name=name,
                    status="completed" if execution.status == ExecutionStatus.COMPLETED else ("failed" if i == len(phase_names) - 1 else "completed"),
                    duration_s=round(duration, 2),
                    start_time=current_time,
                    end_time=end_time,
                    notes=None
                ))
                current_time = end_time

            # Generate KPI summary (simulated)
            kpi_summary = [
                KPISummary(name="下行吞吐量", unit="Mbps", mean=round(random.uniform(80, 120), 1),
                        min=round(random.uniform(40, 60), 1), max=round(random.uniform(140, 180), 1),
                        std=round(random.uniform(10, 30), 1), target=100.0, passed=True),
                KPISummary(name="上行吞吐量", unit="Mbps", mean=round(random.uniform(30, 50), 1),
                        min=round(random.uniform(15, 25), 1), max=round(random.uniform(60, 80), 1),
                        std=round(random.uniform(5, 15), 1), target=40.0, passed=True),
                KPISummary(name="端到端延迟", unit="ms", mean=round(random.uniform(8, 15), 1),
                        min=round(random.uniform(3, 6), 1), max=round(random.uniform(20, 35), 1),
                        std=round(random.uniform(2, 5), 1), target=20.0, passed=True),
                KPISummary(name="RSRP", unit="dBm", mean=round(random.uniform(-85, -75), 1),
                        min=round(random.uniform(-100, -90), 1), max=round(random.uniform(-70, -60), 1),
                        std=round(random.uniform(5, 10), 1), target=-90.0, passed=True),
                KPISummary(name="SINR", unit="dB", mean=round(random.uniform(12, 18), 1),
                        min=round(random.uniform(5, 8), 1), max=round(random.uniform(22, 28), 1),
                        std=round(random.uniform(3, 6), 1), target=10.0, passed=True),
            ]

            # Generate events (simulated)
            events = [
                {"time": (base_time + timedelta(seconds=15)).isoformat(), "type": "handover", "description": "切换到基站 gNB-002"},
                {"time": (base_time + timedelta(seconds=35)).isoformat(), "type": "beam_switch", "description": "波束切换 Beam 3 → Beam 7"},
                {"time": (base_time + timedelta(seconds=50)).isoformat(), "type": "handover", "description": "切换到基站 gNB-003"},
            ]
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
        if not trajectory_data and scenario:
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
        # Calculate pass rate
        passed_kpis = sum(1 for kpi in kpi_summary if kpi.passed)
        pass_rate = (passed_kpis / len(kpi_summary)) * 100 if kpi_summary else 0

        # Determine overall result
        if execution.status == ExecutionStatus.COMPLETED:
            overall_result = "passed" if pass_rate >= 80 else "failed"
        elif execution.status == ExecutionStatus.FAILED:
            overall_result = "failed"
        else:
            overall_result = "incomplete"

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
            phases=phases,
            kpi_summary=kpi_summary,
            overall_result=overall_result,
            pass_rate=round(pass_rate, 1),
            events=events,
            # NEW: Time series and trajectory
            time_series=time_series_data,
            trajectory=trajectory_data,
            # NEW: Detailed configs
            network_config_detail=network_config_detail,
            base_station_config_detail=base_station_config_detail,
            digital_twin_config=digital_twin_config,
            custom_config_highlights=custom_config_highlights,
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
    # Validate execution_id exists before accepting connection
    if execution_id not in _executions:
        await websocket.close(code=4004, reason=f"Execution {execution_id} not found")
        logger.warning(f"WebSocket connection rejected: Execution {execution_id} not found")
        return

    await websocket.accept()

    logger.info(f"WebSocket connected for execution: {execution_id}")

    try:
        # Receive subscription request
        data = await websocket.receive_json()
        subscription = StreamSubscription(**data)

        logger.info(f"Subscription: {subscription.channels}")

        # Mock streaming (replace with actual executor events)
        import asyncio
        from datetime import datetime

        while True:
            # Send mock metrics every second
            if "metrics" in subscription.channels:
                message = MetricsStreamMessage(
                    execution_id=execution_id,
                    timestamp=datetime.now(),
                    message_type="metrics",
                    data={
                        "rsrp_dbm": -85.0,
                        "sinr_db": 15.0,
                        "dl_throughput_mbps": 45.0
                    }
                )
                await websocket.send_json(message.model_dump(mode="json"))

            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for execution: {execution_id}")
    except Exception as e:
        logger.error(f"WebSocket error for execution {execution_id}: {e}")
        await websocket.close()


# ===== System Information =====

@router.get("/capabilities")
async def get_capabilities():
    """
    Get system capabilities for each test mode
    """
    return {
        "digital_twin": {
            "available": True,
            "max_bandwidth_mhz": 100,
            "max_mimo_order": "4x4",
            "acceleration_factor": 10.0
        },
        "conducted": {
            "available": False,  # Requires hardware
            "max_bandwidth_mhz": 100,
            "max_mimo_order": "4x4",
            "requires_topology": True
        },
        "ota": {
            "available": False,  # Requires MPAC
            "max_bandwidth_mhz": 100,
            "max_mimo_order": "4x4",
            "requires_mpac": True
        }
    }