"""Test Plan Management Services"""
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import logging

from app.models.test_plan import (
    TestPlan,
    TestCase,
    TestStep,
    TestExecution,
    TestQueue,
    TestSequence,
    TestPlanStatus,
    TestPlanExecution,
)
from app.models.report import TestReport

logger = logging.getLogger(__name__)


class TestPlanService:
    """Service for managing test plans"""

    def create_test_plan(
        self,
        db: Session,
        name: str,
        created_by: str,
        description: Optional[str] = None,
        test_case_ids: Optional[List[str]] = None,
        **kwargs
    ) -> TestPlan:
        """Create a new test plan"""
        test_case_ids = test_case_ids or []

        test_plan = TestPlan(
            name=name,
            description=description,
            created_by=created_by,
            test_case_ids=test_case_ids,
            total_test_cases=len(test_case_ids),
            status=TestPlanStatus.DRAFT,
            **kwargs
        )

        db.add(test_plan)
        db.commit()
        db.refresh(test_plan)

        # Auto-generate test steps for Virtual Road Test scenarios
        if 'scenario_id' in kwargs and kwargs['scenario_id']:
            logger.info(f"Auto-generating test steps for scenario-based plan: {test_plan.id}")
            self._create_road_test_steps(db, test_plan, kwargs.get('test_environment', {}))

        logger.info(f"Created test plan: {test_plan.id} - {name}")
        return test_plan

    def _create_road_test_steps(
        self,
        db: Session,
        test_plan: TestPlan,
        test_environment: dict
    ) -> None:
        """
        Create standard test steps for Virtual Road Test scenarios

        Automatically generates 8 standard test steps based on Road Test sequence library.
        If scenario has pre-configured step_configuration, use those settings;
        otherwise use defaults from test_environment.
        """
        # Get Road Test sequences in correct order
        road_test_sequences = db.query(TestSequence).filter(
            TestSequence.category.like("Road Test%")
        ).order_by(TestSequence.created_at.asc()).all()

        if len(road_test_sequences) != 8:
            logger.warning(f"Expected 8 Road Test sequences, found {len(road_test_sequences)}")
            return

        # Extract step_configuration from test_environment if present
        step_config = test_environment.get('step_configuration', {}) or {}

        # Define step configurations based on test environment and step_configuration
        # Priority: step_config (from scenario) > test_environment > defaults
        env_cfg = step_config.get('environment_setup', {})
        chamber_cfg = step_config.get('chamber_init', {})
        network_cfg = step_config.get('network_config', {})
        bs_cfg = step_config.get('base_station_setup', {})
        mapper_cfg = step_config.get('ota_mapper', {})
        route_cfg = step_config.get('route_execution', {})
        kpi_cfg = step_config.get('kpi_validation', {})
        report_cfg = step_config.get('report_generation', {})

        step_configs = [
            {
                "sequence_name": "Configure Digital Twin Environment",
                "parameters": {
                    "channel_model_type": env_cfg.get("channel_model", {}).get("type") or "3gpp-statistical",
                    "scenario": env_cfg.get("channel_model", {}).get("scenario") or "UMa",
                    "los_condition": env_cfg.get("channel_model", {}).get("los_condition") or "auto",
                    "interference_enabled": env_cfg.get("interference", {}).get("enabled", False),
                    "scatterers_enabled": env_cfg.get("scatterers", {}).get("enabled", False),
                    "precompute_channel": env_cfg.get("precompute_channel", {}).get("enabled", False),
                    "validate_environment": env_cfg.get("validate_environment", True),
                    "environment_file": env_cfg.get("environment_file")
                },
                "timeout_seconds": env_cfg.get("timeout_seconds", 120)
            },
            {
                "sequence_name": "Initialize OTA Chamber (MPAC)",
                "parameters": {
                    "chamber_id": chamber_cfg.get("chamber_id") or test_environment.get("chamber_id", "MPAC-1"),
                    "verify_connections": chamber_cfg.get("verify_connections", True),
                    "calibrate_position_table": chamber_cfg.get("calibrate_position_table", True)
                },
                "timeout_seconds": chamber_cfg.get("timeout_seconds", 300)
            },
            {
                "sequence_name": "Configure Network",
                "parameters": {
                    "frequency_mhz": network_cfg.get("frequency_mhz") or test_environment.get("frequency_mhz", 3500),
                    "bandwidth_mhz": network_cfg.get("bandwidth_mhz") or test_environment.get("bandwidth_mhz", 100),
                    "technology": network_cfg.get("technology") or test_environment.get("technology", "5G NR"),
                    "verify_signal": network_cfg.get("verify_signal", True)
                },
                "timeout_seconds": network_cfg.get("timeout_seconds", 240)
            },
            {
                "sequence_name": "Setup Base Stations and Channel Model",
                "parameters": {
                    "channel_model": bs_cfg.get("channel_model") or test_environment.get("channel_model", "UMa"),
                    "num_base_stations": bs_cfg.get("num_base_stations") or test_environment.get("num_base_stations", 3),
                    "bs_positions": bs_cfg.get("bs_positions") or test_environment.get("bs_positions", []),
                    "verify_coverage": bs_cfg.get("verify_coverage", True)
                },
                "timeout_seconds": bs_cfg.get("timeout_seconds", 300)
            },
            {
                "sequence_name": "Configure OTA Mapper",
                "parameters": {
                    "route_file": mapper_cfg.get("route_file") or test_environment.get("route_file", ""),
                    "route_type": mapper_cfg.get("route_type") or test_environment.get("route_type", "urban"),
                    "update_rate_hz": mapper_cfg.get("update_rate_hz", 10),
                    "enable_handover": mapper_cfg.get("enable_handover", True),
                    "position_tolerance_m": mapper_cfg.get("position_tolerance_m", 1.0)
                },
                "timeout_seconds": mapper_cfg.get("timeout_seconds", 180)
            },
            {
                "sequence_name": "Execute Route Test",
                "parameters": {
                    "route_duration_s": route_cfg.get("route_duration_s") or test_environment.get("duration_s", 1800),
                    "total_distance_m": route_cfg.get("total_distance_m") or test_environment.get("total_distance_m", 5000),
                    "environment_type": route_cfg.get("environment_type") or test_environment.get("environment_type", "urban"),
                    "monitor_kpis": route_cfg.get("monitor_kpis", True),
                    "log_interval_s": route_cfg.get("log_interval_s", 1),
                    "auto_screenshot": route_cfg.get("auto_screenshot", True)
                },
                "timeout_seconds": route_cfg.get("timeout_seconds") or (test_environment.get("duration_s", 1800) + 300)  # Add 5min buffer
            },
            {
                "sequence_name": "Validate KPIs and Performance Metrics",
                "parameters": {
                    "kpi_thresholds": kpi_cfg.get("kpi_thresholds", {
                        "min_throughput_mbps": 50,
                        "max_latency_ms": 50,
                        "min_rsrp_dbm": -110,
                        "max_packet_loss_percent": 5
                    }),
                    "generate_plots": kpi_cfg.get("generate_plots", True)
                },
                "timeout_seconds": kpi_cfg.get("timeout_seconds", 300)
            },
            {
                "sequence_name": "Generate Test Report",
                "parameters": {
                    "report_format": report_cfg.get("report_format", "pdf"),
                    "include_raw_data": report_cfg.get("include_raw_data", False),
                    "include_screenshots": report_cfg.get("include_screenshots", True),
                    "include_recommendations": report_cfg.get("include_recommendations", True)
                },
                "timeout_seconds": report_cfg.get("timeout_seconds", 180)
            }
        ]

        # Create TestStep instances
        for idx, config in enumerate(step_configs):
            # Find matching sequence
            sequence = next(
                (seq for seq in road_test_sequences if seq.name == config["sequence_name"]),
                None
            )

            if not sequence:
                logger.warning(f"Sequence not found: {config['sequence_name']}")
                continue

            # Create test step
            test_step = TestStep(
                test_plan_id=test_plan.id,
                sequence_library_id=sequence.id,
                order=idx,
                parameters=config["parameters"],
                timeout_seconds=config["timeout_seconds"],
                retry_count=0,
                continue_on_failure=False,
                status="pending"
            )
            db.add(test_step)

            # Increment sequence usage count
            sequence.usage_count = (sequence.usage_count or 0) + 1

        db.commit()
        logger.info(f"Created {len(step_configs)} test steps for plan {test_plan.id}")

    def get_test_plan(self, db: Session, test_plan_id: UUID) -> Optional[TestPlan]:
        """Get a test plan by ID"""
        return db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()

    def list_test_plans(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> List[TestPlan]:
        """List test plans with filters"""
        query = db.query(TestPlan)

        if status:
            query = query.filter(TestPlan.status == status)
        if created_by:
            query = query.filter(TestPlan.created_by == created_by)

        query = query.order_by(TestPlan.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def update_test_plan(
        self,
        db: Session,
        test_plan_id: UUID,
        **kwargs
    ) -> Optional[TestPlan]:
        """Update a test plan"""
        test_plan = self.get_test_plan(db, test_plan_id)
        if not test_plan:
            return None

        # Update test_case count if test_case_ids changed
        if 'test_case_ids' in kwargs:
            kwargs['total_test_cases'] = len(kwargs['test_case_ids'])

        for key, value in kwargs.items():
            if value is not None and hasattr(test_plan, key):
                setattr(test_plan, key, value)

        db.commit()
        db.refresh(test_plan)

        logger.info(f"Updated test plan: {test_plan_id}")
        return test_plan

    def delete_test_plan(self, db: Session, test_plan_id: UUID) -> bool:
        """Delete a test plan and all associated records"""
        test_plan = self.get_test_plan(db, test_plan_id)
        if not test_plan:
            return False

        # Check if it's running or queued
        if test_plan.status in [TestPlanStatus.RUNNING, TestPlanStatus.QUEUED]:
            logger.warning(f"Cannot delete running/queued test plan: {test_plan_id}")
            return False

        try:
            # Delete associated records first (cascade manually)
            # 1. Delete test steps
            db.query(TestStep).filter(TestStep.test_plan_id == test_plan_id).delete()

            # 2. Delete from test queue
            db.query(TestQueue).filter(TestQueue.test_plan_id == test_plan_id).delete()

            # 3. Delete test plan execution history
            db.query(TestPlanExecution).filter(TestPlanExecution.test_plan_id == test_plan_id).delete()

            # 4. Delete test executions
            db.query(TestExecution).filter(TestExecution.test_plan_id == test_plan_id).delete()

            # 5. Unlink test reports (set test_plan_id to NULL, don't delete reports)
            db.query(TestReport).filter(TestReport.test_plan_id == test_plan_id).update(
                {TestReport.test_plan_id: None}
            )

            # Now delete the test plan itself
            db.delete(test_plan)
            db.commit()

            logger.info(f"Deleted test plan and associated records: {test_plan_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting test plan {test_plan_id}: {e}")
            raise

    def mark_ready(self, db: Session, test_plan_id: UUID) -> Optional[TestPlan]:
        """Mark test plan as ready for execution"""
        test_plan = self.get_test_plan(db, test_plan_id)
        if not test_plan:
            return None

        if test_plan.total_test_cases == 0:
            raise ValueError("Cannot mark empty test plan as ready")

        test_plan.status = TestPlanStatus.READY
        db.commit()
        db.refresh(test_plan)

        logger.info(f"Marked test plan {test_plan_id} as ready")
        return test_plan

    def batch_delete(self, db: Session, plan_ids: List[str]) -> dict:
        """Batch delete multiple test plans"""
        deleted_count = 0
        failed_ids = []

        for plan_id_str in plan_ids:
            try:
                plan_id = UUID(plan_id_str)
                test_plan = self.get_test_plan(db, plan_id)

                if test_plan:
                    # Check if plan is not in execution
                    if test_plan.status in [TestPlanStatus.RUNNING, TestPlanStatus.PAUSED]:
                        failed_ids.append({
                            "id": plan_id_str,
                            "reason": f"Cannot delete plan in {test_plan.status} status"
                        })
                        continue

                    db.delete(test_plan)
                    deleted_count += 1
                else:
                    failed_ids.append({
                        "id": plan_id_str,
                        "reason": "Test plan not found"
                    })
            except Exception as e:
                failed_ids.append({
                    "id": plan_id_str,
                    "reason": str(e)
                })

        db.commit()
        logger.info(f"Batch deleted {deleted_count} test plans")

        return {
            "deleted_count": deleted_count,
            "failed": failed_ids,
            "total_requested": len(plan_ids)
        }

    def batch_update_status(
        self,
        db: Session,
        plan_ids: List[str],
        new_status: str
    ) -> dict:
        """Batch update status for multiple test plans"""
        updated_count = 0
        failed_ids = []

        # Validate status
        try:
            status_enum = TestPlanStatus(new_status)
        except ValueError:
            raise ValueError(f"Invalid status: {new_status}")

        for plan_id_str in plan_ids:
            try:
                plan_id = UUID(plan_id_str)
                test_plan = self.get_test_plan(db, plan_id)

                if test_plan:
                    # Validate status transition
                    current_status = test_plan.status

                    # Only allow certain status transitions
                    if current_status == TestPlanStatus.RUNNING and status_enum not in [
                        TestPlanStatus.PAUSED,
                        TestPlanStatus.COMPLETED,
                        TestPlanStatus.FAILED,
                        TestPlanStatus.CANCELLED
                    ]:
                        failed_ids.append({
                            "id": plan_id_str,
                            "reason": f"Invalid transition from {current_status} to {new_status}"
                        })
                        continue

                    test_plan.status = status_enum
                    updated_count += 1
                else:
                    failed_ids.append({
                        "id": plan_id_str,
                        "reason": "Test plan not found"
                    })
            except Exception as e:
                failed_ids.append({
                    "id": plan_id_str,
                    "reason": str(e)
                })

        db.commit()
        logger.info(f"Batch updated status to {new_status} for {updated_count} test plans")

        return {
            "updated_count": updated_count,
            "failed": failed_ids,
            "total_requested": len(plan_ids),
            "new_status": new_status
        }

    def duplicate_test_plan(
        self,
        db: Session,
        test_plan_id: UUID,
        new_name: Optional[str] = None
    ) -> TestPlan:
        """
        Duplicate a test plan with all its steps

        Creates a copy of the test plan with a new ID and name.
        The copy will be in DRAFT status.
        """
        # Get the original test plan
        original = self.get_test_plan(db, test_plan_id)
        if not original:
            raise ValueError(f"Test plan {test_plan_id} not found")

        # Create new test plan with copied data
        duplicate_name = new_name or f"{original.name} (Copy)"

        duplicate = TestPlan(
            name=duplicate_name,
            description=original.description,
            version=original.version,
            status=TestPlanStatus.DRAFT,  # Always start as draft
            dut_info=original.dut_info,
            test_environment=original.test_environment,
            test_case_ids=original.test_case_ids.copy() if original.test_case_ids else [],
            total_test_cases=original.total_test_cases,
            priority=original.priority,
            created_by=original.created_by,
            notes=f"Duplicated from: {original.name}",
            tags=original.tags.copy() if original.tags else [],
            # Reset execution-related fields
            current_test_case_index=0,
            completed_test_cases=0,
            failed_test_cases=0,
            estimated_duration_minutes=original.estimated_duration_minutes,
            actual_duration_minutes=None,
            started_at=None,
            completed_at=None,
            queue_position=None
        )

        db.add(duplicate)
        db.flush()  # Get the ID for the duplicate

        # Copy all test steps
        step_service = TestStepService()
        original_steps = step_service.get_steps(db, test_plan_id)

        for original_step in original_steps:
            duplicate_step = TestStep(
                test_plan_id=duplicate.id,
                sequence_library_id=original_step.sequence_library_id,
                order=original_step.order,
                parameters=original_step.parameters.copy() if original_step.parameters else {},
                timeout_seconds=original_step.timeout_seconds,
                retry_count=original_step.retry_count,
                continue_on_failure=original_step.continue_on_failure,
                # Reset execution fields
                status='pending',
                result=None,
                error_message=None,
                started_at=None,
                completed_at=None
            )
            db.add(duplicate_step)

        db.commit()
        db.refresh(duplicate)

        logger.info(f"Duplicated test plan {test_plan_id} to {duplicate.id}")
        return duplicate

    def export_test_plans(
        self,
        db: Session,
        plan_ids: List[str]
    ) -> dict:
        """
        Export test plans to JSON format

        Parameters:
        - plan_ids: List of test plan UUIDs to export

        Returns:
        - Dictionary containing exported test plans with steps
        """
        import json
        from datetime import datetime

        exported_plans = []

        for plan_id_str in plan_ids:
            try:
                plan_id = UUID(plan_id_str)
                test_plan = self.get_test_plan(db, plan_id)

                if not test_plan:
                    continue

                # Get all steps for this plan
                step_service = TestStepService()
                steps = step_service.get_steps(db, plan_id)

                # Convert to exportable format
                plan_data = {
                    "name": test_plan.name,
                    "description": test_plan.description,
                    "version": test_plan.version,
                    "dut_info": test_plan.dut_info,
                    "test_environment": test_plan.test_environment,
                    "test_case_ids": test_plan.test_case_ids,
                    "priority": test_plan.priority,
                    "notes": test_plan.notes,
                    "tags": test_plan.tags,
                    "steps": [
                        {
                            "order": step.order,
                            "sequence_library_id": str(step.sequence_library_id),
                            "parameters": step.parameters,
                            "timeout_seconds": step.timeout_seconds,
                            "retry_count": step.retry_count,
                            "continue_on_failure": step.continue_on_failure
                        }
                        for step in steps
                    ],
                    "exported_at": datetime.utcnow().isoformat(),
                    "exported_from_id": str(test_plan.id)
                }

                exported_plans.append(plan_data)

            except Exception as e:
                logger.error(f"Error exporting plan {plan_id_str}: {e}")
                continue

        return {
            "version": "1.0",
            "export_date": datetime.utcnow().isoformat(),
            "test_plans": exported_plans,
            "count": len(exported_plans)
        }

    def import_test_plans(
        self,
        db: Session,
        import_data: dict,
        created_by: str
    ) -> List[TestPlan]:
        """
        Import test plans from JSON data

        Parameters:
        - import_data: Dictionary containing test plans to import
        - created_by: User performing the import

        Returns:
        - List of created test plans
        """
        if "test_plans" not in import_data:
            raise ValueError("Invalid import data: missing 'test_plans' key")

        imported_plans = []

        for plan_data in import_data["test_plans"]:
            try:
                # Extract steps before creating plan
                steps_data = plan_data.pop("steps", [])

                # Remove export metadata
                plan_data.pop("exported_at", None)
                plan_data.pop("exported_from_id", None)

                # Create the test plan
                test_plan = TestPlan(
                    name=plan_data.get("name", "Imported Plan"),
                    description=plan_data.get("description"),
                    version=plan_data.get("version", "1.0"),
                    status=TestPlanStatus.DRAFT,  # Always import as draft
                    dut_info=plan_data.get("dut_info"),
                    test_environment=plan_data.get("test_environment"),
                    test_case_ids=plan_data.get("test_case_ids", []),
                    total_test_cases=len(plan_data.get("test_case_ids", [])),
                    priority=plan_data.get("priority", 5),
                    created_by=created_by,
                    notes=plan_data.get("notes"),
                    tags=plan_data.get("tags", []),
                    # Reset execution fields
                    current_test_case_index=0,
                    completed_test_cases=0,
                    failed_test_cases=0
                )

                db.add(test_plan)
                db.flush()  # Get the ID

                # Import steps
                for step_data in steps_data:
                    test_step = TestStep(
                        test_plan_id=test_plan.id,
                        sequence_library_id=UUID(step_data["sequence_library_id"]),
                        order=step_data["order"],
                        parameters=step_data.get("parameters", {}),
                        timeout_seconds=step_data.get("timeout_seconds", 300),
                        retry_count=step_data.get("retry_count", 0),
                        continue_on_failure=step_data.get("continue_on_failure", False),
                        status='pending'
                    )
                    db.add(test_step)

                db.commit()
                db.refresh(test_plan)
                imported_plans.append(test_plan)

                logger.info(f"Imported test plan: {test_plan.id} - {test_plan.name}")

            except Exception as e:
                logger.error(f"Error importing plan: {e}")
                db.rollback()
                continue

        return imported_plans


class TestCaseService:
    """Service for managing test cases"""

    def create_test_case(
        self,
        db: Session,
        name: str,
        test_type: str,
        configuration: dict,
        created_by: str,
        **kwargs
    ) -> TestCase:
        """Create a new test case"""
        test_case = TestCase(
            name=name,
            test_type=test_type,
            configuration=configuration,
            created_by=created_by,
            **kwargs
        )

        db.add(test_case)
        db.commit()
        db.refresh(test_case)

        logger.info(f"Created test case: {test_case.id} - {name}")
        return test_case

    def get_test_case(self, db: Session, test_case_id: UUID) -> Optional[TestCase]:
        """Get a test case by ID"""
        return db.query(TestCase).filter(TestCase.id == test_case_id).first()

    def list_test_cases(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        test_type: Optional[str] = None,
        is_template: Optional[bool] = None
    ) -> List[TestCase]:
        """List test cases with filters"""
        query = db.query(TestCase)

        if test_type:
            query = query.filter(TestCase.test_type == test_type)
        if is_template is not None:
            query = query.filter(TestCase.is_template == is_template)

        query = query.order_by(TestCase.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def update_test_case(
        self,
        db: Session,
        test_case_id: UUID,
        **kwargs
    ) -> Optional[TestCase]:
        """Update a test case"""
        test_case = self.get_test_case(db, test_case_id)
        if not test_case:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(test_case, key):
                setattr(test_case, key, value)

        db.commit()
        db.refresh(test_case)

        logger.info(f"Updated test case: {test_case_id}")
        return test_case

    def delete_test_case(self, db: Session, test_case_id: UUID) -> bool:
        """Delete a test case"""
        test_case = self.get_test_case(db, test_case_id)
        if not test_case:
            return False

        db.delete(test_case)
        db.commit()

        logger.info(f"Deleted test case: {test_case_id}")
        return True


class TestStepService:
    """Service for managing test steps"""

    def get_steps(self, db: Session, test_plan_id: UUID) -> List[TestStep]:
        """Get all steps for a test plan, ordered by order field"""
        return db.query(TestStep).filter(
            TestStep.test_plan_id == test_plan_id
        ).order_by(TestStep.order.asc()).all()

    def create_test_step(
        self,
        db: Session,
        test_plan_id: UUID,
        step_number: int,
        name: str,
        type: str,
        parameters: dict,
        order: int,
        **kwargs
    ) -> TestStep:
        """Create a new test step"""
        # Verify test plan exists
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        test_step = TestStep(
            test_plan_id=test_plan_id,
            step_number=step_number,
            name=name,
            type=type,
            parameters=parameters,
            order=order,
            status="pending",
            **kwargs
        )

        db.add(test_step)
        db.commit()
        db.refresh(test_step)

        logger.info(f"Created test step: {test_step.id} - {name} for plan {test_plan_id}")
        return test_step

    def create_test_step_from_sequence(
        self,
        db: Session,
        test_plan_id: UUID,
        sequence_library_id: UUID,
        order: int,
        parameters: Optional[dict] = None,
        timeout_seconds: int = 300,
        retry_count: int = 0,
        continue_on_failure: bool = False
    ) -> TestStep:
        """Create a new test step from a sequence library item"""
        # Verify test plan exists
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        # Verify sequence exists
        sequence = db.query(TestSequence).filter(TestSequence.id == sequence_library_id).first()
        if not sequence:
            raise ValueError(f"Sequence {sequence_library_id} not found")

        # Create step with sequence reference
        test_step = TestStep(
            test_plan_id=test_plan_id,
            sequence_library_id=sequence_library_id,
            order=order,
            parameters=parameters or {},
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            continue_on_failure=continue_on_failure,
            status="pending"
        )

        db.add(test_step)
        db.commit()
        db.refresh(test_step)

        logger.info(f"Created test step from sequence {sequence_library_id} for plan {test_plan_id}")
        return test_step

    def get_test_steps(self, db: Session, test_plan_id: UUID) -> List[TestStep]:
        """Get all steps for a test plan"""
        return db.query(TestStep).filter(
            TestStep.test_plan_id == test_plan_id
        ).order_by(TestStep.order.asc()).all()

    def get_test_step(self, db: Session, step_id: UUID) -> Optional[TestStep]:
        """Get a test step by ID"""
        return db.query(TestStep).filter(TestStep.id == step_id).first()

    def update_test_step(
        self,
        db: Session,
        step_id: UUID,
        **kwargs
    ) -> Optional[TestStep]:
        """Update a test step"""
        test_step = self.get_test_step(db, step_id)
        if not test_step:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(test_step, key):
                setattr(test_step, key, value)

        db.add(test_step)
        db.commit()
        db.refresh(test_step)

        logger.info(f"Updated test step: {step_id}")
        return test_step

    def delete_test_step(self, db: Session, step_id: UUID) -> bool:
        """Delete a test step"""
        test_step = self.get_test_step(db, step_id)
        if not test_step:
            return False

        test_plan_id = test_step.test_plan_id
        db.delete(test_step)
        db.commit()

        # Reorder remaining steps
        self._reorder_steps(db, test_plan_id)

        logger.info(f"Deleted test step: {step_id}")
        return True

    def reorder_steps(
        self,
        db: Session,
        test_plan_id: UUID,
        step_ids: List[UUID]
    ) -> List[TestStep]:
        """Reorder steps in a test plan"""
        # Verify all steps belong to the test plan
        steps = db.query(TestStep).filter(
            TestStep.test_plan_id == test_plan_id,
            TestStep.id.in_(step_ids)
        ).all()

        if len(steps) != len(step_ids):
            raise ValueError("Some step IDs do not belong to this test plan")

        # Update order
        step_map = {str(step.id): step for step in steps}
        for idx, step_id in enumerate(step_ids):
            step = step_map[str(step_id)]
            step.order = idx

        db.commit()

        # Return reordered steps
        return self.get_test_steps(db, test_plan_id)

    def duplicate_step(
        self,
        db: Session,
        step_id: UUID
    ) -> TestStep:
        """Duplicate a test step"""
        original = self.get_test_step(db, step_id)
        if not original:
            raise ValueError(f"Test step {step_id} not found")

        # Get max order for the test plan
        max_order = db.query(TestStep).filter(
            TestStep.test_plan_id == original.test_plan_id
        ).count()

        # Create duplicate
        duplicate = TestStep(
            test_plan_id=original.test_plan_id,
            step_number=original.step_number + 1000,  # Temporary number
            name=f"{original.name} (Copy)",
            description=original.description,
            type=original.type,
            parameters=original.parameters.copy() if original.parameters else {},
            status="pending",
            order=max_order,
            expected_duration_minutes=original.expected_duration_minutes,
            validation_criteria=original.validation_criteria.copy() if original.validation_criteria else None,
            notes=original.notes,
            tags=original.tags.copy() if original.tags else None,
        )

        db.add(duplicate)
        db.commit()
        db.refresh(duplicate)

        logger.info(f"Duplicated test step {step_id} to {duplicate.id}")
        return duplicate

    def _reorder_steps(self, db: Session, test_plan_id: UUID):
        """Reorder steps after deletion"""
        steps = db.query(TestStep).filter(
            TestStep.test_plan_id == test_plan_id
        ).order_by(TestStep.order.asc()).all()

        for idx, step in enumerate(steps):
            step.order = idx

        db.commit()


class TestQueueService:
    """Service for managing test queue"""

    def queue_test_plan(
        self,
        db: Session,
        test_plan_id: UUID,
        queued_by: str,
        priority: int = 5,
        **kwargs
    ) -> TestQueue:
        """Add a test plan to the execution queue"""
        # Check if already queued
        existing = db.query(TestQueue).filter(
            TestQueue.test_plan_id == test_plan_id
        ).first()
        if existing:
            raise ValueError(f"Test plan {test_plan_id} is already queued")

        # Get test plan and validate
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        if test_plan.status not in [TestPlanStatus.READY, TestPlanStatus.DRAFT]:
            raise ValueError(f"Test plan must be in READY or DRAFT status to queue")

        # Calculate position (last position + 1)
        max_position = db.query(TestQueue).count()
        position = max_position + 1

        # Create queue entry
        queue_item = TestQueue(
            test_plan_id=test_plan_id,
            position=position,
            priority=priority,
            queued_by=queued_by,
            status="queued",
            **kwargs
        )

        # Update test plan status
        test_plan.status = TestPlanStatus.QUEUED
        test_plan.queue_position = position

        db.add(queue_item)
        db.add(test_plan)  # Explicitly add to ensure status change is tracked
        db.commit()
        db.refresh(queue_item)

        logger.info(f"Queued test plan {test_plan_id} at position {position}")
        return queue_item

    def get_queue(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[TestQueue]:
        """Get the current test queue"""
        return db.query(TestQueue).filter(
            TestQueue.status == "queued"
        ).order_by(
            TestQueue.priority.asc(),
            TestQueue.position.asc()
        ).offset(skip).limit(limit).all()

    def remove_from_queue(self, db: Session, test_plan_id: UUID) -> bool:
        """Remove a test plan from the queue"""
        queue_item = db.query(TestQueue).filter(
            TestQueue.test_plan_id == test_plan_id
        ).first()

        if not queue_item:
            return False

        # Update test plan status
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if test_plan:
            test_plan.status = TestPlanStatus.READY
            test_plan.queue_position = None

        db.delete(queue_item)
        db.commit()

        # Reorder queue
        self._reorder_queue(db)

        logger.info(f"Removed test plan {test_plan_id} from queue")
        return True

    def _reorder_queue(self, db: Session):
        """Reorder queue positions after removal"""
        queue_items = db.query(TestQueue).filter(
            TestQueue.status == "queued"
        ).order_by(TestQueue.position.asc()).all()

        for idx, item in enumerate(queue_items, start=1):
            item.position = idx

        db.commit()

    def reorder_queue(self, db: Session, queue_item_ids: List[str]) -> List[TestQueue]:
        """
        Reorder the execution queue

        Parameters:
        - queue_item_ids: List of queue item IDs in desired order

        Returns:
        - Updated list of queue items in new order
        """
        # Get all queue items
        queue_items = db.query(TestQueue).filter(
            TestQueue.id.in_([UUID(qid) for qid in queue_item_ids]),
            TestQueue.status == "queued"
        ).all()

        if len(queue_items) != len(queue_item_ids):
            raise ValueError("Some queue item IDs are invalid or not in queued status")

        # Create mapping from ID to item
        item_map = {str(item.id): item for item in queue_items}

        # Update positions according to the new order
        for idx, queue_id in enumerate(queue_item_ids, start=1):
            item = item_map.get(queue_id)
            if item:
                item.position = idx
                # Update test plan's queue position as well
                test_plan = db.query(TestPlan).filter(
                    TestPlan.id == item.test_plan_id
                ).first()
                if test_plan:
                    test_plan.queue_position = idx

        db.commit()

        # Return updated queue in order
        updated_queue = db.query(TestQueue).filter(
            TestQueue.status == "queued"
        ).order_by(TestQueue.position.asc()).all()

        logger.info(f"Reordered {len(queue_item_ids)} queue items")
        return updated_queue

    def update_queue_priority(
        self,
        db: Session,
        queue_item_id: UUID,
        new_priority: int
    ) -> TestQueue:
        """
        Update priority for a queue item

        Parameters:
        - queue_item_id: UUID of the queue item
        - new_priority: New priority value (1-10)

        Returns:
        - Updated queue item
        """
        if not 1 <= new_priority <= 10:
            raise ValueError("Priority must be between 1 and 10")

        queue_item = db.query(TestQueue).filter(
            TestQueue.id == queue_item_id
        ).first()

        if not queue_item:
            raise ValueError(f"Queue item {queue_item_id} not found")

        if queue_item.status != "queued":
            raise ValueError(f"Can only update priority for queued items")

        queue_item.priority = new_priority

        # Also update the test plan's priority
        test_plan = db.query(TestPlan).filter(
            TestPlan.id == queue_item.test_plan_id
        ).first()
        if test_plan:
            test_plan.priority = new_priority

        db.commit()
        db.refresh(queue_item)

        logger.info(f"Updated priority for queue item {queue_item_id} to {new_priority}")
        return queue_item

    def move_queue_item_up(self, db: Session, test_plan_id: UUID) -> TestQueue:
        """
        Move a queue item up (earlier in queue)

        Parameters:
        - test_plan_id: UUID of the test plan in the queue

        Returns:
        - Updated queue item
        """
        # Find the queue item for this test plan
        queue_item = db.query(TestQueue).filter(
            TestQueue.test_plan_id == test_plan_id,
            TestQueue.status == "queued"
        ).first()

        if not queue_item:
            raise ValueError(f"Test plan {test_plan_id} not found in queue")

        current_position = queue_item.position

        if current_position <= 1:
            raise ValueError("Item is already at the top of the queue")

        # Find the item above
        item_above = db.query(TestQueue).filter(
            TestQueue.position == current_position - 1,
            TestQueue.status == "queued"
        ).first()

        if not item_above:
            raise ValueError("No item found above in queue")

        # Swap positions
        queue_item.position = current_position - 1
        item_above.position = current_position

        # Update test plan queue positions
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if test_plan:
            test_plan.queue_position = current_position - 1

        test_plan_above = db.query(TestPlan).filter(
            TestPlan.id == item_above.test_plan_id
        ).first()
        if test_plan_above:
            test_plan_above.queue_position = current_position

        db.commit()
        db.refresh(queue_item)

        logger.info(f"Moved queue item for test plan {test_plan_id} up to position {queue_item.position}")
        return queue_item

    def move_queue_item_down(self, db: Session, test_plan_id: UUID) -> TestQueue:
        """
        Move a queue item down (later in queue)

        Parameters:
        - test_plan_id: UUID of the test plan in the queue

        Returns:
        - Updated queue item
        """
        # Find the queue item for this test plan
        queue_item = db.query(TestQueue).filter(
            TestQueue.test_plan_id == test_plan_id,
            TestQueue.status == "queued"
        ).first()

        if not queue_item:
            raise ValueError(f"Test plan {test_plan_id} not found in queue")

        current_position = queue_item.position

        # Get max position
        max_position = db.query(TestQueue).filter(
            TestQueue.status == "queued"
        ).count()

        if current_position >= max_position:
            raise ValueError("Item is already at the bottom of the queue")

        # Find the item below
        item_below = db.query(TestQueue).filter(
            TestQueue.position == current_position + 1,
            TestQueue.status == "queued"
        ).first()

        if not item_below:
            raise ValueError("No item found below in queue")

        # Swap positions
        queue_item.position = current_position + 1
        item_below.position = current_position

        # Update test plan queue positions
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if test_plan:
            test_plan.queue_position = current_position + 1

        test_plan_below = db.query(TestPlan).filter(
            TestPlan.id == item_below.test_plan_id
        ).first()
        if test_plan_below:
            test_plan_below.queue_position = current_position

        db.commit()
        db.refresh(queue_item)

        logger.info(f"Moved queue item for test plan {test_plan_id} down to position {queue_item.position}")
        return queue_item

    def move_to_top(self, db: Session, test_plan_id: UUID) -> TestQueue:
        """Move a queue item to the top (first in queue)"""
        queue_item = db.query(TestQueue).filter(
            TestQueue.test_plan_id == test_plan_id,
            TestQueue.status == "queued"
        ).first()

        if not queue_item:
            raise ValueError(f"Test plan {test_plan_id} not found in queue")

        if queue_item.position == 1:
            return queue_item  # Already at top

        # Shift all items down
        items_above = db.query(TestQueue).filter(
            TestQueue.position < queue_item.position,
            TestQueue.status == "queued"
        ).all()

        for item in items_above:
            item.position += 1
            # Update associated test plan
            tp = db.query(TestPlan).filter(TestPlan.id == item.test_plan_id).first()
            if tp:
                tp.queue_position = item.position

        # Move this item to top
        queue_item.position = 1
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if test_plan:
            test_plan.queue_position = 1

        db.commit()
        db.refresh(queue_item)

        logger.info(f"Moved queue item for test plan {test_plan_id} to top")
        return queue_item

    def move_to_bottom(self, db: Session, test_plan_id: UUID) -> TestQueue:
        """Move a queue item to the bottom (last in queue)"""
        queue_item = db.query(TestQueue).filter(
            TestQueue.test_plan_id == test_plan_id,
            TestQueue.status == "queued"
        ).first()

        if not queue_item:
            raise ValueError(f"Test plan {test_plan_id} not found in queue")

        max_position = db.query(TestQueue).filter(
            TestQueue.status == "queued"
        ).count()

        if queue_item.position == max_position:
            return queue_item  # Already at bottom

        # Shift all items below up
        items_below = db.query(TestQueue).filter(
            TestQueue.position > queue_item.position,
            TestQueue.status == "queued"
        ).all()

        for item in items_below:
            item.position -= 1
            # Update associated test plan
            tp = db.query(TestPlan).filter(TestPlan.id == item.test_plan_id).first()
            if tp:
                tp.queue_position = item.position

        # Move this item to bottom
        queue_item.position = max_position
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if test_plan:
            test_plan.queue_position = max_position

        db.commit()
        db.refresh(queue_item)

        logger.info(f"Moved queue item for test plan {test_plan_id} to bottom")
        return queue_item

    def get_queue_item_by_test_plan(self, db: Session, test_plan_id: UUID) -> Optional[TestQueue]:
        """Get queue item by test plan ID"""
        return db.query(TestQueue).filter(
            TestQueue.test_plan_id == test_plan_id,
            TestQueue.status == "queued"
        ).first()


class TestExecutionService:
    """Service for managing test execution"""

    def start_test_plan(
        self,
        db: Session,
        test_plan_id: UUID,
        started_by: str
    ) -> TestPlan:
        """Start executing a test plan"""
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        if test_plan.status not in [TestPlanStatus.READY, TestPlanStatus.QUEUED]:
            raise ValueError(f"Test plan must be READY or QUEUED to start")

        # Update status
        test_plan.status = TestPlanStatus.RUNNING
        test_plan.started_at = datetime.utcnow()
        test_plan.current_test_case_index = 0
        test_plan.completed_test_cases = 0
        test_plan.failed_test_cases = 0

        db.commit()
        db.refresh(test_plan)

        logger.info(f"Started test plan {test_plan_id} by {started_by}")
        return test_plan

    def complete_test_plan(
        self,
        db: Session,
        test_plan_id: UUID
    ) -> TestPlan:
        """Mark test plan as completed"""
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        test_plan.status = TestPlanStatus.COMPLETED
        test_plan.completed_at = datetime.utcnow()

        if test_plan.started_at:
            duration = (test_plan.completed_at - test_plan.started_at).total_seconds() / 60
            test_plan.actual_duration_minutes = duration

        db.commit()

        # Create plan-level execution history record
        from app.models.test_plan import TestPlanExecution
        total_steps = test_plan.total_test_cases or 0
        completed_steps = test_plan.completed_test_cases or total_steps
        failed_steps = test_plan.failed_test_cases or 0
        skipped_steps = max(0, total_steps - completed_steps - failed_steps)
        success_rate = (completed_steps / total_steps) if total_steps > 0 else 1.0

        plan_execution = TestPlanExecution(
            test_plan_id=test_plan_id,
            test_plan_name=test_plan.name,
            test_plan_version=test_plan.version or "1.0",
            status="completed",
            total_steps=total_steps,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            skipped_steps=skipped_steps,
            success_rate=success_rate,
            started_at=test_plan.started_at or datetime.utcnow(),
            completed_at=test_plan.completed_at,
            duration_minutes=test_plan.actual_duration_minutes or 0.0,
            started_by=test_plan.created_by
        )
        db.add(plan_execution)
        db.commit()

        db.refresh(test_plan)

        logger.info(f"Completed test plan {test_plan_id}")
        return test_plan

    def pause_test_plan(self, db: Session, test_plan_id: UUID) -> TestPlan:
        """Pause a running test plan"""
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        if test_plan.status != TestPlanStatus.RUNNING:
            raise ValueError("Can only pause running test plans")

        test_plan.status = TestPlanStatus.PAUSED
        db.commit()
        db.refresh(test_plan)

        logger.info(f"Paused test plan {test_plan_id}")
        return test_plan

    def resume_test_plan(self, db: Session, test_plan_id: UUID) -> TestPlan:
        """Resume a paused test plan"""
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        if test_plan.status != TestPlanStatus.PAUSED:
            raise ValueError("Can only resume paused test plans")

        test_plan.status = TestPlanStatus.RUNNING
        db.commit()
        db.refresh(test_plan)

        logger.info(f"Resumed test plan {test_plan_id}")
        return test_plan

    def cancel_test_plan(self, db: Session, test_plan_id: UUID) -> TestPlan:
        """Cancel a test plan"""
        test_plan = db.query(TestPlan).filter(TestPlan.id == test_plan_id).first()
        if not test_plan:
            raise ValueError(f"Test plan {test_plan_id} not found")

        if test_plan.status == TestPlanStatus.COMPLETED:
            raise ValueError("Cannot cancel completed test plan")

        test_plan.status = TestPlanStatus.CANCELLED
        test_plan.completed_at = datetime.utcnow()

        # Calculate duration if started
        if test_plan.started_at:
            duration = (test_plan.completed_at - test_plan.started_at).total_seconds() / 60
            test_plan.actual_duration_minutes = duration

        db.commit()

        # Create plan-level execution history record
        from app.models.test_plan import TestPlanExecution
        total_steps = test_plan.total_test_cases or 0
        completed_steps = test_plan.completed_test_cases or 0
        failed_steps = test_plan.failed_test_cases or 0
        skipped_steps = max(0, total_steps - completed_steps - failed_steps)
        success_rate = (completed_steps / total_steps) if total_steps > 0 else 0.0

        plan_execution = TestPlanExecution(
            test_plan_id=test_plan_id,
            test_plan_name=test_plan.name,
            test_plan_version=test_plan.version or "1.0",
            status="cancelled",
            total_steps=total_steps,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            skipped_steps=skipped_steps,
            success_rate=success_rate,
            started_at=test_plan.started_at or datetime.utcnow(),
            completed_at=test_plan.completed_at,
            duration_minutes=test_plan.actual_duration_minutes or 0.0,
            error_summary="Test plan was cancelled by user",
            started_by=test_plan.created_by
        )
        db.add(plan_execution)
        db.commit()

        db.refresh(test_plan)

        logger.info(f"Cancelled test plan {test_plan_id}")
        return test_plan


class TestSequenceService:
    """Service for managing test sequences (reusable step templates)"""

    def get_sequences(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
        is_public: Optional[bool] = None,
    ) -> tuple[List[TestSequence], int]:
        """Get test sequences with filters"""
        query = db.query(TestSequence)

        if category:
            query = query.filter(TestSequence.category == category)
        if is_public is not None:
            query = query.filter(TestSequence.is_public == is_public)

        total = query.count()
        sequences = query.order_by(
            TestSequence.usage_count.desc(),
            TestSequence.created_at.desc()
        ).offset(skip).limit(limit).all()

        return sequences, total

    def get_sequence(self, db: Session, sequence_id: UUID) -> Optional[TestSequence]:
        """Get a single test sequence by ID"""
        return db.query(TestSequence).filter(TestSequence.id == sequence_id).first()

    def get_categories(self, db: Session) -> List[str]:
        """Get all unique categories"""
        results = db.query(TestSequence.category).filter(
            TestSequence.category.isnot(None)
        ).distinct().all()
        return [r[0] for r in results if r[0]]

    def get_popular_sequences(
        self, db: Session, limit: int = 10
    ) -> List[TestSequence]:
        """Get most popular sequences by usage count"""
        return db.query(TestSequence).filter(
            TestSequence.is_public == True
        ).order_by(
            TestSequence.usage_count.desc()
        ).limit(limit).all()

    def increment_usage(self, db: Session, sequence_id: UUID) -> None:
        """Increment usage count when sequence is used"""
        sequence = self.get_sequence(db, sequence_id)
        if sequence:
            sequence.usage_count = (sequence.usage_count or 0) + 1
            db.commit()
            logger.info(f"Incremented usage count for sequence {sequence_id}")


class StatisticsService:
    """Service for generating statistics and analytics"""

    def get_test_plan_statistics(self, db: Session) -> dict:
        """Get overall test plan statistics"""
        from sqlalchemy import func

        total = db.query(func.count(TestPlan.id)).scalar() or 0

        # Count by status
        by_status = {}
        status_counts = db.query(
            TestPlan.status,
            func.count(TestPlan.id)
        ).group_by(TestPlan.status).all()

        for status, count in status_counts:
            by_status[status] = count

        # Calculate average duration for completed plans
        avg_duration = db.query(
            func.avg(TestPlan.actual_duration_minutes)
        ).filter(
            TestPlan.status == TestPlanStatus.COMPLETED,
            TestPlan.actual_duration_minutes.isnot(None)
        ).scalar() or 0

        # Calculate success rate
        completed = by_status.get(TestPlanStatus.COMPLETED, 0)
        failed = by_status.get(TestPlanStatus.FAILED, 0)
        total_finished = completed + failed
        success_rate = (completed / total_finished * 100) if total_finished > 0 else 0

        return {
            "total": total,
            "by_status": by_status,
            "avg_duration_minutes": round(avg_duration, 2),
            "success_rate": round(success_rate, 2)
        }

    def get_execution_statistics(
        self,
        db: Session,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> dict:
        """Get execution statistics with optional date filtering"""
        from sqlalchemy import func
        from datetime import datetime, timedelta

        query = db.query(TestExecution)

        # Apply date filters
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(TestExecution.started_at >= start_dt)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(TestExecution.started_at <= end_dt)

        # Total executions
        total_executions = query.count()

        # Total duration (convert from seconds to minutes)
        total_duration = db.query(
            func.sum(TestExecution.duration_sec)
        ).filter(
            TestExecution.duration_sec.isnot(None)
        )
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            total_duration = total_duration.filter(TestExecution.started_at >= start_dt)
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            total_duration = total_duration.filter(TestExecution.started_at <= end_dt)

        total_duration_sec = total_duration.scalar() or 0
        total_duration_value = total_duration_sec / 60  # Convert to minutes

        # Average duration
        avg_duration = (total_duration_value / total_executions) if total_executions > 0 else 0

        # Success rate
        completed_query = query.filter(TestExecution.status == 'completed')
        failed_query = query.filter(TestExecution.status == 'failed')

        completed_count = completed_query.count()
        failed_count = failed_query.count()
        total_finished = completed_count + failed_count

        success_rate = (completed_count / total_finished * 100) if total_finished > 0 else 0

        # Executions by day (last 30 days or within date range)
        if not start_date:
            start_dt = datetime.utcnow() - timedelta(days=30)
        else:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))

        if not end_date:
            end_dt = datetime.utcnow()
        else:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        executions_by_day = []
        current_date = start_dt.date()
        end = end_dt.date()

        while current_date <= end:
            day_start = datetime.combine(current_date, datetime.min.time())
            day_end = datetime.combine(current_date, datetime.max.time())

            count = db.query(func.count(TestExecution.id)).filter(
                TestExecution.started_at >= day_start,
                TestExecution.started_at <= day_end
            ).scalar() or 0

            executions_by_day.append({
                "date": current_date.isoformat(),
                "count": count
            })

            current_date += timedelta(days=1)

        return {
            "total_executions": total_executions,
            "total_duration_minutes": round(total_duration_value, 2),
            "avg_duration_minutes": round(avg_duration, 2),
            "success_rate": round(success_rate, 2),
            "executions_by_day": executions_by_day
        }