"""P2-12 slice 2: Standard Channel Definition (SCD) 服务层.

create 用 slice 1 的 format_standard_channel_filename 从规范配置算标准名 (单一真值: 名字
是配置的派生)。slice 2a 只做 定义 (create/list/get/delete); 关联 (associate + cross-check
+ synced projection 更新清单) 是 slice 2b。
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.hal.nr_arfcn import nr_arfcn_to_freq_mhz
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.models.standard_channel import StandardChannelDefinition
from app.services.mimo_ota.channel_naming import (
    StandardChannelName,
    check_channel_filename_freq,
    format_standard_channel_filename,
)


class StandardChannelError(ValueError):
    """SCD 业务错误 (字段非法 / 重复 / 绑定非法 / 关联不符), caller (API) 映射成 4xx。"""


class StandardChannelNotFound(StandardChannelError):
    """SCD 按 id 找不到。是 StandardChannelError 的子类 (既有 except 仍捕获), 但让 caller
    能把"资源不存在"映射成 404 而非 400 (associate 端点区分 scd_id 失效 vs 关联非法)。"""


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
        raise StandardChannelNotFound(f"标准信道 {scd_id} 不存在")
    return scd


def delete_scd(db: Session, scd_id: UUID) -> None:
    scd = get_scd(db, scd_id)
    binding_id = scd.instrument_connection_id
    had_file = scd.associated_file_path is not None
    db.delete(scd)
    db.flush()  # 让后续 projection 重建 query 看不到它
    if had_file:
        # 删掉的是已关联 SCD → synced projection 同步移除它的派生条目
        _sync_projection_for_binding(db, binding_id)
    db.commit()


# ---- 关联实际 .smu + synced projection (slice 2b) ----

# 路径 a/b: 文件按我们标准名生成 (filename == standard_name);
# 路径 c: 关联已有厂商 .smu (filename = 厂商真文件, 频率元数据仍用 SCD 声明充实)。
_ASSOCIATION_SOURCE_STANDARD = "standard_generated"
_ASSOCIATION_SOURCE_VENDOR = "vendor_associated"
_VALID_ASSOCIATION_SOURCES = frozenset(
    {_ASSOCIATION_SOURCE_STANDARD, _ASSOCIATION_SOURCE_VENDOR}
)


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _scd_to_projection_entry(scd: StandardChannelDefinition) -> dict:
    """SCD (已关联) → available_channel_models 的一条派生 entry。

    频率元数据 (center_frequency_mhz) 从 SCD **声明 ARFCN** 算 = 权威, 非从厂商文件名解析
    (§8 Step 1 解析降为关联时 cross-check; 路径 c 厂商名可能无频率 token 或不可信)。
    normalize_channel_model_entries 优先用 entry 显式 center, 故下游 inventory/下拉框看到的
    是声明真值。``scd_id`` 标记此条为 SCD 派生 (sync 时按此重建; normalizer 会忽略它,
    不进 API 响应) —— 不要在持久化时 strip 掉。
    """
    center_mhz = nr_arfcn_to_freq_mhz(scd.arfcn)  # 声明 → 频率 (round-trip 无损)
    return {
        "filename": scd.associated_file_path,  # CALC:FILT:FILE 加载这个 (路径 c 是厂商真文件)
        "label": scd.standard_name,            # GUI 永远显示标准名
        "description": (
            f"SCD {scd.band} ARFCN {scd.arfcn} BW{scd.bandwidth_mhz} "
            f"{scd.model}/{scd.scenario} {scd.mimo} {scd.polarization} v{scd.version}"
        ),
        "center_frequency_mhz": center_mhz,
        "scd_id": str(scd.id),
    }


def _sync_projection_for_binding(db: Session, instrument_connection_id: UUID) -> None:
    """重建 F64 绑定的 available_channel_models = 该绑定所有"已关联文件"SCD 的派生条目
    + **保留**非 SCD 派生的存量手敲条目 (§9: 逐步收敛, 不 nuke)。

    SCD 派生条目按 ``scd_id`` 标记识别并整体重建 (天然处理新增/改关联/删除 —— 改关联时旧
    文件条目随 scd_id 一并丢弃重建, 不留 phantom)。
    """
    conn = db.get(InstrumentConnection, instrument_connection_id)
    if conn is None:
        return  # SCD 的 FK 保证存在; 防御性早返回
    params = dict(conn.connection_params or {})
    existing = params.get("available_channel_models") or []
    # 保留非 SCD 派生条目 (没有 scd_id 标记的 = 存量手敲 / 别处来源)
    preserved = [
        e for e in existing
        if not (isinstance(e, dict) and e.get("scd_id"))
    ]
    associated = (
        db.query(StandardChannelDefinition)
        .filter(
            StandardChannelDefinition.instrument_connection_id == instrument_connection_id,
            StandardChannelDefinition.associated_file_path.isnot(None),
        )
        .order_by(StandardChannelDefinition.standard_name)
        .all()
    )
    derived = [_scd_to_projection_entry(s) for s in associated]
    params["available_channel_models"] = preserved + derived
    # 整体重新赋值 dict 触发 SQLAlchemy JSON 变更检测 (in-place mutate 不会被 track)
    conn.connection_params = params


def associate_file(
    db: Session,
    scd_id: UUID,
    *,
    file_path: str,
    association_source: str = _ASSOCIATION_SOURCE_VENDOR,
) -> StandardChannelDefinition:
    """把一个实际 .smu 文件关联到 SCD, 并更新 synced projection。

    - scd 不存在 → StandardChannelNotFound。
    - file_path 空 / source 非法 → StandardChannelError。
    - cross-check: check_channel_filename_freq(file_path, scd.arfcn) 不一致 (文件名能解析出
      频率但 ≠ 声明) → StandardChannelError (fail-loud, 抓关联错文件); 解析不出 → 放行
      (SCD 声明本就是真值, 跟 Phase 1 None-skip 一致)。
    - standard_generated (路径 a/b): 文件由我们标准名生成 → basename 必须 == standard_name
      (否则是把别的文件误标成 standard; 抓 mislabel)。
    """
    scd = get_scd(db, scd_id)
    if not file_path or not isinstance(file_path, str):
        raise StandardChannelError("file_path 必须为非空字符串")
    if association_source not in _VALID_ASSOCIATION_SOURCES:
        raise StandardChannelError(
            f"association_source={association_source!r} 非法, 必须是 "
            f"{sorted(_VALID_ASSOCIATION_SOURCES)}"
        )

    check = check_channel_filename_freq(file_path, scd.arfcn)
    if not check.consistent:
        raise StandardChannelError(check.failure_reason())

    if association_source == _ASSOCIATION_SOURCE_STANDARD:
        if _basename(file_path) != scd.standard_name:
            raise StandardChannelError(
                f"association_source=standard_generated 要求文件名 == 标准名 "
                f"{scd.standard_name!r}, 实际 {_basename(file_path)!r} "
                f"(路径 a/b 文件须按标准名生成; 关联厂商已有文件用 vendor_associated)"
            )

    scd.associated_file_path = file_path
    scd.association_source = association_source
    db.flush()  # 让 projection 重建 query 看到本次关联 (不赌 session autoflush)
    _sync_projection_for_binding(db, scd.instrument_connection_id)
    db.commit()
    db.refresh(scd)
    return scd
