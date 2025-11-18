"""Test Plan Management Services"""
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import logging

from app.models.test_plan import (
    TestPlan,
    TestCase,
    TestExecution,
    TestQueue,
    TestSequence,
    TestPlanStatus,
)

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

        logger.info(f"Created test plan: {test_plan.id} - {name}")
        return test_plan

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
        """Delete a test plan"""
        test_plan = self.get_test_plan(db, test_plan_id)
        if not test_plan:
            return False

        # Check if it's running or queued
        if test_plan.status in [TestPlanStatus.RUNNING, TestPlanStatus.QUEUED]:
            logger.warning(f"Cannot delete running/queued test plan: {test_plan_id}")
            return False

        db.delete(test_plan)
        db.commit()

        logger.info(f"Deleted test plan: {test_plan_id}")
        return True

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

        db.commit()
        db.refresh(test_plan)

        logger.info(f"Cancelled test plan {test_plan_id}")
        return test_plan
