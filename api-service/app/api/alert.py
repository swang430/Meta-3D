"""Alert API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from uuid import UUID
from datetime import datetime
import logging

from app.db.database import get_db
from app.models.alert import Alert, AlertSeverity, AlertStatus
from app.schemas.alert import (
    AlertCreate,
    AlertUpdate,
    AlertResponse,
    AlertListResponse,
    AlertSummary,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard Alerts"])
logger = logging.getLogger(__name__)


@router.get("/alerts", response_model=AlertListResponse)
def get_alerts(
    status: Optional[str] = Query(None, description="Filter by status"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get list of alerts

    Returns active alerts by default, with optional filters.
    """
    query = db.query(Alert)

    if status:
        query = query.filter(Alert.status == status)
    else:
        # Default to active alerts
        query = query.filter(Alert.status == AlertStatus.ACTIVE.value)

    if severity:
        query = query.filter(Alert.severity == severity)

    # Order by severity (critical first) and then by creation time
    query = query.order_by(
        Alert.severity.desc(),
        Alert.created_at.desc()
    )

    total = query.count()
    alerts = query.offset(skip).limit(limit).all()

    return AlertListResponse(
        total=total,
        alerts=[AlertResponse.model_validate(a) for a in alerts]
    )


@router.post("/alerts", response_model=AlertResponse, status_code=201)
def create_alert(
    request: AlertCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new alert

    Used by system components to notify users of important events.
    """
    # Map 'type' to 'severity'
    severity_map = {
        "info": AlertSeverity.INFO.value,
        "warning": AlertSeverity.WARNING.value,
        "error": AlertSeverity.ERROR.value,
        "critical": AlertSeverity.CRITICAL.value,
    }
    severity = severity_map.get(request.type, AlertSeverity.WARNING.value)

    alert = Alert(
        title=request.title or f"{request.type.upper()}: Alert",
        message=request.message,
        severity=severity,
        alert_type=request.type,
        source=request.source,
        status=AlertStatus.ACTIVE.value,
        related_entity_type=request.related_entity_type,
        related_entity_id=request.related_entity_id,
        created_by=request.source,
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    logger.info(f"Created alert: {alert.id} - {alert.title}")
    return alert


@router.get("/alerts/summary", response_model=AlertSummary)
def get_alert_summary(db: Session = Depends(get_db)):
    """
    Get alert summary statistics

    Returns counts of active alerts by severity.
    """
    # 单次聚合保证 total 与各级计数来自同一个数据库快照。severity 目前只是
    # String 列、没有 CHECK 约束；未知值仍计入 total，使消费方能通过总数与
    # 四级计数和不一致识别脏数据，不能静默显示“无活动告警”。
    rows = (
        db.query(Alert.severity, func.count(Alert.id))
        .filter(Alert.status == AlertStatus.ACTIVE.value)
        .group_by(Alert.severity)
        .all()
    )
    counts = {severity: count for severity, count in rows}
    total_active = sum(counts.values())

    return AlertSummary(
        total_active=total_active,
        info_count=counts.get(AlertSeverity.INFO.value, 0),
        warning_count=counts.get(AlertSeverity.WARNING.value, 0),
        error_count=counts.get(AlertSeverity.ERROR.value, 0),
        critical_count=counts.get(AlertSeverity.CRITICAL.value, 0),
    )


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific alert by ID"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return alert


@router.patch("/alerts/{alert_id}", response_model=AlertResponse)
def update_alert(
    alert_id: UUID,
    request: AlertUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an alert status

    Use this to acknowledge, resolve, or dismiss alerts.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if request.status is not None:
        alert.status = request.status.value

        if request.status == AlertStatus.ACKNOWLEDGED:
            alert.acknowledged_at = datetime.utcnow()
        elif request.status == AlertStatus.RESOLVED:
            alert.resolved_at = datetime.utcnow()

    if request.is_read is not None:
        alert.is_read = request.is_read

    db.commit()
    db.refresh(alert)

    logger.info(f"Updated alert: {alert_id} - status: {alert.status}")
    return alert


@router.delete("/alerts/{alert_id}", status_code=204)
def dismiss_alert(
    alert_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Dismiss an alert

    Sets the alert status to 'dismissed'.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = AlertStatus.DISMISSED.value
    db.commit()

    logger.info(f"Dismissed alert: {alert_id}")
    return None
