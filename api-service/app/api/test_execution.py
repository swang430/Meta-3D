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
from app.services.execution_failure_alerts import resolve_recorded_outcome

router = APIRouter(prefix="/test-executions", tags=["Test Execution History"])


def _str_or_none(value) -> Optional[str]:
    """config 里读出来的值只有是字符串才用 (内审 F1 的收窄)。"""
    return value if isinstance(value, str) else None


def _is_mimo_ota_execution(
    execution: TestExecution,
    test_type: Optional[str] = None,
) -> bool:
    """Use execution config / TestCase type, never a user-controlled title."""
    cfg = execution.config if isinstance(execution.config, dict) else {}
    descriptors = cfg.get("step_descriptors")
    if isinstance(descriptors, list) and any(
        str(descriptor.get("type") or "").startswith("MIMO_OTA_")
        for descriptor in descriptors
        if isinstance(descriptor, dict)
    ):
        return True
    return test_type == "MIMO_OTA"


def _formal_validation_pass(
    execution: TestExecution,
    test_type: Optional[str] = None,
) -> Optional[bool]:
    """Do not republish legacy MIMO PASS without explicit-real calibration."""
    if not _is_mimo_ota_execution(execution, test_type):
        return execution.validation_pass
    phases = (
        (execution.measurements or {}).get("phases")
        if isinstance(execution.measurements, dict)
        else None
    )
    measure = phases.get("measure") if isinstance(phases, dict) else None
    if not isinstance(measure, dict):
        return None
    if not (
        measure.get("path_loss_verified") is True
        and measure.get("path_loss_calibration_use_mock") is False
    ):
        return None
    return execution.validation_pass


def _to_history_item(
    execution: TestExecution,
    case_name: Optional[str],
    test_type: Optional[str] = None,
) -> ExecutionHistoryItem:
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
        validation_pass=_formal_validation_pass(execution, test_type),
        # P2-34: 告警发布结果 (白名单解析); None = 未记录, 不是"已发布"
        failure_alert_outcome=resolve_recorded_outcome(cfg),
    )


def _history_query(db: Session):
    """历史行基查询: test_executions 本表, mode IS NULL 排除 VRT 行
    (镜像 VRT 自己列表的 mode IS NOT NULL 谓词, vrt_execution_service.py:118),
    显式 outerjoin 快照 TestCase 取执行时的名字 (模型上的 relationship 是
    注释掉的, 不能走属性)。"""
    return (
        db.query(TestExecution, TestCase.name, TestCase.test_type)
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
        for exe, case_name, _test_type in rows:
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
            items=[
                _to_history_item(exe, case_name, test_type)
                for exe, case_name, test_type in rows
            ],
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
    """为某次执行登记可选的 DUT 身份元数据，并读取一次即时 UE 状态。

    服务侧记录 IMSI / phone_number 到 execution.measurements['dut_attach'],
    供后续 SIM 身份核对和执行追溯使用。标准 MIMO OTA 吞吐量流程不会把
    这次初始化前的读取当作正式连接证据：MEASURE 会按 TestCase 配置完
    UXM/F64/开关矩阵后重新确认 CONN，并更新本次受控 attach 记录。

    调用本接口不是标准流程的必需前置条件；调用成功也不代表正式 attach 通过。
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
    """Phase 2l: 把 DUT IMSI/型号写入 TestExecution + 读取即时 RRC 状态。

    服务流程:
      1. 找 TestExecution (必须存在且未 running)
      2. 查 HAL baseStation (若未连/无 query_ue_capability 则降级仅记元数据)
      3. 写 execution.measurements['dut_attach'] 含 imsi / dut_model /
         attached_at / rrc_connected / ue_info_snapshot
      4. 标准吞吐量流程在 MEASURE 初始化后覆盖实时连接事实，并做 SIM 身份核对
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
        from app.services.instrument_test_lease import instrument_test_lease

        async with instrument_test_lease(
            f"attach-dut:{execution_id}",
            control_f64=False,
            control_uxm=True,
            enable_monitoring=False,
        ):
            hal = get_hal_service()
            bs = hal.drivers.get("baseStation")
            if bs is None:
                warnings.append(
                    "baseStation driver not in HAL — DUT attach recorded without RRC verification"
                )
            elif hasattr(bs, "get_cell_state"):
                # ⚠ 连通性判据用**小区状态**，不用 UE 能力（外审 #304 P1）。
                #   `query_ue_capability()` 查的是"这个 DUT 支持几层、什么调制"
                #   （能力），不是"现在连上了没有"（状态）；而 LTE_NR_IRAT 上
                #   `UE_CAPABILITY_*` 命令模板全是 None，即使小区已经回 CONN，
                #   它也恒返回 source="unavailable" → `rrc_connected` 永远写
                #   False → GUI 的「登记 DUT」**永远满足不了严格 DUT 门**。
                #   同 measure 的 `_probe_ue_attached`：判据取
                #   `BSE:STATus:NR5G:<cell>?` 回 CONNected（手册枚举）。
                from app.hal.base_station import CellState

                state = await bs.get_cell_state()
                rrc_connected = state == CellState.CONNECTED
                if not rrc_connected:
                    warnings.append(
                        f"小区状态 {getattr(state, 'value', state)!r} ≠ CONN —— "
                        "DUT 尚未接入 UXM。检查 SIM 是否插好、SIB1 是否已广播。"
                    )
                # 能力查询仍然做，但只用来记 UE 信息（层数/调制），不参与连通性判定
                if hasattr(bs, "query_ue_capability"):
                    try:
                        cap = await bs.query_ue_capability()
                        if cap.get("source") != "unavailable":
                            ue_info_snapshot = cap
                    except Exception as e:  # noqa: BLE001
                        warnings.append(f"UE 能力查询失败（不影响连通性判定）: {e}")
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
