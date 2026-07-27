"""Test Execution History API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from app.db.database import get_db
from app.schemas.test_plan import (
    ExecutionHistoryItem,
    ExecutionHistoryListResponse,
    TestPlanExecutionResponse,
)
from app.models.test_plan import TestCase, TestPlanExecution, TestExecution

router = APIRouter(prefix="/test-executions", tags=["Test Execution History"])


def _to_history_item(execution: TestExecution, case_name: Optional[str]) -> ExecutionHistoryItem:
    """执行行 → 历史列表项。

    相位进度只有 case-runner 在 config.phase_progress 里记
    ({"type": 相位名, "status": completed/failed}, test_case_runner.py);
    commissioning / plan-runner 行没有这个键 → phases_* 保持 None
    (三态语义, GUI 显示 "—", 不伪造 0/N)。
    """
    cfg = execution.config if isinstance(execution.config, dict) else {}
    descriptors = cfg.get("step_descriptors")
    # 畸形收窄 (内审 F1): config 形状不对不许毒整页列表 — 非 list 按
    # "没有"处理 (None 三态), 元素非 dict 跳过, 不进外层 except
    if not isinstance(descriptors, list):
        descriptors = []
    progress = cfg.get("phase_progress")
    phases_done = phases_failed = None
    if isinstance(progress, list):
        phases_done = sum(
            1 for p in progress
            if isinstance(p, dict) and p.get("status") == "completed")
        phases_failed = sum(
            1 for p in progress
            if isinstance(p, dict) and p.get("status") == "failed")
    return ExecutionHistoryItem(
        id=execution.id,
        case_name=case_name,
        source_test_case_id=cfg.get("source_test_case_id"),
        status=execution.status or "unknown",
        phases_total=len(descriptors) if descriptors else None,
        phases_done=phases_done,
        phases_failed=phases_failed,
        duration_sec=execution.duration_sec,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        executed_by=execution.executed_by,
        error_message=execution.error_message,
        validation_pass=execution.validation_pass,
    )


def _history_query(db: Session):
    """历史行基查询: test_executions 本表, mode IS NULL 排除 VRT 行
    (镜像 VRT 自己列表的 mode IS NOT NULL 谓词, vrt_execution_service.py:118),
    显式 outerjoin 快照 TestCase 取执行时的名字 (模型上的 relationship 是
    注释掉的, 不能走属性)。"""
    return (
        db.query(TestExecution, TestCase.name)
        .outerjoin(TestCase, TestExecution.test_case_id == TestCase.id)
        .filter(TestExecution.mode.is_(None))
    )


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
    """仪表盘「最近测试」卡片 (ARCH-1 S2 换源到 test_executions 本表)。

    wire 形状 (id/name/dut/result/date) 不变, 前端零改动;
    name 取快照 TestCase 名 (待决③ 拍板: 与主列表同源, 避免两个"最近"
    来自两张表互相矛盾)。
    """
    try:
        rows = (
            _history_query(db)
            .order_by(TestExecution.executed_at.desc())
            .limit(limit)
            .all()
        )

        recent_tests = []
        for exe, case_name in rows:
            recent_tests.append(RecentTestItem(
                id=str(exe.id),
                name=case_name or "未命名用例",
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


@router.get("", response_model=ExecutionHistoryListResponse)
def get_execution_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """执行历史 (ARCH-1 S2: 数据源 = test_executions 本表, 不再是计划级摘要表)。

    - 每次执行一行 (case-runner / plan-runner 每步 / 暗室首测 / 单相位诊断),
      VRT 行除外 (mode IS NULL 谓词, VRT 有自己的面板与列表)。
    - status 也接受 running — 历史里会出现进行中的行, 用例库靠
      `?status=running` 恢复导航后丢失的执行中徽标 (Codex #237 C3)。
    - 返回行的 id 就是 TestExecution.id, 报告 test_execution_ids 直接引用
      (旧摘要表主键跨表引用查不到任何行, 设计稿 §1.4 的断线)。
    """
    try:
        query = _history_query(db)

        if status:
            query = query.filter(TestExecution.status == status)
        if start_date:
            query = query.filter(TestExecution.executed_at >= start_date)
        if end_date:
            query = query.filter(TestExecution.executed_at <= end_date)

        # Get total count before pagination
        total = query.count()

        # executed_at (行创建时间, NOT NULL) 排序 — completed_at 对 running
        # 行是 NULL, 各方言 NULL 排序位置不同
        rows = (
            query.order_by(TestExecution.executed_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return ExecutionHistoryListResponse(
            total=total,
            items=[_to_history_item(exe, case_name) for exe, case_name in rows],
        )
    except Exception as e:
        # Database unavailable - return empty list
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database unavailable for execution history: {e}")
        return ExecutionHistoryListResponse(
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


# ==================== ARCH-1 S1: 用例执行 cancel ====================


class CancelExecutionResponse(BaseModel):
    execution_id: UUID
    status: str


@router.post("/{execution_id}/cancel", response_model=CancelExecutionResponse)
def cancel_case_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
):
    """协作式取消用例执行 (ARCH-1 S1): 置 cancelled, runner 在相位间尊重。

    只对 case-runner 的执行行有意义; 404 = 行不存在, 409 = 行不在 running
    (已完成/已失败/已取消的执行没有可取消的东西)。挂在本前缀是因为它操作
    的是 TestExecution 行 — 与楼上的 attach-dut 同一张表 (本文件的
    GET/{record_id} 查的是计划级历史表, S2 统一收口)。
    """
    from app.services.test_case_runner import request_cancel

    try:
        cancelled = request_cancel(db, execution_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail="执行不在 running 状态, 无可取消",
        )
    return CancelExecutionResponse(execution_id=execution_id, status="cancelled")


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
