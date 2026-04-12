"""
Workflow Engine Tests

Unit and integration tests for the calibration workflow engine.
"""

import pytest
from datetime import datetime

from app.services.workflow_engine import (
    WorkflowParser,
    WorkflowExecutor,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowExecution,
    WorkflowStatus,
    StepStatus,
    StepType,
    OnFailureAction,
    get_predefined_workflows,
    FULL_CHANNEL_CALIBRATION_WORKFLOW,
    QUICK_VALIDATION_WORKFLOW,
)


# ==================== Parser Tests ====================

class TestWorkflowParser:
    """Tests for WorkflowParser"""

    def test_parse_minimal_workflow(self):
        """Test parsing a minimal valid workflow"""
        yaml_content = """
name: "Minimal Test"
steps:
  - id: step1
    type: channel_calibration
    calibration_type: temporal
"""
        workflow = WorkflowParser.parse_string(yaml_content)
        assert workflow.name == "Minimal Test"
        assert workflow.version == "1.0"  # default
        assert len(workflow.steps) == 1
        assert workflow.steps[0].id == "step1"
        assert workflow.steps[0].type == StepType.CHANNEL_CALIBRATION
        assert workflow.steps[0].calibration_type == "temporal"

    def test_parse_full_workflow(self):
        """Test parsing a workflow with all features"""
        yaml_content = """
name: "Full Test"
version: "2.0"
description: "Full featured workflow"

settings:
  retry_count: 5
  retry_delay_seconds: 10
  stop_on_failure: false
  notification:
    on_complete: true

parameters:
  fc_ghz: 3.5
  calibrated_by: "test"

steps:
  - id: step1
    type: channel_calibration
    calibration_type: temporal
    parameters:
      scenario:
        type: UMa
        condition: LOS
    on_failure: continue
    retry_count: 2
    timeout_seconds: 300
    description: "First step"

  - id: step2
    type: channel_calibration
    calibration_type: doppler
    depends_on: [step1]
    parameters:
      velocity_kmh: 120
"""
        workflow = WorkflowParser.parse_string(yaml_content)

        assert workflow.name == "Full Test"
        assert workflow.version == "2.0"
        assert workflow.description == "Full featured workflow"
        assert workflow.retry_count == 5
        assert workflow.retry_delay_seconds == 10
        assert workflow.stop_on_failure is False
        assert workflow.parameters["fc_ghz"] == 3.5
        assert workflow.parameters["calibrated_by"] == "test"

        assert len(workflow.steps) == 2
        step1 = workflow.steps[0]
        assert step1.id == "step1"
        assert step1.on_failure == OnFailureAction.CONTINUE
        assert step1.retry_count == 2
        assert step1.timeout_seconds == 300
        assert step1.description == "First step"
        assert step1.parameters["scenario"]["type"] == "UMa"

        step2 = workflow.steps[1]
        assert step2.id == "step2"
        assert step2.depends_on == ["step1"]

    def test_parse_all_step_types(self):
        """Test parsing all step types"""
        yaml_content = """
name: "All Types"
steps:
  - id: probe
    type: probe_calibration
    calibration_type: amplitude
  - id: channel
    type: channel_calibration
    calibration_type: temporal
  - id: wait
    type: wait
    parameters:
      seconds: 5
  - id: notify
    type: notify
    parameters:
      message: "Test complete"
"""
        workflow = WorkflowParser.parse_string(yaml_content)
        assert len(workflow.steps) == 4
        assert workflow.steps[0].type == StepType.PROBE_CALIBRATION
        assert workflow.steps[1].type == StepType.CHANNEL_CALIBRATION
        assert workflow.steps[2].type == StepType.WAIT
        assert workflow.steps[3].type == StepType.NOTIFY

    def test_parse_on_failure_actions(self):
        """Test parsing all on_failure actions"""
        yaml_content = """
name: "Failure Actions"
steps:
  - id: s1
    type: wait
    on_failure: stop
  - id: s2
    type: wait
    on_failure: continue
  - id: s3
    type: wait
    on_failure: retry
  - id: s4
    type: wait
    on_failure: skip
"""
        workflow = WorkflowParser.parse_string(yaml_content)
        assert workflow.steps[0].on_failure == OnFailureAction.STOP
        assert workflow.steps[1].on_failure == OnFailureAction.CONTINUE
        assert workflow.steps[2].on_failure == OnFailureAction.RETRY
        assert workflow.steps[3].on_failure == OnFailureAction.SKIP

    def test_parse_error_missing_name(self):
        """Test error when name is missing"""
        yaml_content = """
steps:
  - id: step1
    type: wait
"""
        with pytest.raises(ValueError, match="must have a 'name' field"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_missing_steps(self):
        """Test error when steps are missing"""
        yaml_content = """
name: "No Steps"
"""
        with pytest.raises(ValueError, match="must have at least one step"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_empty_steps(self):
        """Test error when steps array is empty"""
        yaml_content = """
name: "Empty Steps"
steps: []
"""
        with pytest.raises(ValueError, match="must have at least one step"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_missing_step_id(self):
        """Test error when step id is missing"""
        yaml_content = """
name: "No ID"
steps:
  - type: wait
"""
        with pytest.raises(ValueError, match="must have an 'id' field"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_missing_step_type(self):
        """Test error when step type is missing"""
        yaml_content = """
name: "No Type"
steps:
  - id: step1
"""
        with pytest.raises(ValueError, match="must have a 'type' field"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_invalid_step_type(self):
        """Test error when step type is invalid"""
        yaml_content = """
name: "Invalid Type"
steps:
  - id: step1
    type: invalid_type
"""
        with pytest.raises(ValueError, match="Invalid step type"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_invalid_on_failure(self):
        """Test error when on_failure action is invalid"""
        yaml_content = """
name: "Invalid Action"
steps:
  - id: step1
    type: wait
    on_failure: explode
"""
        with pytest.raises(ValueError, match="Invalid on_failure action"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_unknown_dependency(self):
        """Test error when dependency references unknown step"""
        yaml_content = """
name: "Bad Dependency"
steps:
  - id: step1
    type: wait
    depends_on: [unknown_step]
"""
        with pytest.raises(ValueError, match="depends on unknown step"):
            WorkflowParser.parse_string(yaml_content)

    def test_parse_error_unknown_parallel(self):
        """Test error when parallel_with references unknown step"""
        yaml_content = """
name: "Bad Parallel"
steps:
  - id: step1
    type: wait
    parallel_with: [unknown_step]
"""
        with pytest.raises(ValueError, match="parallel_with unknown step"):
            WorkflowParser.parse_string(yaml_content)

    def test_to_yaml(self):
        """Test serializing workflow to YAML"""
        yaml_content = """
name: "Round Trip"
version: "1.5"
steps:
  - id: step1
    type: channel_calibration
    calibration_type: temporal
"""
        workflow = WorkflowParser.parse_string(yaml_content)
        output = WorkflowParser.to_yaml(workflow)

        # Parse the output and verify
        workflow2 = WorkflowParser.parse_string(output)
        assert workflow2.name == workflow.name
        assert workflow2.version == workflow.version
        assert len(workflow2.steps) == len(workflow.steps)
        assert workflow2.steps[0].id == workflow.steps[0].id


# ==================== Predefined Workflow Tests ====================

class TestPredefinedWorkflows:
    """Tests for predefined workflows"""

    def test_full_channel_calibration_parses(self):
        """Test that full channel calibration workflow parses correctly"""
        workflow = WorkflowParser.parse_string(FULL_CHANNEL_CALIBRATION_WORKFLOW)
        assert workflow.name == "Full Channel Calibration"
        assert len(workflow.steps) == 7  # All 6 channel calibrations + EIS
        assert workflow.retry_count == 2
        assert workflow.stop_on_failure is False

    def test_quick_validation_parses(self):
        """Test that quick validation workflow parses correctly"""
        workflow = WorkflowParser.parse_string(QUICK_VALIDATION_WORKFLOW)
        assert workflow.name == "Quick Validation"
        assert len(workflow.steps) == 2
        assert workflow.retry_count == 1
        assert workflow.stop_on_failure is True

    def test_get_predefined_workflows(self):
        """Test getting all predefined workflows"""
        workflows = get_predefined_workflows()
        assert "full_channel_calibration" in workflows
        assert "quick_validation" in workflows

        full = workflows["full_channel_calibration"]
        assert isinstance(full, WorkflowDefinition)
        assert full.name == "Full Channel Calibration"

        quick = workflows["quick_validation"]
        assert isinstance(quick, WorkflowDefinition)
        assert quick.name == "Quick Validation"


# ==================== Execution Tests ====================

class TestWorkflowExecution:
    """Tests for WorkflowExecution data class"""

    def test_progress_percent_empty(self):
        """Test progress calculation with no steps"""
        workflow = WorkflowDefinition(
            name="Empty",
            version="1.0",
            steps=[],
        )
        execution = WorkflowExecution(id="test", workflow=workflow)
        assert execution.progress_percent == 0.0

    def test_progress_percent_partial(self):
        """Test progress calculation with partial completion"""
        workflow = WorkflowDefinition(
            name="Test",
            version="1.0",
            steps=[
                WorkflowStep(id="s1", type=StepType.WAIT),
                WorkflowStep(id="s2", type=StepType.WAIT),
                WorkflowStep(id="s3", type=StepType.WAIT),
                WorkflowStep(id="s4", type=StepType.WAIT),
            ],
        )
        execution = WorkflowExecution(id="test", workflow=workflow)

        # Complete 2 of 4 steps
        from app.services.workflow_engine import StepResult
        execution.step_results["s1"] = StepResult(step_id="s1", status=StepStatus.COMPLETED)
        execution.step_results["s2"] = StepResult(step_id="s2", status=StepStatus.FAILED)

        assert execution.progress_percent == 50.0

    def test_passed_failed_counts(self):
        """Test passed/failed step counting"""
        workflow = WorkflowDefinition(
            name="Test",
            version="1.0",
            steps=[
                WorkflowStep(id="s1", type=StepType.WAIT),
                WorkflowStep(id="s2", type=StepType.WAIT),
                WorkflowStep(id="s3", type=StepType.WAIT),
            ],
        )
        execution = WorkflowExecution(id="test", workflow=workflow)

        from app.services.workflow_engine import StepResult
        execution.step_results["s1"] = StepResult(
            step_id="s1", status=StepStatus.COMPLETED, validation_pass=True
        )
        execution.step_results["s2"] = StepResult(
            step_id="s2", status=StepStatus.COMPLETED, validation_pass=False
        )
        execution.step_results["s3"] = StepResult(
            step_id="s3", status=StepStatus.FAILED
        )

        assert execution.passed_steps == 1
        assert execution.failed_steps == 2


# ==================== Executor Tests (with DB) ====================

class TestWorkflowExecutor:
    """Integration tests for WorkflowExecutor"""

    @pytest.fixture
    def db_session(self):
        """Create test database session"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.database import Base

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()

        yield session

        session.close()

    def test_create_execution(self, db_session):
        """Test creating a workflow execution"""
        workflow = WorkflowParser.parse_string("""
name: "Test"
steps:
  - id: s1
    type: wait
    parameters:
      seconds: 0.1
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)

        assert execution.id is not None
        assert execution.status == WorkflowStatus.PENDING
        assert execution.workflow.name == "Test"

    def test_get_execution(self, db_session):
        """Test retrieving an execution"""
        workflow = WorkflowParser.parse_string("""
name: "Test"
steps:
  - id: s1
    type: wait
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)

        retrieved = executor.get_execution(execution.id)
        assert retrieved is not None
        assert retrieved.id == execution.id

        unknown = executor.get_execution("unknown-id")
        assert unknown is None

    def test_run_wait_step(self, db_session):
        """Test running a simple wait step"""
        workflow = WorkflowParser.parse_string("""
name: "Wait Test"
steps:
  - id: wait1
    type: wait
    parameters:
      seconds: 0.01
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.started_at is not None
        assert execution.completed_at is not None
        assert "wait1" in execution.step_results
        assert execution.step_results["wait1"].status == StepStatus.COMPLETED
        assert execution.progress_percent == 100.0

    def test_run_notify_step(self, db_session):
        """Test running a notify step"""
        workflow = WorkflowParser.parse_string("""
name: "Notify Test"
steps:
  - id: notify1
    type: notify
    parameters:
      message: "Test notification"
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.step_results["notify1"].output["message"] == "Test notification"

    def test_run_channel_calibration_step(self, db_session):
        """Test running a channel calibration step"""
        workflow = WorkflowParser.parse_string("""
name: "Calibration Test"
parameters:
  fc_ghz: 3.5
  calibrated_by: "test"
steps:
  - id: temporal1
    type: channel_calibration
    calibration_type: temporal
    parameters:
      scenario:
        type: UMa
        condition: LOS
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.session_id is not None
        result = execution.step_results["temporal1"]
        assert result.status == StepStatus.COMPLETED
        assert result.calibration_id is not None
        assert result.validation_pass is not None

    def test_run_dependency_check(self, db_session):
        """Test that dependencies are checked"""
        workflow = WorkflowParser.parse_string("""
name: "Dependency Test"
steps:
  - id: step1
    type: wait
    parameters:
      seconds: 0.01
  - id: step2
    type: wait
    depends_on: [step1]
    parameters:
      seconds: 0.01
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.step_results["step1"].status == StepStatus.COMPLETED
        assert execution.step_results["step2"].status == StepStatus.COMPLETED

    def test_run_stop_on_failure(self, db_session):
        """Test that workflow stops on failure when configured"""
        workflow = WorkflowParser.parse_string("""
name: "Failure Test"
settings:
  stop_on_failure: true
  retry_count: 0
steps:
  - id: bad_step
    type: channel_calibration
    calibration_type: unknown_type
  - id: good_step
    type: wait
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        assert execution.status == WorkflowStatus.FAILED
        assert "bad_step" in execution.step_results
        assert "good_step" not in execution.step_results  # Never reached

    def test_run_continue_on_failure(self, db_session):
        """Test that workflow continues when on_failure=continue"""
        workflow = WorkflowParser.parse_string("""
name: "Continue Test"
settings:
  stop_on_failure: false
  retry_count: 0
steps:
  - id: bad_step
    type: channel_calibration
    calibration_type: unknown_type
    on_failure: continue
  - id: good_step
    type: wait
    parameters:
      seconds: 0.01
""")
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        # Should complete despite failure
        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.step_results["bad_step"].status == StepStatus.FAILED
        assert execution.step_results["good_step"].status == StepStatus.COMPLETED

    def test_run_quick_validation_workflow(self, db_session):
        """Test running the quick validation predefined workflow"""
        workflows = get_predefined_workflows()
        workflow = workflows["quick_validation"]

        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        assert execution.status == WorkflowStatus.COMPLETED
        assert len(execution.step_results) == 2
        assert execution.session_id is not None


# ==================== API Tests ====================

class TestWorkflowAPI:
    """Tests for workflow API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client with initialized database"""
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db.database import Base, get_db
        from app.main import app

        # Create in-memory database
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        yield TestClient(app)

        # Clean up
        app.dependency_overrides.clear()

    def test_list_predefined_workflows(self, client):
        """Test listing predefined workflows"""
        response = client.get("/api/v1/workflows/predefined")
        assert response.status_code == 200

        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert data["total"] >= 2

        workflow_ids = [w["id"] for w in data["workflows"]]
        assert "full_channel_calibration" in workflow_ids
        assert "quick_validation" in workflow_ids

    def test_get_predefined_workflow(self, client):
        """Test getting a predefined workflow"""
        response = client.get("/api/v1/workflows/predefined/quick_validation")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Quick Validation"
        assert len(data["steps"]) == 2

    def test_get_predefined_workflow_not_found(self, client):
        """Test getting a non-existent workflow"""
        response = client.get("/api/v1/workflows/predefined/nonexistent")
        assert response.status_code == 404

    def test_get_predefined_workflow_yaml(self, client):
        """Test getting workflow as YAML"""
        response = client.get("/api/v1/workflows/predefined/quick_validation/yaml")
        assert response.status_code == 200

        data = response.json()
        assert "yaml_content" in data
        assert "Quick Validation" in data["yaml_content"]

    def test_parse_valid_workflow(self, client):
        """Test parsing a valid workflow"""
        yaml_content = """
name: "API Test"
steps:
  - id: step1
    type: wait
"""
        response = client.post(
            "/api/v1/workflows/parse",
            json={"yaml_content": yaml_content}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["valid"] is True
        assert data["workflow"]["name"] == "API Test"
        assert data["error_message"] is None

    def test_parse_invalid_workflow(self, client):
        """Test parsing an invalid workflow"""
        yaml_content = """
# Missing name
steps:
  - id: step1
    type: wait
"""
        response = client.post(
            "/api/v1/workflows/parse",
            json={"yaml_content": yaml_content}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["valid"] is False
        assert data["workflow"] is None
        assert "name" in data["error_message"]

    def test_execute_predefined_workflow(self, client):
        """Test executing a predefined workflow"""
        response = client.post(
            "/api/v1/workflows/execute",
            json={
                "workflow_id": "quick_validation",
                "parameter_overrides": {
                    "fc_ghz": 3.5
                }
            }
        )
        assert response.status_code == 202

        data = response.json()
        assert data["workflow_name"] == "Quick Validation"
        assert data["status"] in ["pending", "running", "completed", "failed"]
        assert "id" in data

    def test_execute_custom_workflow(self, client):
        """Test executing a custom workflow"""
        yaml_content = """
name: "Custom API Test"
steps:
  - id: wait1
    type: wait
    parameters:
      seconds: 0.01
"""
        response = client.post(
            "/api/v1/workflows/execute",
            json={"yaml_content": yaml_content}
        )
        assert response.status_code == 202

        data = response.json()
        assert data["workflow_name"] == "Custom API Test"
        assert data["status"] in ["pending", "running", "completed", "failed"]

    def test_execute_workflow_no_input(self, client):
        """Test executing without workflow_id or yaml_content"""
        response = client.post(
            "/api/v1/workflows/execute",
            json={}
        )
        assert response.status_code == 400
        assert "workflow_id or yaml_content" in response.json()["detail"]

    def test_list_executions(self, client):
        """Test listing workflow executions"""
        # First execute a workflow
        client.post(
            "/api/v1/workflows/execute",
            json={"workflow_id": "quick_validation"}
        )

        response = client.get("/api/v1/workflows/executions")
        assert response.status_code == 200

        data = response.json()
        assert "executions" in data
        assert "total" in data

    def test_get_execution(self, client):
        """Test getting a specific execution"""
        # First execute a workflow
        exec_response = client.post(
            "/api/v1/workflows/execute",
            json={"workflow_id": "quick_validation"}
        )
        exec_id = exec_response.json()["id"]

        response = client.get(f"/api/v1/workflows/executions/{exec_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == exec_id
        assert data["workflow_name"] == "Quick Validation"

    def test_get_execution_not_found(self, client):
        """Test getting a non-existent execution"""
        response = client.get("/api/v1/workflows/executions/nonexistent-id")
        assert response.status_code == 404
