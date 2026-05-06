"""Instrument API endpoints

输出格式适配前端 InstrumentsResponse / InstrumentCategory 类型定义。
后端 DB 模型 → 前端友好的扁平化 JSON。
"""
from fastapi import APIRouter, Depends, HTTPException
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
    from app.services.instrument_hal_service import has_real_driver
    caps = model_db.capabilities or {}
    
    is_supported = has_real_driver(category_key, model_db.model)
    status = "available" if is_supported else "pending_dev"
    
    return FEInstrumentModel(
        id=str(model_db.id),
        vendor=model_db.vendor,
        model=model_db.model,
        summary=_make_summary(model_db),
        interfaces=_extract_interfaces(caps),
        capabilities=_extract_capabilities_summary(caps),
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

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((ip, port))

        scpi_logger.info(
            f"[SCPI-PROBE] {category_key} → Running {len(COMMON_SCPI_COMMANDS)} diagnostic commands on {ip}:{port}",
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
