"""
Virtual Road Test API

REST API endpoints for virtual road test scenarios, topologies, and executions
"""

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from typing import List, Optional
import logging

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
    MetricsStreamMessage,
    StreamSubscription,
    TestMode,
    ExecutionStatus,
)
from app.data.scenario_library import (
    get_all_scenarios,
    get_scenario_by_id,
    get_scenarios_by_category,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/road-test", tags=["Virtual Road Test"])

# In-memory storage (replace with database in production)
_custom_scenarios: dict[str, RoadTestScenario] = {}
_topologies: dict[str, NetworkTopology] = {}
_executions: dict[str, TestExecution] = {}
_execution_status: dict[str, TestStatus] = {}
_execution_metrics: dict[str, TestMetrics] = {}


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
