"""Scenario Navigation API

Endpoints for navigating between scenarios and test plans.
Enables creating test plans from scenarios and querying test plans by scenario.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.database import get_db
from app.models.test_plan import TestPlan
from app.schemas.test_plan import TestPlanResponse, TestPlanCreate
from app.services.test_plan_service import TestPlanService
from app.data.scenario_library import get_scenario_by_id

router = APIRouter(prefix="/scenarios", tags=["Scenario Navigation"])


@router.post("/{scenario_id}/create-test-plan", response_model=TestPlanResponse, status_code=201)
def create_test_plan_from_scenario(
    scenario_id: str,
    request: TestPlanCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new test plan from a scenario

    This creates a test plan linked to the specified scenario.
    The scenario_id will be stored in the test plan for reference.
    """
    # Note: scenario validation is optional - test plan can reference
    # any scenario_id including future or external scenarios

    service = TestPlanService()

    # Determine created_by
    created_by = request.created_by
    if created_by is None:
        created_by = "system"

    test_plan = service.create_test_plan(
        db=db,
        name=request.name,
        description=request.description or f"Test plan from scenario {scenario_id}",
        version=request.version,
        created_by=created_by,
        dut_info=request.dut_info or {},
        test_environment=request.test_environment or {},
        scenario_id=scenario_id,  # Link to the scenario
        test_case_ids=request.test_case_ids or [],
        priority=request.priority,
        notes=request.notes,
        tags=request.tags or [],
    )

    return test_plan


@router.get("/{scenario_id}/test-plans", response_model=List[TestPlanResponse])
def get_test_plans_by_scenario(
    scenario_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all test plans associated with a scenario

    Returns a list of test plans that were created from or linked to
    the specified scenario.
    """
    test_plans = db.query(TestPlan).filter(
        TestPlan.scenario_id == scenario_id
    ).order_by(TestPlan.created_at.desc()).all()

    return test_plans
