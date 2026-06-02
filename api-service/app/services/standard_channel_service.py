"""P2-12 slice 2: Standard Channel Definition (SCD) 服务层.

create 用 slice 1 的 format_standard_channel_filename 从规范配置算标准名 (单一真值: 名字
是配置的派生)。slice 2a 只做 定义 (create/list/get/delete); 关联 (associate + cross-check
+ synced projection 更新清单) 是 slice 2b。
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.standard_channel import StandardChannelDefinition
from app.services.mimo_ota.channel_naming import (
    StandardChannelName,
    format_standard_channel_filename,
)


class StandardChannelError(ValueError):
    """SCD 业务错误 (字段非法 / 重复 / 不存在), caller (API) 映射成 4xx。"""


def _compute_standard_name(
    *, band: str, arfcn: int, bandwidth_mhz: int, model: str, scenario: str,
    mimo: str, polarization: str, version: int,
) -> str:
    """规范配置 → 标准名 (slice 1 命名契约; 字段非 alnum → ValueError)。"""
    try:
        return format_standard_channel_filename(
            StandardChannelName(
                band=band, arfcn=arfcn, bandwidth_mhz=bandwidth_mhz, model=model,
                scenario=scenario, mimo=mimo, polarization=polarization, version=version,
            )
        )
    except ValueError as e:
        raise StandardChannelError(str(e)) from e


def create_scd(
    db: Session,
    *,
    instrument_connection_id: UUID,
    band: str,
    arfcn: int,
    bandwidth_mhz: int,
    model: str,
    scenario: str,
    mimo: str,
    polarization: str,
    version: int = 1,
    description: Optional[str] = None,
) -> StandardChannelDefinition:
    """定义一个标准信道 (declared_only, 未关联文件)。标准名从规范配置算 (单一真值)。

    重复 (同绑定同标准名) → StandardChannelError。
    """
    standard_name = _compute_standard_name(
        band=band, arfcn=arfcn, bandwidth_mhz=bandwidth_mhz, model=model,
        scenario=scenario, mimo=mimo, polarization=polarization, version=version,
    )
    dup = (
        db.query(StandardChannelDefinition)
        .filter(
            StandardChannelDefinition.instrument_connection_id == instrument_connection_id,
            StandardChannelDefinition.standard_name == standard_name,
        )
        .first()
    )
    if dup is not None:
        raise StandardChannelError(
            f"该 F64 绑定上已存在标准信道 {standard_name!r} "
            f"(同规范配置同版本; 改版本号或复用现有)"
        )
    scd = StandardChannelDefinition(
        instrument_connection_id=instrument_connection_id,
        band=band, arfcn=arfcn, bandwidth_mhz=bandwidth_mhz, model=model,
        scenario=scenario, mimo=mimo, polarization=polarization, version=version,
        standard_name=standard_name,
        association_source="declared_only",
        description=description,
    )
    db.add(scd)
    db.commit()
    db.refresh(scd)
    return scd


def list_scds(
    db: Session, *, instrument_connection_id: Optional[UUID] = None,
) -> List[StandardChannelDefinition]:
    """列标准信道; 给 instrument_connection_id 时只列该绑定的。"""
    q = db.query(StandardChannelDefinition)
    if instrument_connection_id is not None:
        q = q.filter(
            StandardChannelDefinition.instrument_connection_id == instrument_connection_id
        )
    return q.order_by(StandardChannelDefinition.standard_name).all()


def get_scd(db: Session, scd_id: UUID) -> StandardChannelDefinition:
    scd = db.get(StandardChannelDefinition, scd_id)
    if scd is None:
        raise StandardChannelError(f"标准信道 {scd_id} 不存在")
    return scd


def delete_scd(db: Session, scd_id: UUID) -> None:
    scd = get_scd(db, scd_id)
    db.delete(scd)
    db.commit()
