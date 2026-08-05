"""
系统日志管理 API

提供对 api-service/logs/ 目录下结构化日志文件的查询、过滤和下载能力。
日志格式为每行一个 JSON 对象（由 logging_config.py 的 JsonFormatter 生成）。

端点:
  GET /system-logs/files           — 列出所有日志文件
  GET /system-logs/tail            — 尾读指定文件（支持级别/关键词过滤）
  GET /system-logs/download/{name} — 下载原始日志文件
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

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


def _entry_matches(
    entry: LogEntry,
    level: Optional[str],
    keyword: Optional[str],
    session_id: Optional[str],
    hal_mode: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> bool:
    """日志过滤谓词 —— `/tail` 与 `/export` **共用这一份**。

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


def _scan_tail_entries(
    filepath: Path,
    max_entries: int,
    predicate,
) -> Tuple[List[LogEntry], int]:
    """
    从文件末尾反向扫描, 边读边过滤, 凑满 max_entries 条匹配行为止。

    过滤必须发生在扫描过程中而非截尾之后 — 否则低频 WARNING/ERROR 会被
    高频 INFO 冲出固定行数的原始窗口 (2026-07-31 P2-11 相位失败三次落盘
    但面板不可见的根因)。扫描行数以 _TAIL_SCAN_LIMIT 封顶 — 3s 轮询下的
    最坏开销按行数有界 (字节数不设上限: 无换行的损坏/巨行文件仍会整读,
    与旧实现同病, 字节上限在 backlog)。

    返回 (匹配条目按时间正序, 实际扫描的非空行数)。
    """
    matched: List[LogEntry] = []
    scanned = 0
    chunk_size = 8192

    with open(filepath, 'rb') as f:
        # 移动到文件末尾
        f.seek(0, 2)
        remaining = f.tell()
        buffer = b''

        while remaining > 0 and len(matched) < max_entries and scanned < _TAIL_SCAN_LIMIT:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            buffer = f.read(read_size) + buffer

            # 按行拆分; 第一个片段可能被 chunk 边界截断, 留给下一轮拼接
            split_lines = buffer.split(b'\n')
            buffer = split_lines[0]
            for line in reversed(split_lines[1:]):
                stripped = line.strip()
                if not stripped:
                    continue
                scanned += 1
                entry = _parse_log_line(stripped.decode('utf-8', errors='replace'))
                if entry is not None and predicate(entry):
                    matched.append(entry)
                    if len(matched) >= max_entries:
                        break
                if scanned >= _TAIL_SCAN_LIMIT:
                    break

        # 文件开头剩余的半行
        if buffer.strip() and len(matched) < max_entries and scanned < _TAIL_SCAN_LIMIT:
            scanned += 1
            entry = _parse_log_line(buffer.strip().decode('utf-8', errors='replace'))
            if entry is not None and predicate(entry):
                matched.append(entry)

    matched.reverse()  # 恢复时间顺序
    return matched, scanned


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
        if entry.is_file() and entry.suffix in ('.log', '') and not entry.name.startswith('.'):
            stat = entry.stat()
            # 当前活跃文件 = 没有日期后缀的文件
            is_current = '.' not in entry.stem or entry.name in ('app.log', 'scpi.log')
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

    entries, scanned = _scan_tail_entries(
        filepath,
        max_entries=lines,
        predicate=lambda e: _entry_matches(
            e, level, keyword, session_id, execution_id=execution_id),
    )

    return LogTailResponse(
        filename=filename,
        total_lines_read=scanned,
        filtered_count=len(entries),
        entries=entries,
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
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue

                entry = _parse_log_line(stripped)
                if entry is None:
                    continue

                # ⚠ 用 `/tail` 那同一个谓词，别再抄一份 —— 抄出来的两份
                # 一定会漂（P1-34 内审 F3：屏幕 5 条、导出全量）。
                if not _entry_matches(
                        entry, level, keyword, session_id, hal_mode, execution_id):
                    continue

                yield stripped + "\n"

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

# 已知的活跃日志文件名集合（用于 is_current 判定）
_ACTIVE_LOG_NAMES = {
    "app.log", "scpi.log", "db.log",
    "calibration.log", "measurement.log", "channel_engine.log",
    "audit.log", "alert.log", "frontend.log",
}


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

