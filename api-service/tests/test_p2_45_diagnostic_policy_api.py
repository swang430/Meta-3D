from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.test_plan import update_test_case_execution_policy
from app.db.database import Base
from app.models.test_plan import TestCase
from app.schemas.test_plan import TestCaseExecutionPolicyUpdate


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _case(db):
    row = TestCase(
        name="LTE diagnostic",
        test_type="MIMO_OTA",
        configuration={"precheck_strict_cal": False},
        created_by="test",
    )
    db.add(row)
    db.commit()
    return row


def test_dedicated_policy_endpoint_records_server_owned_testcase_audit(db):
    row = _case(db)

    response = update_test_case_execution_policy(
        row.id,
        TestCaseExecutionPolicyUpdate(
            mode="diagnostic",
            reason="现场先打通硬件，待校准后正式复测",
            updated_by="site-operator",
        ),
        db,
    )

    db.refresh(row)
    assert response.test_case_id == row.id
    assert response.policy.mode == "diagnostic"
    assert response.policy.updated_at.tzinfo is not None
    assert row.execution_policy == response.policy.model_dump(mode="json")


def test_return_to_formal_is_an_audited_update_not_silent_delete(db):
    row = _case(db)
    first = update_test_case_execution_policy(
        row.id,
        TestCaseExecutionPolicyUpdate(
            mode="diagnostic",
            reason="initial bring-up",
            updated_by="operator-a",
        ),
        db,
    )
    second = update_test_case_execution_policy(
        row.id,
        TestCaseExecutionPolicyUpdate(
            mode="formal",
            reason="校准完成，恢复正式候选",
            updated_by="quality-owner",
        ),
        db,
    )

    assert second.policy.mode == "formal"
    assert second.policy.updated_by == "quality-owner"
    assert second.policy.updated_at >= first.policy.updated_at
    assert row.execution_policy is not None


def test_policy_endpoint_rejects_missing_case_and_unstructured_audit(db):
    with pytest.raises(Exception) as exc_info:
        update_test_case_execution_policy(
            uuid4(),
            TestCaseExecutionPolicyUpdate(
                mode="diagnostic",
                reason="bring-up",
                updated_by="operator",
            ),
            db,
        )
    assert getattr(exc_info.value, "status_code", None) == 404

    for field in ("reason", "updated_by"):
        with pytest.raises(ValidationError):
            TestCaseExecutionPolicyUpdate.model_validate(
                {
                    "mode": "diagnostic",
                    "reason": "valid",
                    "updated_by": "operator",
                    field: " ",
                }
            )


def test_legacy_configuration_flag_does_not_create_server_policy(db):
    row = _case(db)
    assert row.configuration["precheck_strict_cal"] is False
    assert row.execution_policy is None
