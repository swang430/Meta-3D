"""
系统日志管理 API

提供对 api-service/logs/ 目录下结构化日志文件的查询、过滤和下载能力。
日志格式为每行一个 JSON 对象（由 logging_config.py 的 JsonFormatter 生成）。

端点:
  GET /system-logs/files           — 列出所有日志文件
  GET /system-logs/tail            — 尾读指定文件（支持级别/关键词过滤）
  GET /system-logs/history         — 显式游标读取更早一页
  GET /system-logs/download/{name} — 下载原始日志文件
"""

import base64
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, List, NamedTuple, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/system-logs", tags=["System Logs"])


# ── Schemas ─────────────────────────────────────────────────────

class LogFileInfo(BaseModel):
    """日志文件元信息"""
    filename: str
    size_bytes: int
    size_human: str
    last_modified: str
    is_current: bool  # 是否为当前活跃的日志文件（非归档）


class LogEntry(BaseModel):
    """解析后的单条日志"""
    ts: str
    level: str
    logger: str
    hal_mode: str = "-"
    session_id: str = "-"
    execution_id: str = "-"
    instrument_id: str = "-"
    msg: str
    raw: Optional[str] = None  # 原始 JSON 行（供详情展开）


class LogTailResponse(BaseModel):
    """尾读响应"""
    filename: str
    total_lines_read: int
    filtered_count: int
    entries: List[LogEntry]
    older_cursor: Optional[str] = None
    has_older: bool = False


class LogFilesResponse(BaseModel):
    """文件列表响应"""
    log_dir: str
    files: List[LogFileInfo]


# ── Helpers ─────────────────────────────────────────────────────

def _get_log_dir() -> Path:
    """获取日志目录的绝对路径"""
    log_dir = Path(settings.log_dir)
    if not log_dir.is_absolute():
        # 相对路径基于 api-service/ 目录
        base = Path(__file__).parent.parent.parent
        log_dir = base / log_dir
    return log_dir.resolve()


def _safe_filename(filename: str) -> Path:
    """校验文件名安全性，防止路径遍历"""
    # 只允许字母、数字、点、横线、下划线
    if not re.match(r'^[\w\-\.]+$', filename):
        raise HTTPException(status_code=400, detail=f"非法文件名: {filename}")

    log_dir = _get_log_dir()
    filepath = (log_dir / filename).resolve()

    # 确保文件在日志目录内
    if not str(filepath).startswith(str(log_dir)):
        raise HTTPException(status_code=403, detail="路径遍历攻击被拦截")

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"日志文件不存在: {filename}")

    return filepath


def _human_size(size_bytes: int) -> str:
    """将字节数转换为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# 反向扫描的行数上限 — /tail 被面板 3s 轮询高频调用, 不允许整文件扫
# (app.log 按天轮转, 峰值 ~250 行/分 → 2 万行 ≈ 80 分钟窗口)。
_TAIL_SCAN_LIMIT = 20_000

# 历史页只由用户显式点击触发，不进入自动轮询。仍给单次请求设扫描预算，避免
# 极稀疏过滤一次扫完整个超大文件；空匹配页也会返回向前推进的新游标。
_HISTORY_SCAN_LIMIT = 100_000
_CURSOR_VERSION = 2
_CURSOR_ANCHOR_BYTES = 64
_ACTIVE_LOG_NAMES = {
    "app.log", "scpi.log", "db.log",
    "calibration.log", "measurement.log", "channel_engine.log",
    "audit.log", "alert.log", "frontend.log",
}


def _entry_matches(
    entry: LogEntry,
    level: Optional[str],
    keyword: Optional[str],
    session_id: Optional[str],
    hal_mode: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> bool:
    """日志过滤谓词 —— `/tail`、`/history` 与 `/export` **共用这一份**。

    ⚠ P1-35 之前 `/export` 自己抄了一份，两处会漂（P1-34 内审 F3 抓到的
    「屏幕 5 条、导出全量」就是同一个母题）。要改过滤语义只改这里。

    `level` 支持**逗号分隔的多个级别**（如 `WARNING,ERROR,CRITICAL`）——
    因为后端是**精确相等**不是门槛，没有任何单值能表达「WARNING 及以上」，
    而故障分诊恰恰要的就是那个。
    ⚠ 仍然是**精确匹配**（对集合），不是序数比较：`ZoneLogsAlerts`
    （P2-19 #258）的跨流去重依赖「不同 level 的流天然不相交」，
    改成门槛式会让那里出错。
    """
    if level:
        wanted = {p.strip().upper() for p in level.split(",") if p.strip()}
        if entry.level.upper() not in wanted:
            return False
    if keyword:
        kw_lower = keyword.lower()
        if kw_lower not in entry.msg.lower() and kw_lower not in entry.logger.lower():
            return False
    if session_id and entry.session_id != session_id:
        return False
    if execution_id and entry.execution_id != execution_id:
        return False
    if hal_mode and entry.hal_mode.lower() != hal_mode.lower():
        return False
    return True


def _inherit_parent_context(
    continuations: List[LogEntry], parent: LogEntry,
) -> List[LogEntry]:
    """Give RAW rows their parent's identity while retaining RAW level/text."""
    inherited = {
        "ts": parent.ts,
        "logger": parent.logger,
        "hal_mode": parent.hal_mode,
        "session_id": parent.session_id,
        "execution_id": parent.execution_id,
        "instrument_id": parent.instrument_id,
    }
    return [entry.model_copy(update=inherited) for entry in continuations]


def _is_raw_entry(entry: LogEntry) -> bool:
    """Structural continuation test; filtering remains centralized elsewhere."""
    return entry.level.upper() == "RAW"


class _CursorState(NamedTuple):
    device: int
    inode: int
    offset: int
    snapshot_eof: int
    boundary_hash: str
    eof_hash: str


def _sample_digest(stream: BinaryIO, start: int, end: int) -> str:
    """固定字节样本指纹；游标校验成本不随翻页深度增长。"""
    # 用 pread 绕过 BufferedReader 的用户态 read-ahead cache；否则另一个句柄
    # 等长改写后，同一个 stream.seek/read 仍可能读到扫描阶段缓存的旧字节。
    sample = os.pread(stream.fileno(), end - start, start)
    if len(sample) != end - start:
        raise HTTPException(status_code=409, detail="日志文件已截断，请刷新后重新浏览")
    return hashlib.sha256(sample).hexdigest()[:24]


def _boundary_digest(stream: BinaryIO, offset: int, snapshot_eof: int) -> str:
    return _sample_digest(
        stream,
        max(0, offset - _CURSOR_ANCHOR_BYTES),
        min(snapshot_eof, offset + _CURSOR_ANCHOR_BYTES),
    )


def _eof_digest(stream: BinaryIO, snapshot_eof: int) -> str:
    return _sample_digest(
        stream,
        max(0, snapshot_eof - _CURSOR_ANCHOR_BYTES),
        snapshot_eof,
    )


def _validate_cursor_state(
    state: _CursorState,
    stream: BinaryIO,
    stat: os.stat_result,
) -> None:
    current = os.fstat(stream.fileno())
    if (state.device, state.inode) != (stat.st_dev, stat.st_ino):
        raise HTTPException(status_code=409, detail="日志文件已轮转或替换，请刷新后重新浏览")
    if (current.st_dev, current.st_ino) != (stat.st_dev, stat.st_ino):
        raise HTTPException(status_code=409, detail="日志文件已轮转或替换，请刷新后重新浏览")
    if state.offset < 0 or state.snapshot_eof < state.offset or state.snapshot_eof > current.st_size:
        raise HTTPException(status_code=409, detail="日志文件已截断，请刷新后重新浏览")
    if state.offset > 0:
        stream.seek(state.offset - 1)
        if stream.read(1) != b"\n":
            raise HTTPException(status_code=409, detail="日志分页边界已变化，请刷新后重新浏览")
    if state.boundary_hash != _boundary_digest(stream, state.offset, state.snapshot_eof):
        raise HTTPException(status_code=409, detail="日志分页边界内容已变化，请刷新后重新浏览")
    if state.eof_hash != _eof_digest(stream, state.snapshot_eof):
        raise HTTPException(status_code=409, detail="日志快照尾部内容已变化，请刷新后重新浏览")


def _encode_cursor(
    stream: BinaryIO,
    stat: os.stat_result,
    offset: int,
    snapshot_eof: int,
) -> str:
    """游标绑定同一文件实例、分页边界和初始 EOF；EOF 后 append 不参与校验。"""
    current = os.fstat(stream.fileno())
    if (current.st_dev, current.st_ino) != (stat.st_dev, stat.st_ino):
        raise HTTPException(status_code=409, detail="日志文件已轮转或替换，请刷新后重新浏览")
    if snapshot_eof > current.st_size:
        raise HTTPException(status_code=409, detail="日志文件已截断，请刷新后重新浏览")
    payload = {
        "v": _CURSOR_VERSION,
        "dev": stat.st_dev,
        "ino": stat.st_ino,
        "offset": offset,
        "snapshot_eof": snapshot_eof,
        "boundary_hash": _boundary_digest(stream, offset, snapshot_eof),
        "eof_hash": _eof_digest(stream, snapshot_eof),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, stream: BinaryIO, stat: os.stat_result) -> _CursorState:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
        version = int(payload["v"])
        device = int(payload["dev"])
        inode = int(payload["ino"])
        offset = int(payload["offset"])
        snapshot_eof = int(payload["snapshot_eof"])
        boundary_hash = str(payload["boundary_hash"])
        eof_hash = str(payload["eof_hash"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="历史日志游标格式无效，请刷新后重试") from exc

    if version != _CURSOR_VERSION:
        raise HTTPException(status_code=400, detail="历史日志游标版本不受支持，请刷新后重试")

    state = _CursorState(
        device, inode, offset, snapshot_eof, boundary_hash, eof_hash,
    )
    _validate_cursor_state(state, stream, stat)
    return state


def _scan_reverse_entries(
    stream: BinaryIO,
    file_size: int,
    max_entries: int,
    predicate,
    *,
    before_offset: Optional[int] = None,
    scan_limit: int = _TAIL_SCAN_LIMIT,
) -> Tuple[List[LogEntry], int, int, bool]:
    """
    从文件末尾反向扫描, 边读边过滤, 凑满 max_entries 条匹配行为止。

    过滤必须发生在扫描过程中而非截尾之后 — 否则低频 WARNING/ERROR 会被
    高频 INFO 冲出固定行数的原始窗口 (2026-07-31 P2-11 相位失败三次落盘
    但面板不可见的根因)。扫描行数以 _TAIL_SCAN_LIMIT 封顶 — 3s 轮询下的
    最坏开销按行数有界 (字节数不设上限: 无换行的损坏/巨行文件仍会整读,
    与旧实现同病, 字节上限在 backlog)。

    返回 (匹配条目按时间正序, 实际扫描的非空行数, 下一位置, 是否还有更早内容)。
    字节位置只会落在行首；历史页因此可以从上次停止处继续，不重新扫描文件尾。
    """
    matched: List[LogEntry] = []
    matched_groups = 0
    # Reverse scan sees traceback lines before their structured parent. Hold
    # them until the parent decides whether the whole group matches filters.
    pending_continuations: List[LogEntry] = []
    scanned = 0
    end = file_size if before_offset is None else before_offset
    if end < 0 or end > file_size:
        raise HTTPException(status_code=409, detail="日志文件已截断，请刷新后重新浏览")
    if end == 0 or file_size == 0:
        return [], 0, 0, False

    next_offset = end
    chunk_size = 8192
    position = end
    buffer = b""
    buffer_start = end

    while (
        position > 0
        and matched_groups < max_entries
        and (scanned < scan_limit or pending_continuations)
    ):
        read_start = max(0, position - chunk_size)
        stream.seek(read_start)
        block = stream.read(position - read_start)
        buffer = block + buffer
        buffer_start = read_start
        position = read_start

        parts = buffer.split(b"\n")
        # parts[0] 可能被 chunk 边界截断，留给下一轮；其余都是完整行。
        part_starts = []
        part_start = buffer_start
        for part in parts:
            part_starts.append(part_start)
            part_start += len(part) + 1

        for index in range(len(parts) - 1, 0, -1):
            next_offset = part_starts[index]
            stripped = parts[index].strip()
            if not stripped:
                continue
            scanned += 1
            entry = _parse_log_line(stripped.decode("utf-8", errors="replace"))
            if entry is not None:
                if _is_raw_entry(entry):
                    pending_continuations.append(entry)
                else:
                    if predicate(entry):
                        # ``matched`` is in newest→oldest scan order; append
                        # Rn..R1 then parent so final reverse becomes P,R1..Rn.
                        matched.extend(_inherit_parent_context(pending_continuations, entry))
                        matched.append(entry)
                        matched_groups += 1
                    pending_continuations.clear()
            if (
                matched_groups >= max_entries
                or (scanned >= scan_limit and not pending_continuations)
            ):
                break

        buffer = parts[0]

    # 文件开头没有前导换行，它是最后一条待处理的完整行。
    if (
        position == 0
        and matched_groups < max_entries
        and (scanned < scan_limit or pending_continuations)
    ):
        next_offset = 0
        stripped = buffer.strip()
        if stripped:
            scanned += 1
            entry = _parse_log_line(stripped.decode("utf-8", errors="replace"))
            if entry is not None:
                if _is_raw_entry(entry):
                    pending_continuations.append(entry)
                else:
                    if predicate(entry):
                        matched.extend(_inherit_parent_context(pending_continuations, entry))
                        matched.append(entry)
                        matched_groups += 1
                    pending_continuations.clear()

    # A file/page that begins with unparented RAW data keeps the legacy
    # standalone behavior; level filters still exclude it as RAW.
    if pending_continuations and any(predicate(entry) for entry in pending_continuations):
        matched.extend(pending_continuations)

    matched.reverse()
    return matched, scanned, next_offset, next_offset > 0


def _parse_log_line(line: str) -> Optional[LogEntry]:
    """尝试将一行日志解析为 LogEntry"""
    try:
        obj = json.loads(line)
        return LogEntry(
            ts=obj.get("ts", ""),
            level=obj.get("level", "UNKNOWN"),
            logger=obj.get("logger", ""),
            hal_mode=obj.get("hal_mode", "-"),
            session_id=obj.get("session_id", "-"),
            execution_id=obj.get("execution_id", "-"),
            instrument_id=obj.get("instrument_id", "-"),
            msg=obj.get("msg", line),
            raw=line,
        )
    except (json.JSONDecodeError, ValueError):
        # 非 JSON 行（如 Python traceback 续行）
        return LogEntry(
            ts="",
            level="RAW",
            logger="",
            msg=line,
            raw=line,
        )


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/files", response_model=LogFilesResponse)
def list_log_files():
    """
    列出日志目录下所有日志文件。

    返回每个文件的名称、大小、最后修改时间，以及是否为当前活跃文件。
    """
    log_dir = _get_log_dir()

    if not log_dir.exists():
        return LogFilesResponse(log_dir=str(log_dir), files=[])

    files = []
    for entry in sorted(log_dir.iterdir()):
        is_log_file = entry.name.endswith(".log") or ".log." in entry.name
        if entry.is_file() and is_log_file and not entry.name.startswith('.'):
            stat = entry.stat()
            # 只有固定写入目标是活跃文件；带轮转后缀的同族文件都是归档。
            is_current = entry.name in _ACTIVE_LOG_NAMES
            files.append(LogFileInfo(
                filename=entry.name,
                size_bytes=int(stat.st_size),
                size_human=_human_size(stat.st_size),
                last_modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                is_current=is_current,
            ))

    # 按修改时间倒序（最新在前）
    files.sort(key=lambda f: f.last_modified, reverse=True)

    return LogFilesResponse(log_dir=str(log_dir), files=files)


@router.get("/tail", response_model=LogTailResponse)
def tail_log_file(
    filename: str = Query(default="app.log", description="日志文件名"),
    lines: int = Query(default=200, ge=1, le=2000, description="返回的最大匹配条数"),
    level: Optional[str] = Query(default=None, description="逗号分隔的级别集合（如 `WARNING,ERROR,CRITICAL`）。**精确匹配不是门槛** —— ZoneLogsAlerts 的跨流去重依赖不同 level 的流互不相交，别改成 >="),
    keyword: Optional[str] = Query(default=None, description="按关键词过滤（模糊匹配 msg 和 logger 字段）"),
    session_id: Optional[str] = Query(default=None, description="按 session_id 精确过滤"),
    execution_id: Optional[str] = Query(default=None, description="按测试执行 id 精确过滤（一次执行跨多请求、也可能不在请求里，与 session_id 是两个生命周期）"),
):
    """
    读取指定日志文件中最新的 N 条匹配日志，支持多维度过滤。

    过滤发生在反向扫描过程中: 从文件末尾往回读, 直到凑满 lines 条匹配行、
    扫到文件开头或达到 _TAIL_SCAN_LIMIT 行上限。带过滤条件时窗口是
    "最新 N 条匹配行"而非"最新 N 行原始行" — 低频 WARNING/ERROR 不会被
    高频 INFO 冲出窗口。total_lines_read 为实际扫描的行数。
    """
    filepath = _safe_filename(filename)

    with open(filepath, "rb") as stream:
        stat = os.fstat(stream.fileno())
        entries, scanned, next_offset, has_older = _scan_reverse_entries(
            stream,
            stat.st_size,
            max_entries=lines,
            predicate=lambda e: _entry_matches(
                e, level, keyword, session_id, execution_id=execution_id),
            scan_limit=_TAIL_SCAN_LIMIT,
        )
        older_cursor = (
            _encode_cursor(stream, stat, next_offset, stat.st_size)
            if has_older else None
        )

    return LogTailResponse(
        filename=filename,
        total_lines_read=scanned,
        filtered_count=len(entries),
        entries=entries,
        older_cursor=older_cursor,
        has_older=has_older,
    )


@router.get("/history", response_model=LogTailResponse)
def read_log_history(
    cursor: str = Query(description="由 `/tail` 或上一页返回的不透明历史游标"),
    filename: str = Query(default="app.log", description="日志文件名"),
    lines: int = Query(default=200, ge=1, le=2000, description="返回的最大匹配条数"),
    level: Optional[str] = Query(default=None, description="逗号分隔的级别集合；精确匹配"),
    keyword: Optional[str] = Query(default=None, description="按关键词过滤"),
    session_id: Optional[str] = Query(default=None, description="按 session_id 精确过滤"),
    execution_id: Optional[str] = Query(default=None, description="按测试执行 id 精确过滤"),
):
    """从显式游标继续读取更早日志；本端点不得用于自动轮询。"""
    filepath = _safe_filename(filename)
    with open(filepath, "rb") as stream:
        stat = os.fstat(stream.fileno())
        cursor_state = _decode_cursor(cursor, stream, stat)
        entries, scanned, next_offset, has_older = _scan_reverse_entries(
            stream,
            stat.st_size,
            max_entries=lines,
            predicate=lambda e: _entry_matches(
                e, level, keyword, session_id, execution_id=execution_id,
            ),
            before_offset=cursor_state.offset,
            scan_limit=_HISTORY_SCAN_LIMIT,
        )
        # decode 后到 scan 结束之间也可能发生截断/原位改写；最终页没有下一枚
        # cursor，同样必须复验输入游标，不能靠 encode 的副作用兜底。
        _validate_cursor_state(cursor_state, stream, stat)
        older_cursor = (
            _encode_cursor(stream, stat, next_offset, cursor_state.snapshot_eof)
            if has_older else None
        )
    return LogTailResponse(
        filename=filename,
        total_lines_read=scanned,
        filtered_count=len(entries),
        entries=entries,
        older_cursor=older_cursor,
        has_older=has_older,
    )


@router.get("/download/{filename}")
def download_log_file(filename: str):
    """
    下载原始日志文件（全量）。

    返回文件流，适合附加到报告中或离线分析。
    """
    filepath = _safe_filename(filename)

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/export/{filename}")
def export_filtered_logs(
    filename: str,
    level: Optional[str] = Query(default=None, description="逗号分隔的级别集合（如 `WARNING,ERROR,CRITICAL`）。**精确匹配不是门槛** —— ZoneLogsAlerts 的跨流去重依赖不同 level 的流互不相交，别改成 >="),
    keyword: Optional[str] = Query(default=None, description="按关键词过滤"),
    session_id: Optional[str] = Query(default=None, description="按 session_id 过滤"),
    hal_mode: Optional[str] = Query(default=None, description="按 HAL 模式过滤 (mock/real)"),
    execution_id: Optional[str] = Query(default=None, description="按测试执行 id 精确过滤（一次执行跨多请求、也可能不在请求里，与 session_id 是两个生命周期）"),
):
    """
    按过滤条件导出日志。

    与 /download 不同，此端点会根据筛选条件只导出匹配的行。
    返回 JSONL 格式的文件流。
    """
    filepath = _safe_filename(filename)

    def filtered_stream():
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            group: list[tuple[str, LogEntry]] = []

            def emit_group():
                if not group:
                    return []
                parent = group[0][1]
                if not _entry_matches(
                    parent, level, keyword, session_id, hal_mode, execution_id,
                ):
                    return []
                return [raw for raw, _entry in group]

            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue

                entry = _parse_log_line(stripped)
                if entry is None:
                    continue
                if _is_raw_entry(entry) and group:
                    group.append((stripped, entry))
                    continue

                for raw in emit_group():
                    yield raw + "\n"
                group = [(stripped, entry)]

            for raw in emit_group():
                yield raw + "\n"

    # 导出文件名带过滤标记
    parts = [filename.replace('.log', '')]
    if level:
        parts.append(level.lower())
    if hal_mode:
        parts.append(hal_mode.lower())
    if keyword:
        parts.append(keyword[:20])
    export_name = "_".join(parts) + "_export.jsonl"

    return StreamingResponse(
        filtered_stream(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{export_name}"'},
    )


# ── 前端日志接收 ────────────────────────────────────────────────

import logging

# 前端日志通道使用的 logger
_frontend_logger = logging.getLogger("app.frontend")

class FrontendLogEntry(BaseModel):
    """浏览器端单条日志"""
    ts: Optional[float] = None        # Unix ms 时间戳
    level: str = "INFO"               # DEBUG / INFO / WARN / ERROR
    action: str = ""                  # 操作标识 (e.g. "page_nav", "btn_click")
    page: Optional[str] = None        # 当前页面路由
    component: Optional[str] = None   # 组件名
    message: Optional[str] = None     # 日志消息
    # 可选扩展字段
    url: Optional[str] = None         # API URL
    status_code: Optional[int] = None # HTTP 状态码
    elapsed_ms: Optional[float] = None  # 请求耗时
    error: Optional[str] = None       # 错误信息
    user_agent: Optional[str] = None  # 浏览器 UA


class FrontendLogBatch(BaseModel):
    """前端日志批量上报"""
    entries: List[FrontendLogEntry]
    session_id: Optional[str] = None  # 前端会话标识


class FrontendLogResponse(BaseModel):
    """上报响应"""
    accepted: int
    message: str = "ok"


@router.post("/frontend", response_model=FrontendLogResponse)
def ingest_frontend_logs(batch: FrontendLogBatch):
    """
    接收前端浏览器上报的行为日志。

    前端通过 POST 批量提交用户操作、API 请求摘要、
    WebSocket 状态变化和前端异常等事件。

    所有日志写入 frontend.log，不传播到 console/app.log。
    """
    count = 0
    for entry in batch.entries:
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        level = level_map.get(entry.level.upper(), logging.INFO)

        msg = entry.message or entry.action or "frontend_event"

        extra = {
            "action": entry.action,
            "page": entry.page or "-",
            "component": entry.component or "-",
        }
        if batch.session_id:
            extra["frontend_session"] = batch.session_id
        if entry.url:
            extra["url"] = entry.url
        if entry.status_code is not None:
            extra["status_code"] = entry.status_code
        if entry.elapsed_ms is not None:
            extra["elapsed_ms"] = entry.elapsed_ms
        if entry.error:
            extra["error"] = entry.error
        if entry.user_agent:
            extra["user_agent"] = entry.user_agent
        if entry.ts:
            extra["client_ts"] = entry.ts

        _frontend_logger.log(level, msg, extra=extra)
        count += 1

    return FrontendLogResponse(accepted=count)
