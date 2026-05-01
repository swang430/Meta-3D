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
from typing import List, Optional

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


def _tail_file(filepath: Path, max_lines: int = 200) -> List[str]:
    """
    高效地从文件末尾读取最后 N 行。

    使用反向读取策略，避免将整个大文件加载到内存中。
    """
    lines = []
    chunk_size = 8192

    with open(filepath, 'rb') as f:
        # 移动到文件末尾
        f.seek(0, 2)
        file_size = f.tell()
        remaining = file_size
        buffer = b''

        while remaining > 0 and len(lines) < max_lines:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            chunk = f.read(read_size)
            buffer = chunk + buffer

            # 按行拆分
            split_lines = buffer.split(b'\n')

            # 除了第一个不完整的片段外，其余都是完整行
            buffer = split_lines[0]
            for line in reversed(split_lines[1:]):
                stripped = line.strip()
                if stripped:
                    lines.append(stripped.decode('utf-8', errors='replace'))
                    if len(lines) >= max_lines:
                        break

        # 处理剩余 buffer
        if buffer.strip() and len(lines) < max_lines:
            lines.append(buffer.strip().decode('utf-8', errors='replace'))

    lines.reverse()  # 恢复时间顺序
    return lines


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
    lines: int = Query(default=200, ge=1, le=2000, description="读取的最大行数"),
    level: Optional[str] = Query(default=None, description="按日志级别过滤 (DEBUG/INFO/WARNING/ERROR)"),
    keyword: Optional[str] = Query(default=None, description="按关键词过滤（模糊匹配 msg 和 logger 字段）"),
    session_id: Optional[str] = Query(default=None, description="按 session_id 精确过滤"),
):
    """
    读取指定日志文件的最后 N 行，支持多维度过滤。

    使用反向文件读取避免大文件内存问题。
    过滤在读取之后进行，所以实际返回条目数可能少于 lines。
    """
    filepath = _safe_filename(filename)

    # 读取原始行
    raw_lines = _tail_file(filepath, max_lines=lines)

    # 解析为结构化条目
    entries = []
    for line in raw_lines:
        entry = _parse_log_line(line)
        if entry is None:
            continue

        # 级别过滤
        if level and entry.level.upper() != level.upper():
            continue

        # 关键词过滤（搜索 msg 和 logger）
        if keyword:
            kw_lower = keyword.lower()
            if kw_lower not in entry.msg.lower() and kw_lower not in entry.logger.lower():
                continue

        # session_id 过滤
        if session_id and entry.session_id != session_id:
            continue

        entries.append(entry)

    return LogTailResponse(
        filename=filename,
        total_lines_read=len(raw_lines),
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
    level: Optional[str] = Query(default=None, description="按日志级别过滤"),
    keyword: Optional[str] = Query(default=None, description="按关键词过滤"),
    session_id: Optional[str] = Query(default=None, description="按 session_id 过滤"),
    hal_mode: Optional[str] = Query(default=None, description="按 HAL 模式过滤 (mock/real)"),
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

                # 级别过滤
                if level and entry.level.upper() != level.upper():
                    continue
                # 关键词过滤
                if keyword:
                    kw_lower = keyword.lower()
                    if kw_lower not in entry.msg.lower() and kw_lower not in entry.logger.lower():
                        continue
                # session_id 过滤
                if session_id and entry.session_id != session_id:
                    continue
                # HAL 模式过滤
                if hal_mode and entry.hal_mode.lower() != hal_mode.lower():
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

