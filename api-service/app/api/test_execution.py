"""Test Execution History API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from app.db.database import get_db
from app.schemas.test_plan import (
    ExecutionHistoryItem,
    ExecutionHistoryListResponse,
)
from app.models.test_plan import TestCase, TestExecution

router = APIRouter(prefix="/test-executions", tags=["Test Execution History"])


def _str_or_none(value) -> Optional[str]:
    """config 里读出来的值只有是字符串才用 (内审 F1 的收窄)。"""
    return value if isinstance(value, str) else None


def _to_history_item(execution: TestExecution, case_name: Optional[str]) -> ExecutionHistoryItem:
    """执行行 → 历史列表项。

    相位进度只有 case-runner 在 config.phase_progress 里记
    ({"type": 相位名, "status": StepExecutionStatus.value ∈
    success/failed/skipped/running}, test_case_runner.py 相位循环 append 唯一写方 —
    P2-19: 此处 docstring 原写 completed/failed 是错误 token, 它当过计数
    谓词与测试 fixture 的种子, 三处同错自洽致 phases_done 恒 0);
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
            if isinstance(p, dict) and p.get("status") == "success")
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
        # Codex #238 迟到 C-1: case-runner 的失败文本写在
        # config["error_message"] 不写列 (三处写 config; 五个终态写入点
        # 没有一处写列) — 只读列会让 failed 用例行在历史里失去诊断信息。
        # 兜底读同样要 isinstance 收窄 (内审 F1): 非串会让 Pydantic 拒绝
        # 整行 → 被外层 except 吞成空表, 正是本文件毒行不变量禁的事
        error_message=execution.error_message or _str_or_none(
            cfg.get("error_message")),
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
    executed_by: Optional[List[str]] = Query(None),
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
        if executed_by:
            # 按来源链收窄, 可传多个 (?executed_by=a&executed_by=b)。
            # 收窄必须在服务端 (limit 之前) — 客户端过滤是在拿到 limit
            # 窗口之后才跑, 某条链的行一多就把想要的行挤没了:
            #   Codex #238 C-3: plan-runner 的 stale running 行挤掉
            #     case 执行 → 用例库恢复不出取消入口;
            #   Codex #239 迟到: adhoc 诊断行挤掉正式执行 → 待归档列表
            #     空, 报告选不到执行结果 (AGENTS.md §2.3.5)。
            # 两次同一母题, 所以判据一律留在这里, 消费方显式列出要哪几条链。
            query = query.filter(TestExecution.executed_by.in_(executed_by))
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


# ARCH-1 S4b (设计稿 §1.7): 这里原有 GET / DELETE /{record_id} 两条, 读的是
# **旧表** test_plan_executions —— 而本路由器的列表与 /recent 读的是
# test_executions。两表 id 空间不相交, 所以"列表列出来的每一行, 拿它的 id 去查
# 详情都会 404"。至今没炸是因为**零调用方** (全 GUI 只调 /recent、/{id}/cancel、
# /{id}/attach-dut)。它是一颗埋着的雷: 谁将来给执行历史加个"点开看详情"就撞上。
# 处置 = 删 (去掉档修法; 给零调用方的路由换源是纯浪费)。

class CancelExecutionResponse(BaseModel):
    execution_id: UUID
    status: str


@router.post("/{execution_id}/cancel", response_model=CancelExecutionResponse)
def cancel_case_execution(
    execution_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """协作式取消用例执行 (ARCH-1 S1): 置 cancelled, runner 在相位间尊重。

    只对 case-runner 的执行行有意义; 404 = 行不存在, 409 = 行不在 running
    (已完成/已失败/已取消的执行没有可取消的东西)。挂在本前缀是因为它操作
    的是 TestExecution 行 — 与楼上的 attach-dut 同一张表。
    (本文件原有的 GET/DELETE {record_id} 查的是**另一张**表
    test_plan_executions, 已随 ARCH-1 S4b 删除。)
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
    request.state.execution_id = str(execution_id)
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
