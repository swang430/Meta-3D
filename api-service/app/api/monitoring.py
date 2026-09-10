"""Monitoring API endpoints (Phase 2 - WebSocket enabled)"""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any, Literal, Set
from datetime import datetime
import logging
import asyncio
import json

from app.db.database import get_db
from app.services.instrument_hal_service import (
    build_unavailable_monitoring_data,
    get_hal_service,
)
from app.services.instrument_test_lease import is_test_monitoring_enabled

router = APIRouter()
logger = logging.getLogger(__name__)


class MonitoringMetric(BaseModel):
    """单项实时监控观测。"""
    name: str
    value: float | None
    unit: str
    timestamp: datetime
    status: Literal["observed", "unavailable", "simulated"]
    provenance: Literal["real", "simulated", "unknown"]
    reason: str | None


class MonitoringFeedsResponse(BaseModel):
    """Monitoring feeds response"""
    feeds: List[MonitoringMetric]
    timestamp: datetime


class MonitoringDataPoint(BaseModel):
    """实时监控数据点。"""
    metric_name: str
    value: float | None
    unit: str
    timestamp: str
    status: Literal["observed", "unavailable", "simulated"]
    provenance: Literal["real", "simulated", "unknown"]
    reason: str | None


class MonitoringBroadcast(BaseModel):
    """WebSocket broadcast message"""
    type: str  # "metrics", "alert", "status"
    data: Dict[str, Any]
    timestamp: str


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        """Broadcast message to all connected clients"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.add(connection)

        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


async def generate_monitoring_data() -> Dict[str, Any]:
    """
    从仪表 HAL 生成实时监控观测。

    缺测、模拟与读取失败均保留显式状态，不生成数值兜底。
    """
    # 空闲时不允许 GUI 的 REST/WS 刷新重新触发任何仪表 SCPI。测试租约进入后
    # 才开放实时指标；退出时租约先关此门，再释放 F64 ATE socket。
    if not is_test_monitoring_enabled():
        return build_unavailable_monitoring_data(
            reason="当前没有启用实时监控的测试租约",
        )

    hal_service = get_hal_service()

    try:
        # Get aggregated metrics from HAL service
        metrics = await hal_service.get_aggregated_metrics()

        if not metrics:
            return build_unavailable_monitoring_data(
                reason="HAL 服务未返回监控观测",
            )

        return metrics

    except Exception as e:
        logger.error(f"读取 HAL 监控指标失败: {e}")
        return build_unavailable_monitoring_data(
            reason="HAL 监控读取失败",
        )


async def monitoring_data_broadcaster():
    """
    向所有已连接客户端广播实时监控观测，每秒更新一次。
    """
    logger.info("Starting monitoring data broadcaster")

    while True:
        try:
            if manager.active_connections:
                # 租约关闭后仍发布完整 unavailable 形态，避免客户端继续把最后一个
                # 数值当作实时值；generate_monitoring_data 的空闲门保证不访问 HAL。
                metrics = await generate_monitoring_data()

                # Create broadcast message
                message = MonitoringBroadcast(
                    type="metrics",
                    data=metrics,
                    timestamp=datetime.utcnow().isoformat()
                )

                # Broadcast to all clients
                await manager.broadcast(message.model_dump_json())

            # Wait 1 second before next update
            await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"Error in monitoring broadcaster: {e}")
            await asyncio.sleep(1.0)


@router.get("/monitoring/feeds", response_model=MonitoringFeedsResponse)
async def get_monitoring_feeds(db: Session = Depends(get_db)):
    """
    Get current monitoring data feeds (REST endpoint)

    For one-time data fetch. For real-time updates, use WebSocket endpoint.
    """
    metrics_data = await generate_monitoring_data()

    feeds = [
        MonitoringMetric(
            name=name,
            value=data["value"],
            unit=data["unit"],
            timestamp=data["timestamp"],
            status=data["status"],
            provenance=data["provenance"],
            reason=data["reason"],
        )
        for name, data in metrics_data.items()
    ]

    return MonitoringFeedsResponse(feeds=feeds, timestamp=datetime.utcnow())


@router.websocket("/ws/monitoring")
async def websocket_monitoring_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time monitoring data

    Clients connect to this endpoint to receive continuous monitoring updates.
    Data is broadcast every 1 second.

    Message format:
    {
        "type": "metrics",
        "data": {
            "metric_name": {
                "value": float | null,
                "unit": str,
                "timestamp": str,
                "status": "observed" | "unavailable" | "simulated",
                "provenance": "real" | "simulated" | "unknown",
                "reason": str | null
            },
            ...
        },
        "timestamp": str
    }
    """
    await manager.connect(websocket)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connection established",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client messages (e.g., ping, control commands)
                data = await websocket.receive_text()

                # Handle client requests
                try:
                    request = json.loads(data)
                    if request.get("type") == "ping":
                        await websocket.send_json({
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received: {data}")

            except WebSocketDisconnect:
                logger.info("Client disconnected normally")
                break
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)
