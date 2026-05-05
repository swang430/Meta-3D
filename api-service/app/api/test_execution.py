"""Test Execution History API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from app.db.database import get_db
from app.schemas.test_plan import (
    TestPlanExecutionResponse,
    TestPlanExecutionListResponse,
)
from app.models.test_plan import TestPlanExecution, TestExecution

router = APIRouter(prefix="/test-executions", tags=["Test Execution History"])


# Schema for recent tests (matches frontend RecentTest type)
from pydantic import BaseModel
from typing import List


class RecentTestItem(BaseModel):
    id: str
    name: str
    dut: str
    result: str
    date: str


class RecentTestsResponse(BaseModel):
    recentTests: List[RecentTestItem]


@router.get("/recent", response_model=RecentTestsResponse)
def get_recent_tests(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get recent test executions for dashboard display

    Returns a simplified list of recent test executions.
    """
    try:
        executions = db.query(TestPlanExecution).order_by(
            TestPlanExecution.completed_at.desc()
        ).limit(limit).all()

        recent_tests = []
        for exe in executions:
            recent_tests.append(RecentTestItem(
                id=str(exe.id),
                name=exe.test_plan_name or "Unknown Plan",
                dut="DUT-001",  # Placeholder - could be extended to include actual DUT info
                result=exe.status or "unknown",
                date=exe.completed_at.strftime("%Y-%m-%d %H:%M") if exe.completed_at else "N/A"
            ))

        return RecentTestsResponse(recentTests=recent_tests)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error fetching recent tests: {e}")
        return RecentTestsResponse(recentTests=[])


@router.get("", response_model=TestPlanExecutionListResponse)
def get_execution_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    test_plan_id: Optional[UUID] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """
    Get test plan execution history with filters

    Filters:
    - test_plan_id: Filter by test plan ID
    - status: Filter by execution status (completed, failed, cancelled)
    - start_date: Filter executions after this date
    - end_date: Filter executions before this date
    """
    try:
        query = db.query(TestPlanExecution)

        # Apply filters
        if test_plan_id:
            query = query.filter(TestPlanExecution.test_plan_id == test_plan_id)
        if status:
            query = query.filter(TestPlanExecution.status == status)
        if start_date:
            query = query.filter(TestPlanExecution.completed_at >= start_date)
        if end_date:
            query = query.filter(TestPlanExecution.completed_at <= end_date)

        # Get total count before pagination
        total = query.count()

        # Apply pagination and order
        executions = query.order_by(
            TestPlanExecution.completed_at.desc()
        ).offset(skip).limit(limit).all()

        return TestPlanExecutionListResponse(
            total=total,
            items=[TestPlanExecutionResponse.model_validate(exe) for exe in executions]
        )
    except Exception as e:
        # Database unavailable - return empty list
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for execution history: {e}")
        return TestPlanExecutionListResponse(
            total=0,
            items=[]
        )


@router.get("/{record_id}", response_model=TestPlanExecutionResponse)
def get_execution_record(
    record_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a single test plan execution record by ID"""
    execution = db.query(TestPlanExecution).filter(
        TestPlanExecution.id == record_id
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution record not found")

    return execution


@router.delete("/{record_id}", status_code=204)
def delete_execution_record(
    record_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a test plan execution record"""
    execution = db.query(TestPlanExecution).filter(
        TestPlanExecution.id == record_id
    ).first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution record not found")

    db.delete(execution)
    db.commit()

    return None


# ==================== Phase 2l: DUT Attach 显式入口 ====================


class AttachDutRequest(BaseModel):
    """前端在测试启动前调用本接口"宣布"DUT 已放入暗室并发起 attach。

    服务侧记录 IMSI / phone_number 到 execution.measurements['dut_attach'],
    precheck phase 拿这个跟 baseStation.query_ue_capability 报告的 UE 信息
    比对, 不匹配则 FAIL (避免对错车测试)。

    工艺前提: DUT 已物理放入暗室静区, SIM 已插入并能 attach 到 UXM。
    """
    imsi: str
    phone_number: Optional[str] = None
    dut_model: Optional[str] = None
    dut_serial: Optional[str] = None
    notes: Optional[str] = None


class AttachDutResponse(BaseModel):
    success: bool
    execution_id: UUID
    dut_imsi: str
    rrc_connected: bool
    ue_info: Optional[dict] = None
    warnings: List[str] = []
    error: Optional[str] = None


@router.post("/{execution_id}/attach-dut", response_model=AttachDutResponse, status_code=200)
async def attach_dut(
    execution_id: UUID,
    request: AttachDutRequest,
    db: Session = Depends(get_db),
):
    """Phase 2l: 把 DUT IMSI/型号写入 TestExecution + 验证 RRC 状态。

    服务流程:
      1. 找 TestExecution (必须存在且未 running)
      2. 查 HAL baseStation (若未连/无 query_ue_capability 则降级仅记元数据)
      3. 写 execution.measurements['dut_attach'] 含 imsi / dut_model /
         attached_at / rrc_connected / ue_info_snapshot
      4. precheck phase 拿到这个数据做 IMSI 一致性检查
    """
    execution = db.query(TestExecution).filter(TestExecution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail=f"TestExecution {execution_id} not found")

    if execution.status == "running":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot attach DUT to running execution; abort first"
        )

    warnings: list[str] = []
    ue_info_snapshot: Optional[dict] = None
    rrc_connected = False

    # Best-effort UE Capability + UE info query
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
        bs = hal.drivers.get("baseStation")
        if bs is None:
            warnings.append("baseStation driver not in HAL — DUT attach recorded without RRC verification")
        else:
            if hasattr(bs, "query_ue_capability"):
                cap = await bs.query_ue_capability()
                if cap.get("source") == "unavailable":
                    warnings.append(
                        "UE capability unavailable; DUT may not have attached to UXM yet. "
                        "Verify the SIM is inserted and SIB1 has been broadcast."
                    )
                else:
                    rrc_connected = True
                    ue_info_snapshot = cap
            elif hasattr(bs, "get_ue_info"):
                info = await bs.get_ue_info()
                rrc_connected = bool(info.get("connected"))
                ue_info_snapshot = info
            else:
                warnings.append("baseStation driver lacks query_ue_capability/get_ue_info")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"UE state query raised: {e}")

    # Persist to measurements JSON (no schema migration needed — TestExecution.measurements is JSON)
    if execution.measurements is None:
        execution.measurements = {}
    execution.measurements["dut_attach"] = {
        "imsi": request.imsi,
        "phone_number": request.phone_number,
        "dut_model": request.dut_model,
        "dut_serial": request.dut_serial,
        "notes": request.notes,
        "attached_at": datetime.now(timezone.utc).isoformat(),
        "rrc_connected": rrc_connected,
        "ue_info_snapshot": ue_info_snapshot,
        "warnings": warnings,
    }
    flag_modified(execution, "measurements")
    db.commit()

    return AttachDutResponse(
        success=True,
        execution_id=execution_id,
        dut_imsi=request.imsi,
        rrc_connected=rrc_connected,
        ue_info=ue_info_snapshot,
        warnings=warnings,
    )
