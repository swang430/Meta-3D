"""Instrument API endpoints

输出格式适配前端 InstrumentsResponse / InstrumentCategory 类型定义。
后端 DB 模型 → 前端友好的扁平化 JSON。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from uuid import UUID
import logging
from contextlib import asynccontextmanager
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.database import get_db
from app.hal.base import (
    redact_instrument_command_text,
    redact_instrument_exchange_text,
    resolve_configured_tcpip_connection,
)
from app.hal.propsim_f64 import _TOPOLOGY_ESCAPE_HINT
from app.hal.uxm_base_station import normalize_uxm_connection_selector
from app.models.diagnostic_run import DiagnosticKind
from app.models.instrument import (
    InstrumentCategory as InstrumentCategoryModel,
    InstrumentModel as InstrumentModelDB,
    InstrumentConnection as InstrumentConnectionDB,
)
from app.schemas.instrument import (
    UpdateInstrumentCategoryRequest,
)
from app.services.diagnostic_context import build_diagnostic_context
from app.services.instrument_test_lease import instrument_test_lease

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# 前端友好的响应 Schema（与前端 types/api.ts 一一对应）
# ============================================================

class FEInstrumentModel(BaseModel):
    """对应前端 InstrumentModel 类型"""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: str
    vendor: str
    model: str
    summary: str
    interfaces: List[str]
    capabilities: List[str]
    # P2-3: canonical capability tokens this model CAN expose (per
    # ``DriverClass.model_capabilities``). Distinct from ``capabilities``
    # above, which is a freeform datasheet-derived badge list. Empty
    # list means either no real driver is registered for the model, or
    # the driver intentionally declared no tokens. Used by GUI to gate
    # plan-binding picks before HAL Reload (closes the P1-1 pre-flight
    # gap of needing the driver connected to know what it'd support).
    model_capabilities: List[str] = []
    bandwidth: Optional[str] = None
    channels: Optional[str] = None
    status: Literal["available", "pending_dev"]


class FEInstrumentConnection(BaseModel):
    """对应前端 InstrumentConnection 类型"""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: Optional[str] = None  # DB InstrumentConnection UUID, 供 SCD 等按 connection 关联的 API 用
    endpoint: Optional[str] = None
    controller: Optional[str] = None
    notes: Optional[str] = None
    connection_params: Optional[Dict[str, Any]] = None


class FEInstrumentCategory(BaseModel):
    """对应前端 InstrumentCategory 类型"""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    categoryId: Optional[str] = None  # DB UUID, 供拓扑编辑器等关联查询
    key: str
    label: str
    description: str
    tags: List[str] = []
    selectedModelId: Optional[str] = None
    connection: FEInstrumentConnection
    models: List[FEInstrumentModel]
    isActive: bool = True
    usagePhase: List[str] = []  # ["calibration", "test"]
    driverMode: str = "auto"  # "auto" | "mock" | "real"


class FEInstrumentsResponse(BaseModel):
    """对应前端 InstrumentsResponse 类型"""
    categories: List[FEInstrumentCategory]


# ============================================================
# 数据转换函数
# ============================================================

def _extract_capabilities_summary(caps: Dict[str, Any]) -> List[str]:
    """从 capabilities JSON 提取能力标签列表，用于 Badge 展示"""
    tags = []
    if caps.get("mimo_config"):
        tags.append(f"MIMO {caps['mimo_config']}")
    if caps.get("technology"):
        for tech in caps["technology"][:3]:
            tags.append(tech)
    if caps.get("fading_profiles"):
        for fp in caps["fading_profiles"][:2]:
            tags.append(fp)
    if caps.get("measurements"):
        for m in caps["measurements"][:3]:
            tags.append(m)
    if caps.get("ports"):
        tags.append(f"{caps['ports']}-Port")
    if caps.get("axes"):
        tags.append(f"{caps['axes']}-Axis")
    if caps.get("max_payload_kg"):
        tags.append(f"Max {caps['max_payload_kg']}kg")
    if caps.get("ports_in") and caps.get("ports_out"):
        tags.append(f"{caps['ports_in']}×{caps['ports_out']} Matrix")
    if caps.get("dynamic_range_db"):
        tags.append(f"DR {caps['dynamic_range_db']}dB")
    return tags


def _extract_interfaces(caps: Dict[str, Any]) -> List[str]:
    """从 capabilities 提取接口列表"""
    return caps.get("interfaces", [])


def _make_summary(model_db: InstrumentModelDB) -> str:
    """生成型号摘要"""
    caps = model_db.capabilities or {}
    parts = []
    if caps.get("channels"):
        parts.append(f"{caps['channels']}通道")
    if caps.get("bandwidth_mhz"):
        parts.append(f"{caps['bandwidth_mhz']}MHz带宽")
    if caps.get("frequency_range_ghz"):
        fr = caps["frequency_range_ghz"]
        if isinstance(fr, list) and len(fr) == 2:
            parts.append(f"{fr[0]}-{fr[1]}GHz")
    if caps.get("analysis_bandwidth_mhz"):
        parts.append(f"分析带宽{caps['analysis_bandwidth_mhz']}MHz")
    if caps.get("max_bandwidth_mhz"):
        parts.append(f"最大{caps['max_bandwidth_mhz']}MHz")
    if caps.get("positioning_accuracy_deg"):
        parts.append(f"精度±{caps['positioning_accuracy_deg']}°")
    if model_db.full_name:
        parts.insert(0, model_db.full_name)
    return " | ".join(parts) if parts else f"{model_db.vendor} {model_db.model}"


def _convert_model(model_db: InstrumentModelDB, category_key: str) -> FEInstrumentModel:
    """DB InstrumentModel → 前端 FEInstrumentModel"""
    from app.services.instrument_hal_service import get_real_driver_class
    caps = model_db.capabilities or {}

    # Single lookup serves two purposes: support-status badge (was the
    # legacy ``has_real_driver`` call) and P2-3 model_capabilities
    # surface. Sharing one registry read keeps the two answers in sync.
    driver_cls = get_real_driver_class(category_key, model_db.model)
    status = "available" if driver_cls is not None else "pending_dev"
    model_capability_tokens = sorted(
        getattr(driver_cls, "model_capabilities", frozenset()) or frozenset()
    )

    return FEInstrumentModel(
        id=str(model_db.id),
        vendor=model_db.vendor,
        model=model_db.model,
        summary=_make_summary(model_db),
        interfaces=_extract_interfaces(caps),
        capabilities=_extract_capabilities_summary(caps),
        model_capabilities=model_capability_tokens,
        bandwidth=f"{caps['bandwidth_mhz']}MHz" if caps.get("bandwidth_mhz") else (
            f"{caps['analysis_bandwidth_mhz']}MHz" if caps.get("analysis_bandwidth_mhz") else (
                f"{caps['max_bandwidth_mhz']}MHz" if caps.get("max_bandwidth_mhz") else None
            )
        ),
        channels=str(caps["channels"]) if caps.get("channels") else (
            f"{caps['ports']}-Port" if caps.get("ports") else None
        ),
        status=status,
    )


def _convert_connection(conn_db: Optional[InstrumentConnectionDB]) -> FEInstrumentConnection:
    """DB InstrumentConnection → 前端 FEInstrumentConnection"""
    if not conn_db:
        return FEInstrumentConnection()
    return FEInstrumentConnection(
        id=str(conn_db.id),
        endpoint=conn_db.endpoint or "",
        controller=conn_db.protocol or "",
        notes=conn_db.notes or "",
        connection_params=conn_db.connection_params,
    )


def _category_tags(cat: InstrumentCategoryModel) -> List[str]:
    """为仪器类别生成标签"""
    tags = []
    if cat.category_name_en:
        tags.append(cat.category_name_en)
    return tags


def _convert_category(
    cat: InstrumentCategoryModel,
    models: List[InstrumentModelDB],
    conn: Optional[InstrumentConnectionDB],
) -> FEInstrumentCategory:
    """DB InstrumentCategory → 前端 FEInstrumentCategory"""
    return FEInstrumentCategory(
        categoryId=str(cat.id),
        key=cat.category_key,
        label=cat.category_name,
        description=cat.description or "",
        tags=_category_tags(cat),
        selectedModelId=str(cat.selected_model_id) if cat.selected_model_id else None,
        connection=_convert_connection(conn),
        models=[_convert_model(m, cat.category_key) for m in models],
        isActive=cat.is_active if cat.is_active is not None else True,
        usagePhase=cat.usage_phase if cat.usage_phase else [],
        driverMode=cat.driver_mode if cat.driver_mode else "auto",
    )


# ============================================================
# API Endpoints
# ============================================================

@router.get("/instruments/catalog", response_model=FEInstrumentsResponse)
def get_instrument_catalog(db: Session = Depends(get_db)):
    """
    获取完整仪器目录

    返回格式严格对齐前端 InstrumentsResponse 类型:
    { categories: InstrumentCategory[] }
    """
    try:
        categories_db = db.query(InstrumentCategoryModel).order_by(
            InstrumentCategoryModel.display_order
        ).all()

        fe_categories = []
        for cat in categories_db:
            models = db.query(InstrumentModelDB).filter(
                InstrumentModelDB.category_id == cat.id
            ).order_by(InstrumentModelDB.display_order).all()

            conn = db.query(InstrumentConnectionDB).filter(
                InstrumentConnectionDB.category_id == cat.id
            ).first()

            fe_categories.append(_convert_category(cat, models, conn))

        return FEInstrumentsResponse(categories=fe_categories)

    except Exception as e:
        logger.error(f"Error fetching instrument catalog: {e}", exc_info=True)
        return FEInstrumentsResponse(categories=[])


class HalReloadResult(BaseModel):
    """Response for POST /instruments/hal/reload (success path)."""
    drivers_loaded: int
    drivers: List[str]
    duration_ms: int
    forced: bool = False  # True when reload proceeded despite active blockers (force=true)


class HalReloadBlocker(BaseModel):
    """One reason a HAL reload was refused.

    Mirrors ``app.services.hal_reload_policy.ReloadBlocker`` for the
    wire surface. ``kind`` lets the GUI branch on blocker type when
    additional sources (in-flight diagnostics, calibration sessions)
    get wired in later — today only ``"test_execution"`` is emitted
    (ARCH-1 S4c 之前是 ``"test_plan"``, 那半截随计划链拆除删掉了)。"""
    kind: str
    id: str
    name: str
    status: str
    detail: str


class HalReloadRefusedResult(BaseModel):
    """Response body for HTTP 409 from POST /instruments/hal/reload
    when ``force=false`` and active blockers exist.

    GUI uses ``blockers`` to render a precise message ("2 executions
    are holding the drivers: …") and offers a "Force reload anyway"
    button that re-POSTs with ``?force=true``.

    ⚠️ ARCH-1 S4c: blockers 是**执行行**不是测试计划 —— 用例执行 / 暗室
    首测 / 单相位诊断的 running 行, 外加硬件 VRT 的 paused 行。"""
    refused: bool = True
    reason: str
    blockers: List[HalReloadBlocker]
    force_hint: str = (
        "Re-POST with ?force=true to override (will abort the in-flight "
        "work — operator takes responsibility for the cleanup)."
    )


class ChannelModelEntry(BaseModel):
    """One operator-selectable channel-model file."""
    filename: str
    label: str
    description: Optional[str] = None
    type: str  # smu / rtc / asc / unknown
    # P2-10 Step 1: 资产盘点元数据 (从文件名频率 token 解析或 config 显式给), 服务
    # emulation_file 选择 (.smu↔TestCase 频率匹配)。None = 文件名无频率 token。
    center_frequency_mhz: Optional[float] = None
    nr_arfcn: Optional[int] = None
    # P2-12 slice 4: SCD 派生 entry 的 SCD UUID (手敲条目为 None)。GUI 下拉选 SCD 派生项
    # 时存 scd_id (measure 查 SCD 解析 .smu + 频率 cross-check), 选手敲项存裸 emulation_file。
    scd_id: Optional[str] = None


class ChannelModelsListResult(BaseModel):
    """Response for GET /instruments/{category_key}/channel-models.

    ``items`` may be empty for legitimate reasons (no driver loaded yet,
    driver doesn't speak channel models, or operator hasn't populated
    the curated list). ``reason`` distinguishes the cases so the GUI can
    show "loading..." vs "no driver" vs "configure in settings".
    """
    items: List[ChannelModelEntry]
    reason: Optional[str] = None  # "driver_not_loaded" | "not_a_channel_emulator" | None


class _UnverifiedScpiAdapter(logging.LoggerAdapter):
    """给手敲 SCPI / 连通性探测那几条路的日志自动打上「来源不确定」。

    为什么是 unverified 而不是 real（P1-48）：这几条路绕开正规驱动，
    直接 socket 连数据库里配的地址 —— 地址可能指向仪器模拟器、代理、
    或者接错的设备，**连上了不等于对面是真仪器**。标 real 会把
    「连上了某个端口」说成「真仪器回的数」，界面上还会亮成绿色。

    用 Adapter 而不是逐个日志点加 extra：那条路有十几个日志点，
    逐个加会漏，**新开的点也自动带上**。
    """

    def __init__(self, logger, driver=None):
        super().__init__(logger, {})
        # 走已加载的 HAL 驱动时，来源是**已知的**（`_get_loaded_hal_driver` 只返回
        # 真驱动，Mock 会被它跳过）—— 这时必须按驱动自己的真假标，
        # 否则真仪器的往返会被盖成「来源不确定」，那是反方向的同一个毛病（外审指出）。
        self._driver = driver

    def process(self, msg, kwargs):
        extra = dict(kwargs.get("extra") or {})
        if self._driver is not None:
            from app.services.instrument_hal_service import is_mock_driver
            src = "mock" if is_mock_driver(self._driver) else "real"
            extra.setdefault("driver_source", src)
            extra.setdefault("simulated", src == "mock")
        else:
            extra.setdefault("driver_source", "unverified")
            extra.setdefault("simulated", None)
        kwargs["extra"] = extra
        return msg, kwargs


def _unverified_scpi_logger(driver=None) -> logging.LoggerAdapter:
    """拿 SCPI 日志器。

    ``driver`` 为 None（裸 socket 直连配置地址）→ 标「来源不确定」；
    传了 driver（走已加载的 HAL 驱动）→ 按驱动自己的真假标。
    """
    return _UnverifiedScpiAdapter(logging.getLogger("app.hal.scpi"), driver)


@router.post(
    "/instruments/hal/reload",
    response_model=HalReloadResult,
    responses={409: {"model": HalReloadRefusedResult}},
)
async def reload_hal_service(
    force: bool = Query(
        False,
        description=(
            "Override the refuse-while-in-flight check (P2-5). When "
            "True, reload proceeds even with **executions actively "
            "holding the drivers** (用例执行 / 暗室首测 / 单相位诊断的 "
            "running 行, 以及硬件 VRT 的 paused 行) — that in-flight "
            "work will fail with closed-VISA-session errors. "
            "Default False = safe behaviour. "
            "(ARCH-1 S4c 之前这里写的是 running TestPlans —— 计划链已拆除, "
            "照那个描述判断会误以为 force 只影响计划, 而实际会打断真在跑的测试。)"
        ),
    ),
    db: Session = Depends(get_db),
) -> HalReloadResult:
    """Tear down the HAL service and re-init it from the current DB state.

    Use after editing instrument selection / endpoint / driver_mode in
    the GUI — without this, those changes don't take effect until a
    backend restart (HAL initializes once at FastAPI lifespan startup).

    Returns a summary of what's now loaded. The full readiness report
    is also logged to stdout/log file with the formatted table.

    **P2-5 refuse-while-in-flight policy**: when a **TestExecution is
    actively holding the drivers** — any ``running`` row (用例执行 /
    暗室首测 / 单相位诊断), plus hardware VRT rows that are ``paused``
    (pause releases nothing) — the default reload returns HTTP 409 with
    the blocker list instead of tearing down the drivers. Operator can
    re-POST with ``?force=true`` to override (they take responsibility
    for the aborted test).

    ⚠️ ARCH-1 S4c: the criterion used to be ``TestPlan ∈ (running,
    paused)``. 计划链已整个拆除 —— 计划行**永远不会**再产生 409。
    这份文档进 OpenAPI, 操作员被拦时按它去找"在跑的测试计划"会一无所获,
    然后直接上 force=true —— 而 force 会把真在跑的用例执行一起绕过。

    **P2-5 concurrency**: shutdown + reinit run inside the HAL
    lifecycle lock (``reload_hal_service_atomic``) so two concurrent
    reloads serialise instead of racing the global ``_hal_service``
    assignment.

    Side effects (when proceeding):
    - Drops every active VISA / pyvisa session held by the previous
      driver instances.
    - Calls each driver's disconnect() — fine if drivers are well-
      behaved, but a misbehaving driver could block here.

    See docs/site-debug/2026-05-13-retrospective.md §B for the
    motivating problem (init-once HAL + config-then-restart loop)
    and docs/roadmap-first-call.md P2-5 for the policy decision
    (refuse + force + mutex, audit-driven A+D combo).
    """
    import time
    from app.services.hal_reload_policy import find_reload_blockers
    from app.services.instrument_hal_service import (
        DriverMode,
        get_hal_service,
        reload_hal_service_atomic,
    )
    from app.services.instrument_test_lease import hal_mutation_guard

    def _refused_response(blockers):
        payload = HalReloadRefusedResult(
            reason=(
                f"HAL reload refused: {len(blockers)} active "
                f"blocker(s). Operator must cancel/complete the "
                f"in-flight work first, or re-POST with ?force=true "
                f"to abort it."
            ),
            blockers=[
                HalReloadBlocker(
                    kind=b.kind, id=b.id, name=b.name,
                    status=b.status, detail=b.detail,
                )
                for b in blockers
            ],
        )
        return JSONResponse(status_code=409, content=payload.model_dump())

    # Refuse arm: check blockers BEFORE acquiring the lifecycle lock,
    # so a no-op refusal doesn't serialise behind in-progress reloads.
    if not force:
        blockers = find_reload_blockers(db)
        if blockers:
            return _refused_response(blockers)

    started = time.monotonic()
    # Preserve the mode the service was running in (REAL vs MOCK_FALLBACK
    # vs MOCK_FORCE) — operators usually don't want to switch global mode
    # when reloading specific instruments.
    async def _reload_now() -> None:
        prior_service = get_hal_service()
        prior_mode = (
            getattr(prior_service, "mode", DriverMode.REAL)
            if prior_service else DriverMode.REAL
        )
        await reload_hal_service_atomic(prior_mode)

    if force:
        # force 是现场主动放弃在飞操作的逃生口，保留其原有“立即拆”语义。
        await _reload_now()
    else:
        # 第二次检查必须在与测试租约相同的锁内：第一次检查后若测试开始，
        # 此处会等待其完整释放；本锁到手后再查，消除 check→reload TOCTOU。
        async with hal_mutation_guard():
            blockers = find_reload_blockers(db)
            if blockers:
                return _refused_response(blockers)
            await _reload_now()
    fresh = get_hal_service()
    drivers = sorted(fresh.drivers.keys()) if fresh else []
    duration_ms = int((time.monotonic() - started) * 1000)
    return HalReloadResult(
        drivers_loaded=len(drivers),
        drivers=drivers,
        duration_ms=duration_ms,
        forced=force,
    )


@router.get(
    "/instruments/{category_key}/channel-models",
    response_model=ChannelModelsListResult,
)
async def list_channel_models_endpoint(
    category_key: str,
    db: Session = Depends(get_db),
) -> ChannelModelsListResult:
    """List operator-selectable channel-model files for a category.

    Only meaningful for ``channelEmulator``-style categories whose driver
    overrides ``ChannelEmulatorDriver.list_channel_models``. Other
    categories return an empty list with ``reason="not_a_channel_emulator"``.

    Source of truth (today): the operator's curated list in
    ``InstrumentConnection.connection_params['available_channel_models']``.
    We deliberately don't probe the F64 over SCPI/FTP because:
    - F64 ATE Server doesn't expose MMEM SCPI (verified 2026-05-13);
    - the CAICT chamber's F64 has its FTP service disabled.

    See memory ``project_f64_ate_server_capabilities`` for the field reality.

    When ``items`` is empty:
    - ``reason="driver_not_loaded"`` — HAL hasn't bound a driver for this
      category yet. GUI should suggest "Reload HAL drivers" or check
      that the instrument is selected + connection IP filled in.
    - ``reason="not_a_channel_emulator"`` — wrong category for this
      endpoint.
    - ``reason=None`` with empty items — driver loaded, but nothing
      configured in ``connection_params['available_channel_models']``.
      GUI should suggest "configure available models in instrument
      resources".
    """
    cat = (
        db.query(InstrumentCategoryModel)
        .filter(InstrumentCategoryModel.category_key == category_key)
        .first()
    )
    if cat is None:
        raise HTTPException(
            status_code=404,
            detail=f"Instrument category '{category_key}' not found",
        )

    # Resolve HAL driver. ``hal.drivers`` is keyed by category_key.
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
    except Exception:  # noqa: BLE001
        hal = None
    driver = (hal.drivers or {}).get(category_key) if hal else None

    # driver 仅用于区分 not_a_channel_emulator (非信道仿真器类别, 如 VNA), **不从 driver
    # 读数据**。available_channel_models 的真值源是实时 DB connection_params (operator /
    # SCD associate 维护): RealPropsimF64Driver.list_channel_models 读 HAL 启动注入的
    # self._available_channel_models 快照, MockChannelEmulator 没 override 返回 [] —— 两者在
    # SCD associate / ChannelModelsCard add 更新 DB 后都 stale (smoke 2026-06-03 抓到:
    # associate 后 emulation_file 下拉 / ChannelModelsCard 看不到新条目)。且无 driver 做真正
    # 动态发现 (F64 ATE Server 无 MMEM SCPI, FTP closed)。故统一读实时 DB connection_params。
    if driver is not None and not callable(getattr(driver, "list_channel_models", None)):
        return ChannelModelsListResult(items=[], reason="not_a_channel_emulator")

    from app.hal.channel_emulator import normalize_channel_model_entries
    conn = (
        db.query(InstrumentConnectionDB)
        .filter(InstrumentConnectionDB.category_id == cat.id)
        .first()
    )
    raw_params = (conn.connection_params if conn else None) or {}
    raw_entries = raw_params.get("available_channel_models") or []
    normalised = normalize_channel_model_entries(raw_entries)
    items = [ChannelModelEntry(**entry) for entry in normalised]
    # ``reason`` stays ``driver_not_loaded`` when items is empty so the GUI
    # still tells the operator "drivers aren't bound" — but if the DB has
    # a curated list, the items are surfaced and ``reason=None``.
    return ChannelModelsListResult(
        items=items,
        # 空清单: driver 没绑 → driver_not_loaded (提示 reload); driver 绑了但 DB 没配 →
        # reason=None (GUI 引导去配置)。DB 有 curated list → items 出来 reason=None。
        reason="driver_not_loaded" if (not items and driver is None) else None,
    )


# ============================================================
# P2-1 Phase 1: Topology profile endpoints (UXM-specific today,
# pattern generalisable when CMX500 / other multi-app instruments land)
# ============================================================

class TopologyProfileEntry(BaseModel):
    """One row in the topology profile listing.

    `compatible_with_current_test_app` is computed against the live HAL
    driver's detected_test_app at request time — null when there's no
    live driver to compare against (HAL not initialised, mock mode,
    no UXM driver bound) so the GUI doesn't have to special-case the
    'we don't know yet' state.

    P2-1 Phase 2.1: `is_system_preset` flags the 7 built-in templates
    (seeded by ``app.services.bootstrap.topology_profiles_seeder``); GUI
    renders these as read-only with a 'duplicate to edit' affordance."""
    profile_id: str
    name: str
    description: str
    category: str  # "siso" / "mimo" / "calibration" — from UxmTopologyProfile.category
    compatible_test_apps: List[str]
    compatible_with_current_test_app: Optional[bool] = None
    is_system_preset: bool = False


class TopologyProfilesListResult(BaseModel):
    """Response for GET /instruments/{cat}/topology-profiles.

    `current_test_app` is the live-detected app name from the driver
    (e.g. `'LTE_NR_IRAT'`), null when no live driver. GUI uses this to
    label the dropdown ('Currently running: LTE_NR_IRAT — only LTE
    topologies compatible') and to grey out incompatible options.

    `selected_topology_profile_id` is what's currently persisted on
    the binding (operator's last selection); GUI pre-selects this in
    the dropdown."""
    items: List[TopologyProfileEntry]
    current_test_app: Optional[str] = None
    selected_topology_profile_id: Optional[str] = None
    reason: Optional[str] = None  # "not_a_uxm" | None


class SelectTopologyProfileRequest(BaseModel):
    """Payload for PUT /instruments/{cat}/topology-profile.

    `profile_id=null` clears the selection (operator wants no auto-apply
    on next HAL reload). `profile_id="some_id"` persists + (if live
    driver available + compat) immediately calls apply on the driver."""
    profile_id: Optional[str] = None


class SelectTopologyProfileResult(BaseModel):
    """Response for PUT /instruments/{cat}/topology-profile.

    `persisted` is always True on a 200 (we never partially persist —
    refuses bail before the DB write). `applied_now` is True only
    when the live driver was reachable AND compat allowed; False with
    a non-empty `apply_skipped_reason` when we wrote the binding but
    didn't push to the driver (no live driver / not a UXM / etc).
    Distinguishes 'saved your preference, will take effect next HAL
    reload' from 'saved + already live'."""
    persisted: bool
    profile_id: Optional[str]
    applied_now: bool = False
    apply_skipped_reason: Optional[str] = None
    test_app: Optional[str] = None


def _list_topology_profiles_for_category(
    db: Session, category_key: str,
) -> List[Dict[str, Any]]:
    """Today: UXM is the only category with topology profiles. Future
    multi-app instruments (CMX500, etc.) add their own profile registry
    + a category → registry dispatch here.

    Returns the raw row dicts — caller wraps them in Pydantic + adds
    runtime compat status. Empty list means 'no profiles for this
    category' (and caller should set reason='not_a_uxm' or equivalent).

    P2-1 Phase 2.1: source is now ``instrument_topology_profiles`` DB
    table (includes built-ins seeded by the bootstrap seeder + any
    operator-created custom profiles). The in-code ``_PROFILE_REGISTRY``
    is only a fallback if the seeder hasn't run yet (first-boot race).
    """
    if category_key != "baseStation":
        # No other category exposes topology profiles in Phase 1.
        return []
    from app.services.topology_profile_service import list_rows

    rows = list_rows(db)
    if not rows:
        # Greenfield first-boot fallback — surface the in-code built-ins
        # so the GUI isn't empty before bootstrap has run.
        from app.hal.uxm_test_profiles import (
            _PROFILE_REGISTRY, _register_builtin_profiles,
        )
        if not _PROFILE_REGISTRY:
            _register_builtin_profiles()
        return [
            {
                "profile_id": p.profile_id,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "compatible_test_apps": list(p.compatible_test_apps),
                "is_system_preset": True,
            }
            for p in _PROFILE_REGISTRY.values()
        ]
    return [
        {
            "profile_id": r.profile_id,
            "name": r.name,
            "description": r.description or "",
            "category": r.category,
            "compatible_test_apps": list(r.compatible_test_apps or []),
            "is_system_preset": bool(r.is_system_preset),
        }
        for r in rows
    ]


def _resolve_current_test_app(driver: Any) -> Optional[str]:
    """Return the canonical command-profile name for ``driver`` (post
    ``detect_profile()`` normalisation), falling back to the raw
    ``detected_test_app`` alias when the driver doesn't expose
    ``_cmds`` (non-UXM drivers, mocks in tests).

    Codex P2 (PR #36): ``RealUxmDriver.apply_topology_profile()``
    compares the proposed profile's ``compatible_test_apps`` against
    ``self._cmds.PROFILE_NAME`` (canonical, e.g. ``"5G_NR_Test"``).
    The endpoint preflights here must agree, otherwise a UXM that
    reports a recognised alias such as ``"5G NR Test"`` (with space)
    or ``"5G_NR_TEST"`` (uppercase) — both listed in
    ``Uxm5GNRTestAppProfile.APP_NAME_MATCH`` — gets exact-match-rejected
    against ``["5G_NR_Test"]`` and returns 409 / greys-out a valid
    choice, even though the driver-level apply would have accepted it.
    """
    # ``isinstance(..., str)`` guard rather than truthiness so unittest
    # MagicMock drivers (which auto-fabricate any attribute as a Mock
    # object) don't slip a Mock through as the "resolved" name.
    cmds = getattr(driver, "_cmds", None)
    profile_name = getattr(cmds, "PROFILE_NAME", None)
    if isinstance(profile_name, str) and profile_name:
        return profile_name
    raw = getattr(driver, "detected_test_app", None)
    return raw if isinstance(raw, str) else None


@router.get(
    "/instruments/{category_key}/topology-profiles",
    response_model=TopologyProfilesListResult,
)
def list_topology_profiles_endpoint(
    category_key: str,
    db: Session = Depends(get_db),
) -> TopologyProfilesListResult:
    """P2-1: list operator-selectable topology profiles for a binding.

    Operator picks one in the GUI; it persists to
    `InstrumentConnection.connection_params['topology_profile_id']`
    and gets auto-applied on the next HAL reload (after the live
    Test App is detected and compat-verified).

    The 'compatible_with_current_test_app' flag per item reflects the
    live HAL state — operator sees grey-out for choices that won't
    work today (without preventing them from picking one if they
    plan to change the UXM Test App first)."""
    cat = (
        db.query(InstrumentCategoryModel)
        .filter(InstrumentCategoryModel.category_key == category_key)
        .first()
    )
    if cat is None:
        raise HTTPException(
            status_code=404,
            detail=f"Instrument category '{category_key}' not found",
        )

    raw = _list_topology_profiles_for_category(db, category_key)
    if not raw:
        return TopologyProfilesListResult(
            items=[], current_test_app=None,
            selected_topology_profile_id=None,
            reason="not_a_uxm" if category_key != "baseStation" else None,
        )

    # Live HAL state — for compat-flagging items.
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
    except Exception:
        hal = None
    driver = (hal.drivers or {}).get(category_key) if hal else None
    current_test_app: Optional[str] = None
    if driver is not None:
        current_test_app = _resolve_current_test_app(driver)

    # Persisted selection (operator's last PUT).
    conn = (
        db.query(InstrumentConnectionDB)
        .filter(InstrumentConnectionDB.category_id == cat.id)
        .first()
    )
    selected = None
    if conn and isinstance(conn.connection_params, dict):
        selected = conn.connection_params.get("topology_profile_id")

    items = []
    for entry in raw:
        compat = None
        if current_test_app is not None:
            # Compat-check: empty list = compatible-with-any; else
            # exact-match (case-insensitive) check.
            if not entry["compatible_test_apps"]:
                compat = True
            else:
                target = current_test_app.upper()
                compat = any(a.upper() == target for a in entry["compatible_test_apps"])
        items.append(TopologyProfileEntry(
            compatible_with_current_test_app=compat,
            **entry,
        ))

    return TopologyProfilesListResult(
        items=items,
        current_test_app=current_test_app,
        selected_topology_profile_id=selected,
    )


@router.put(
    "/instruments/{category_key}/topology-profile",
    response_model=SelectTopologyProfileResult,
    responses={409: {"description": "Topology incompatible with detected Test App"}},
)
async def select_topology_profile_endpoint(
    category_key: str,
    request: SelectTopologyProfileRequest,
    db: Session = Depends(get_db),
) -> SelectTopologyProfileResult:
    """P2-1: operator selects a topology profile for a UXM binding.

    Behaviour:
    - `profile_id=null`: clears the selection (`connection_params`
      drops the `topology_profile_id` key). 200, applied_now=False.
    - `profile_id="..."` with unknown id: 404.
    - `profile_id="..."` with known id, no live HAL driver: persists
      to `connection_params`, 200 with applied_now=False +
      apply_skipped_reason='no_live_driver'. Takes effect on next
      HAL reload.
    - `profile_id="..."` known + live driver + compatible: persists,
      calls `driver.apply_topology_profile`, 200 with applied_now=True.
    - `profile_id="..."` known + live driver + INCOMPATIBLE: 409 with
      reason='incompatible_test_app' (matches P2-5 refuse pattern).
      The binding is NOT persisted — refuses bail before DB write so
      operator can't accidentally save a doomed selection.
    """
    cat = (
        db.query(InstrumentCategoryModel)
        .filter(InstrumentCategoryModel.category_key == category_key)
        .first()
    )
    if cat is None:
        raise HTTPException(
            status_code=404,
            detail=f"Instrument category '{category_key}' not found",
        )

    conn = (
        db.query(InstrumentConnectionDB)
        .filter(InstrumentConnectionDB.category_id == cat.id)
        .first()
    )
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail=f"No connection row for category '{category_key}' — configure endpoint first",
        )

    profile_id = request.profile_id

    # Validate profile_id (if non-null) exists. P2-1 Phase 2.1: source of
    # truth is the DB table (built-ins seeded by bootstrap + operator
    # custom profiles). Fall back to in-code registry for the greenfield
    # first-boot window where bootstrap hasn't run yet.
    proposed_dc = None
    if profile_id is not None:
        from app.services.topology_profile_service import (
            TopologyProfileNotFound, get_dataclass,
        )
        try:
            proposed_dc = get_dataclass(db, profile_id)
        except TopologyProfileNotFound:
            from app.hal.uxm_test_profiles import (
                _PROFILE_REGISTRY, _register_builtin_profiles,
            )
            if not _PROFILE_REGISTRY:
                _register_builtin_profiles()
            proposed_dc = _PROFILE_REGISTRY.get(profile_id)
            if proposed_dc is None:
                # Surface what's actually available so operator can pick
                # a real one (DB + in-code combined for completeness).
                from app.services.topology_profile_service import list_rows
                db_ids = [r.profile_id for r in list_rows(db)]
                available = sorted(set(db_ids) | set(_PROFILE_REGISTRY.keys()))
                raise HTTPException(
                    status_code=404,
                    detail=f"Topology profile {profile_id!r} not found. "
                           f"Available: {available}",
                )

    # Get live driver (if any) for compat check + immediate apply.
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
    except Exception:
        hal = None
    driver = (hal.drivers or {}).get(category_key) if hal else None

    # Compat check BEFORE DB write — refuses don't half-persist.
    if proposed_dc is not None and driver is not None:
        if hasattr(driver, "apply_topology_profile"):
            current_app = _resolve_current_test_app(driver)
            if not proposed_dc.is_compatible_with(current_app):
                return JSONResponse(
                    status_code=409,
                    content={
                        "refused": True,
                        "reason": "incompatible_test_app",
                        "profile_id": profile_id,
                        "test_app": current_app,
                        "profile_compatible_with": list(proposed_dc.compatible_test_apps),
                        "detail": (
                            f"Topology profile {profile_id!r} compatible with "
                            f"{proposed_dc.compatible_test_apps}, but UXM is currently "
                            f"running Test App {current_app!r}. Pick a compatible "
                            f"profile or switch the UXM hardware to a matching Test App."
                        ),
                    },
                )

    # 持有 UXM-only 租约跨过“最终兼容性复查→持久化→立即下发”，避免 reload
    # 在拿 driver 与首条 SCPI 之间换实例，也避免空闲 Local 门让本端点静默退化。
    async with instrument_test_lease(
        f"uxm-topology-profile:{category_key}",
        control_f64=False,
        control_uxm=(category_key == "baseStation"),
        enable_monitoring=False,
    ):
        from app.services.instrument_hal_service import get_hal_service
        live_hal = get_hal_service()
        driver = (live_hal.drivers or {}).get(category_key) if live_hal else None
        if proposed_dc is not None and driver is not None and hasattr(
            driver, "apply_topology_profile"
        ):
            current_app = _resolve_current_test_app(driver)
            if not proposed_dc.is_compatible_with(current_app):
                return JSONResponse(
                    status_code=409,
                    content={
                        "refused": True,
                        "reason": "incompatible_test_app",
                        "profile_id": profile_id,
                        "test_app": current_app,
                        "profile_compatible_with": list(
                            proposed_dc.compatible_test_apps
                        ),
                        "detail": (
                            f"Topology profile {profile_id!r} compatible with "
                            f"{proposed_dc.compatible_test_apps}, but UXM is currently "
                            f"running Test App {current_app!r}. Pick a compatible "
                            f"profile or switch the UXM hardware to a matching Test App."
                        ),
                    },
                )

        params = dict(conn.connection_params or {})
        if profile_id is None:
            params.pop("topology_profile_id", None)
        else:
            params["topology_profile_id"] = profile_id
        conn.connection_params = params
        db.commit()

        applied_now = False
        apply_skipped_reason: Optional[str] = None
        test_app: Optional[str] = None
        if profile_id is None:
            apply_skipped_reason = "no_selection"
        elif driver is None:
            apply_skipped_reason = "no_live_driver"
        elif not hasattr(driver, "apply_topology_profile"):
            apply_skipped_reason = "driver_does_not_support_topology_profiles"
        else:
            result = await driver.apply_topology_profile(proposed_dc)
            applied_now = bool(result.get("applied"))
            test_app = result.get("test_app")
            if not applied_now:
                apply_skipped_reason = result.get("reason") or "unknown"

        return SelectTopologyProfileResult(
            persisted=True,
            profile_id=profile_id,
            applied_now=applied_now,
            apply_skipped_reason=apply_skipped_reason,
            test_app=test_app,
        )


# ============================================================
# P2-1 Phase 2.1: topology profile CRUD
# ------------------------------------------------------------
# Operator-owned create / update / delete / duplicate. System presets
# (is_system_preset=True) reject PUT/DELETE — operator clones first
# via duplicate(), then edits the copy. Same pattern as chamber
# presets (ChamberConfiguration.is_system_preset). Path scoped under
# the category so future per-instrument profile registries (CMX500
# etc.) can branch on category_key without API churn.
# ============================================================


class TopologyProfileDetail(BaseModel):
    """Full topology profile row — operator-mutable fields + meta.

    Mirrors ``UxmTopologyProfile`` dataclass + DB row. Used as the
    request/response shape for create / update / duplicate / single-get.
    """
    profile_id: str
    name: str
    description: Optional[str] = None
    category: str = "general"

    band: str = "N78"
    frequency_mhz: float = 3500.0
    bandwidth_mhz: float = 100.0
    scs_khz: int = 30
    duplex: str = "TDD"
    arfcn: Optional[int] = None

    mimo_layers: int = 2
    mimo_port_preset: str = "2x2"

    dl_power_dbm: float = -50.0
    ssb_power_dbm: float = -50.0

    modulation: str = "256QAM"
    target_mcs: int = 28

    sched_algo: str = "FULLBUFFER"
    enable_amc: bool = False
    tdd_pattern: str = "DDDSU"
    tdd_period: str = "5MS"
    harq_max_trans: int = 4
    harq_processes: int = 16
    csi_rs_ports: Optional[int] = None
    stat_count: int = 5000

    cell_id: str = "CELL0"
    state_file: Optional[str] = None

    compatible_test_apps: List[str] = []
    notes: Optional[str] = ""

    is_system_preset: bool = False
    created_by: Optional[str] = None


class CreateTopologyProfileRequest(BaseModel):
    """Payload for POST /instruments/{cat}/topology-profiles.

    ``name`` is required (used to generate the ``custom_<slug>``
    profile_id). All other fields fall back to ``UxmTopologyProfile``
    dataclass defaults — operator can build a minimal profile by
    sending only ``{"name": "..."}`` and tweaking later via PUT.
    """
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    band: Optional[str] = None
    frequency_mhz: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    scs_khz: Optional[int] = None
    duplex: Optional[str] = None
    arfcn: Optional[int] = None
    mimo_layers: Optional[int] = None
    mimo_port_preset: Optional[str] = None
    dl_power_dbm: Optional[float] = None
    ssb_power_dbm: Optional[float] = None
    modulation: Optional[str] = None
    target_mcs: Optional[int] = None
    sched_algo: Optional[str] = None
    enable_amc: Optional[bool] = None
    tdd_pattern: Optional[str] = None
    tdd_period: Optional[str] = None
    harq_max_trans: Optional[int] = None
    harq_processes: Optional[int] = None
    csi_rs_ports: Optional[int] = None
    stat_count: Optional[int] = None
    cell_id: Optional[str] = None
    state_file: Optional[str] = None
    compatible_test_apps: Optional[List[str]] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None


class UpdateTopologyProfileRequest(BaseModel):
    """Payload for PUT /instruments/{cat}/topology-profiles/{profile_id}.

    All fields optional — partial update. Unknown fields rejected at
    the service layer so frontend drift surfaces loudly. Same allowlist
    as create.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    band: Optional[str] = None
    frequency_mhz: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    scs_khz: Optional[int] = None
    duplex: Optional[str] = None
    arfcn: Optional[int] = None
    mimo_layers: Optional[int] = None
    mimo_port_preset: Optional[str] = None
    dl_power_dbm: Optional[float] = None
    ssb_power_dbm: Optional[float] = None
    modulation: Optional[str] = None
    target_mcs: Optional[int] = None
    sched_algo: Optional[str] = None
    enable_amc: Optional[bool] = None
    tdd_pattern: Optional[str] = None
    tdd_period: Optional[str] = None
    harq_max_trans: Optional[int] = None
    harq_processes: Optional[int] = None
    csi_rs_ports: Optional[int] = None
    stat_count: Optional[int] = None
    cell_id: Optional[str] = None
    state_file: Optional[str] = None
    compatible_test_apps: Optional[List[str]] = None
    notes: Optional[str] = None


def _row_to_detail(row) -> TopologyProfileDetail:
    """Map ORM row → API detail schema. Tolerates ``None`` for nullable
    columns by falling back to schema defaults (description / notes)."""
    return TopologyProfileDetail(
        profile_id=row.profile_id,
        name=row.name,
        description=row.description,
        category=row.category,
        band=row.band,
        frequency_mhz=row.frequency_mhz,
        bandwidth_mhz=row.bandwidth_mhz,
        scs_khz=row.scs_khz,
        duplex=row.duplex,
        arfcn=row.arfcn,
        mimo_layers=row.mimo_layers,
        mimo_port_preset=row.mimo_port_preset,
        dl_power_dbm=row.dl_power_dbm,
        ssb_power_dbm=row.ssb_power_dbm,
        modulation=row.modulation,
        target_mcs=row.target_mcs,
        sched_algo=row.sched_algo,
        enable_amc=bool(row.enable_amc),
        tdd_pattern=row.tdd_pattern,
        tdd_period=row.tdd_period,
        harq_max_trans=row.harq_max_trans,
        harq_processes=row.harq_processes,
        csi_rs_ports=row.csi_rs_ports,
        stat_count=row.stat_count,
        cell_id=row.cell_id,
        state_file=row.state_file,
        compatible_test_apps=list(row.compatible_test_apps or []),
        notes=row.notes or "",
        is_system_preset=bool(row.is_system_preset),
        created_by=row.created_by,
    )


def _profile_dataclass_to_detail(profile) -> TopologyProfileDetail:
    """Map in-code ``UxmTopologyProfile`` dataclass → API detail schema.

    Used as the greenfield first-boot fallback for the single-GET
    endpoint, mirroring the same fallback in
    ``_list_topology_profiles_for_category``: if the bootstrap seeder
    hasn't run, the list endpoint surfaces the in-code built-ins, so the
    detail endpoint must too — otherwise the GUI lists profiles whose
    editor 404s.

    Built-ins are always system presets (``is_system_preset=True``,
    ``created_by=None``) — the editor will banner read-only as expected.
    """
    return TopologyProfileDetail(
        profile_id=profile.profile_id,
        name=profile.name,
        description=profile.description,
        category=profile.category,
        band=profile.band,
        frequency_mhz=profile.frequency_mhz,
        bandwidth_mhz=profile.bandwidth_mhz,
        scs_khz=profile.scs_khz,
        duplex=profile.duplex,
        arfcn=profile.arfcn,
        mimo_layers=profile.mimo_layers,
        mimo_port_preset=profile.mimo_port_preset,
        dl_power_dbm=profile.dl_power_dbm,
        ssb_power_dbm=profile.ssb_power_dbm,
        modulation=profile.modulation,
        target_mcs=profile.target_mcs,
        sched_algo=profile.sched_algo,
        enable_amc=bool(profile.enable_amc),
        tdd_pattern=profile.tdd_pattern,
        tdd_period=profile.tdd_period,
        harq_max_trans=profile.harq_max_trans,
        harq_processes=profile.harq_processes,
        csi_rs_ports=profile.csi_rs_ports,
        stat_count=profile.stat_count,
        cell_id=profile.cell_id,
        state_file=profile.state_file,
        compatible_test_apps=list(profile.compatible_test_apps or []),
        notes=profile.notes or "",
        is_system_preset=True,
        created_by=None,
    )


def _lookup_builtin_profile(profile_id: str):
    """Greenfield first-boot fallback lookup. Returns the in-code
    ``UxmTopologyProfile`` dataclass for ``profile_id`` if it's a built-in,
    else ``None``. Mirrors the registry-initialization pattern used by
    ``_list_topology_profiles_for_category``.
    """
    from app.hal.uxm_test_profiles import (
        _PROFILE_REGISTRY, _register_builtin_profiles,
    )
    if not _PROFILE_REGISTRY:
        _register_builtin_profiles()
    return _PROFILE_REGISTRY.get(profile_id)


def _require_baseStation(category_key: str) -> None:
    """Reject CRUD calls on non-baseStation categories.

    Today topology profiles only apply to UXM baseStation; routing CRUD
    calls under category-scoped paths means a future CMX500 / etc. can
    plug in with its own profile schema without breaking existing URLs.
    """
    if category_key != "baseStation":
        raise HTTPException(
            status_code=404,
            detail=f"Topology profiles are not defined for category "
                   f"'{category_key}' (only 'baseStation' today).",
        )


@router.get(
    "/instruments/{category_key}/topology-profiles/{profile_id}",
    response_model=TopologyProfileDetail,
    responses={404: {"description": "Profile not found"}},
)
def get_topology_profile_endpoint(
    category_key: str,
    profile_id: str,
    db: Session = Depends(get_db),
) -> TopologyProfileDetail:
    """P2-1 Phase 2.2: full single-profile detail for the GUI editor.

    The list endpoint deliberately returns only the truncated
    ``TopologyProfileEntry`` shape (profile_id / name / category /
    compatible_test_apps + live compat flag) to keep list responses
    small. The editor modal needs all 25+ knobs to populate the form,
    so it hits this endpoint on open.
    """
    _require_baseStation(category_key)
    from app.services.topology_profile_service import (
        TopologyProfileNotFound, get_row, list_rows,
    )
    try:
        row = get_row(db, profile_id)
    except TopologyProfileNotFound:
        # Greenfield first-boot fallback: mirror
        # ``_list_topology_profiles_for_category``'s behavior — if the
        # bootstrap seeder hasn't populated the table yet, the list
        # endpoint surfaces in-code built-ins, so the detail endpoint
        # must too (otherwise GUI lists profiles whose editor 404s).
        # Codex P2 (PR #40 review): without this, clicking edit on a
        # built-in profile in greenfield boot opens an empty modal.
        if not list_rows(db):
            builtin = _lookup_builtin_profile(profile_id)
            if builtin is not None:
                return _profile_dataclass_to_detail(builtin)
        raise HTTPException(
            status_code=404,
            detail=f"Topology profile {profile_id!r} not found",
        )
    return _row_to_detail(row)


@router.post(
    "/instruments/{category_key}/topology-profiles",
    response_model=TopologyProfileDetail,
    status_code=201,
    responses={400: {"description": "Bad request — unknown field or empty name"}},
)
def create_topology_profile_endpoint(
    category_key: str,
    request: CreateTopologyProfileRequest,
    db: Session = Depends(get_db),
) -> TopologyProfileDetail:
    """Create a new operator-owned topology profile.

    ``profile_id`` is auto-allocated (``custom_<slug>``) — operators
    don't pick raw IDs (prevents namespace collisions with built-ins
    and slug-formatting surprises). Operator gets the assigned ID back
    in the response so the GUI can pre-select it.
    """
    _require_baseStation(category_key)
    from app.services.topology_profile_service import create
    fields = request.model_dump(exclude_unset=True, exclude={"name", "created_by"})
    try:
        row = create(
            db, name=request.name, fields=fields, created_by=request.created_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return _row_to_detail(row)


@router.put(
    "/instruments/{category_key}/topology-profiles/{profile_id}",
    response_model=TopologyProfileDetail,
    responses={
        404: {"description": "Profile not found"},
        409: {"description": "System preset — duplicate to edit"},
        400: {"description": "Bad request — unknown field"},
    },
)
def update_topology_profile_endpoint(
    category_key: str,
    profile_id: str,
    request: UpdateTopologyProfileRequest,
    db: Session = Depends(get_db),
) -> TopologyProfileDetail:
    """Partial-update an existing topology profile.

    Refuses ``is_system_preset=True`` rows with 409 — operator must
    duplicate first. Unknown field keys return 400 (loud frontend drift).
    """
    _require_baseStation(category_key)
    from app.services.topology_profile_service import (
        TopologyProfileImmutable, TopologyProfileNotFound, update,
    )
    fields = request.model_dump(exclude_unset=True)
    try:
        row = update(db, profile_id, fields)
    except TopologyProfileNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Topology profile {profile_id!r} not found",
        )
    except TopologyProfileImmutable as e:
        # 409 mirrors P2-5 refuse pattern — request well-formed but the
        # target's state forbids the operation.
        return JSONResponse(
            status_code=409,
            content={
                "refused": True,
                "reason": "is_system_preset",
                "profile_id": profile_id,
                "detail": str(e),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return _row_to_detail(row)


@router.delete(
    "/instruments/{category_key}/topology-profiles/{profile_id}",
    responses={
        204: {"description": "Deleted"},
        404: {"description": "Profile not found"},
        409: {"description": "System preset — cannot delete"},
    },
    status_code=204,
)
def delete_topology_profile_endpoint(
    category_key: str,
    profile_id: str,
    db: Session = Depends(get_db),
):
    """Delete an operator-owned topology profile.

    Refuses ``is_system_preset=True`` rows with 409. Does NOT touch
    bindings — if some category has the profile bound via
    ``connection_params['topology_profile_id']``, that selection silently
    becomes stale (HAL reload warns + skips auto-apply). The GUI should
    warn before delete if bindings reference the row.
    """
    _require_baseStation(category_key)
    from app.services.topology_profile_service import (
        TopologyProfileImmutable, TopologyProfileNotFound, delete,
    )
    try:
        delete(db, profile_id)
    except TopologyProfileNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Topology profile {profile_id!r} not found",
        )
    except TopologyProfileImmutable as e:
        return JSONResponse(
            status_code=409,
            content={
                "refused": True,
                "reason": "is_system_preset",
                "profile_id": profile_id,
                "detail": str(e),
            },
        )
    db.commit()


@router.post(
    "/instruments/{category_key}/topology-profiles/{profile_id}/duplicate",
    response_model=TopologyProfileDetail,
    status_code=201,
    responses={404: {"description": "Source profile not found"}},
)
def duplicate_topology_profile_endpoint(
    category_key: str,
    profile_id: str,
    db: Session = Depends(get_db),
) -> TopologyProfileDetail:
    """Clone any profile (incl. system presets) into a new editable copy.

    The new copy gets ``is_system_preset=False`` so operator can edit /
    delete it. The name is suffixed with ``(副本)`` so it's visually
    distinct in the dropdown.
    """
    _require_baseStation(category_key)
    from app.services.topology_profile_service import (
        TopologyProfileNotFound, duplicate,
    )
    try:
        row = duplicate(db, profile_id)
    except TopologyProfileNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Topology profile {profile_id!r} not found",
        )
    db.commit()
    return _row_to_detail(row)


# ============================================================
# Channel-model curated-list CRUD
# ------------------------------------------------------------
# Operators were maintaining the list by hand-editing the JSON in the
# ``connection_params`` field. These endpoints replace that with surgical
# add / remove that:
#   - preserves unrelated keys in connection_params (don't blow away
#     port-map / alignment_name / etc when editing channel models)
#   - de-dupes by filename (case-sensitive — F64's SCPI is case-sensitive)
#   - rejects empty / non-string filenames at the API boundary so they
#     never reach the normaliser as a silent drop
#
# The endpoints don't trigger HAL reload — the GUI does that explicitly
# via the existing /hal/reload button so the operator controls timing
# (mid-test edits are a thing they may want to do without bouncing the
# driver, even if the new entry won't be visible until reload).
# ============================================================

class AddChannelModelRequest(BaseModel):
    """Payload for POST /instruments/{cat}/channel-models."""
    filename: str
    label: Optional[str] = None
    description: Optional[str] = None


@router.post(
    "/instruments/{category_key}/channel-models",
    response_model=ChannelModelsListResult,
)
def add_channel_model_entry(
    category_key: str,
    payload: AddChannelModelRequest,
    db: Session = Depends(get_db),
) -> ChannelModelsListResult:
    """Append one entry to ``connection_params['available_channel_models']``.

    De-duplicates by ``filename`` — if a row with the same filename exists,
    the request 409s. Use DELETE first if you mean to replace it.
    """
    from app.hal.channel_emulator import normalize_channel_model_entries

    filename = (payload.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=422, detail="filename must be a non-empty string")

    cat = (
        db.query(InstrumentCategoryModel)
        .filter(InstrumentCategoryModel.category_key == category_key)
        .first()
    )
    if cat is None:
        raise HTTPException(status_code=404, detail=f"category '{category_key}' not found")

    conn = (
        db.query(InstrumentConnectionDB)
        .filter(InstrumentConnectionDB.category_id == cat.id)
        .first()
    )
    if conn is None:
        # The category exists but the operator hasn't created an
        # InstrumentConnection record yet — happens when they're seeding
        # a fresh DB. Create a minimal record so the channel-model list
        # has somewhere to live.
        conn = InstrumentConnectionDB(category_id=cat.id, created_by="system")
        db.add(conn)
        db.flush()

    params = dict(conn.connection_params or {})
    existing = list(params.get("available_channel_models") or [])
    # Check duplicates using the normaliser output so the comparison is
    # against canonical filenames — protects against "EPA_5Hz.smu" added
    # twice with different surrounding shapes (bare string vs dict).
    for normalised in normalize_channel_model_entries(existing):
        if normalised["filename"] == filename:
            raise HTTPException(
                status_code=409,
                detail=f"channel model '{filename}' already in the list",
            )

    new_entry: Dict[str, Any] = {"filename": filename}
    if payload.label:
        new_entry["label"] = payload.label
    if payload.description:
        new_entry["description"] = payload.description
    existing.append(new_entry)
    params["available_channel_models"] = existing
    conn.connection_params = params
    # JSONB columns need an explicit "modified" flag for SQLAlchemy to
    # detect the in-place mutation; reassigning the dict (above) is
    # sufficient on most backends, but flag_modified is the belt-and-
    # suspenders form that works across PG/SQLite without behaviour drift.
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(conn, "connection_params")
    db.commit()

    normalised_all = normalize_channel_model_entries(existing)
    items = [ChannelModelEntry(**entry) for entry in normalised_all]
    return ChannelModelsListResult(items=items)


@router.delete(
    "/instruments/{category_key}/channel-models/{filename}",
    response_model=ChannelModelsListResult,
)
def remove_channel_model_entry(
    category_key: str,
    filename: str,
    db: Session = Depends(get_db),
) -> ChannelModelsListResult:
    """Remove the entry with the matching ``filename``.

    404 if the category or the entry doesn't exist. Preserves every other
    key in ``connection_params``.
    """
    from app.hal.channel_emulator import normalize_channel_model_entries

    cat = (
        db.query(InstrumentCategoryModel)
        .filter(InstrumentCategoryModel.category_key == category_key)
        .first()
    )
    if cat is None:
        raise HTTPException(status_code=404, detail=f"category '{category_key}' not found")

    conn = (
        db.query(InstrumentConnectionDB)
        .filter(InstrumentConnectionDB.category_id == cat.id)
        .first()
    )
    if conn is None or not conn.connection_params:
        raise HTTPException(status_code=404, detail=f"no curated list configured for '{category_key}'")

    params = dict(conn.connection_params)
    existing = list(params.get("available_channel_models") or [])
    if not existing:
        raise HTTPException(status_code=404, detail=f"curated list for '{category_key}' is empty")

    # Filter by matching the normalised filename — handles the mixed-
    # shape case (some entries are bare strings, others dicts) without
    # the caller having to know.
    kept_raw: List[Any] = []
    removed = False
    for raw in existing:
        if isinstance(raw, str):
            if raw == filename:
                removed = True
                continue
            kept_raw.append(raw)
        elif isinstance(raw, dict) and raw.get("filename") == filename:
            removed = True
            continue
        else:
            kept_raw.append(raw)

    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"channel model '{filename}' not in the curated list",
        )

    params["available_channel_models"] = kept_raw
    conn.connection_params = params
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(conn, "connection_params")
    db.commit()

    items = [ChannelModelEntry(**entry) for entry in normalize_channel_model_entries(kept_raw)]
    return ChannelModelsListResult(items=items)


@router.put("/instruments/{category_key}", response_model=FEInstrumentCategory)
def update_instrument_category(
    category_key: str,
    request: UpdateInstrumentCategoryRequest,
    db: Session = Depends(get_db)
):
    """
    更新仪器类别的选型和连接配置

    返回格式严格对齐前端 InstrumentCategory 类型。
    """
    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()

    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    # Update selected model (支持前端 modelId 和后端 selected_model_id)
    resolved_model_id = request.get_model_id()
    if resolved_model_id is not None:
        model = db.query(InstrumentModelDB).filter(
            InstrumentModelDB.id == resolved_model_id,
            InstrumentModelDB.category_id == category.id
        ).first()

        if not model:
            raise HTTPException(400, "Invalid model ID for this category")

        category.selected_model_id = resolved_model_id

    # Update or create connection
    if request.connection:
        connection = db.query(InstrumentConnectionDB).filter(
            InstrumentConnectionDB.category_id == category.id
        ).first()

        if not connection:
            connection = InstrumentConnectionDB(
                category_id=category.id,
                created_by="system"
            )
            db.add(connection)

        conn_data = request.connection.dict(exclude_unset=True)
        # 将前端的 controller 字段映射回 DB 的 protocol
        if "controller" in conn_data:
            conn_data["protocol"] = conn_data.pop("controller")

        # 从 endpoint 自动解析 controller_ip 和 port
        # 支持: "IP:Port", "TCPIP0::IP::inst0::INSTR", 纯 IP
        if "endpoint" in conn_data and conn_data["endpoint"]:
            parsed_ip, parsed_port = _parse_endpoint_to_ip_port(conn_data["endpoint"])
            if parsed_ip:
                conn_data["controller_ip"] = parsed_ip
            if parsed_port:
                conn_data["port"] = parsed_port

        for key, value in conn_data.items():
            if value is not None and hasattr(connection, key):
                setattr(connection, key, value)

    db.commit()
    db.refresh(category)

    # 取最新数据构建返回
    models = db.query(InstrumentModelDB).filter(
        InstrumentModelDB.category_id == category.id
    ).order_by(InstrumentModelDB.display_order).all()

    conn = db.query(InstrumentConnectionDB).filter(
        InstrumentConnectionDB.category_id == category.id
    ).first()

    return _convert_category(category, models, conn)


# ============================================================
# 连接测试
# ============================================================

class TestConnectionResult(BaseModel):
    """测试连接结果"""
    success: bool
    status: str  # "connected" | "timeout" | "refused" | "error"
    message: str
    idn: Optional[str] = None  # *IDN? response if SCPI
    latency_ms: Optional[float] = None


class TestConnectionRequest(BaseModel):
    """测试连接请求（可选覆盖参数）"""
    # 基站/信道仿真器类别按单会话控制，不接受未保存地址覆盖。
    ip: Optional[str] = None      # 其他仪表可覆盖数据库 IP 测试未保存编辑
    port: Optional[int] = None    # 覆盖数据库中的端口
    protocol: Optional[str] = None
    run_by: Optional[str] = None  # 操作员标识，写入 diagnostic_runs.run_by


def _merged_connection_config(conn: Optional[Any]) -> Dict[str, Any]:
    """构造与 HAL 初始化完全相同的 DB 连接配置真值。"""
    if conn is None:
        return {}
    config: Dict[str, Any] = {
        "endpoint": conn.endpoint,
        "ip": conn.controller_ip,
        "port": conn.port,
        "protocol": conn.protocol,
    }
    if conn.connection_params and isinstance(conn.connection_params, dict):
        config.update(conn.connection_params)
    return config


def _resolve_diagnostic_tcp_target(
    conn: Optional[Any],
    *,
    override_ip: Optional[str] = None,
    override_port: Optional[int] = None,
    default_port: Optional[int] = 5025,
) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """解析人工诊断 socket 目标；请求体 override 是一次性完整真值源。"""
    if override_ip is not None or override_port is not None:
        if not str(override_ip or "").strip():
            return None, None, "请求体覆盖 port 时必须同时提供 IP"
        config: Dict[str, Any] = {
            "ip": str(override_ip).strip(),
            "port": override_port if override_port is not None else 5025,
        }
    else:
        config = _merged_connection_config(conn)

    host, port, _resource, error = resolve_configured_tcpip_connection(config)
    if error:
        return None, None, error
    if not host:
        return None, None, "未配置 IP 地址"
    if not _validate_ip_address(host):
        return None, None, f"IP 地址格式无效: '{host}'"
    if port is None:
        if default_port is None:
            return None, None, (
                "单会话仪表未配置显式连接端口或完整 VISA resource；"
                "请保存完整配置并重新加载 HAL"
            )
        port = default_port
    return host, port, None


def _reconcile_diagnostic_target_with_live_driver(
    driver: Any,
    *,
    requested_ip: Optional[str],
    requested_port: Optional[int],
    target_error: Optional[str],
    override_requested: bool,
    require_saved_match: bool = False,
) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """让人工诊断请求与实际复用的 HAL 会话保持同一目标真值。"""
    must_match = override_requested or require_saved_match
    if must_match and target_error:
        return None, None, target_error

    driver_config = getattr(driver, "config", None)
    if not isinstance(driver_config, dict):
        if must_match:
            return None, None, (
                "无法核实活动 HAL 会话目标；请重新加载 HAL"
                if require_saved_match and not override_requested
                else "无法核实活动 HAL 会话目标，拒绝请求体地址覆盖"
            )
        return requested_ip, requested_port, None

    live_ip, live_port, _resource, live_error = (
        resolve_configured_tcpip_connection(driver_config)
    )
    if live_error or not live_ip:
        if must_match:
            prefix = (
                "无法核实活动 HAL 会话目标；请重新加载 HAL"
                if require_saved_match and not override_requested
                else "无法核实活动 HAL 会话目标，拒绝请求体地址覆盖"
            )
            return None, None, (
                prefix
                + (f": {live_error}" if live_error else "")
            )
        return requested_ip, requested_port, target_error

    actual_port = live_port
    for attr in ("port", "_port"):
        candidate = getattr(driver, attr, None)
        if isinstance(candidate, int) and 1 <= candidate <= 65535:
            actual_port = candidate
            break
    if actual_port is None:
        if must_match:
            return None, None, "无法核实活动 HAL 会话的实际端口；请重新加载 HAL"
        return requested_ip, requested_port, target_error
    if must_match and (
        requested_ip != live_ip or requested_port != actual_port
    ):
        if require_saved_match and not override_requested:
            return None, None, (
                "已保存配置与活动 HAL 会话目标不一致；"
                "请重新加载 HAL 后再操作"
            )
        return None, None, (
            "请求体覆盖目标与活动 HAL 会话目标不一致；"
            "请先保存配置并重新加载 HAL"
        )
    return live_ip, actual_port, None


def _single_session_saved_target_validator(
    category_key: str,
    *,
    db: Session,
    category_id: Any,
    saved_config: Dict[str, Any],
):
    """在协调锁内重读 DB 真值，再于 Remote acquire 前核对活动单会话。"""
    if category_key not in {"baseStation", "channelEmulator"}:
        return None

    def _canonical_identity(config: Dict[str, Any]) -> tuple[Any, ...]:
        host, port, resource, error = resolve_configured_tcpip_connection(config)
        canonical_resource = (
            tuple(part.strip().casefold() for part in resource.split("::"))
            if resource is not None
            else None
        )
        if category_key == "baseStation":
            protocol, profile = normalize_uxm_connection_selector(config)
        else:
            protocol = None
            profile = None
        return host.casefold(), port, canonical_resource, error, protocol, profile

    saved_identity = _canonical_identity(saved_config)

    def _validate(hal: Any) -> Optional[str]:
        current_conn = (
            db.query(InstrumentConnectionDB)
            .populate_existing()
            .filter(InstrumentConnectionDB.category_id == category_id)
            .first()
        )
        current_config = _merged_connection_config(current_conn)
        current_identity = _canonical_identity(current_config)

        # 若等待锁期间配置已变化，不能继续使用锁外捕获的 raw fallback。
        if current_identity != saved_identity:
            return "已保存连接配置在请求期间发生变化；请重试操作"

        current_ip, _current_port, _current_resource, current_error, _, _ = (
            current_identity
        )

        driver = _get_loaded_hal_driver_from_hal(hal, category_key)
        if driver is None:
            # 没有活动真实 driver 时，端点会走已校验的 DB raw fallback。
            return current_error

        driver_config = getattr(driver, "config", None)
        if not isinstance(driver_config, dict):
            return "无法核实活动 HAL 会话目标；请重新加载 HAL"
        live_identity = _canonical_identity(driver_config)
        live_ip, _live_port, _live_resource, live_error, _, _ = live_identity
        if live_error or not live_ip:
            return (
                "无法核实活动 HAL 会话目标；请重新加载 HAL"
                + (f": {live_error}" if live_error else "")
            )
        if current_identity != live_identity:
            return (
                "已保存配置与活动 HAL 会话目标不一致；"
                "请重新加载 HAL 后再操作"
            )
        return None

    return _validate


def _single_session_override_error(
    category_key: str, override_requested: bool
) -> Optional[str]:
    if override_requested and category_key in {"baseStation", "channelEmulator"}:
        return (
            "基站/信道仿真器为单会话控制类别，不允许一次性地址覆盖；"
            "请先保存配置并重新加载 HAL"
        )
    return None


@router.post("/instruments/{category_key}/test-connection", response_model=TestConnectionResult)
async def test_instrument_connection(
    category_key: str,
    body: Optional[TestConnectionRequest] = None,
    db: Session = Depends(get_db),
):
    """
    测试仪器连接

    尝试通过 TCP socket 连接到仪器的 IP:Port，
    如果是 SCPI 协议，发送 *IDN? 查询。

    非单会话仪表支持请求体覆盖 IP/Port。基站/信道仿真器类别必须先保存地址并
    reload HAL，再复用唯一活动会话，禁止用临时地址另开连接。
    """
    import socket
    import time
    from contextlib import AsyncExitStack

    # 使用 SCPI 命名空间的 logger，确保记录到 scpi.log
    scpi_logger = _unverified_scpi_logger()

    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    conn = db.query(InstrumentConnectionDB).filter(
        InstrumentConnectionDB.category_id == category.id
    ).first()

    raw_ip, raw_port, raw_target_error = _resolve_diagnostic_tcp_target(
        conn,
        override_ip=body.ip if body else None,
        override_port=body.port if body else None,
        default_port=(
            None
            if category_key in {"baseStation", "channelEmulator"}
            else 5025
        ),
    )
    preloaded_hal_driver = _get_loaded_hal_driver(category_key)
    override_requested = bool(body and (body.ip is not None or body.port is not None))
    single_session_error = _single_session_override_error(
        category_key, override_requested
    )
    if single_session_error:
        return TestConnectionResult(
            success=False,
            status="error",
            message=single_session_error,
        )
    preflight_error = raw_target_error
    if preloaded_hal_driver is not None:
        _live_ip, _live_port, preflight_error = (
            _reconcile_diagnostic_target_with_live_driver(
            preloaded_hal_driver,
            requested_ip=raw_ip,
            requested_port=raw_port,
            target_error=raw_target_error,
            override_requested=override_requested,
        )
        )
    protocol = (body.protocol if body and body.protocol else None) or (conn.protocol if conn else None) or ""

    if preflight_error:
        return TestConnectionResult(
            success=False,
            status="error",
            message=preflight_error,
        )

    validate_saved_target = _single_session_saved_target_validator(
        category_key,
        db=db,
        category_id=category.id,
        saved_config=_merged_connection_config(conn),
    )

    from app.services.instrument_test_lease import instrument_test_lease

    stack = AsyncExitStack()
    await stack.enter_async_context(instrument_test_lease(
        f"test-connection:{category_key}",
        control_f64=(category_key == "channelEmulator"),
        control_uxm=(category_key == "baseStation"),
        enable_monitoring=False,
        validate_before_remote=validate_saved_target,
    ))

    # 已加载的 F64/UXM 必须复用租约刚取得的唯一 HAL 会话；另开 raw socket
    # 会顶掉单会话仪表的既有连接并制造 BrokenPipe。只有 HAL 无该驱动时，
    # 才走下面的临时 TCP 探测路径。
    hal_driver = _get_loaded_hal_driver(category_key)
    if hal_driver is not None:
        ip, port, live_target_error = _reconcile_diagnostic_target_with_live_driver(
            hal_driver,
            requested_ip=raw_ip,
            requested_port=raw_port,
            target_error=raw_target_error,
            override_requested=override_requested,
        )
        if live_target_error:
            await stack.aclose()
            return TestConnectionResult(
                success=False,
                status="error",
                message=live_target_error,
            )
    else:
        ip, port, target_error = raw_ip, raw_port, raw_target_error

    # 摘要行挪到**选定传输方式之后**才发（外审 P1）：
    #   - 走已加载的驱动 → 按它自己的真假标，且文案说清是「复用现有会话」而不是
    #     「新建 TCP 连接」—— 那条分支根本没有新建连接，原文案在说假话；
    #   - 走裸 socket → 保持「来源不确定」。
    # 原先摘要在查找驱动**之前**发，于是摘要标 unverified、同一次操作的往返记录标 real。
    if hal_driver is not None:
        scpi_logger = _unverified_scpi_logger(hal_driver)
        scpi_logger.info(
            f"[TEST-CONN] {category_key} → 复用已加载的 HAL 会话 "
            f"({type(hal_driver).__name__})，未新建 TCP 连接",
            extra={"instrument_id": category_key, "direction": "CONNECT"},
        )
    else:
        scpi_logger.info(
            f"[TEST-CONN] {category_key} → TCP connecting {ip}:{port} (protocol={protocol})",
            extra={"instrument_id": category_key, "direction": "CONNECT"},
        )

    if hal_driver is not None:
        try:
            result = await _run_command_via_hal(
                hal_driver,
                "*IDN?",
                scpi_logger,
                category_key,
                timeout_ms=3000,
            )
            if conn:
                from datetime import datetime
                conn.status = "connected" if result.success else "error"
                conn.last_connected_at = datetime.utcnow() if result.success else None
                conn.last_error = None if result.success else result.error
                db.commit()
            return TestConnectionResult(
                success=result.success,
                status="connected" if result.success else "error",
                message=(
                    f"已通过现有 HAL 会话连接 {category_key}"
                    if result.success
                    else f"HAL 会话查询失败: {result.error}"
                ),
                idn=result.response,
                latency_ms=round(result.latency_ms, 1),
            )
        finally:
            await stack.aclose()

    if target_error:
        await stack.aclose()
        return TestConnectionResult(
            success=False,
            status="error",
            message=target_error,
        )

    sock = None
    start = time.monotonic()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((ip, port))
        latency = (time.monotonic() - start) * 1000

        scpi_logger.info(
            f"[TEST-CONN] {category_key} → TCP connected to {ip}:{port} ({latency:.0f}ms)",
            extra={"instrument_id": category_key, "direction": "CONNECT", "latency_ms": round(latency, 1)},
        )

        idn_response = None
        # Try SCPI *IDN? query if protocol suggests it
        if "SCPI" in protocol.upper():
            try:
                scpi_logger.debug(
                    f"[TEST-CONN] {category_key} → WRITE: *IDN?",
                    extra={"instrument_id": category_key, "direction": "WRITE", "command": "*IDN?"},
                )
                sock.sendall(b"*IDN?\n")
                idn_response = sock.recv(1024).decode("utf-8", errors="replace").strip()
                scpi_logger.info(
                    f"[TEST-CONN] {category_key} ← RESP: {idn_response}",
                    extra={"instrument_id": category_key, "direction": "READ", "response": idn_response},
                )
            except Exception as e:
                idn_response = "(SCPI query failed, but TCP connected)"
                scpi_logger.warning(
                    f"[TEST-CONN] {category_key} ← SCPI *IDN? failed: {e}",
                    extra={"instrument_id": category_key, "direction": "ERROR"},
                )

        # Update status in DB (only if conn record exists)
        if conn:
            from datetime import datetime
            conn.status = "connected"
            conn.last_connected_at = datetime.utcnow()
            conn.last_error = None
            db.commit()

        return TestConnectionResult(
            success=True,
            status="connected",
            message=f"成功连接到 {ip}:{port}",
            idn=idn_response,
            latency_ms=round(latency, 1),
        )

    except socket.timeout:
        elapsed = (time.monotonic() - start) * 1000
        scpi_logger.warning(
            f"[TEST-CONN] {category_key} → TIMEOUT {ip}:{port} ({elapsed:.0f}ms)",
            extra={"instrument_id": category_key, "direction": "ERROR", "error": "timeout"},
        )
        if conn:
            conn.status = "error"
            conn.last_error = f"Connection timeout to {ip}:{port}"
            db.commit()
        return TestConnectionResult(
            success=False,
            status="timeout",
            message=f"连接超时: {ip}:{port} (3秒)",
        )
    except ConnectionRefusedError:
        scpi_logger.warning(
            f"[TEST-CONN] {category_key} → REFUSED {ip}:{port}",
            extra={"instrument_id": category_key, "direction": "ERROR", "error": "refused"},
        )
        if conn:
            conn.status = "error"
            conn.last_error = f"Connection refused by {ip}:{port}"
            db.commit()
        return TestConnectionResult(
            success=False,
            status="refused",
            message=f"连接被拒绝: {ip}:{port}（端口未开放或服务未启动）",
        )
    except OSError as e:
        scpi_logger.error(
            f"[TEST-CONN] {category_key} → OS ERROR {ip}:{port}: {e}",
            extra={"instrument_id": category_key, "direction": "ERROR", "error": str(e)},
        )
        if conn:
            conn.status = "error"
            conn.last_error = str(e)
            db.commit()
        return TestConnectionResult(
            success=False,
            status="error",
            message=f"网络错误: {e}",
        )
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        await stack.aclose()


# ============================================================
# SCPI 命令终端
# ============================================================

class ScpiCommandRequest(BaseModel):
    """SCPI 命令请求"""
    command: str
    ip: Optional[str] = None
    port: Optional[int] = None
    timeout_ms: int = 3000  # 默认 3 秒超时
    run_by: Optional[str] = None  # 操作员标识，写入 diagnostic_runs.run_by


class ScpiCommandResult(BaseModel):
    """单条 SCPI 命令结果"""
    command: str
    response: Optional[str] = None
    success: bool
    error: Optional[str] = None
    latency_ms: float


class ScpiProbeResult(BaseModel):
    """批量 SCPI 探测结果"""
    ip: str
    port: int
    results: List[ScpiCommandResult]


async def _maybe_await(value):
    """Return ``value`` directly if sync, otherwise await it. Lets us treat
    sync and async HAL driver primitives (``_query``/``_write``) the same
    — see app/hal/base.py for the polymorphic dispatch we rely on here.
    """
    import asyncio
    if asyncio.iscoroutine(value):
        return await value
    return value


def _driver_supports_timeout_kwarg(driver) -> bool:
    """driver._do_query/_do_write 是否接受 timeout 关键字参数。

    P1-16 (2026-05-28): F64/FS16 (socket-based, asyncio.to_thread + raw recv)
    `_do_query` 显式签名 `(cmd, timeout=None)` — 慢操作 (F64 加载后 *OPC?、
    INP:LEV:MEAS?) 必须显式给足 timeout, 否则默认短超时让真响应迟到串到下一次读
    (desync 级联)。pyvisa-based driver (UXM/ENA/FSVA/CMW500 等) `_do_query(cmd)`
    没 timeout 形参 (timeout 是 visa_resource.timeout) — 透传 timeout=X 会 TypeError。
    introspect `_do_query` 而非 `_query`: 后者是 base 模板方法 (一律 **kwargs),
    真正的 signature constraint 在子类 override 的 `_do_query` 上。
    """
    import inspect

    try:
        sig = inspect.signature(driver._do_query)
    except (ValueError, TypeError, AttributeError):
        return False
    params = sig.parameters
    if "timeout" in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


async def _run_command_via_hal(
    driver,
    command: str,
    scpi_logger: logging.Logger,
    category_key: str,
    timeout_ms: Optional[int] = None,
) -> ScpiCommandResult:
    # 传输方式已经定了：走的是这个已加载的驱动，来源就是**已知的** ——
    # 改用按它派生的日志器，别让调用方传进来的「来源不确定」把真往返标错（外审 P1）。
    scpi_logger = _unverified_scpi_logger(driver)
    """Execute one SCPI command through the loaded HAL driver's primitives.

    Reuses the live VISA session the driver already holds — critical for
    single-client instruments (e.g. PROPSIM FS16's TCP SOCKET port,
    where opening a second client either times out at the application
    layer or is silently ignored). On 2026-05-13 at CAICT, FS16's
    diagnostic terminal showed 5/5 "timed out, 0ms" exactly because
    the old socket-only path opened a parallel SOCKET while HAL already
    held one.

    P1-16: ``timeout_ms`` 在 driver 接受 ``timeout`` kwarg 时透传 — 修 F64/FS16
    慢操作 desync (5/27 CAICT 现场: 经后端 set 输入参考的 closed-loop 没闭环
    的直接原因之一, 见 [morning-log §10.5])。不支持的 driver 保持默认行为。
    """
    import time

    is_query = command.strip().endswith("?")
    safe_command = redact_instrument_command_text(command)
    start = time.monotonic()
    pass_timeout = timeout_ms is not None and _driver_supports_timeout_kwarg(driver)
    try:
        scpi_logger.debug(
            f"[SCPI-TERM via HAL] {category_key} → {safe_command}"
            + (f" (timeout={timeout_ms}ms)" if pass_timeout else ""),
            extra={
                "instrument_id": category_key,
                "direction": "WRITE",
                "command": safe_command,
            },
        )
        if is_query:
            if pass_timeout:
                raw = await _maybe_await(driver._query(command.strip(), timeout=timeout_ms))
            else:
                raw = await _maybe_await(driver._query(command.strip()))
            raw_str = str(raw or "").strip()
            safe_response = redact_instrument_exchange_text(
                raw_str, command=command
            )
            scpi_logger.debug(
                f"[SCPI-TERM via HAL] {category_key} ← "
                f"{safe_response[:200] if safe_response else '(empty)'}",
                extra={
                    "instrument_id": category_key,
                    "direction": "READ",
                    "response": safe_response[:500],
                },
            )
            latency = (time.monotonic() - start) * 1000
            if not raw_str:
                return ScpiCommandResult(
                    command=command.strip(),
                    response=None,
                    success=False,
                    error="仪器未返回数据（空响应）",
                    latency_ms=round(latency, 1),
                )
            return ScpiCommandResult(
                command=command.strip(),
                response=raw_str,
                success=True,
                latency_ms=round(latency, 1),
            )
        # Write command — no response expected.
        if pass_timeout:
            await _maybe_await(driver._write(command.strip(), timeout=timeout_ms))
        else:
            await _maybe_await(driver._write(command.strip()))
        latency = (time.monotonic() - start) * 1000
        return ScpiCommandResult(
            command=command.strip(),
            response=None,
            success=True,
            latency_ms=round(latency, 1),
        )
    except Exception as e:  # noqa: BLE001
        latency = (time.monotonic() - start) * 1000
        safe_error = redact_instrument_exchange_text(e, command=command)
        scpi_logger.warning(
            f"[SCPI-TERM via HAL] {category_key} ← ERROR on "
            f"'{safe_command}': {safe_error}",
            extra={"instrument_id": category_key, "direction": "ERROR"},
        )
        return ScpiCommandResult(
            command=command.strip(),
            success=False,
            error=f"{type(e).__name__}: {e}",
            latency_ms=round(latency, 1),
        )


def _get_loaded_hal_driver_from_hal(hal: Any, category_key: str):
    """从指定 HAL 快照读取可直接通信的真实 driver。"""
    if hal is None:
        return None
    driver = (getattr(hal, "drivers", None) or {}).get(category_key)
    if driver is None:
        return None
    if type(driver).__name__.startswith("Mock"):
        return None
    if not callable(getattr(driver, "_query", None)):
        return None
    if not callable(getattr(driver, "_write", None)):
        return None
    return driver


def _get_loaded_hal_driver(category_key: str):
    """Return the live HAL driver instance for ``category_key`` if it's a
    *real* driver that can actually talk to hardware; otherwise None so
    the caller falls back to opening a fresh TCP socket.

    Skip cases:
      1. HAL service not initialised yet.
      2. No driver loaded for this category.
      3. Driver is a Mock — Mock drivers inherit the base no-op
         ``_do_query`` that returns ``""``. Routing the SCPI terminal
         through a Mock makes ``/scpi-probe`` and ``/scpi-command``
         silently return empty (latency 1-2 ms) instead of probing the
         configured IP. We hit this on 2026-05-13 at CAICT when HAL
         was in mock_fallback mode and the operator tried the UXM SCPI
         terminal on a freshly-configured IP — every command came back
         "instrument did not return data" because the Mock was happily
         intercepting them. Skipping Mock here lets the socket fallback
         take over so the operator can probe the real box.
      4. Driver doesn't expose ``_query`` / ``_write`` primitives.
    """
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
    except Exception:  # noqa: BLE001
        return None
    return _get_loaded_hal_driver_from_hal(hal, category_key)


def _send_scpi_command(
    sock: "socket.socket",
    command: str,
    scpi_logger: logging.Logger,
    category_key: str,
) -> ScpiCommandResult:
    """通过已连接的 socket 发送单条 SCPI 命令并返回结果"""
    import time

    is_query = command.strip().endswith("?")
    safe_command = redact_instrument_command_text(command)
    start = time.monotonic()

    try:
        scpi_logger.debug(
            f"[SCPI-TERM] {category_key} → WRITE: {safe_command}",
            extra={
                "instrument_id": category_key,
                "direction": "WRITE",
                "command": safe_command,
            },
        )
        sock.sendall((command.strip() + "\n").encode())

        response = None
        if is_query:
            raw = sock.recv(4096).decode("utf-8", errors="replace").strip()
            response = raw if raw else None
            safe_response = redact_instrument_exchange_text(raw, command=command)
            scpi_logger.debug(
                f"[SCPI-TERM] {category_key} ← RESP: "
                f"{safe_response[:200] if safe_response else '(empty)'}",
                extra={
                    "instrument_id": category_key,
                    "direction": "READ",
                    "response": safe_response[:500],
                },
            )

            # 查询命令返回空响应 → 仪器未真正响应
            if not raw:
                latency = (time.monotonic() - start) * 1000
                return ScpiCommandResult(
                    command=command.strip(),
                    response=None,
                    success=False,
                    error="仪器未返回数据（空响应），请检查连接和 IP 地址",
                    latency_ms=round(latency, 1),
                )

        latency = (time.monotonic() - start) * 1000
        return ScpiCommandResult(
            command=command.strip(),
            response=response,
            success=True,
            latency_ms=round(latency, 1),
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        safe_error = redact_instrument_exchange_text(e, command=command)
        scpi_logger.warning(
            f"[SCPI-TERM] {category_key} ← ERROR on "
            f"'{safe_command}': {safe_error}",
            extra={"instrument_id": category_key, "direction": "ERROR"},
        )
        return ScpiCommandResult(
            command=command.strip(),
            success=False,
            error=str(e),
            latency_ms=round(latency, 1),
        )


# 常用 SCPI 诊断命令集
COMMON_SCPI_COMMANDS = [
    ("*IDN?", "设备标识"),
    ("*OPC?", "操作完成查询"),
    ("*STB?", "状态字节"),
    ("SYST:ERR?", "错误队列"),
    ("SYST:VERS?", "SCPI 版本"),
]


def _resolve_ip_port(
    body_ip: Optional[str],
    body_port: Optional[int],
    conn: Optional[Any],
) -> tuple:
    """兼容包装：从一次性 override 或完整 DB 配置解析 IP 和 Port。"""
    ip, port, _error = _resolve_diagnostic_tcp_target(
        conn, override_ip=body_ip, override_port=body_port
    )
    return ip, port


def _parse_endpoint_to_ip_port(endpoint: str) -> tuple:
    """
    从多种格式的端点字符串中解析出 IP 和 Port。

    支持的格式:
    - VISA: "TCPIP0::192.168.0.132::inst0::INSTR" → ("192.168.0.132", None)
    - VISA with port: "TCPIP0::192.168.0.132::5025::INSTR" → ("192.168.0.132", 5025)
    - IP:Port: "192.168.0.132:5025" → ("192.168.0.132", 5025)
    - Plain IP: "192.168.0.132" → ("192.168.0.132", None)
    """
    import re

    ep = endpoint.strip()
    if not ep:
        return None, None

    # VISA 资源字符串: TCPIP[n]::host[::port]::...::INSTR
    if ep.upper().startswith("TCPIP"):
        parts = ep.split("::")
        # parts[0] = "TCPIP0", parts[1] = IP/hostname, parts[2+] = inst/port/INSTR
        if len(parts) >= 2:
            ip_candidate = parts[1].strip()
            port_candidate = None
            # Check if parts[2] is a port number
            if len(parts) >= 3:
                try:
                    port_candidate = int(parts[2].strip())
                except ValueError:
                    pass
            return ip_candidate, port_candidate
        return None, None

    # IP:Port 格式
    if ":" in ep:
        host_part, port_part = ep.rsplit(":", 1)
        try:
            return host_part.strip(), int(port_part.strip())
        except ValueError:
            return ep, None

    # 纯 IP
    return ep, None


def _validate_ip_address(ip: str) -> bool:
    """验证 IPv4 地址格式"""
    import re
    if not ip:
        return False
    # IPv4 pattern
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip)
    if not match:
        return False
    return all(0 <= int(g) <= 255 for g in match.groups())


def _audit_scpi_run(
    db: Session,
    *,
    category_key: str,
    target_name: str,
    params: Dict[str, Any],
    success: bool,
    output: Optional[str],
    error_message: Optional[str],
    duration_ms: int,
    run_by: Optional[str],
) -> None:
    """Persist one diagnostic_runs row for an SCPI Console action.

    SCPI Console fires direct-IP, so lab_profile_id=None — the minimal
    DiagnosticContext still gives us the truncate + record helpers.
    Best-effort: audit failures are logged but never propagated, since
    the operator already has the SCPI result and the audit trail is
    secondary to the primary action.
    """
    try:
        ctx = build_diagnostic_context(db, lab_profile_id=None)
        ctx.record_run(
            db,
            kind=DiagnosticKind.SCPI_COMMAND,
            target_name=target_name,
            success=success,
            params=params,
            output=output,
            error_message=error_message,
            duration_ms=duration_ms,
            run_by=run_by,
        )
    except Exception as e:
        logger.warning(
            "Failed to audit SCPI run for %s: %s", category_key, e, exc_info=True
        )


@router.post("/instruments/{category_key}/scpi-command", response_model=ScpiCommandResult)
async def send_scpi_command(
    category_key: str,
    request: ScpiCommandRequest,
    db: Session = Depends(get_db),
):
    """
    向仪器发送单条 SCPI 命令并返回响应。

    查询命令（以 ? 结尾）会等待并返回仪器响应；
    写入命令只发送不读取。
    """
    import socket
    import time

    scpi_logger = _unverified_scpi_logger()

    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    conn = db.query(InstrumentConnectionDB).filter(
        InstrumentConnectionDB.category_id == category.id
    ).first()

    raw_ip, raw_port, raw_target_error = _resolve_diagnostic_tcp_target(
        conn,
        override_ip=request.ip,
        override_port=request.port,
        default_port=(
            None
            if category_key in {"baseStation", "channelEmulator"}
            else 5025
        ),
    )
    override_requested = request.ip is not None or request.port is not None
    raw_command = request.command.strip()
    safe_command = redact_instrument_command_text(raw_command)
    target_name = f"{category_key}: {safe_command}"
    audit_params: Dict[str, Any] = {
        "category_key": category_key,
        "command": safe_command,
        "ip": request.ip if request.ip is not None else raw_ip,
        "port": request.port if request.port is not None else raw_port,
        "timeout_ms": request.timeout_ms,
    }
    audit_started = time.monotonic()

    def _audit(result: ScpiCommandResult) -> ScpiCommandResult:
        _audit_scpi_run(
            db,
            category_key=category_key,
            target_name=target_name,
            params=audit_params,
            success=result.success,
            output=(
                redact_instrument_exchange_text(
                    result.response, command=raw_command
                )
                if result.response is not None else None
            ),
            error_message=(
                redact_instrument_exchange_text(
                    result.error, command=raw_command
                )
                if result.error is not None else None
            ),
            duration_ms=int((time.monotonic() - audit_started) * 1000),
            run_by=request.run_by,
        )
        return result

    single_session_error = _single_session_override_error(
        category_key, override_requested
    )
    if single_session_error:
        return _audit(ScpiCommandResult(
            command=request.command,
            success=False,
            error=single_session_error,
            latency_ms=0,
        ))

    preloaded_hal_driver = _get_loaded_hal_driver(category_key)
    preflight_error = raw_target_error
    if preloaded_hal_driver is not None:
        _live_ip, _live_port, preflight_error = (
            _reconcile_diagnostic_target_with_live_driver(
            preloaded_hal_driver,
            requested_ip=raw_ip,
            requested_port=raw_port,
            target_error=raw_target_error,
            override_requested=override_requested,
        )
        )
    if preflight_error:
        return _audit(ScpiCommandResult(
            command=request.command,
            success=False,
            error=preflight_error,
            latency_ms=0,
        ))

    validate_saved_target = _single_session_saved_target_validator(
        category_key,
        db=db,
        category_id=category.id,
        saved_config=_merged_connection_config(conn),
    )

    async with instrument_test_lease(
        f"scpi-command:{category_key}",
        control_f64=(category_key == "channelEmulator"),
        control_uxm=(category_key == "baseStation"),
        enable_monitoring=False,
        validate_before_remote=validate_saved_target,
    ):
        # 在租约内重新解析 driver，防止 HAL reload 在解析与首条命令之间换实例。
        hal_driver = _get_loaded_hal_driver(category_key)
        if hal_driver is not None:
            ip, port, live_target_error = _reconcile_diagnostic_target_with_live_driver(
                hal_driver,
                requested_ip=raw_ip,
                requested_port=raw_port,
                target_error=raw_target_error,
                override_requested=override_requested,
            )
            if live_target_error:
                return _audit(ScpiCommandResult(
                    command=request.command,
                    success=False,
                    error=live_target_error,
                    latency_ms=0,
                ))
            audit_params["ip"] = ip
            audit_params["port"] = port
            result = await _run_command_via_hal(
                hal_driver, request.command, scpi_logger, category_key,
                timeout_ms=request.timeout_ms,
            )
            return _audit(result)

        ip, port, target_error = raw_ip, raw_port, raw_target_error
        if target_error:
            return _audit(ScpiCommandResult(
                command=request.command,
                success=False,
                error=target_error,
                latency_ms=0,
            ))

        if not ip:
            return _audit(ScpiCommandResult(
                command=request.command,
                success=False,
                error="未配置 IP 地址",
                latency_ms=0,
            ))
        if not _validate_ip_address(ip):
            return _audit(ScpiCommandResult(
                command=request.command,
                success=False,
                error=f"IP 地址格式无效: '{ip}'",
                latency_ms=0,
            ))

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(request.timeout_ms / 1000.0)
            sock.connect((ip, port))
            result = _send_scpi_command(
                sock, request.command, scpi_logger, category_key
            )
            sock.close()
            return _audit(result)
        except socket.timeout:
            return _audit(ScpiCommandResult(
                command=request.command,
                success=False,
                error=f"连接超时: {ip}:{port}",
                latency_ms=request.timeout_ms,
            ))
        except Exception as e:
            return _audit(ScpiCommandResult(
                command=request.command,
                success=False,
                error=str(e),
                latency_ms=0,
            ))


@router.post("/instruments/{category_key}/scpi-probe", response_model=ScpiProbeResult)
async def probe_scpi_commands(
    category_key: str,
    body: Optional[TestConnectionRequest] = None,
    db: Session = Depends(get_db),
):
    """
    对仪器执行一组常用 SCPI 诊断命令 (*IDN?, *OPC?, *STB?, SYST:ERR?, SYST:VERS?)。

    用于连接成功后快速检查仪器状态。
    """
    import socket
    import time

    scpi_logger = _unverified_scpi_logger()

    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    conn = db.query(InstrumentConnectionDB).filter(
        InstrumentConnectionDB.category_id == category.id
    ).first()

    raw_ip, raw_port, raw_target_error = _resolve_diagnostic_tcp_target(
        conn,
        override_ip=body.ip if body else None,
        override_port=body.port if body else None,
        default_port=(
            None
            if category_key in {"baseStation", "channelEmulator"}
            else 5025
        ),
    )
    preloaded_hal_driver = _get_loaded_hal_driver(category_key)
    override_requested = bool(body and (body.ip is not None or body.port is not None))
    single_session_error = _single_session_override_error(
        category_key, override_requested
    )
    if single_session_error:
        raise HTTPException(400, single_session_error)
    preflight_error = raw_target_error
    if preloaded_hal_driver is not None:
        _live_ip, _live_port, preflight_error = (
            _reconcile_diagnostic_target_with_live_driver(
            preloaded_hal_driver,
            requested_ip=raw_ip,
            requested_port=raw_port,
            target_error=raw_target_error,
            override_requested=override_requested,
        )
        )
    if preflight_error:
        raise HTTPException(400, preflight_error)

    validate_saved_target = _single_session_saved_target_validator(
        category_key,
        db=db,
        category_id=category.id,
        saved_config=_merged_connection_config(conn),
    )

    results: List[ScpiCommandResult] = []
    audit_started = time.monotonic()

    async with instrument_test_lease(
        f"scpi-probe:{category_key}",
        control_f64=(category_key == "channelEmulator"),
        control_uxm=(category_key == "baseStation"),
        enable_monitoring=False,
        validate_before_remote=validate_saved_target,
    ):
        # Prefer the live HAL driver session if loaded — avoids a parallel
        # TCP client to single-session instruments. Driver lookup stays inside
        # the lease so reload cannot swap it before the first command.
        hal_driver = _get_loaded_hal_driver(category_key)
        if hal_driver is not None:
            ip, port, live_target_error = _reconcile_diagnostic_target_with_live_driver(
                hal_driver,
                requested_ip=raw_ip,
                requested_port=raw_port,
                target_error=raw_target_error,
                override_requested=override_requested,
            )
            if live_target_error:
                raise HTTPException(400, live_target_error)
            # 传输方式已定：走这个已加载的驱动 → 摘要行也要按它的真假标。
            # 否则会出现「摘要标 unverified、同一次探测的命令记录标 real」自相矛盾（外审 P1）。
            scpi_logger = _unverified_scpi_logger(hal_driver)
            scpi_logger.info(
                f"[SCPI-PROBE] {category_key} → Running {len(COMMON_SCPI_COMMANDS)} "
                f"diagnostic commands via live HAL driver ({type(hal_driver).__name__})",
                extra={"instrument_id": category_key, "direction": "PROBE"},
            )
            for cmd, _desc in COMMON_SCPI_COMMANDS:
                results.append(await _run_command_via_hal(
                    hal_driver, cmd, scpi_logger, category_key
                ))
        else:
            ip, port, target_error = raw_ip, raw_port, raw_target_error
            if target_error:
                raise HTTPException(400, target_error)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect((ip, port))
                scpi_logger.info(
                    f"[SCPI-PROBE] {category_key} → Running {len(COMMON_SCPI_COMMANDS)} "
                    f"diagnostic commands on {ip}:{port} via fresh socket "
                    f"(HAL driver not loaded)",
                    extra={"instrument_id": category_key, "direction": "PROBE"},
                )
                for cmd, _desc in COMMON_SCPI_COMMANDS:
                    results.append(_send_scpi_command(
                        sock, cmd, scpi_logger, category_key
                    ))
                sock.close()
            except Exception as e:
                scpi_logger.error(
                    f"[SCPI-PROBE] {category_key} → Connection failed: {e}",
                    extra={"instrument_id": category_key, "direction": "ERROR"},
                )
                executed = {r.command for r in results}
                for cmd, _desc in COMMON_SCPI_COMMANDS:
                    if cmd not in executed:
                        results.append(ScpiCommandResult(
                            command=cmd,
                            success=False,
                            error=str(e),
                            latency_ms=0,
                        ))

    # Single audit row for the whole probe — operator cognition is
    # "one health check", per-command rows would just be noise.
    all_succeeded = bool(results) and all(r.success for r in results)
    output_summary = "\n".join(
        f"{r.command} → {'OK: ' + (r.response or '(no response)') if r.success else 'FAIL: ' + (r.error or 'unknown')}"
        for r in results
    )
    first_error = next((r.error for r in results if not r.success and r.error), None)
    _audit_scpi_run(
        db,
        category_key=category_key,
        target_name=f"probe:{category_key}",
        params={
            "category_key": category_key,
            "ip": ip,
            "port": port,
            "commands": [cmd for cmd, _ in COMMON_SCPI_COMMANDS],
        },
        success=all_succeeded,
        output=output_summary,
        error_message=None if all_succeeded else first_error,
        duration_ms=int((time.monotonic() - audit_started) * 1000),
        run_by=body.run_by if body else None,
    )

    return ScpiProbeResult(ip=ip, port=port, results=results)


# ============================================================
# HAL 模式管理
# ============================================================

class HALModeStatus(BaseModel):
    """当前 HAL 驱动模式状态"""
    mode: str  # "mock" | "real"
    driver_count: int
    active_drivers: List[str]


class HALModeSwitchRequest(BaseModel):
    """切换 HAL 模式请求"""
    mode: str  # "mock" | "real"


class HALModeSwitchResult(BaseModel):
    """切换 HAL 模式结果"""
    success: bool
    previous_mode: str
    current_mode: str
    active_drivers: List[str]
    driver_count: int
    message: str


@router.get("/instruments/hal/status", response_model=HALModeStatus)
def get_hal_status():
    """获取当前 HAL 驱动模式和状态"""
    from app.services.instrument_hal_service import get_hal_service
    hal = get_hal_service()
    return HALModeStatus(
        mode=hal.mode.value,
        driver_count=len(hal.drivers),
        active_drivers=list(hal.drivers.keys()),
    )


# ============================================================
# P3-5: composite readiness snapshot (drivers + lab + cal + dut-attach)
# ============================================================

class DriverReadinessRowResponse(BaseModel):
    """One driver's row in the readiness report. Shape mirrors
    ``app.services.readiness.DriverReadinessRow``.

    ``extras`` is driver-specific (F64 surfaces firmware_version /
    band_label / product_family from P3-4's SYST:INFO? parse; other
    drivers return ``{}`` until they override ``readiness_metadata()``).
    """
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    category: str
    model: str
    endpoint: str
    status: Literal["ok", "warn", "fail", "skipped"]
    detail: str
    extras: Dict[str, Any] = {}
    # P1-11: when status=="fail", "network" (TCP unreachable — likely
    # wrong subnet) vs "scpi" (TCP reached, *IDN?/connect failed). None
    # whenever status != "fail".
    fail_kind: Optional[Literal["network", "scpi"]] = None


class SubnetReachabilityResponse(BaseModel):
    """P1-11: per-/24-subnet reachability rollup of the driver rows.

    ``reachable=False`` means at least one instrument on this subnet
    failed TCP preflight (``fail_kind=="network"``) — the control PC
    most likely isn't on this subnet. ``hint`` is an actionable,
    runbook-pointing string for unreachable subnets, ``null`` for
    reachable ones. The sentinel cidr ``"unknown"`` buckets rows whose
    endpoint had no parseable IPv4 host.

    P1-13: ``probed`` is False when NO instrument on this subnet was actually
    network-probed (mock-HAL mode, or bindings with no parseable host:port) —
    the subnet is then 未探测/unknown and ``reachable`` is meaningless (don't
    render it as reachable). Tri-state: ``!probed`` = unknown; ``probed &&
    reachable`` = reachable; ``probed && !reachable`` = unreachable."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    cidr: str
    reachable: bool
    instrument_count: int
    unreachable_count: int
    hint: Optional[str] = None
    probed: bool = False


class LabProfileReadinessResponse(BaseModel):
    """Active LabProfile state. ``status`` ∈
    {"ok", "inactive", "missing", "ambiguous"} — see
    ``app.services.readiness.LabProfileReadiness`` for semantics."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    is_active: bool
    status: Literal["ok", "inactive", "missing", "ambiguous"]
    detail: str


class CalibrationReadinessResponse(BaseModel):
    """Active lab's calibration certificate validity. ``status`` ∈
    {"valid", "expired", "missing", "no_lab"} — distinguishes
    "no lab to even look at a cert through" from "lab exists but
    has no cert bound" so the GUI can suggest the right next step
    (set up lab vs run calibration)."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    certificate_number: Optional[str] = None
    valid_until_iso: Optional[str] = None
    status: Literal["valid", "expired", "missing", "no_lab"]
    days_remaining: Optional[int] = None
    detail: str


class DutAttachReadinessResponse(BaseModel):
    """DUT-attach state — placeholder in this build. ``status`` is
    always ``"not_implemented"`` because no runtime model exists
    (no probe-sensing, RFID, session table). Field is surfaced so
    the readiness shape is forward-compatible with future sensing
    work — swapping in a real implementation won't break the
    openapi contract or GUI consumers."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    status: Literal["not_implemented"]
    detail: str


class HALReadinessResponse(BaseModel):
    """Composite snapshot returned by ``GET /instruments/hal/readiness``.

    ``available=False`` means HAL hasn't initialised yet (the
    lifespan startup hasn't run, or a reload is mid-flight). The
    GUI should render "HAL not ready" rather than treating the
    placeholder sub-sections as the live state."""
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    available: bool
    drivers: List[DriverReadinessRowResponse]
    lab_profile: LabProfileReadinessResponse
    calibration: CalibrationReadinessResponse
    dut_attach: DutAttachReadinessResponse
    generated_at_iso: str
    # P1-11: per-/24-subnet reachability rollup. Empty list when HAL
    # hasn't initialised or no drivers carry a parseable IP.
    subnets: List[SubnetReachabilityResponse] = []


@router.get("/instruments/hal/readiness", response_model=HALReadinessResponse)
def get_hal_readiness(
    lab_profile_id: Optional[UUID] = Query(
        None,
        description=(
            "当前浏览器显式选择的 LabProfile；省略时保留唯一 active lab 兼容语义"
        ),
    ),
    db: Session = Depends(get_db),
):
    """P3-5: composite "is the chamber actually ready?" snapshot.

    Bundles the HAL-owned per-driver snapshot with request-time LabProfile
    state, calibration certificate validity, and a DUT-attach placeholder.
    When ``lab_profile_id`` is explicit, the Lab/calibration sections are
    scoped to that exact active profile; omission keeps unique-active
    compatibility. Operator can
    Slack-paste a single JSON or open one GUI panel instead of grep-
    ing log files for HAL init + checking LabProfile separately +
    looking up cert expiry by hand.

    Returns ``available=false`` with empty HAL-owned driver/subnet sections
    when HAL hasn't initialised yet (lifespan not run, mid-reload). The
    DB-only LabProfile/calibration sections remain live in that state.
    """
    from app.services.instrument_hal_service import get_hal_service
    from app.services.readiness import (
        build_calibration_readiness,
        build_lab_profile_readiness,
    )

    try:
        lab_section = build_lab_profile_readiness(db, lab_profile_id)
    except ValueError as exc:
        # An explicit stale/inactive selection is a caller-visible conflict.
        # Never fall back to another active LabProfile and risk a false green.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    calibration_section = build_calibration_readiness(db, lab_section)

    hal = get_hal_service()
    report = hal.last_readiness_report if hal else None

    if report is None:
        # HAL not initialised — return a shaped placeholder so the GUI
        # doesn't have to special-case 404 / missing field handling.
        from datetime import datetime as _dt
        return HALReadinessResponse(
            available=False,
            drivers=[],
            lab_profile=LabProfileReadinessResponse(
                profile_id=lab_section.profile_id,
                profile_name=lab_section.profile_name,
                is_active=lab_section.is_active,
                status=lab_section.status,
                detail=lab_section.detail,
            ),
            calibration=CalibrationReadinessResponse(
                certificate_number=calibration_section.certificate_number,
                valid_until_iso=calibration_section.valid_until_iso,
                status=calibration_section.status,
                days_remaining=calibration_section.days_remaining,
                detail=calibration_section.detail,
            ),
            dut_attach=DutAttachReadinessResponse(
                status="not_implemented",
                detail="HAL not initialised yet",
            ),
            generated_at_iso=_dt.utcnow().isoformat(),
            subnets=[],
        )

    return HALReadinessResponse(
        available=True,
        drivers=[
            DriverReadinessRowResponse(
                category=r.category,
                model=r.model,
                endpoint=r.endpoint,
                status=r.status,
                detail=r.detail,
                extras=r.extras,
                fail_kind=r.fail_kind,
            )
            for r in report.drivers
        ],
        lab_profile=LabProfileReadinessResponse(
            profile_id=lab_section.profile_id,
            profile_name=lab_section.profile_name,
            is_active=lab_section.is_active,
            status=lab_section.status,
            detail=lab_section.detail,
        ),
        calibration=CalibrationReadinessResponse(
            certificate_number=calibration_section.certificate_number,
            valid_until_iso=calibration_section.valid_until_iso,
            status=calibration_section.status,
            days_remaining=calibration_section.days_remaining,
            detail=calibration_section.detail,
        ),
        dut_attach=DutAttachReadinessResponse(
            status=report.dut_attach.status,
            detail=report.dut_attach.detail,
        ),
        generated_at_iso=report.generated_at_iso,
        subnets=[
            SubnetReachabilityResponse(
                cidr=s.cidr,
                reachable=s.reachable,
                instrument_count=s.instrument_count,
                unreachable_count=s.unreachable_count,
                hint=s.hint,
                probed=s.probed,
            )
            for s in report.subnets
        ],
    )


@router.post("/instruments/hal/switch", response_model=HALModeSwitchResult)
async def switch_hal_mode_endpoint(request: HALModeSwitchRequest):
    """
    运行时切换 HAL 驱动模式（Mock ↔ Real）

    不需要重启服务。切换后所有驱动会被重新初始化。
    """
    from app.services.instrument_hal_service import switch_hal_mode, DriverMode
    from app.services.instrument_test_lease import (
        active_test_lease_purpose,
        hal_mutation_guard,
    )

    if request.mode not in ("mock", "real"):
        raise HTTPException(400, f"Invalid mode: {request.mode}. Use 'mock' or 'real'.")

    target_mode = DriverMode.MOCK if request.mode == "mock" else DriverMode.REAL

    try:
        async with hal_mutation_guard():
            active_lease = active_test_lease_purpose()
            if active_lease is not None:
                raise HTTPException(
                    409,
                    f"仪表操作 {active_lease!r} 正在运行，结束前不能切换 HAL 模式",
                )
            result = await switch_hal_mode(target_mode)
        return HALModeSwitchResult(
            success=True,
            previous_mode=result["previous_mode"],
            current_mode=result["current_mode"],
            active_drivers=result["active_drivers"],
            driver_count=result["driver_count"],
            message=f"已切换到 {result['current_mode']} 模式，{result['driver_count']} 个驱动已激活",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HAL mode switch failed: {e}", exc_info=True)
        return HALModeSwitchResult(
            success=False,
            previous_mode=request.mode,
            current_mode="unknown",
            active_drivers=[],
            driver_count=0,
            message=f"切换失败: {e}",
        )


# ============================================================
# 仪器品类启停
# ============================================================

class ToggleActiveRequest(BaseModel):
    """启停请求"""
    isActive: bool


class ToggleActiveResult(BaseModel):
    """启停结果"""
    key: str
    isActive: bool
    message: str


@router.patch("/instruments/{category_key}/active", response_model=ToggleActiveResult)
def toggle_category_active(
    category_key: str,
    request: ToggleActiveRequest,
    db: Session = Depends(get_db),
):
    """
    切换仪器品类的启用/停用状态

    用途：校准完成后停用 VNA，测试阶段只保留必需仪器在线。
    """
    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    category.is_active = request.isActive
    db.commit()

    action = "启用" if request.isActive else "停用"
    logger.info(f"[Instrument] {category_key} {action}")

    return ToggleActiveResult(
        key=category_key,
        isActive=request.isActive,
        message=f"已{action} {category.category_name}",
    )

# ============================================================
# 仪器级驱动模式
# ============================================================

class DriverModeRequest(BaseModel):
    """仪器级驱动模式切换请求"""
    mode: str  # "auto" | "mock" | "real"


class DriverModeResult(BaseModel):
    """仪器级驱动模式切换结果"""
    key: str
    driverMode: str
    message: str


@router.patch("/instruments/{category_key}/driver-mode", response_model=DriverModeResult)
def set_instrument_driver_mode(
    category_key: str,
    request: DriverModeRequest,
    db: Session = Depends(get_db),
):
    """
    设置单台仪器的驱动模式（auto / mock / real）

    - auto: 跟随全局 HAL 开关
    - mock: 强制使用仿真驱动（不论全局设定）
    - real: 强制使用真实驱动（不论全局设定）

    修改后需要重新切换全局 HAL 模式（或重启服务）以应用。
    """
    valid_modes = ("auto", "mock", "real")
    if request.mode not in valid_modes:
        raise HTTPException(400, f"无效的驱动模式: '{request.mode}'。可选: {valid_modes}")

    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    category.driver_mode = request.mode
    db.commit()

    mode_labels = {"auto": "自动", "mock": "强制仿真", "real": "强制真实"}
    label = mode_labels.get(request.mode, request.mode)
    logger.info(f"[Instrument] {category_key} driver_mode → {request.mode}")

    return DriverModeResult(
        key=category_key,
        driverMode=request.mode,
        message=f"已将 {category.category_name} 设为 {label} 模式",
    )


# ============================================================
# F64 现场编排端点 (2026-07-21 现场收口, onsite-20260721-todo P2-1)
#
# F64 仿真启停 (start/stop_emulation)、输入定标 (set_baseband_power/set_crest_factor)、
# 输出增益 (set_output_gain) 此前只被 cal/measure 服务内部调, 无 standalone HTTP 入口。
# 现场编排 (reset+attach 可重复性 / 降功率找临界) 要经脚本驱动这些动作, 且**必须走驱动
# 方法** —— F64 GO/GOS 有幂等怪癖 (已停态 GOS / STATIC 3→3 / GO 前 0→0 均报 -200) +
# broadcaster 会插进多步命令之间, 驱动用 _scpi_lock 事务 + drain + 错误门保护; 裸发
# scpi-command 无锁无 drain 会踩 -200 假失败。
#
# ⭐ 定位: 全部是**哑执行工具** —— 传什么设什么, 端点不做任何场景判断。参数值 (输入
# 参考 / 峰均比 / 增益 …) 由上层"参数决议层"从通用测试参数 (测试例) + 实验室链路档案
# (线损/路损标定) 计算得出, 或由测试例显式覆盖 (设计见 onsite-20260721-todo P0-2/P2-3);
# 端点内不得固化任何经验值。
#
# 遵循 hal/reload·scpi-command·positioner 先例 (HAL 操作端点不进 checked-in
# openapi.yaml, D19); 现场脚本经 curl 消费。
# ============================================================

async def _call_f64_method(method, *args):
    """调 F64 驱动方法; 品类实际绑到不支持该操作的驱动 (agent F5: FS16 与
    channelEmulator 共用 category key, getattr 命中 ChannelEmulatorDriver 基类
    的 NotImplementedError) → 400 "不支持" 而非裸 500。"""
    try:
        return await method(*args)
    except NotImplementedError as e:
        raise HTTPException(400, f"当前驱动不支持该操作: {e}")


class EmulationControlRequest(BaseModel):
    action: str  # "start" (DIAG:SIMU:GO) | "stop" (DIAG:SIMU:GOS 停并倒回)


class F64ControlOwnershipRequest(BaseModel):
    action: str  # "release_local" | "acquire_remote"


class F64LoadSmuRequest(BaseModel):
    # 必须是操作员提供的 F64 本机路径；系统不猜文件名、不扫描目录。
    file_path: str = Field(min_length=1)


class OutputGainRequest(BaseModel):
    # agent F5: 空列表 → all({})=True 零下发却假成功; min_length=1 让空列表 422
    ports: List[int] = Field(min_length=1)   # F64 输出口号 (1..16), 非空
    gain_db: float     # 绝对增益 (OUTP:GAIN:CH), 支持正负 (负 = 衰减)


def _refuse_f64_control_change_while_running(db: Session) -> None:
    """控制权切换/换场景会影响整台 F64，执行中一律拒绝。"""
    from app.services.hal_reload_policy import find_reload_blockers
    from app.services.test_case_runner import has_active_case_run

    blockers = find_reload_blockers(db)
    active_case = has_active_case_run()
    if active_case is not None:
        blockers.append({
            "kind": "case_run",
            "id": active_case,
            "name": f"execution {active_case}",
            "status": "running",
        })
    if blockers:
        def serialize(blocker):
            if isinstance(blocker, dict):
                return blocker
            return {
                "kind": blocker.kind,
                "id": blocker.id,
                "name": blocker.name,
                "status": blocker.status,
            }

        raise HTTPException(
            status_code=409,
            detail={
                "message": "F64 正被测试执行占用，不能切换控制权或加载 .smu",
                "blockers": [serialize(blocker) for blocker in blockers],
            },
        )


@asynccontextmanager
async def _exclusive_f64_control_operation(db: Session):
    """与正式执行/破坏性诊断共用单飞门，覆盖整个控制操作。"""
    from app.services.execution_exclusion_guard import (
        active_unsafe_diagnostic,
        release_unsafe_diagnostic,
        try_acquire_unsafe_diagnostic,
    )

    token = try_acquire_unsafe_diagnostic("f64_control_operation")
    if token is None:
        active = active_unsafe_diagnostic() or "unknown"
        raise HTTPException(409, f"破坏性操作 '{active}' 正在占用仪表")
    try:
        # token 先占位，正式 runner 的反向门此刻已经生效；随后复查进程任务和 DB 行，
        # 消除“检查完才被别的流程抢占”的 TOCTOU 窗口。
        _refuse_f64_control_change_while_running(db)
        yield
    finally:
        release_unsafe_diagnostic(token)


@router.get("/instruments/{category_key}/control-ownership")
async def get_control_ownership(category_key: str):
    """读取驱动控制门状态，不向 F64/UXM 发送 SCPI。"""
    driver = _get_loaded_hal_driver(category_key)
    if driver is None:
        raise HTTPException(404, f"{category_key} HAL driver 未加载")
    local = bool(getattr(driver, "local_control_reserved", False))
    release_failed = bool(getattr(driver, "local_release_failed", False))
    connected = (
        getattr(driver, "_visa_resource", None) is not None
        or getattr(driver, "_visa_session", None) is not None
    )
    return {
        # ⚠ 取值说的是**我们这一端做了什么**，不是仪器面板上是什么模式。
        #   `ate_socket_released` = 我们关掉了 ATE socket 并停止后台轮询；
        #   仪器**是否真的回到 Local**，手册原文说要操作员在 F64 GUI 右上角
        #   点 Local Mode 按钮（PROPSIM User Reference §20.1：开远程连接发第一条
        #   ATE 命令后自动进 remote mode，回 local 需人工点击）。我们没有、也
        #   查不到那个状态，所以字段名不能替仪器宣布"它在 Local"（内审母题 B）。
        #   ⓪ 2026-08-07 改名前叫 `local`，那是在断言一件我们没核实过的事。
        "control_mode": (
            "release_unconfirmed"
            if release_failed
            else (
                "ate_socket_released" if local
                else ("remote" if connected else "disconnected")
            )
        ),
        "remote_polling_suppressed": local,
        "connected": connected,
    }


@router.post("/instruments/{category_key}/control-ownership")
async def set_control_ownership(
    category_key: str,
    request: F64ControlOwnershipRequest,
    db: Session = Depends(get_db),
):
    """F64/UXM 控制会话的现场应急手工交接。

    正常测试无需调用此端点：租约会自动取得并释放。release_local 只关闭驱动
    控制会话并暂停后台轮询，不发停止仿真/停止小区/停止信令；acquire_remote
    只用于现场显式重连。UXM 手册没有证实 Local SCPI，因此不发送猜测指令。
    """
    async with _exclusive_f64_control_operation(db):
        driver = _get_loaded_hal_driver(category_key)
        if driver is None:
            raise HTTPException(404, f"{category_key} HAL driver 未加载")
        action = request.action.strip().lower()
        if action == "release_local":
            method = getattr(driver, "release_to_local_control", None)
        elif action == "acquire_remote":
            method = getattr(driver, "acquire_remote_control", None)
        else:
            raise HTTPException(400, f"未知 action '{action}' (release_local|acquire_remote)")
        if method is None:
            raise HTTPException(400, f"{category_key} 驱动不支持控制权交接")
        ok = await _call_f64_method(method)
        local = bool(getattr(driver, "local_control_reserved", False))
        release_failed = bool(getattr(driver, "local_release_failed", False))
        connected = (
            getattr(driver, "_visa_resource", None) is not None
            or getattr(driver, "_visa_session", None) is not None
        )
        # 取值语义见上面 GET 端点的注释：说的是我们这端做了什么，
        # 不是仪器面板上是什么模式（手册：回 Local 要人在 F64 GUI 上点）。
        if release_failed:
            control_mode = "release_unconfirmed"
        else:
            control_mode = (
                "ate_socket_released" if local
                else ("remote" if connected else "disconnected")
            )
        return {
            "ok": bool(ok),
            "action": action,
            "control_mode": control_mode,
            "remote_polling_suppressed": local,
            "connected": connected,
            "last_error": None if ok else getattr(driver, "_last_error", None),
        }


@router.post("/instruments/{category_key}/load-smu")
async def load_smu_endpoint(
    category_key: str,
    request: F64LoadSmuRequest,
    db: Session = Depends(get_db),
):
    """必要时重新取得 Remote，加载操作员指定 `.smu`，并以 STATE? 回读验收。"""
    file_path = request.file_path.strip()
    if not file_path.lower().endswith(".smu"):
        raise HTTPException(400, "只允许加载显式指定的 .smu 文件路径")
    if not (
        PureWindowsPath(file_path).is_absolute()
        or PurePosixPath(file_path).is_absolute()
    ):
        raise HTTPException(400, "必须提供 F64 本机上的完整绝对 .smu 路径")

    async with _exclusive_f64_control_operation(db):
        async with instrument_test_lease(
            f"f64-load-smu:{category_key}",
            control_f64=True,
            control_uxm=False,
            enable_monitoring=False,
        ):
            driver = _get_loaded_hal_driver(category_key)
            if driver is None:
                raise HTTPException(404, f"{category_key} HAL driver 未加载")
            load = getattr(driver, "load_local_scenario", None)
            confirm = getattr(driver, "confirm_scenario_loaded", None)
            if load is None or confirm is None:
                raise HTTPException(400, f"{category_key} 驱动不支持 .smu 加载及回读确认")
            loaded = bool(await _call_f64_method(load, file_path))
            verification = await _call_f64_method(confirm) if loaded else None
            confirmed = bool(verification and verification.get("confirmed"))
            return {
                "ok": loaded and confirmed,
                "loaded_file": file_path if loaded else None,
                "verification": verification,
                "last_error": None if loaded and confirmed else getattr(driver, "_last_error", None),
            }


@router.post("/instruments/{category_key}/emulation-control")
async def emulation_control(category_key: str, request: EmulationControlRequest):
    """F64 仿真启停 (走驱动 start/stop_emulation, 含幂等热修 + 锁事务 + 错误门)。

    ⚠ 2026-07-21 真机实证的状态机风险 (P1-2 待对齐): 本固件下 GOS 在运行态未观察到
    真停 (数据流不断); 对已运行态反复 GO 会持续 -200 累积, 极端情况把 PropSim 业务层
    搞卡死 (仅剩 SYST:INFO? 应答, *RST 救不回, 只能重启 PropSim)。调用方应先查状态、
    避免盲目重试 start。
    """
    async with instrument_test_lease(
        f"f64-emulation-control:{category_key}",
        control_f64=True,
        control_uxm=False,
        enable_monitoring=False,
    ):
        driver = _get_loaded_hal_driver(category_key)
        if driver is None:
            raise HTTPException(404, f"{category_key} HAL driver 未加载 (需 Real 模式 + 已连接)")
        action = request.action.strip().lower()
        if action == "start":
            method = getattr(driver, "start_emulation", None)
        elif action == "stop":
            method = getattr(driver, "stop_emulation", None)
        else:
            raise HTTPException(400, f"未知 action '{action}' (start|stop)")
        if method is None:
            raise HTTPException(400, f"{category_key} 驱动不支持 {action}_emulation")
        ok = await _call_f64_method(method)
        return {
            "ok": bool(ok),
            "action": action,
            "emulation_running": getattr(driver, "_emulation_running", None),
            "last_error": None if ok else getattr(driver, "_last_error", None),
        }


@router.post("/instruments/{category_key}/output-gain")
async def set_output_gain_endpoint(category_key: str, request: OutputGainRequest):
    """F64 输出增益批量下发 (走驱动 set_output_gain, OUTP:GAIN:CH + 错误门)。

    ⚠ 定位: 逐口**小范围**校准补偿。2026-07-21 真机实证 per-port 有范围上限 (超限
    -200 "Parameter exceeds set limits", 且各口上限可不同 → 批量下发部分口生效部分
    被拒, 电平不一致)。大幅 / 整体输出功率调整不用此端点, 走 P0-4 归一化总功率方案。
    """
    async with instrument_test_lease(
        f"f64-output-gain:{category_key}",
        control_f64=True,
        control_uxm=False,
        enable_monitoring=False,
    ):
        driver = _get_loaded_hal_driver(category_key)
        if driver is None:
            raise HTTPException(404, f"{category_key} HAL driver 未加载")
        method = getattr(driver, "set_output_gain", None)
        if method is None:
            raise HTTPException(400, f"{category_key} 驱动不支持 set_output_gain")
        results: Dict[int, bool] = {}
        for p in request.ports:
            results[p] = bool(await _call_f64_method(method, p, request.gain_db))
        all_ok = all(results.values())
        return {
            "ok": all_ok,
            "gain_db": request.gain_db,
            "ports": results,
            "last_error": None if all_ok else getattr(driver, "_last_error", None),
        }


@router.get("/instruments/{category_key}/output-calibration/{output_num}")
async def get_output_calibration_endpoint(category_key: str, output_num: int):
    """读回 F64 输出口当前增益+相位 (走驱动 get_output_calibration, OUTP:CALIB:GET? + 重试)。

    ⚠ 2026-07-21 真机实测: 本机固件对 OUTP:CALIB:GET? 不返回数据 (驱动重试后仍 None,
    本端点回 ok=false/calibration=null)。读回路径保留, 待对照 F64 手册确认命令适用
    条件 / 固件差异; 调用方不得依赖它拿"当前增益基准"。
    """
    async with instrument_test_lease(
        f"f64-output-calibration:{category_key}",
        control_f64=True,
        control_uxm=False,
        enable_monitoring=False,
    ):
        driver = _get_loaded_hal_driver(category_key)
        if driver is None:
            raise HTTPException(404, f"{category_key} HAL driver 未加载")
        method = getattr(driver, "get_output_calibration", None)
        if method is None:
            raise HTTPException(400, f"{category_key} 驱动不支持 get_output_calibration")
        calib = await _call_f64_method(method, output_num)
        return {"ok": calib is not None, "output_num": output_num, "calibration": calib}


class InputReferenceRequest(BaseModel):
    power_dbm: float                         # 输入参考电平 (INP:LEV:AMP:CH)
    input_ports: Optional[List[int]] = None  # 物理输入口号 (1-based);
    #   None = 驱动用**从仿真回读的真实输入口号** (GROUP:INPUTS:GET?), 回读不到则拒绝下发


@router.post("/instruments/{category_key}/input-reference")
async def set_input_reference_endpoint(category_key: str, request: InputReferenceRequest):
    """F64 输入参考电平 (走驱动 set_baseband_power, INP:LEV:AMP:CH + 错误门)。2026-07-21 验证 ✓。

    值是**派生量**, 不在此固化: input_ref = UXM DL 功率(dBm/BW 口径) − UXM→F64 线缆
    损耗, 由参数决议层计算或测试例显式覆盖 (P0-2/P2-3)。注意 load .smu 会带回工程内嵌
    默认输入参考、冲掉先前设置 → 每次加载后必须重新下发。

    input_ports (Codex #221 R5 P2 → F64R-2 已解): 上层参数决议层按真实激活拓扑传的
    物理输入口号列表; **不传则驱动用加载后回读的真实输入口号** (`GROUP:INPUTS:GET?`
    逐组并集, **不是** 1..N —— 口号不保证连续), 回读不到则 fail-loud 拒绝下发 ——
    不再用 `_tx_antennas` 猜 (那个冷缓存在操作员手动加载 4x4 .smu 后会停在构造默认 2、
    只覆盖输入 1/2 致 MIMO 不平衡, 端点还回 ok=true)。
    """
    async with instrument_test_lease(
        f"f64-input-reference:{category_key}",
        control_f64=True,
        control_uxm=False,
        enable_monitoring=False,
    ):
        driver = _get_loaded_hal_driver(category_key)
        if driver is None:
            raise HTTPException(404, f"{category_key} HAL driver 未加载")
        method = getattr(driver, "set_baseband_power", None)
        if method is None:
            raise HTTPException(400, f"{category_key} 驱动不支持 set_baseband_power")
        # 没给 ports 时先让驱动补齐拓扑 —— 与 /crest-factor 同口径。
        if not request.input_ports:
            _ensure = getattr(driver, "ensure_topology", None)
            if callable(_ensure):
                await _ensure()
        ok = await _call_f64_method(method, request.power_dbm, request.input_ports)
        # 回显实际下发的口号，不能用请求里的 None 冒充未知。
        _eff_ports = request.input_ports
        if not _eff_ports:
            _getter = getattr(driver, "get_active_input_ports", None)
            _eff_ports = _getter() if callable(_getter) else None
        return {"ok": bool(ok), "power_dbm": request.power_dbm,
                "input_ports": _eff_ports,
                "last_error": None if ok else getattr(driver, "_last_error", None)}


class CrestFactorRequest(BaseModel):
    # agent F5: min_length=1 让显式空列表 422
    # F64R-2: 默认从 [1,2,3,4] 改成 None —— 硬编码 1-4 在非连续口 (如仿真只占 {3,5})
    # 下会配错口, 跟 input-reference 这个兄弟端点的口径也不一致 (它已改成回读真实口号)。
    # None = 驱动用回读的真实输入口号, 读不到则 fail-loud。
    input_ports: Optional[List[int]] = Field(default=None, min_length=1)
    crest_db: float


@router.post("/instruments/{category_key}/crest-factor")
async def set_crest_factor_endpoint(category_key: str, request: CrestFactorRequest):
    """F64 峰均比 (走驱动 set_crest_factor + 错误门)。2026-07-21 验证 ✓。

    值是**波形属性**, 不在此固化: 峰均比由制式 × 带宽 × 业务形态决定 (由参数决议层
    查波形表提供或测试例显式覆盖, P0-2/P2-3)。load .smu 会带回工程内嵌默认值、冲掉
    先前设置 → 每次加载后必须重新下发。

    input_ports (F64R-2): 不传则用驱动**回读的真实输入口号** (与兄弟端点
    /input-reference 同口径), 读不到则 400 —— 旧的硬编码默认 [1,2,3,4] 在非连续口
    (如仿真只占 {3,5}) 下会配错口。
    """
    async with instrument_test_lease(
        f"f64-crest-factor:{category_key}",
        control_f64=True,
        control_uxm=False,
        enable_monitoring=False,
    ):
        driver = _get_loaded_hal_driver(category_key)
        if driver is None:
            raise HTTPException(404, f"{category_key} HAL driver 未加载")
        method = getattr(driver, "set_crest_factor", None)
        if method is None:
            raise HTTPException(400, f"{category_key} 驱动不支持 set_crest_factor")
        ports = request.input_ports
        if not ports:
            # 后端重启后缓存空但仪表仍有场景，先按需补回读。
            _ensure = getattr(driver, "ensure_topology", None)
            if callable(_ensure):
                await _ensure()
            _getter = getattr(driver, "get_active_input_ports", None)
            ports = (_getter() if callable(_getter) else None) or []
        if not ports:
            raise HTTPException(
                400,
                f"{category_key} 物理输入口未知 (仿真未加载 / 拓扑回读失败) —"
                f" 请显式传 input_ports, 或先加载仿真。不按猜测的端口号下发峰均比。"
                f"{_TOPOLOGY_ESCAPE_HINT}",
            )
        results: Dict[int, bool] = {}
        for inp in ports:
            results[inp] = bool(await _call_f64_method(method, inp, request.crest_db))
        all_ok = all(results.values())
        return {"ok": all_ok, "crest_db": request.crest_db, "ports": results,
                "last_error": None if all_ok else getattr(driver, "_last_error", None)}


# ============================================================
# U-5: Positioner (转台) standalone 控制端点
#
# driver 的 move_to/get_position/stop/reset(=HOME) 此前只被 cal/QZ 服务内部调, 无
# standalone HTTP 入口 → 2026-05-27 现场无法单独验证转台回零/定位/4方位扫 (morning-log
# §10, U-5 "无结论"真因)。本段补 standalone 端点, 让现场连上即可经 Swagger/GUI 单独驱动
# 转台, 不依赖完整 cal 流程。遵循 hal/reload·scpi-command 先例 (HAL 操作端点不进 checked-in
# openapi.yaml, D19); GUI 经 service.ts 手写消费。Aerotech 协议见
# docs/site-debug/2026-06-04-positioner-turntable.md。
# ============================================================

class PositionerMoveRequest(BaseModel):
    azimuth: float
    elevation: float = 0.0


class PositionerSweepRequest(BaseModel):
    # 默认 4 方位 (P0-5 验收: 4 azimuth 给 4 个不同吞吐值)
    angles: List[float] = [0.0, 90.0, 180.0, 270.0]
    home_first: bool = True
    tolerance_deg: float = 0.5


class PositionerResult(BaseModel):
    ok: bool
    azimuth: Optional[float] = None
    elevation: Optional[float] = None
    reason: Optional[str] = None
    message: Optional[str] = None


class PositionerSweepPoint(BaseModel):
    target: float
    actual_azimuth: Optional[float] = None
    actual_elevation: Optional[float] = None
    within_tolerance: Optional[bool] = None


class PositionerSweepResult(BaseModel):
    ok: bool
    points: List[PositionerSweepPoint] = []
    reason: Optional[str] = None
    message: Optional[str] = None


_POSITIONER_REASON_MSG = {
    "hal_unavailable": "HAL 服务不可用",
    "driver_not_loaded": "positioner 驱动未加载 — 检查仪器已选 + 连接 IP 已填, 或重载 HAL 驱动",
    "not_a_positioner": "绑定的驱动不是转台驱动",
    "position_read_failed": "位置回读失败 (PFBK 通信?) — 实际位置未知, 勿信显示值",
    "aborted": "已被急停中止",
}

# 急停协调 (Codex P1 #132): sweep 是多步 long-running loop, operator 按急停时该 loop 需观察到
# 中止信号, 否则会在 ABORT 后继续发 move。模块级 flag: stop 端点 set, sweep 每步前检查; 单次
# 指令 (move/home/sweep) 开始时 clear (新指令覆盖旧急停态)。FastAPI 端点同 event loop 串行,
# 无锁够用 (用可变 dict 免 global 声明)。
_positioner_stop_flag = {"requested": False}


def _resolve_positioner():
    """拿 positioner HAL driver。返回 (driver, error_reason); 成功 (driver, None)。"""
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
    except Exception:  # noqa: BLE001
        return None, "hal_unavailable"
    driver = (hal.drivers or {}).get("positioner") if hal else None
    if driver is None:
        return None, "driver_not_loaded"
    # PositionerDriver 鸭子检查 (move_to + get_position 是接口核心)
    if not (callable(getattr(driver, "move_to", None))
            and callable(getattr(driver, "get_position", None))):
        return None, "not_a_positioner"
    return driver, None


async def _positioner_position(
    driver,
) -> tuple[tuple[Optional[float], Optional[float]], Optional[str]]:
    """读位置反馈 (PFBK)。返回 ((az, el), error); 失败时 error 非 None。

    不伪造到位 (Codex P2 #132): 吞异常返回 (0,0) 会让现场误判转台在 home / within tolerance,
    而实际 PFBK 通信坏了。callers 据 error 标 position_read_failed, 不返回假成功。
    """
    try:
        az, el = await driver.get_position()
        return (az, el), None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[Positioner] get_position failed: {e}")
        return (None, None), str(e)


@router.post("/instruments/positioner/home", response_model=PositionerResult)
async def positioner_home() -> PositionerResult:
    """转台回零 (HOME)。首次上电 / 位置不可信时必须先回零。"""
    driver, reason = _resolve_positioner()
    if driver is None:
        return PositionerResult(ok=False, reason=reason,
                                message=_POSITIONER_REASON_MSG.get(reason))
    _positioner_stop_flag["requested"] = False  # 新指令清除旧急停态
    ok = await driver.reset()  # PositionerDriver.reset() == HOME 回零
    (az, el), pos_err = await _positioner_position(driver)
    if not ok:
        return PositionerResult(ok=False, azimuth=az, elevation=el, reason="home_failed",
                                message="回零失败 — 查控制器故障 (AXISFAULT) / 限位 / 使能")
    if pos_err:
        return PositionerResult(ok=False, azimuth=az, elevation=el, reason="position_read_failed",
                                message=_POSITIONER_REASON_MSG["position_read_failed"])
    return PositionerResult(ok=True, azimuth=az, elevation=el, message="已回零")


@router.post("/instruments/positioner/move", response_model=PositionerResult)
async def positioner_move(request: PositionerMoveRequest) -> PositionerResult:
    """转台绝对定位 (MOVEABS)。单轴转台忽略 elevation。"""
    driver, reason = _resolve_positioner()
    if driver is None:
        return PositionerResult(ok=False, reason=reason,
                                message=_POSITIONER_REASON_MSG.get(reason))
    _positioner_stop_flag["requested"] = False  # 新指令清除旧急停态
    ok = await driver.move_to(request.azimuth, request.elevation)
    (az, el), pos_err = await _positioner_position(driver)
    if not ok:
        return PositionerResult(ok=False, azimuth=az, elevation=el, reason="move_failed",
                                message="定位失败 — 查到位超时 / 故障 / 位置超差")
    if pos_err:
        return PositionerResult(ok=False, azimuth=az, elevation=el, reason="position_read_failed",
                                message=_POSITIONER_REASON_MSG["position_read_failed"])
    return PositionerResult(ok=True, azimuth=az, elevation=el, message=f"已到位 Az={az:.2f}°")


@router.get("/instruments/positioner/position", response_model=PositionerResult)
async def positioner_position() -> PositionerResult:
    """读转台当前位置反馈 (PFBK)。"""
    driver, reason = _resolve_positioner()
    if driver is None:
        return PositionerResult(ok=False, reason=reason,
                                message=_POSITIONER_REASON_MSG.get(reason))
    (az, el), pos_err = await _positioner_position(driver)
    if pos_err:
        return PositionerResult(ok=False, azimuth=az, elevation=el, reason="position_read_failed",
                                message=_POSITIONER_REASON_MSG["position_read_failed"])
    return PositionerResult(ok=True, azimuth=az, elevation=el)


@router.post("/instruments/positioner/stop", response_model=PositionerResult)
async def positioner_stop() -> PositionerResult:
    """转台急停 (ABORT)。异常 / 门禁 / 急停联锁时调用。"""
    driver, reason = _resolve_positioner()
    if driver is None:
        return PositionerResult(ok=False, reason=reason,
                                message=_POSITIONER_REASON_MSG.get(reason))
    _positioner_stop_flag["requested"] = True  # 通知 in-flight sweep 停止后续 move (Codex P1)
    note_operator_stop = getattr(driver, "note_operator_stop", None)
    if callable(note_operator_stop):
        note_operator_stop()
    ok = await driver.stop()
    if not ok:
        invalidate_position = getattr(driver, "_invalidate_cached_feedback", None)
        if callable(invalidate_position):
            invalidate_position()
        return PositionerResult(
            ok=False,
            azimuth=None,
            elevation=None,
            reason="stop_failed",
            message="急停失败；转台是否已停止与当前位置均未知",
        )
    (az, el), pos_err = await _positioner_position(driver)
    return PositionerResult(
        ok=True, azimuth=az, elevation=el,
        reason=None,
        message=(
            "已确认停止；编码器位置未知，请重新读取 PFBK"
            if pos_err
            else "已急停"
        ),
    )


@router.post("/instruments/positioner/sweep", response_model=PositionerSweepResult)
async def positioner_sweep(request: PositionerSweepRequest) -> PositionerSweepResult:
    """4 方位 (或自定义角度) 扫描验证: 每角度定位 + 回读 + 比对容差。

    P0-5 验收预演 (4 azimuth 应给 4 个不同吞吐值; 此端点先验证转台几何到位)。
    任一角度定位失败即停止并返回已完成点。
    """
    driver, reason = _resolve_positioner()
    if driver is None:
        return PositionerSweepResult(ok=False, reason=reason,
                                     message=_POSITIONER_REASON_MSG.get(reason))
    stop_generation_reader = getattr(driver, "operator_stop_generation", None)
    motion_stop_generation = (
        stop_generation_reader() if callable(stop_generation_reader) else None
    )
    motion_stop_kwargs = (
        {"expected_operator_stop_generation": motion_stop_generation}
        if motion_stop_generation is not None
        else {}
    )
    _positioner_stop_flag["requested"] = False  # 兼容无 generation 的旧驱动

    def operator_stop_changed() -> bool:
        return bool(
            motion_stop_generation is not None
            and callable(stop_generation_reader)
            and stop_generation_reader() != motion_stop_generation
        )

    if request.home_first:
        home_ok = await driver.reset(**motion_stop_kwargs)
        if operator_stop_changed():
            return PositionerSweepResult(
                ok=False,
                reason="aborted",
                message="回零期间收到急停, 中止扫描",
            )
        if not home_ok:
            return PositionerSweepResult(ok=False, reason="home_failed",
                                         message="回零失败, 中止扫描")
    points: List[PositionerSweepPoint] = []
    for target in request.angles:
        if _positioner_stop_flag["requested"] or operator_stop_changed():
            return PositionerSweepResult(ok=False, points=points, reason="aborted",
                                         message=f"已被急停中止, 完成 {len(points)} 点")
        moved = await driver.move_to(target, 0.0, **motion_stop_kwargs)
        (az, el), pos_err = await _positioner_position(driver)
        within = (
            None
            if pos_err
            else bool(moved) and abs(az - target) <= request.tolerance_deg
        )
        points.append(PositionerSweepPoint(
            target=target, actual_azimuth=az, actual_elevation=el,
            within_tolerance=within,
        ))
        if not moved:
            return PositionerSweepResult(
                ok=False, points=points, reason="move_failed",
                message=f"定位到 {target:.1f}° 失败, 已完成 {len(points) - 1} 点",
            )
        if pos_err:
            return PositionerSweepResult(
                ok=False, points=points, reason="position_read_failed",
                message=f"{target:.1f}° 位置回读失败 (PFBK?), 中止扫描",
            )
    all_ok = all(p.within_tolerance is True for p in points)
    return PositionerSweepResult(
        ok=all_ok, points=points,
        reason=None if all_ok else "tolerance_exceeded",
        message=(f"{len(points)} 方位全部到位 (±{request.tolerance_deg}°)" if all_ok
                 else "部分角度位置超差, 查 degree/counts 换算 / 机械传动"),
    )
