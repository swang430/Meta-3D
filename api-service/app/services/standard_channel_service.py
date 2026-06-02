"""P2-12 slice 2: Standard Channel Definition (SCD) 服务层.

create 用 slice 1 的 format_standard_channel_filename 从规范配置算标准名 (单一真值: 名字
是配置的派生)。slice 2a 只做 定义 (create/list/get/delete); 关联 (associate + cross-check
+ synced projection 更新清单) 是 slice 2b。
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.models.standard_channel import StandardChannelDefinition
from app.services.mimo_ota.channel_naming import (
    StandardChannelName,
    format_standard_channel_filename,
)


class StandardChannelError(ValueError):
    """SCD 业务错误 (字段非法 / 重复 / 不存在 / 绑定非法), caller (API) 映射成 4xx。"""


# SCD 绑定必须是信道仿真器连接: synced projection 更新的是该 binding 的
# connection_params['available_channel_models'], 而只有 channelEmulator category 的
# connection 会被 list_channel_models / F64 流程消费 (见 app/api/instrument.py
# list_channel_models_endpoint)。挂到别的类别 = projection 永不被消费的死数据。
#
# 注意: 这里是 DB 的 category_key (camelCase "channelEmulator"), 跟 HAL driver registry
# 用的 "channel_emulator" (snake) 不是一个命名空间, 别混 (bootstrap/instruments.py _CE_KEY
# 是同一个 camelCase 取值)。
_CHANNEL_EMULATOR_CATEGORY_KEY = "channelEmulator"


def _resolve_channel_emulator_binding(
    db: Session, instrument_connection_id: UUID,
) -> InstrumentConnection:
    """resolve + 校验 binding 是存在的 channelEmulator 连接, 否则 StandardChannelError。

    Codex (#117): 不校验直接插入, 在生产 PostgreSQL 上 stale/填错的 id 会变成 commit 时
    未捕获的 IntegrityError (500 而非 4xx); 而存在但非 channelEmulator 的连接被静默接受,
    SCD 挂到一个 available_channel_models projection 根本不被 F64 流程消费的 binding 上
    (死数据)。所以先 resolve, 缺失 / 错类别都 fail-loud 成业务错误。
    """
    conn = db.get(InstrumentConnection, instrument_connection_id)
    if conn is None:
        raise StandardChannelError(
            f"F64 绑定 {instrument_connection_id} 不存在 "
            f"(instrument_connection_id 失效或填错)"
        )
    category = conn.category or db.get(InstrumentCategory, conn.category_id)
    category_key = getattr(category, "category_key", None)
    if category_key != _CHANNEL_EMULATOR_CATEGORY_KEY:
        raise StandardChannelError(
            f"绑定 {instrument_connection_id} 是 {category_key!r} 类别, 不是信道仿真器 "
            f"({_CHANNEL_EMULATOR_CATEGORY_KEY!r}); SCD 的 available_channel_models "
            f"projection 只被信道仿真器流程消费, 挂到别的类别是死数据"
        )
    return conn


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

    绑定非法 (不存在 / 非信道仿真器) → StandardChannelError。
    重复 (同绑定同标准名) → StandardChannelError。
    """
    # 先校验 binding: 最根本的前置条件 (挂到哪台 F64), 失败比字段非法 / 重复更基础。
    _resolve_channel_emulator_binding(db, instrument_connection_id)
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
