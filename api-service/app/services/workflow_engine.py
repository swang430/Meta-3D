"""
Calibration Workflow Engine

YAML-based workflow definition and execution for calibration sequences.

Features:
- YAML workflow parsing and validation
- Sequential and parallel step execution
- Progress tracking and status reporting
- Error handling and retry logic
- Session integration

Workflow YAML Format:
```yaml
name: "Full System Calibration"
description: "Complete probe and channel calibration workflow"
version: "1.0"

settings:
  retry_count: 3
  retry_delay_seconds: 5
  stop_on_failure: true
  notification:
    on_complete: true
    on_failure: true

parameters:
  fc_ghz: 3.5
  calibrated_by: "system"

steps:
  - id: probe_amplitude
    type: probe_calibration
    calibration_type: amplitude
    parameters:
      probe_ids: [0, 1, 2, 3]
      frequency_range:
        start_mhz: 700
        stop_mhz: 6000
        step_mhz: 100
    on_failure: continue

  - id: channel_temporal
    type: channel_calibration
    calibration_type: temporal
    parameters:
      scenario:
        type: UMa
        condition: LOS
    depends_on: [probe_amplitude]

  - id: channel_doppler
    type: channel_calibration
    calibration_type: doppler
    parameters:
      velocity_kmh: 120
    parallel_with: [channel_temporal]
```
"""

import yaml
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ==================== Enums ====================

class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class StepType(str, Enum):
    PROBE_CALIBRATION = "probe_calibration"
    CHANNEL_CALIBRATION = "channel_calibration"
    WAIT = "wait"
    CONDITION = "condition"
    NOTIFY = "notify"


class OnFailureAction(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"
    RETRY = "retry"
    SKIP = "skip"


# ==================== Data Classes ====================

@dataclass
class StepResult:
    """Result of a workflow step execution"""
    step_id: str
    status: StepStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    calibration_id: Optional[str] = None
    validation_pass: Optional[bool] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    output: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStep:
    """Definition of a workflow step"""
    id: str
    type: StepType
    calibration_type: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    parallel_with: List[str] = field(default_factory=list)
    on_failure: OnFailureAction = OnFailureAction.STOP
    retry_count: Optional[int] = None
    timeout_seconds: Optional[int] = None
    condition: Optional[str] = None
    description: Optional[str] = None


@dataclass
class WorkflowDefinition:
    """Complete workflow definition"""
    name: str
    version: str
    steps: List[WorkflowStep]
    description: Optional[str] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)

    @property
    def retry_count(self) -> int:
        return self.settings.get("retry_count", 3)

    @property
    def retry_delay_seconds(self) -> int:
        return self.settings.get("retry_delay_seconds", 5)

    @property
    def stop_on_failure(self) -> bool:
        return self.settings.get("stop_on_failure", True)


@dataclass
class WorkflowExecution:
    """State of a workflow execution"""
    id: str
    workflow: WorkflowDefinition
    status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step_index: int = 0
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    session_id: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        if not self.workflow.steps:
            return 0.0
        completed = sum(
            1 for r in self.step_results.values()
            if r.status in (StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED)
        )
        return (completed / len(self.workflow.steps)) * 100

    @property
    def passed_steps(self) -> int:
        return sum(
            1 for r in self.step_results.values()
            if r.status == StepStatus.COMPLETED and r.validation_pass
        )

    @property
    def failed_steps(self) -> int:
        return sum(
            1 for r in self.step_results.values()
            if r.status == StepStatus.FAILED or (r.status == StepStatus.COMPLETED and not r.validation_pass)
        )


# ==================== YAML Parser ====================

class WorkflowParser:
    """Parse YAML workflow definitions"""

    @staticmethod
    def parse_file(file_path: str) -> WorkflowDefinition:
        """Parse workflow from YAML file"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Workflow file not found: {file_path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        return WorkflowParser.parse_dict(data)

    @staticmethod
    def parse_string(yaml_content: str) -> WorkflowDefinition:
        """Parse workflow from YAML string"""
        data = yaml.safe_load(yaml_content)
        return WorkflowParser.parse_dict(data)

    @staticmethod
    def parse_dict(data: Dict[str, Any]) -> WorkflowDefinition:
        """Parse workflow from dictionary"""
        # Validate required fields
        if "name" not in data:
            raise ValueError("Workflow must have a 'name' field")
        if "steps" not in data or not data["steps"]:
            raise ValueError("Workflow must have at least one step")

        # Parse steps
        steps = []
        for step_data in data["steps"]:
            step = WorkflowParser._parse_step(step_data)
            steps.append(step)

        # Validate step dependencies
        step_ids = {s.id for s in steps}
        for step in steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    raise ValueError(f"Step '{step.id}' depends on unknown step '{dep_id}'")
            for par_id in step.parallel_with:
                if par_id not in step_ids:
                    raise ValueError(f"Step '{step.id}' parallel_with unknown step '{par_id}'")

        return WorkflowDefinition(
            name=data["name"],
            version=data.get("version", "1.0"),
            description=data.get("description"),
            settings=data.get("settings", {}),
            parameters=data.get("parameters", {}),
            steps=steps,
        )

    @staticmethod
    def _parse_step(data: Dict[str, Any]) -> WorkflowStep:
        """Parse a single workflow step"""
        if "id" not in data:
            raise ValueError("Each step must have an 'id' field")
        if "type" not in data:
            raise ValueError(f"Step '{data['id']}' must have a 'type' field")

        try:
            step_type = StepType(data["type"])
        except ValueError:
            raise ValueError(f"Invalid step type: {data['type']}")

        on_failure = OnFailureAction.STOP
        if "on_failure" in data:
            try:
                on_failure = OnFailureAction(data["on_failure"])
            except ValueError:
                raise ValueError(f"Invalid on_failure action: {data['on_failure']}")

        return WorkflowStep(
            id=data["id"],
            type=step_type,
            calibration_type=data.get("calibration_type"),
            parameters=data.get("parameters", {}),
            depends_on=data.get("depends_on", []),
            parallel_with=data.get("parallel_with", []),
            on_failure=on_failure,
            retry_count=data.get("retry_count"),
            timeout_seconds=data.get("timeout_seconds"),
            condition=data.get("condition"),
            description=data.get("description"),
        )

    @staticmethod
    def to_yaml(workflow: WorkflowDefinition) -> str:
        """Serialize workflow to YAML string"""
        data = {
            "name": workflow.name,
            "version": workflow.version,
            "description": workflow.description,
            "settings": workflow.settings,
            "parameters": workflow.parameters,
            "steps": [
                {
                    "id": step.id,
                    "type": step.type.value,
                    "calibration_type": step.calibration_type,
                    "parameters": step.parameters,
                    "depends_on": step.depends_on,
                    "parallel_with": step.parallel_with,
                    "on_failure": step.on_failure.value,
                    "retry_count": step.retry_count,
                    "timeout_seconds": step.timeout_seconds,
                    "condition": step.condition,
                    "description": step.description,
                }
                for step in workflow.steps
            ]
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)


# ==================== Workflow Executor ====================

class WorkflowExecutor:
    """Execute calibration workflows"""

    def __init__(self, db_session):
        self.db = db_session
        self._executions: Dict[str, WorkflowExecution] = {}

    def create_execution(self, workflow: WorkflowDefinition) -> WorkflowExecution:
        """Create a new workflow execution"""
        execution = WorkflowExecution(
            id=str(uuid.uuid4()),
            workflow=workflow,
            status=WorkflowStatus.PENDING,
        )
        self._executions[execution.id] = execution
        return execution

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get workflow execution by ID"""
        return self._executions.get(execution_id)

    def run(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Run a workflow execution synchronously"""
        execution.status = WorkflowStatus.RUNNING
        execution.started_at = datetime.utcnow()

        try:
            # Create calibration session
            from app.services.channel_calibration_service import ChannelCalibrationService
            channel_service = ChannelCalibrationService(self.db)

            session = channel_service.create_session(
                name=f"Workflow: {execution.workflow.name}",
                description=execution.workflow.description,
                workflow_id=execution.id,
                configuration=execution.workflow.parameters,
            )
            execution.session_id = str(session.id)

            # Execute steps
            for i, step in enumerate(execution.workflow.steps):
                execution.current_step_index = i

                # Check dependencies
                if not self._check_dependencies(execution, step):
                    result = StepResult(
                        step_id=step.id,
                        status=StepStatus.SKIPPED,
                        error_message="Dependencies not met",
                    )
                    execution.step_results[step.id] = result
                    continue

                # Execute step
                result = self._execute_step(execution, step)
                execution.step_results[step.id] = result

                # Handle failure
                if result.status == StepStatus.FAILED:
                    if step.on_failure == OnFailureAction.STOP or execution.workflow.stop_on_failure:
                        execution.status = WorkflowStatus.FAILED
                        execution.error_message = f"Step '{step.id}' failed: {result.error_message}"
                        break

            # Mark as completed if not failed
            if execution.status == WorkflowStatus.RUNNING:
                execution.status = WorkflowStatus.COMPLETED

            # Update session
            channel_service.complete_session(
                session_id=session.id,
                overall_pass=execution.status == WorkflowStatus.COMPLETED and execution.failed_steps == 0,
                total_calibrations=len(execution.step_results),
                passed_calibrations=execution.passed_steps,
                failed_calibrations=execution.failed_steps,
            )

        except Exception as e:
            logger.exception(f"Workflow execution failed: {e}")
            execution.status = WorkflowStatus.FAILED
            execution.error_message = str(e)

        execution.completed_at = datetime.utcnow()
        return execution

    def _check_dependencies(self, execution: WorkflowExecution, step: WorkflowStep) -> bool:
        """Check if step dependencies are met"""
        for dep_id in step.depends_on:
            dep_result = execution.step_results.get(dep_id)
            if not dep_result:
                return False
            if dep_result.status != StepStatus.COMPLETED:
                return False
            # Optionally check if dependency passed
            # if not dep_result.validation_pass:
            #     return False
        return True

    def _execute_step(self, execution: WorkflowExecution, step: WorkflowStep) -> StepResult:
        """Execute a single workflow step"""
        result = StepResult(
            step_id=step.id,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        max_retries = step.retry_count or execution.workflow.retry_count
        retry_delay = execution.workflow.retry_delay_seconds

        for attempt in range(max_retries + 1):
            try:
                if step.type == StepType.PROBE_CALIBRATION:
                    self._execute_probe_calibration(execution, step, result)
                elif step.type == StepType.CHANNEL_CALIBRATION:
                    self._execute_channel_calibration(execution, step, result)
                elif step.type == StepType.WAIT:
                    self._execute_wait(step, result)
                elif step.type == StepType.NOTIFY:
                    self._execute_notify(execution, step, result)
                else:
                    raise ValueError(f"Unknown step type: {step.type}")

                result.status = StepStatus.COMPLETED
                break

            except Exception as e:
                result.retry_count = attempt + 1
                result.error_message = str(e)

                if attempt < max_retries:
                    result.status = StepStatus.RETRYING
                    logger.warning(f"Step '{step.id}' failed, retrying ({attempt + 1}/{max_retries}): {e}")
                    import time
                    time.sleep(retry_delay)
                else:
                    result.status = StepStatus.FAILED
                    logger.error(f"Step '{step.id}' failed after {max_retries} retries: {e}")

        result.completed_at = datetime.utcnow()
        return result

    def _execute_probe_calibration(
        self,
        execution: WorkflowExecution,
        step: WorkflowStep,
        result: StepResult
    ):
        """Execute a probe calibration step"""
        from app.services.probe_calibration_service import ProbeCalibrationService

        service = ProbeCalibrationService(self.db)
        params = {**execution.workflow.parameters, **step.parameters}

        cal_type = step.calibration_type
        if cal_type == "amplitude":
            calibration = service.run_amplitude_calibration(
                probe_ids=params.get("probe_ids", [0]),
                polarization=params.get("polarization", "V"),
                frequency_range=params.get("frequency_range", {}),
                calibrated_by=params.get("calibrated_by", "workflow"),
            )
        elif cal_type == "phase":
            calibration = service.run_phase_calibration(
                probe_ids=params.get("probe_ids", [0]),
                reference_probe_id=params.get("reference_probe_id", 0),
                polarization=params.get("polarization", "V"),
                frequency_range=params.get("frequency_range", {}),
                calibrated_by=params.get("calibrated_by", "workflow"),
            )
        else:
            raise ValueError(f"Unknown probe calibration type: {cal_type}")

        result.calibration_id = str(calibration.id)
        result.validation_pass = calibration.validation_pass if hasattr(calibration, 'validation_pass') else True
        result.output = {"calibration_type": cal_type, "probe_ids": params.get("probe_ids")}

    def _execute_channel_calibration(
        self,
        execution: WorkflowExecution,
        step: WorkflowStep,
        result: StepResult
    ):
        """Execute a channel calibration step"""
        from app.services.channel_calibration_service import ChannelCalibrationService

        service = ChannelCalibrationService(self.db)
        params = {**execution.workflow.parameters, **step.parameters}
        session_id = uuid.UUID(execution.session_id) if execution.session_id else None

        cal_type = step.calibration_type
        if cal_type == "temporal":
            scenario = params.get("scenario", {})
            calibration = service.run_temporal_calibration(
                scenario_type=scenario.get("type", "UMa"),
                scenario_condition=scenario.get("condition", "LOS"),
                fc_ghz=params.get("fc_ghz", 3.5),
                session_id=session_id,
                calibrated_by=params.get("calibrated_by", "workflow"),
            )
        elif cal_type == "doppler":
            calibration = service.run_doppler_calibration(
                velocity_kmh=params.get("velocity_kmh", 120),
                fc_ghz=params.get("fc_ghz", 3.5),
                session_id=session_id,
                calibrated_by=params.get("calibrated_by", "workflow"),
            )
        elif cal_type == "spatial_correlation":
            scenario = params.get("scenario", {})
            calibration = service.run_spatial_correlation_calibration(
                scenario_type=scenario.get("type", "UMa"),
                scenario_condition=scenario.get("condition", "NLOS"),
                fc_ghz=params.get("fc_ghz", 3.5),
                antenna_spacing_wavelengths=params.get("antenna_spacing_wavelengths", 0.5),
                session_id=session_id,
                calibrated_by=params.get("calibrated_by", "workflow"),
            )
        elif cal_type == "angular_spread":
            scenario = params.get("scenario", {})
            calibration = service.run_angular_spread_calibration(
                scenario_type=scenario.get("type", "UMa"),
                scenario_condition=scenario.get("condition", "NLOS"),
                fc_ghz=params.get("fc_ghz", 3.5),
                session_id=session_id,
                calibrated_by=params.get("calibrated_by", "workflow"),
            )
        elif cal_type == "quiet_zone":
            quiet_zone = params.get("quiet_zone", {})
            calibration = service.run_quiet_zone_calibration(
                quiet_zone_shape=quiet_zone.get("shape", "sphere"),
                quiet_zone_diameter_m=quiet_zone.get("diameter_m", 1.0),
                fc_ghz=params.get("fc_ghz", 3.5),
                session_id=session_id,
                calibrated_by=params.get("calibrated_by", "workflow"),
            )
        elif cal_type == "eis":
            dut = params.get("dut", {})
            calibration = service.run_eis_validation(
                fc_ghz=params.get("fc_ghz", 3.5),
                dut_model=dut.get("model", "Reference"),
                dut_type=dut.get("type", "vehicle"),
                session_id=session_id,
                measured_by=params.get("calibrated_by", "workflow"),
            )
        else:
            raise ValueError(f"Unknown channel calibration type: {cal_type}")

        result.calibration_id = str(calibration.id)
        result.validation_pass = calibration.validation_pass
        result.output = {"calibration_type": cal_type}

    def _execute_wait(self, step: WorkflowStep, result: StepResult):
        """Execute a wait step"""
        import time
        wait_seconds = step.parameters.get("seconds", 1)
        time.sleep(wait_seconds)
        result.validation_pass = True

    def _execute_notify(self, execution: WorkflowExecution, step: WorkflowStep, result: StepResult):
        """Execute a notification step"""
        # Placeholder for notification logic
        message = step.parameters.get("message", "Workflow notification")
        logger.info(f"Workflow notification: {message}")
        result.validation_pass = True
        result.output = {"message": message}


# ==================== Predefined Workflows ====================

FULL_CHANNEL_CALIBRATION_WORKFLOW = """
name: "Full Channel Calibration"
description: "Complete channel calibration sequence for 3GPP scenarios"
version: "1.0"

settings:
  retry_count: 2
  retry_delay_seconds: 3
  stop_on_failure: false

parameters:
  fc_ghz: 3.5
  calibrated_by: "system"

steps:
  - id: temporal_uma_los
    type: channel_calibration
    calibration_type: temporal
    description: "Temporal calibration for UMa LOS"
    parameters:
      scenario:
        type: UMa
        condition: LOS

  - id: temporal_uma_nlos
    type: channel_calibration
    calibration_type: temporal
    description: "Temporal calibration for UMa NLOS"
    parameters:
      scenario:
        type: UMa
        condition: NLOS

  - id: doppler_120
    type: channel_calibration
    calibration_type: doppler
    description: "Doppler calibration at 120 km/h"
    parameters:
      velocity_kmh: 120

  - id: spatial_corr
    type: channel_calibration
    calibration_type: spatial_correlation
    description: "Spatial correlation calibration"
    parameters:
      scenario:
        type: UMa
        condition: NLOS
      antenna_spacing_wavelengths: 0.5

  - id: angular_spread
    type: channel_calibration
    calibration_type: angular_spread
    description: "Angular spread calibration"
    parameters:
      scenario:
        type: UMa
        condition: NLOS

  - id: quiet_zone
    type: channel_calibration
    calibration_type: quiet_zone
    description: "Quiet zone uniformity calibration"
    parameters:
      quiet_zone:
        shape: sphere
        diameter_m: 1.0

  - id: eis_validation
    type: channel_calibration
    calibration_type: eis
    description: "EIS validation"
    parameters:
      dut:
        model: "Reference DUT"
        type: vehicle
"""

QUICK_VALIDATION_WORKFLOW = """
name: "Quick Validation"
description: "Quick validation workflow for daily checks"
version: "1.0"

settings:
  retry_count: 1
  stop_on_failure: true

parameters:
  fc_ghz: 3.5

steps:
  - id: temporal_check
    type: channel_calibration
    calibration_type: temporal
    parameters:
      scenario:
        type: UMa
        condition: LOS

  - id: doppler_check
    type: channel_calibration
    calibration_type: doppler
    parameters:
      velocity_kmh: 120
"""

# CAL-07: 新增校准工作流模板

FULL_SYSTEM_CALIBRATION_WORKFLOW = """
name: "Full System Calibration"
description: "Complete system calibration including path loss, RF chain, and E2E"
version: "1.0"

settings:
  retry_count: 2
  retry_delay_seconds: 5
  stop_on_failure: true
  notification:
    on_complete: true
    on_failure: true

parameters:
  fc_ghz: 3.5
  frequency_mhz: 3500
  chamber_id: "default"
  calibrated_by: "system"

steps:
  - id: probe_path_loss
    type: probe_calibration
    calibration_type: amplitude
    description: "探头路损校准 - 测量 SGH 到各探头的路损"
    parameters:
      probe_ids: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
      frequency_range:
        start_mhz: 3400
        stop_mhz: 3600
        step_mhz: 50

  - id: phase_calibration
    type: probe_calibration
    calibration_type: phase
    description: "相位校准 - 确保通道间相位一致性"
    parameters:
      probe_ids: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
      reference_probe_id: 0
    depends_on: [probe_path_loss]

  - id: uplink_chain
    type: probe_calibration
    calibration_type: amplitude
    description: "上行链路校准 - LNA 增益校准"
    parameters:
      chain_type: uplink
    on_failure: continue

  - id: downlink_chain
    type: probe_calibration
    calibration_type: amplitude
    description: "下行链路校准 - PA 增益校准"
    parameters:
      chain_type: downlink
    on_failure: continue
    parallel_with: [uplink_chain]

  - id: quiet_zone
    type: channel_calibration
    calibration_type: quiet_zone
    description: "静区均匀性校准"
    parameters:
      quiet_zone:
        shape: sphere
        diameter_m: 1.0
    depends_on: [probe_path_loss, phase_calibration]

  - id: notification_complete
    type: notify
    description: "全系统校准完成通知"
    parameters:
      message: "Full system calibration completed successfully"
    depends_on: [quiet_zone]
"""

FREQUENCY_CHANGE_WORKFLOW = """
name: "Frequency Change Calibration"
description: "Quick calibration after frequency band change"
version: "1.0"

settings:
  retry_count: 1
  retry_delay_seconds: 3
  stop_on_failure: false

parameters:
  new_frequency_mhz: 3500
  calibrated_by: "system"

steps:
  - id: path_loss_recheck
    type: probe_calibration
    calibration_type: amplitude
    description: "新频点路损验证"
    parameters:
      probe_ids: [0, 1, 2, 3]
      frequency_range:
        start_mhz: 3400
        stop_mhz: 3600
        step_mhz: 100

  - id: phase_recheck
    type: probe_calibration
    calibration_type: phase
    description: "新频点相位验证"
    parameters:
      probe_ids: [0, 1, 2, 3]
      reference_probe_id: 0
    depends_on: [path_loss_recheck]

  - id: temporal_validation
    type: channel_calibration
    calibration_type: temporal
    description: "时域信道验证"
    parameters:
      scenario:
        type: UMa
        condition: LOS
    depends_on: [phase_recheck]
"""

PATH_LOSS_ONLY_WORKFLOW = """
name: "Path Loss Calibration Only"
description: "Quick path loss calibration for specific probes"
version: "1.0"

settings:
  retry_count: 2
  stop_on_failure: true

parameters:
  frequency_mhz: 3500
  calibrated_by: "system"

steps:
  - id: path_loss
    type: probe_calibration
    calibration_type: amplitude
    description: "探头路损测量"
    parameters:
      probe_ids: [0, 1, 2, 3, 4, 5, 6, 7]
      frequency_range:
        start_mhz: 3400
        stop_mhz: 3600
        step_mhz: 50
"""


def get_predefined_workflows() -> Dict[str, WorkflowDefinition]:
    """Get all predefined workflows"""
    return {
        "full_channel_calibration": WorkflowParser.parse_string(FULL_CHANNEL_CALIBRATION_WORKFLOW),
        "quick_validation": WorkflowParser.parse_string(QUICK_VALIDATION_WORKFLOW),
        "full_system_calibration": WorkflowParser.parse_string(FULL_SYSTEM_CALIBRATION_WORKFLOW),
        "frequency_change": WorkflowParser.parse_string(FREQUENCY_CHANGE_WORKFLOW),
        "path_loss_only": WorkflowParser.parse_string(PATH_LOSS_ONLY_WORKFLOW),
    }


def get_workflow_template_list() -> List[Dict[str, Any]]:
    """Get list of available workflow templates with metadata"""
    workflows = get_predefined_workflows()
    return [
        {
            "id": workflow_id,
            "name": workflow.name,
            "description": workflow.description,
            "version": workflow.version,
            "num_steps": len(workflow.steps),
            "estimated_duration_minutes": len(workflow.steps) * 5
        }
        for workflow_id, workflow in workflows.items()
    ]
