import sys
import os
import uuid
from sqlalchemy.orm import Session

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.database import SessionLocal, init_db
from app.services.test_plan_service import TestPlanService, TestStepService
from app.models.test_plan import TestPlan, TestStep

def verify_bug():
    print("Initializing DB...")
    init_db()
    db = SessionLocal()

    # 1. Create Test Plan
    print("Creating Test Plan...")
    plan_service = TestPlanService()
    plan = plan_service.create_test_plan(
        db=db,
        name=f"Bug Verify Plan {uuid.uuid4()}",
        created_by="tester"
    )
    print(f"Plan created: {plan.id}")

    # 2. Create Test Step
    print("Creating Test Step...")
    step_service = TestStepService()
    step = step_service.create_test_step(
        db=db,
        test_plan_id=plan.id,
        step_number=1,
        name="Step 1",
        type="test",
        parameters={},
        order=1,
        timeout_seconds=300,
        retry_count=0
    )
    print(f"Step created: {step.id}, timeout={step.timeout_seconds}, retry={step.retry_count}")

    # 3. Update Test Step
    print("Updating Test Step...")
    updated_step = step_service.update_test_step(
        db=db,
        step_id=step.id,
        timeout_seconds=900,
        retry_count=3
    )
    
    print(f"Update returned: timeout={updated_step.timeout_seconds}, retry={updated_step.retry_count}")

    # 4. Verify in DB (New Session)
    db.close()
    db2 = SessionLocal()
    step_from_db = db2.query(TestStep).filter(TestStep.id == step.id).first()
    
    print(f"DB Verification: timeout={step_from_db.timeout_seconds}, retry={step_from_db.retry_count}")

    if step_from_db.timeout_seconds == 900 and step_from_db.retry_count == 3:
        print("✅ BUG NOT REPRODUCED in Service Layer. It works.")
    else:
        print("❌ BUG REPRODUCED in Service Layer.")

    db2.close()

if __name__ == "__main__":
    verify_bug()
