"""
End-to-End Calibration System Tests

Integration tests for the complete calibration workflow:
1. Workflow execution
2. Calibration data persistence
3. Report generation
4. API integration
"""

import pytest
import os
from datetime import datetime
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.services.workflow_engine import (
    WorkflowParser,
    WorkflowExecutor,
    get_predefined_workflows,
    WorkflowStatus,
    StepStatus,
)
from app.services.channel_calibration_service import ChannelCalibrationService
from app.services.calibration_report_generator import CalibrationReportGenerator
from app.models.channel_calibration import (
    ChannelCalibrationSession,
    TemporalChannelCalibration,
    DopplerCalibration,
)


class TestE2ECalibrationWorkflow:
    """End-to-end tests for calibration workflow"""

    @pytest.fixture
    def db_session(self):
        """Create test database session"""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()

        yield session

        session.close()

    @pytest.fixture
    def client(self, db_session):
        """Create test client with database override"""
        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_e2e_quick_validation_workflow(self, db_session):
        """
        E2E Test: Quick Validation Workflow

        Flow:
        1. Execute quick_validation workflow
        2. Verify calibration session created
        3. Verify calibration records created
        4. Generate report from calibration data
        """
        # Step 1: Get and execute workflow
        workflows = get_predefined_workflows()
        workflow = workflows["quick_validation"]

        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        # Verify execution completed
        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.session_id is not None

        # Step 2: Verify session created
        session = db_session.query(ChannelCalibrationSession).filter(
            ChannelCalibrationSession.id == UUID(execution.session_id)
        ).first()

        assert session is not None
        assert session.name == f"Workflow: {workflow.name}"
        assert session.status == "completed"

        # Step 3: Verify calibration records
        temporal_cals = db_session.query(TemporalChannelCalibration).filter(
            TemporalChannelCalibration.session_id == session.id
        ).all()

        doppler_cals = db_session.query(DopplerCalibration).filter(
            DopplerCalibration.session_id == session.id
        ).all()

        assert len(temporal_cals) == 1  # quick_validation has 1 temporal
        assert len(doppler_cals) == 1   # quick_validation has 1 doppler

        # Verify calibration data
        temporal = temporal_cals[0]
        assert temporal.scenario_type == "UMa"
        assert temporal.scenario_condition == "LOS"
        assert temporal.fc_ghz == 3.5
        assert temporal.validation_pass is not None

        doppler = doppler_cals[0]
        assert doppler.velocity_kmh == 120
        assert doppler.validation_pass is not None

        # Step 4: Generate report
        report_gen = CalibrationReportGenerator(db_session)
        report_path = report_gen.generate_channel_calibration_report(
            session_id=session.id,
        )

        assert os.path.exists(report_path)
        assert os.path.getsize(report_path) > 0

        # Cleanup
        os.remove(report_path)

    def test_e2e_custom_workflow_execution(self, db_session):
        """
        E2E Test: Custom Workflow

        Flow:
        1. Parse custom YAML workflow
        2. Execute workflow
        3. Verify all steps completed
        4. Check step results
        """
        yaml_content = """
name: "E2E Test Workflow"
description: "Custom workflow for E2E testing"
version: "1.0"

settings:
  retry_count: 1
  stop_on_failure: false

parameters:
  fc_ghz: 3.5
  calibrated_by: "e2e_test"

steps:
  - id: temporal_uma_los
    type: channel_calibration
    calibration_type: temporal
    description: "Temporal calibration UMa LOS"
    parameters:
      scenario:
        type: UMa
        condition: LOS

  - id: temporal_uma_nlos
    type: channel_calibration
    calibration_type: temporal
    description: "Temporal calibration UMa NLOS"
    parameters:
      scenario:
        type: UMa
        condition: NLOS

  - id: doppler_60
    type: channel_calibration
    calibration_type: doppler
    description: "Doppler at 60 km/h"
    parameters:
      velocity_kmh: 60

  - id: doppler_120
    type: channel_calibration
    calibration_type: doppler
    description: "Doppler at 120 km/h"
    parameters:
      velocity_kmh: 120
"""
        # Parse and execute
        workflow = WorkflowParser.parse_string(yaml_content)
        assert len(workflow.steps) == 4

        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        # Verify completion
        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.progress_percent == 100.0
        assert len(execution.step_results) == 4

        # Verify each step
        for step_id in ["temporal_uma_los", "temporal_uma_nlos", "doppler_60", "doppler_120"]:
            assert step_id in execution.step_results
            result = execution.step_results[step_id]
            assert result.status == StepStatus.COMPLETED
            assert result.calibration_id is not None

        # Verify database records
        session_id = UUID(execution.session_id)
        temporal_count = db_session.query(TemporalChannelCalibration).filter(
            TemporalChannelCalibration.session_id == session_id
        ).count()
        doppler_count = db_session.query(DopplerCalibration).filter(
            DopplerCalibration.session_id == session_id
        ).count()

        assert temporal_count == 2
        assert doppler_count == 2

    def test_e2e_workflow_with_failure_handling(self, db_session):
        """
        E2E Test: Workflow with step failures

        Flow:
        1. Execute workflow with invalid step
        2. Verify failure handled correctly
        3. Check workflow continues (stop_on_failure=false)
        """
        yaml_content = """
name: "Failure Test Workflow"
settings:
  retry_count: 0
  stop_on_failure: false

steps:
  - id: valid_step
    type: channel_calibration
    calibration_type: temporal
    on_failure: continue
    parameters:
      scenario:
        type: UMa
        condition: LOS

  - id: invalid_step
    type: channel_calibration
    calibration_type: invalid_type
    on_failure: continue

  - id: another_valid_step
    type: channel_calibration
    calibration_type: doppler
    on_failure: continue
    parameters:
      velocity_kmh: 120
"""
        workflow = WorkflowParser.parse_string(yaml_content)
        executor = WorkflowExecutor(db_session)
        execution = executor.create_execution(workflow)
        execution = executor.run(execution)

        # Workflow should complete despite failure
        assert execution.status == WorkflowStatus.COMPLETED

        # Check step results
        assert execution.step_results["valid_step"].status == StepStatus.COMPLETED
        assert execution.step_results["invalid_step"].status == StepStatus.FAILED
        assert execution.step_results["another_valid_step"].status == StepStatus.COMPLETED

        # 1 passed, 1 failed, 1 passed = total 3, failed 1
        assert execution.failed_steps >= 1

    def test_e2e_api_workflow_execution(self, client, db_session):
        """
        E2E Test: API Workflow Execution

        Flow:
        1. Execute workflow via API
        2. Get execution status via API
        3. Generate report via API
        """
        # Step 1: Execute workflow
        response = client.post(
            "/api/v1/workflows/execute",
            json={
                "workflow_id": "quick_validation",
                "parameter_overrides": {
                    "fc_ghz": 3.5,
                    "calibrated_by": "api_e2e_test"
                }
            }
        )
        assert response.status_code == 202

        exec_data = response.json()
        assert exec_data["workflow_name"] == "Quick Validation"
        assert "id" in exec_data
        execution_id = exec_data["id"]

        # Step 2: Get execution status
        response = client.get(f"/api/v1/workflows/executions/{execution_id}")
        assert response.status_code == 200

        status_data = response.json()
        assert status_data["id"] == execution_id
        assert status_data["status"] in ["completed", "failed"]
        assert status_data["session_id"] is not None

        # Step 3: Generate report
        response = client.post(
            "/api/v1/calibration-reports/channel",
            json={
                "session_id": status_data["session_id"],
                "calibration_type": None
            }
        )
        assert response.status_code == 200

        report_data = response.json()
        assert report_data["success"] is True
        assert "report_path" in report_data

        # Cleanup report file
        if os.path.exists(report_data["report_path"]):
            os.remove(report_data["report_path"])

    def test_e2e_comprehensive_report_generation(self, client, db_session):
        """
        E2E Test: Comprehensive Report

        Flow:
        1. Execute workflow to create calibration data
        2. Generate comprehensive report (probe + channel)
        3. Verify report contains all sections
        """
        # Execute workflow first
        response = client.post(
            "/api/v1/workflows/execute",
            json={"workflow_id": "quick_validation"}
        )
        assert response.status_code == 202

        # Generate comprehensive report
        response = client.post(
            "/api/v1/calibration-reports/comprehensive",
            json={
                "include_probe": True,
                "include_channel": True,
                "title": "E2E Test Comprehensive Report"
            }
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "report_path" in data

        # Verify file exists and has content
        report_path = data["report_path"]
        assert os.path.exists(report_path)
        assert os.path.getsize(report_path) > 1000  # Should be > 1KB

        # Cleanup
        os.remove(report_path)

    def test_e2e_calibration_service_direct(self, db_session):
        """
        E2E Test: Direct Service Usage

        Flow:
        1. Create session via service
        2. Run calibrations via service
        3. Complete session
        4. Verify all data persisted
        """
        service = ChannelCalibrationService(db_session)

        # Create session
        session = service.create_session(
            name="E2E Direct Service Test",
            description="Testing direct service calls",
        )
        assert session is not None
        assert session.id is not None

        # Run calibrations
        temporal = service.run_temporal_calibration(
            scenario_type="UMa",
            scenario_condition="LOS",
            fc_ghz=3.5,
            session_id=session.id,
            calibrated_by="e2e_test",
        )
        assert temporal.id is not None
        assert temporal.session_id == session.id

        doppler = service.run_doppler_calibration(
            velocity_kmh=120,
            fc_ghz=3.5,
            session_id=session.id,
            calibrated_by="e2e_test",
        )
        assert doppler.id is not None
        assert doppler.session_id == session.id

        spatial = service.run_spatial_correlation_calibration(
            scenario_type="UMa",
            scenario_condition="NLOS",
            fc_ghz=3.5,
            antenna_spacing_wavelengths=0.5,
            session_id=session.id,
            calibrated_by="e2e_test",
        )
        assert spatial.id is not None

        # Complete session
        service.complete_session(
            session_id=session.id,
            overall_pass=True,
            total_calibrations=3,
            passed_calibrations=3,
            failed_calibrations=0,
        )

        # Verify session updated
        updated_session = db_session.query(ChannelCalibrationSession).filter(
            ChannelCalibrationSession.id == session.id
        ).first()

        assert updated_session.status == "completed"
        assert updated_session.total_calibrations == 3
        assert updated_session.overall_pass is True

    def test_e2e_list_calibrations(self, db_session):
        """
        E2E Test: List and Query Calibrations

        Flow:
        1. Create multiple calibrations
        2. List by type
        3. Verify filtering works
        """
        service = ChannelCalibrationService(db_session)

        # Create session
        session = service.create_session(name="List Test Session")

        # Create multiple calibrations
        for scenario in ["UMa", "UMi"]:
            for condition in ["LOS", "NLOS"]:
                service.run_temporal_calibration(
                    scenario_type=scenario,
                    scenario_condition=condition,
                    fc_ghz=3.5,
                    session_id=session.id,
                )

        for velocity in [30, 60, 90, 120]:
            service.run_doppler_calibration(
                velocity_kmh=velocity,
                fc_ghz=3.5,
                session_id=session.id,
            )

        # Query calibrations directly from database
        temporal_count = db_session.query(TemporalChannelCalibration).filter(
            TemporalChannelCalibration.session_id == session.id
        ).count()
        doppler_count = db_session.query(DopplerCalibration).filter(
            DopplerCalibration.session_id == session.id
        ).count()

        assert temporal_count == 4
        assert doppler_count == 4

        # Use list_calibrations by type (returns List[Dict])
        temporal_list = service.list_calibrations(calibration_type="temporal")
        assert len(temporal_list) >= 4

        doppler_list = service.list_calibrations(calibration_type="doppler")
        assert len(doppler_list) >= 4


class TestE2EAPIIntegration:
    """API integration tests"""

    @pytest.fixture
    def client(self):
        """Create test client"""
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
        app.dependency_overrides.clear()

    def test_api_full_workflow_lifecycle(self, client):
        """
        E2E API Test: Full Workflow Lifecycle

        1. List predefined workflows
        2. Get workflow details
        3. Execute workflow
        4. Check execution status
        5. List executions
        """
        # 1. List workflows
        response = client.get("/api/v1/workflows/predefined")
        assert response.status_code == 200
        workflows = response.json()
        assert workflows["total"] >= 2

        # 2. Get details
        response = client.get("/api/v1/workflows/predefined/quick_validation")
        assert response.status_code == 200
        details = response.json()
        assert details["name"] == "Quick Validation"
        assert len(details["steps"]) == 2

        # 3. Execute
        response = client.post(
            "/api/v1/workflows/execute",
            json={"workflow_id": "quick_validation"}
        )
        assert response.status_code == 202
        execution = response.json()
        exec_id = execution["id"]

        # 4. Check status
        response = client.get(f"/api/v1/workflows/executions/{exec_id}")
        assert response.status_code == 200
        status = response.json()
        assert status["id"] == exec_id

        # 5. List executions
        response = client.get("/api/v1/workflows/executions")
        assert response.status_code == 200
        executions = response.json()
        assert executions["total"] >= 1

    def test_api_parse_and_execute_custom_workflow(self, client):
        """
        E2E API Test: Custom Workflow

        1. Parse YAML
        2. Execute custom workflow
        """
        yaml_content = """
name: "API Custom Test"
steps:
  - id: wait_step
    type: wait
    parameters:
      seconds: 0.01
  - id: notify_step
    type: notify
    parameters:
      message: "API E2E test complete"
"""
        # Parse
        response = client.post(
            "/api/v1/workflows/parse",
            json={"yaml_content": yaml_content}
        )
        assert response.status_code == 200
        parse_result = response.json()
        assert parse_result["valid"] is True
        assert parse_result["workflow"]["name"] == "API Custom Test"

        # Execute
        response = client.post(
            "/api/v1/workflows/execute",
            json={"yaml_content": yaml_content}
        )
        assert response.status_code == 202
        execution = response.json()
        assert execution["status"] in ["completed", "running", "pending"]

    def test_api_report_endpoints(self, client):
        """
        E2E API Test: Report Generation Endpoints
        """
        # Comprehensive
        response = client.post(
            "/api/v1/calibration-reports/comprehensive",
            json={"title": "API Test Report"}
        )
        assert response.status_code == 200

        # Probe
        response = client.post(
            "/api/v1/calibration-reports/probe",
            json={}
        )
        assert response.status_code == 200

        # Channel
        response = client.post(
            "/api/v1/calibration-reports/channel",
            json={}
        )
        assert response.status_code == 200

    def test_api_health_check(self, client):
        """
        E2E API Test: Health Check
        """
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
