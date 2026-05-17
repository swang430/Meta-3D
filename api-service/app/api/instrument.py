"""Instrument API endpoints

输出格式适配前端 InstrumentsResponse / InstrumentCategory 类型定义。
后端 DB 模型 → 前端友好的扁平化 JSON。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from uuid import UUID
import logging
from typing import Optional, List, Dict, Any

from pydantic import BaseModel

from app.db.database import get_db
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

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# 前端友好的响应 Schema（与前端 types/api.ts 一一对应）
# ============================================================

class FEInstrumentModel(BaseModel):
    """对应前端 InstrumentModel 类型"""
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
    status: str  # 'available' | 'offline' | 'reserved' | 'maintenance'


class FEInstrumentConnection(BaseModel):
    """对应前端 InstrumentConnection 类型"""
    endpoint: Optional[str] = None
    controller: Optional[str] = None
    notes: Optional[str] = None
    connection_params: Optional[Dict[str, Any]] = None


class FEInstrumentCategory(BaseModel):
    """对应前端 InstrumentCategory 类型"""
    categoryId: Optional[str] = None  # DB UUID, 供拓扑编辑器等关联查询
    key: str
    label: str
    description: str
    tags: Optional[List[str]] = None
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
    get wired in later — today only ``"test_plan"`` is emitted."""
    kind: str
    id: str
    name: str
    status: str
    detail: str


class HalReloadRefusedResult(BaseModel):
    """Response body for HTTP 409 from POST /instruments/hal/reload
    when ``force=false`` and active blockers exist.

    GUI uses ``blockers`` to render a precise message ("3 test plans
    are running: …") and offers a "Force reload anyway" button that
    re-POSTs with ``?force=true``."""
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


class ChannelModelsListResult(BaseModel):
    """Response for GET /instruments/{category_key}/channel-models.

    ``items`` may be empty for legitimate reasons (no driver loaded yet,
    driver doesn't speak channel models, or operator hasn't populated
    the curated list). ``reason`` distinguishes the cases so the GUI can
    show "loading..." vs "no driver" vs "configure in settings".
    """
    items: List[ChannelModelEntry]
    reason: Optional[str] = None  # "driver_not_loaded" | "not_a_channel_emulator" | None


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
            "True, reload proceeds even with running TestPlans — the "
            "in-flight work will fail with closed-VISA-session errors. "
            "Default False = safe behaviour."
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

    **P2-5 refuse-while-in-flight policy**: when a ``TestPlan`` is in
    ``running`` or ``paused`` state, the default reload returns HTTP
    409 with the blocker list instead of tearing down the drivers.
    Operator can re-POST with ``?force=true`` to override (they take
    responsibility for the aborted test).

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

    # Refuse arm: check blockers BEFORE acquiring the lifecycle lock,
    # so a no-op refusal doesn't serialise behind in-progress reloads.
    if not force:
        blockers = find_reload_blockers(db)
        if blockers:
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
            # 409 Conflict — semantic match: "the request is valid but
            # the current state of the target resource (HAL + in-flight
            # tests) makes it impossible to apply right now".
            #
            # Codex P2 fix: return JSONResponse directly so the body
            # shape IS the documented HalReloadRefusedResult model
            # (top-level ``refused`` / ``blockers`` / etc.). The
            # previous HTTPException(detail=payload.model_dump()) form
            # wrapped the payload in ``{"detail": {...}}``, mismatching
            # the ``responses={409: {"model": HalReloadRefusedResult}}``
            # contract — any generated client would look for
            # ``response.blockers`` at the top level and miss the
            # nested copy.
            return JSONResponse(
                status_code=409, content=payload.model_dump(),
            )

    started = time.monotonic()
    # Preserve the mode the service was running in (REAL vs MOCK_FALLBACK
    # vs MOCK_FORCE) — operators usually don't want to switch global mode
    # when reloading specific instruments.
    prior_service = get_hal_service()
    prior_mode = getattr(prior_service, "mode", DriverMode.REAL) if prior_service else DriverMode.REAL
    await reload_hal_service_atomic(prior_mode)
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

    if driver is not None:
        list_fn = getattr(driver, "list_channel_models", None)
        if not callable(list_fn):
            # Driver doesn't speak the channel-emulator contract — fine,
            # not an error. (E.g. asking VNA category for channel models.)
            return ChannelModelsListResult(items=[], reason="not_a_channel_emulator")

        # _maybe_await tolerates both async and sync implementations of
        # list_channel_models — the base class is async but drivers could
        # override with a sync method for simple curated-list cases.
        raw_items = await _maybe_await(list_fn())
        items = [ChannelModelEntry(**entry) for entry in raw_items]
        return ChannelModelsListResult(items=items)

    # No live driver. Stage 1 source of truth is the curated list in
    # ``InstrumentConnection.connection_params['available_channel_models']``,
    # which is set by the operator in the GUI and lives in the DB
    # independent of whether the F64 is reachable. Read + normalise so
    # offline planning works (HAL in mock mode, instrument unreachable,
    # or driver hasn't been loaded yet).
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
        reason="driver_not_loaded" if not items else None,
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
    'we don't know yet' state."""
    profile_id: str
    name: str
    description: str
    category: str  # "siso" / "mimo" / "calibration" — from UxmTestProfile.category
    compatible_test_apps: List[str]
    compatible_with_current_test_app: Optional[bool] = None


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
    category_key: str,
) -> List[Dict[str, Any]]:
    """Today: UXM is the only category with topology profiles. Future
    multi-app instruments (CMX500, etc.) add their own profile registry
    + a category → registry dispatch here.

    Returns the raw template dicts — caller wraps them in Pydantic + adds
    runtime compat status. Empty list means 'no profiles for this
    category' (and caller should set reason='not_a_uxm' or equivalent).
    """
    if category_key != "baseStation":
        # No other category exposes topology profiles in Phase 1.
        return []
    from app.hal.uxm_test_profiles import _PROFILE_REGISTRY, _register_builtin_profiles

    if not _PROFILE_REGISTRY:
        _register_builtin_profiles()
    return [
        {
            "profile_id": p.profile_id,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "compatible_test_apps": list(p.compatible_test_apps),
        }
        for p in _PROFILE_REGISTRY.values()
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

    raw = _list_topology_profiles_for_category(category_key)
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

    # Validate profile_id (if non-null) exists in the registry.
    if profile_id is not None:
        from app.hal.uxm_test_profiles import _PROFILE_REGISTRY, _register_builtin_profiles
        if not _PROFILE_REGISTRY:
            _register_builtin_profiles()
        if profile_id not in _PROFILE_REGISTRY:
            available = sorted(_PROFILE_REGISTRY.keys())
            raise HTTPException(
                status_code=404,
                detail=f"Topology profile {profile_id!r} not found. Available: {available}",
            )

    # Get live driver (if any) for compat check + immediate apply.
    try:
        from app.services.instrument_hal_service import get_hal_service
        hal = get_hal_service()
    except Exception:
        hal = None
    driver = (hal.drivers or {}).get(category_key) if hal else None

    # Compat check BEFORE DB write — refuses don't half-persist.
    if profile_id is not None and driver is not None:
        if hasattr(driver, "apply_topology_profile"):
            # Pre-flight: call apply with the proposed id, see if it
            # would refuse, but DON'T let it actually run SCPI yet
            # (we want to commit DB first if compat passes). Cheap
            # path: load the profile + run is_compatible_with directly
            # rather than letting apply_topology_profile do its log + return.
            from app.hal.uxm_test_profiles import get_profile
            try:
                proposed = get_profile(profile_id)
            except KeyError as e:
                raise HTTPException(status_code=404, detail=str(e))
            current_app = _resolve_current_test_app(driver)
            if not proposed.is_compatible_with(current_app):
                return JSONResponse(
                    status_code=409,
                    content={
                        "refused": True,
                        "reason": "incompatible_test_app",
                        "profile_id": profile_id,
                        "test_app": current_app,
                        "profile_compatible_with": list(proposed.compatible_test_apps),
                        "detail": (
                            f"Topology profile {profile_id!r} compatible with "
                            f"{proposed.compatible_test_apps}, but UXM is currently "
                            f"running Test App {current_app!r}. Pick a compatible "
                            f"profile or switch the UXM hardware to a matching Test App."
                        ),
                    },
                )

    # Persist (or clear) the selection.
    params = dict(conn.connection_params or {})
    if profile_id is None:
        params.pop("topology_profile_id", None)
    else:
        params["topology_profile_id"] = profile_id
    conn.connection_params = params
    db.commit()

    # Optionally apply NOW if we have a live driver.
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
        result = await driver.apply_topology_profile(profile_id)
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
    ip: Optional[str] = None      # 覆盖数据库中的 IP（用于测试未保存的编辑）
    port: Optional[int] = None    # 覆盖数据库中的端口
    protocol: Optional[str] = None
    run_by: Optional[str] = None  # 操作员标识，写入 diagnostic_runs.run_by


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

    支持通过请求体覆盖 IP/Port，以便在保存配置前先测试连接。
    """
    import socket
    import time

    # 使用 SCPI 命名空间的 logger，确保记录到 scpi.log
    scpi_logger = logging.getLogger("app.hal.scpi")

    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    conn = db.query(InstrumentConnectionDB).filter(
        InstrumentConnectionDB.category_id == category.id
    ).first()

    # 优先使用请求体中的覆盖值，其次使用数据库中保存的值
    ip = (body.ip if body and body.ip else None) or (conn.controller_ip if conn else None)
    port = (body.port if body and body.port else None) or (conn.port if conn else None) or 5025
    protocol = (body.protocol if body and body.protocol else None) or (conn.protocol if conn else None) or ""

    if not ip:
        return TestConnectionResult(
            success=False,
            status="error",
            message="未配置连接信息（IP 地址为空）",
        )

    # 验证 IP 地址格式
    if not _validate_ip_address(ip):
        return TestConnectionResult(
            success=False,
            status="error",
            message=f"IP 地址格式无效: '{ip}'。请输入有效的 IPv4 地址（如 192.168.0.132）或 VISA 资源字符串（如 TCPIP0::192.168.0.132::inst0::INSTR）",
        )

    scpi_logger.info(
        f"[TEST-CONN] {category_key} → TCP connecting {ip}:{port} (protocol={protocol})",
        extra={"instrument_id": category_key, "direction": "CONNECT"},
    )

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

        sock.close()

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


async def _run_command_via_hal(
    driver,
    command: str,
    scpi_logger: logging.Logger,
    category_key: str,
) -> ScpiCommandResult:
    """Execute one SCPI command through the loaded HAL driver's primitives.

    Reuses the live VISA session the driver already holds — critical for
    single-client instruments (e.g. PROPSIM FS16's TCP SOCKET port,
    where opening a second client either times out at the application
    layer or is silently ignored). On 2026-05-13 at CAICT, FS16's
    diagnostic terminal showed 5/5 "timed out, 0ms" exactly because
    the old socket-only path opened a parallel SOCKET while HAL already
    held one.
    """
    import time

    is_query = command.strip().endswith("?")
    start = time.monotonic()
    try:
        scpi_logger.debug(
            f"[SCPI-TERM via HAL] {category_key} → {command}",
            extra={"instrument_id": category_key, "direction": "WRITE", "command": command},
        )
        if is_query:
            raw = await _maybe_await(driver._query(command.strip()))
            raw_str = str(raw or "").strip()
            scpi_logger.debug(
                f"[SCPI-TERM via HAL] {category_key} ← {raw_str[:200] if raw_str else '(empty)'}",
                extra={"instrument_id": category_key, "direction": "READ"},
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
        scpi_logger.warning(
            f"[SCPI-TERM via HAL] {category_key} ← ERROR on '{command}': {e}",
            extra={"instrument_id": category_key, "direction": "ERROR"},
        )
        return ScpiCommandResult(
            command=command.strip(),
            success=False,
            error=f"{type(e).__name__}: {e}",
            latency_ms=round(latency, 1),
        )


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
    if hal is None:
        return None
    driver = (hal.drivers or {}).get(category_key)
    if driver is None:
        return None
    # Skip Mock* drivers — project convention names every mock class
    # MockXxx (MockBaseStation, MockChannelEmulator, MockRfSwitch, etc.)
    # and reserves RealXxx for actual hardware-talking implementations.
    if type(driver).__name__.startswith("Mock"):
        return None
    if not callable(getattr(driver, "_query", None)):
        return None
    if not callable(getattr(driver, "_write", None)):
        return None
    return driver


def _send_scpi_command(
    sock: "socket.socket",
    command: str,
    scpi_logger: logging.Logger,
    category_key: str,
) -> ScpiCommandResult:
    """通过已连接的 socket 发送单条 SCPI 命令并返回结果"""
    import time

    is_query = command.strip().endswith("?")
    start = time.monotonic()

    try:
        scpi_logger.debug(
            f"[SCPI-TERM] {category_key} → WRITE: {command}",
            extra={"instrument_id": category_key, "direction": "WRITE", "command": command},
        )
        sock.sendall((command.strip() + "\n").encode())

        response = None
        if is_query:
            raw = sock.recv(4096).decode("utf-8", errors="replace").strip()
            response = raw if raw else None
            scpi_logger.debug(
                f"[SCPI-TERM] {category_key} ← RESP: {raw[:200] if raw else '(empty)'}",
                extra={"instrument_id": category_key, "direction": "READ", "response": raw[:500] if raw else ""},
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
        scpi_logger.warning(
            f"[SCPI-TERM] {category_key} ← ERROR on '{command}': {e}",
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
    """从请求体或数据库解析 IP 和 Port"""
    ip = body_ip or (conn.controller_ip if conn else None)
    port = body_port or (conn.port if conn else None) or 5025
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

    scpi_logger = logging.getLogger("app.hal.scpi")

    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    conn = db.query(InstrumentConnectionDB).filter(
        InstrumentConnectionDB.category_id == category.id
    ).first()

    ip, port = _resolve_ip_port(request.ip, request.port, conn)
    target_name = f"{category_key}: {request.command.strip()}"
    audit_params: Dict[str, Any] = {
        "category_key": category_key,
        "command": request.command.strip(),
        "ip": ip,
        "port": port,
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
            output=result.response,
            error_message=result.error,
            duration_ms=int((time.monotonic() - audit_started) * 1000),
            run_by=request.run_by,
        )
        return result

    # HAL-first routing same as /scpi-probe. See _run_command_via_hal docstring.
    hal_driver = _get_loaded_hal_driver(category_key)
    if hal_driver is not None:
        result = await _run_command_via_hal(hal_driver, request.command, scpi_logger, category_key)
        return _audit(result)

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

        result = _send_scpi_command(sock, request.command, scpi_logger, category_key)

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

    scpi_logger = logging.getLogger("app.hal.scpi")

    category = db.query(InstrumentCategoryModel).filter(
        InstrumentCategoryModel.category_key == category_key
    ).first()
    if not category:
        raise HTTPException(404, f"Category '{category_key}' not found")

    conn = db.query(InstrumentConnectionDB).filter(
        InstrumentConnectionDB.category_id == category.id
    ).first()

    ip = (body.ip if body and body.ip else None) or (conn.controller_ip if conn else None)
    port = (body.port if body and body.port else None) or (conn.port if conn else None) or 5025

    if not ip:
        raise HTTPException(400, "未配置 IP 地址")
    if not _validate_ip_address(ip):
        raise HTTPException(400, f"IP 地址格式无效: '{ip}'。请检查端点配置。")

    results: List[ScpiCommandResult] = []
    audit_started = time.monotonic()

    # Prefer the live HAL driver session if loaded — avoids opening a
    # parallel TCP client to single-session instruments. Fall back to
    # opening a fresh socket only when HAL hasn't loaded this category
    # (e.g. driver_mode=mock, or before HAL init has run).
    hal_driver = _get_loaded_hal_driver(category_key)
    if hal_driver is not None:
        scpi_logger.info(
            f"[SCPI-PROBE] {category_key} → Running {len(COMMON_SCPI_COMMANDS)} "
            f"diagnostic commands via live HAL driver ({type(hal_driver).__name__})",
            extra={"instrument_id": category_key, "direction": "PROBE"},
        )
        for cmd, _desc in COMMON_SCPI_COMMANDS:
            results.append(await _run_command_via_hal(hal_driver, cmd, scpi_logger, category_key))
    else:
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
                result = _send_scpi_command(sock, cmd, scpi_logger, category_key)
                results.append(result)

            sock.close()

        except Exception as e:
            scpi_logger.error(
                f"[SCPI-PROBE] {category_key} → Connection failed: {e}",
                extra={"instrument_id": category_key, "direction": "ERROR"},
            )
            # 将连接错误作为所有未执行命令的结果
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
    category: str
    model: str
    endpoint: str
    status: str  # "ok" | "fail" | "skipped"
    detail: str
    extras: Dict[str, Any] = {}


class LabProfileReadinessResponse(BaseModel):
    """Active LabProfile state. ``status`` ∈
    {"ok", "inactive", "missing", "ambiguous"} — see
    ``app.services.readiness.LabProfileReadiness`` for semantics."""
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None
    is_active: bool
    status: str
    detail: str


class CalibrationReadinessResponse(BaseModel):
    """Active lab's calibration certificate validity. ``status`` ∈
    {"valid", "expired", "missing", "no_lab"} — distinguishes
    "no lab to even look at a cert through" from "lab exists but
    has no cert bound" so the GUI can suggest the right next step
    (set up lab vs run calibration)."""
    certificate_number: Optional[str] = None
    valid_until_iso: Optional[str] = None
    status: str
    days_remaining: Optional[int] = None
    detail: str


class DutAttachReadinessResponse(BaseModel):
    """DUT-attach state — placeholder in this build. ``status`` is
    always ``"not_implemented"`` because no runtime model exists
    (no probe-sensing, RFID, session table). Field is surfaced so
    the readiness shape is forward-compatible with future sensing
    work — swapping in a real implementation won't break the
    openapi contract or GUI consumers."""
    status: str
    detail: str


class HALReadinessResponse(BaseModel):
    """Composite snapshot returned by ``GET /instruments/hal/readiness``.

    ``available=False`` means HAL hasn't initialised yet (the
    lifespan startup hasn't run, or a reload is mid-flight). The
    GUI should render "HAL not ready" rather than treating the
    placeholder sub-sections as the live state."""
    available: bool
    drivers: List[DriverReadinessRowResponse]
    lab_profile: LabProfileReadinessResponse
    calibration: CalibrationReadinessResponse
    dut_attach: DutAttachReadinessResponse
    generated_at_iso: str


@router.get("/instruments/hal/readiness", response_model=HALReadinessResponse)
def get_hal_readiness():
    """P3-5: composite "is the chamber actually ready?" snapshot.

    Bundles the per-driver readiness rows (previously only logged at
    startup) with active LabProfile state, active calibration
    certificate validity, and a DUT-attach placeholder. Operator can
    Slack-paste a single JSON or open one GUI panel instead of grep-
    ing log files for HAL init + checking LabProfile separately +
    looking up cert expiry by hand.

    Returns ``available=false`` with empty/placeholder sub-sections
    when HAL hasn't initialised yet (lifespan not run, mid-reload).
    GUI should treat that as "not ready" rather than rendering the
    placeholder values as live.
    """
    from app.services.instrument_hal_service import get_hal_service

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
                is_active=False,
                status="missing",
                detail="HAL not initialised yet",
            ),
            calibration=CalibrationReadinessResponse(
                status="no_lab",
                detail="HAL not initialised yet",
            ),
            dut_attach=DutAttachReadinessResponse(
                status="not_implemented",
                detail="HAL not initialised yet",
            ),
            generated_at_iso=_dt.utcnow().isoformat(),
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
            )
            for r in report.drivers
        ],
        lab_profile=LabProfileReadinessResponse(
            profile_id=report.lab_profile.profile_id,
            profile_name=report.lab_profile.profile_name,
            is_active=report.lab_profile.is_active,
            status=report.lab_profile.status,
            detail=report.lab_profile.detail,
        ),
        calibration=CalibrationReadinessResponse(
            certificate_number=report.calibration.certificate_number,
            valid_until_iso=report.calibration.valid_until_iso,
            status=report.calibration.status,
            days_remaining=report.calibration.days_remaining,
            detail=report.calibration.detail,
        ),
        dut_attach=DutAttachReadinessResponse(
            status=report.dut_attach.status,
            detail=report.dut_attach.detail,
        ),
        generated_at_iso=report.generated_at_iso,
    )


@router.post("/instruments/hal/switch", response_model=HALModeSwitchResult)
async def switch_hal_mode_endpoint(request: HALModeSwitchRequest):
    """
    运行时切换 HAL 驱动模式（Mock ↔ Real）

    不需要重启服务。切换后所有驱动会被重新初始化。
    """
    from app.services.instrument_hal_service import switch_hal_mode, DriverMode

    if request.mode not in ("mock", "real"):
        raise HTTPException(400, f"Invalid mode: {request.mode}. Use 'mock' or 'real'.")

    target_mode = DriverMode.MOCK if request.mode == "mock" else DriverMode.REAL

    try:
        result = await switch_hal_mode(target_mode)
        return HALModeSwitchResult(
            success=True,
            previous_mode=result["previous_mode"],
            current_mode=result["current_mode"],
            active_drivers=result["active_drivers"],
            driver_count=result["driver_count"],
            message=f"已切换到 {result['current_mode']} 模式，{result['driver_count']} 个驱动已激活",
        )
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
