"""Monitoring API endpoints (Phase 2 - WebSocket enabled)"""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any, Set
from datetime import datetime
import logging
import asyncio
import json
import random

from app.db.database import get_db
from app.services.instrument_hal_service import get_hal_service

router = APIRouter()
logger = logging.getLogger(__name__)


class MonitoringMetric(BaseModel):
    """Single monitoring metric"""
    name: str
    value: float
    unit: str
    timestamp: datetime


class MonitoringFeedsResponse(BaseModel):
    """Monitoring feeds response"""
    feeds: List[MonitoringMetric]
    timestamp: datetime


class MonitoringDataPoint(BaseModel):
    """Real-time monitoring data point"""
    metric_name: str
    value: float
    unit: str
    timestamp: str
    status: str  # "normal", "warning", "critical"


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
    Generate monitoring data from instrument HAL

    Phase 2.4.6: Uses HAL service with mock drivers
    Phase 3+: Will use real instrument drivers
    """
    hal_service = get_hal_service()

    try:
        # Get aggregated metrics from HAL service
        metrics = await hal_service.get_aggregated_metrics()

        if not metrics:
            # Fallback to simple mock data if HAL service not initialized
            logger.warning("HAL service returned empty metrics, using fallback")
            return _generate_fallback_data()

        return metrics

    except Exception as e:
        logger.error(f"Error getting HAL metrics: {e}")
        return _generate_fallback_data()


def _generate_fallback_data() -> Dict[str, Any]:
    """
    Fallback monitoring data generator

    Used when HAL service is unavailable or returns errors
    """
    now = datetime.utcnow().isoformat()

    # Generate realistic metrics with random variations
    throughput = 150.0 + random.uniform(-20, 30)
    snr = 25.0 + random.uniform(-3, 3)
    quiet_zone = 0.8 + random.uniform(-0.15, 0.15)
    eirp = 45.0 + random.uniform(-2, 2)
    temperature = 23.0 + random.uniform(-1, 1)

    # Determine status based on thresholds
    def get_status(value: float, warning_threshold: float, critical_threshold: float,
                   is_higher_better: bool = True) -> str:
        if is_higher_better:
            if value < critical_threshold:
                return "critical"
            elif value < warning_threshold:
                return "warning"
        else:
            if value > critical_threshold:
                return "critical"
            elif value > warning_threshold:
                return "warning"
        return "normal"

    metrics = {
        "throughput": {
            "value": round(throughput, 2),
            "unit": "Mbps",
            "timestamp": now,
            "status": get_status(throughput, 140, 120)
        },
        "snr": {
            "value": round(snr, 2),
            "unit": "dB",
            "timestamp": now,
            "status": get_status(snr, 22, 18)
        },
        "quiet_zone_uniformity": {
            "value": round(quiet_zone, 3),
            "unit": "dB",
            "timestamp": now,
            "status": get_status(quiet_zone, 0.7, 0.6)
        },
        "eirp": {
            "value": round(eirp, 2),
            "unit": "dBm",
            "timestamp": now,
            "status": get_status(eirp, 43, 41)
        },
        "temperature": {
            "value": round(temperature, 1),
            "unit": "°C",
            "timestamp": now,
            "status": get_status(temperature, 25, 28, is_higher_better=False)
        }
    }

    return metrics


async def monitoring_data_broadcaster():
    """
    Background task to broadcast monitoring data to all connected clients

    Runs continuously and sends updates every 1 second
    """
    logger.info("Starting monitoring data broadcaster")

    while True:
        try:
            if manager.active_connections:
                # Generate monitoring data from HAL service
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
    now = datetime.utcnow()
    metrics_data = await generate_monitoring_data()

    feeds = [
        MonitoringMetric(
            name=name,
            value=data["value"],
            unit=data["unit"],
            timestamp=now
        )
        for name, data in metrics_data.items()
    ]

    return MonitoringFeedsResponse(feeds=feeds, timestamp=now)


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
                "value": float,
                "unit": str,
                "timestamp": str,
                "status": "normal" | "warning" | "critical"
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
