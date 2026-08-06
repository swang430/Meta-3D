"""
Chamber Configuration API Endpoints

暗室配置管理 API
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import math

from app.db.database import get_db
from app.models.probe import Probe
from app.models.switch_topology import SwitchTopology
from app.models.lab_profile import LabProfile
from app.schemas.probe import ProbesListResponse
from app.models.chamber import (
    ChamberConfiguration,
    ChamberType,
    CHAMBER_PRESETS,
    create_chamber_from_preset,
)
from app.schemas.chamber import (
    ChamberConfigurationCreate,
    ChamberConfigurationUpdate,
    ChamberConfigurationResponse,
    ChamberFromPresetRequest,
    ChamberPresetsResponse,
    ChamberPresetInfo,
    ChamberListResponse,
    RequiredCalibrationsResponse,
    LinkBudgetResponse,
)
from app.services.chamber_resolution import (
    bind_current_chamber,
    calibration_chamber_reference_counts,
    resolve_current_chamber,
)
from app.services.lab_resolution import LabResolutionError

router = APIRouter(prefix="/chambers", tags=["Chamber Configuration"])


def _to_response(
    chamber: ChamberConfiguration,
    current_chamber_id: Optional[UUID] = None,
) -> ChamberConfigurationResponse:
    """转换为响应模型"""
    data = {
        "id": chamber.id,
        "name": chamber.name,
        "description": chamber.description,
        "chamber_type": chamber.chamber_type,
        # Wire compatibility only: operational state is derived from the
        # resolved LabProfile binding, never the retained legacy DB flag.
        "is_active": chamber.id == current_chamber_id,
        "is_system_preset": chamber.is_system_preset,
        "chamber_radius_m": chamber.chamber_radius_m,
        "quiet_zone_diameter_m": chamber.quiet_zone_diameter_m,
        "num_probes": chamber.num_probes,
        "num_polarizations": chamber.num_polarizations,
        "num_rings": chamber.num_rings,
        "has_lna": chamber.has_lna,
        "lna_gain_db": chamber.lna_gain_db,
        "lna_noise_figure_db": chamber.lna_noise_figure_db,
        "has_pa": chamber.has_pa,
        "pa_gain_db": chamber.pa_gain_db,
        "pa_p1db_dbm": chamber.pa_p1db_dbm,
        "has_duplexer": chamber.has_duplexer,
        "duplexer_isolation_db": chamber.duplexer_isolation_db,
        "duplexer_insertion_loss_db": chamber.duplexer_insertion_loss_db,
        "has_turntable": chamber.has_turntable,
        "turntable_max_load_kg": chamber.turntable_max_load_kg,
        "has_channel_emulator": chamber.has_channel_emulator,
        "ce_bidirectional": chamber.ce_bidirectional,
        "ce_num_ota_ports": chamber.ce_num_ota_ports,
        "ce_min_input_dbm": chamber.ce_min_input_dbm,
        "freq_min_mhz": chamber.freq_min_mhz,
        "freq_max_mhz": chamber.freq_max_mhz,
        "supports_trp": chamber.supports_trp,
        "supports_tis": chamber.supports_tis,
        "supports_mimo_ota": chamber.supports_mimo_ota,
        "typical_cable_loss_db": chamber.typical_cable_loss_db,
        "probe_gain_dbi": chamber.probe_gain_dbi,
        "probe_distribution": chamber.probe_distribution,  # P1-10
        "created_at": chamber.created_at,
        "updated_at": chamber.updated_at,
        "created_by": chamber.created_by,
        "supported_tests": chamber.get_supported_tests(),
        "max_ul_radius_m": chamber.calculate_max_radius_for_ul(),
    }
    return ChamberConfigurationResponse(**data)


def _current_chamber_id(
    db: Session,
    lab_profile_id: Optional[UUID],
    *,
    required: bool,
) -> Optional[UUID]:
    """Resolve the current chamber and translate configuration errors to 422.

    Full-list/detail responses remain usable when no lab was selected and the
    active-lab fallback is ambiguous.  Endpoints whose meaning is explicitly
    "current" pass ``required=True`` and fail loudly instead.
    """
    try:
        return resolve_current_chamber(db, lab_profile_id).id
    except (LabResolutionError, ValueError) as exc:
        if required or lab_profile_id is not None:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return None


@router.get("/presets", response_model=ChamberPresetsResponse)
def get_chamber_presets():
    """
    获取所有暗室预设模板

    返回 Type A/B/C/D 四种预设配置的详细信息。
    """
    presets = []
    for preset_type, preset_data in CHAMBER_PRESETS.items():
        presets.append(ChamberPresetInfo(
            type=preset_type,
            name=preset_data["name"],
            description=preset_data["description"],
            chamber_radius_m=preset_data["chamber_radius_m"],
            num_probes=preset_data["num_probes"],
            has_lna=preset_data["has_lna"],
            has_pa=preset_data["has_pa"],
            has_duplexer=preset_data["has_duplexer"],
            supports_trp=preset_data["supports_trp"],
            supports_tis=preset_data["supports_tis"],
            supports_mimo_ota=preset_data["supports_mimo_ota"],
        ))
    return ChamberPresetsResponse(presets=presets)


@router.post("/from-preset", response_model=ChamberConfigurationResponse)
def create_chamber_from_preset_api(
    request: ChamberFromPresetRequest,
    db: Session = Depends(get_db)
):
    """
    从预设模板创建暗室配置

    选择 Type A/B/C/D 之一，可选指定自定义名称和覆盖核心参数。
    """
    try:
        chamber = create_chamber_from_preset(
            preset_type=request.preset_type.value,
            name=request.name,
            chamber_radius_m=request.chamber_radius_m,
            quiet_zone_diameter_m=request.quiet_zone_diameter_m,
            num_probes=request.num_probes,
            lna_gain_db=request.lna_gain_db,
            lna_noise_figure_db=request.lna_noise_figure_db,
            pa_gain_db=request.pa_gain_db,
            pa_p1db_dbm=request.pa_p1db_dbm
        )
        db.add(chamber)
        db.commit()
        db.refresh(chamber)
        return _to_response(chamber)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.post("", response_model=ChamberConfigurationResponse)
def create_chamber(
    chamber_data: ChamberConfigurationCreate,
    db: Session = Depends(get_db)
):
    """
    创建自定义暗室配置
    """
    chamber = ChamberConfiguration(**chamber_data.model_dump())
    db.add(chamber)
    db.commit()
    db.refresh(chamber)
    return _to_response(chamber)


@router.get("", response_model=ChamberListResponse)
def list_chambers(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False, description="只返回当前 LabProfile 绑定的配置"),
    lab_profile_id: Optional[UUID] = Query(None, description="LabProfile；省略时要求唯一 active lab"),
):
    """
    获取暗室配置列表
    """
    current_id = _current_chamber_id(
        db, lab_profile_id, required=active_only,
    )
    query = db.query(ChamberConfiguration)
    if active_only:
        query = query.filter(ChamberConfiguration.id == current_id)

    total = query.count()
    chambers = query.offset(skip).limit(limit).all()

    return ChamberListResponse(
        items=[_to_response(c, current_id) for c in chambers],
        total=total
    )


@router.get("/active", response_model=ChamberConfigurationResponse)
def get_active_chamber(
    db: Session = Depends(get_db),
    lab_profile_id: Optional[UUID] = Query(None, description="LabProfile；省略时要求唯一 active lab"),
):
    """
    获取当前激活的暗室配置
    """
    current_id = _current_chamber_id(db, lab_profile_id, required=True)
    chamber = db.get(ChamberConfiguration, current_id)
    return _to_response(chamber, current_id)


@router.get("/{chamber_id}", response_model=ChamberConfigurationResponse)
def get_chamber(
    chamber_id: UUID,
    db: Session = Depends(get_db),
    lab_profile_id: Optional[UUID] = Query(None),
):
    """
    获取指定暗室配置
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    return _to_response(
        chamber,
        _current_chamber_id(db, lab_profile_id, required=False),
    )


@router.put("/{chamber_id}", response_model=ChamberConfigurationResponse)
def update_chamber(
    chamber_id: UUID,
    update_data: ChamberConfigurationUpdate,
    db: Session = Depends(get_db),
    lab_profile_id: Optional[UUID] = Query(None),
):
    """
    更新暗室配置
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    if chamber.is_system_preset:
        raise HTTPException(
            status_code=409,
            detail=(
                "This chamber is a system preset and cannot be edited. "
                "POST /api/v1/chambers/{id}/duplicate to create an editable copy."
            ),
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(chamber, key, value)

    db.commit()
    db.refresh(chamber)
    return _to_response(
        chamber,
        _current_chamber_id(db, lab_profile_id, required=False),
    )


@router.post("/{chamber_id}/duplicate", response_model=ChamberConfigurationResponse, status_code=201)
def duplicate_chamber(
    chamber_id: UUID,
    db: Session = Depends(get_db),
    lab_profile_id: Optional[UUID] = Query(None),
):
    """复制一个现有暗室配置，得到一份用户可编辑的副本.

    System presets (``is_system_preset=True``) cannot be edited in place
    by design — call this endpoint to clone the preset, then modify the
    returned row freely. The clone:

    - Has a fresh ``id``
    - Has ``is_system_preset=False`` (so PUT/DELETE are allowed)
    - Has ``is_active=False`` (operator decides when to activate)
    - Carries a ``"<原名> (副本)"`` name so it sorts next to the source
    """
    source = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not source:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    # Copy every persisted column except identity/lifecycle fields.
    excluded = {
        "id", "created_at", "updated_at", "is_active", "is_system_preset",
    }
    payload = {
        col.name: getattr(source, col.name)
        for col in ChamberConfiguration.__table__.columns
        if col.name not in excluded
    }
    payload["name"] = f"{source.name} (副本)"
    payload["is_system_preset"] = False
    payload["is_active"] = False

    clone = ChamberConfiguration(**payload)
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return _to_response(
        clone,
        _current_chamber_id(db, lab_profile_id, required=False),
    )


@router.post("/{chamber_id}/activate", response_model=ChamberConfigurationResponse)
def activate_chamber(
    chamber_id: UUID,
    db: Session = Depends(get_db),
    lab_profile_id: Optional[UUID] = Query(None, description="要重新绑定的 LabProfile"),
):
    """
    将指定暗室绑定为所选 LabProfile 的当前暗室。
    """
    try:
        _lab, chamber = bind_current_chamber(db, chamber_id, lab_profile_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (LabResolutionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(chamber)
    return _to_response(chamber, chamber.id)


@router.delete("/{chamber_id}")
def delete_chamber(chamber_id: UUID, db: Session = Depends(get_db)):
    """删除暗室配置 (连同其探头 + RF 拓扑一起删, 单事务)。

    守门:
    - 系统预设 → 409 (不可删)
    - 被 lab profile 引用 → 409 (先改指向/删除该 lab, 避免 orphan 掉 lab 的暗室关联)

    依赖清理 (避免 orphan / FK 报错):
    - switch_topologies.chamber_id 是 RESTRICT 外键 → 必须先删该暗室的拓扑, 否则 500
    - probes.chamber_config_id 是 SET NULL → 直接删暗室会把探头 orphan 成 NULL, 故显式删除
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    if chamber.is_system_preset:
        raise HTTPException(
            status_code=409,
            detail="系统预设暗室不可删除（如不想看到，请在界面隐藏，而非删除该行）。",
        )

    # 被 lab profile 引用 → 拦截 (否则 SET NULL 会断掉 lab 的暗室关联)
    labs = db.query(LabProfile).filter(LabProfile.chamber_config_id == chamber_id).all()
    if labs:
        names = "、".join(lp.name for lp in labs)
        raise HTTPException(
            status_code=409,
            detail=(
                f"暗室被 {len(labs)} 个 Lab Profile 引用（{names}），"
                "请先把它们改指向其它暗室或删除这些 Lab 后再删暗室。"
            ),
        )

    calibration_refs = calibration_chamber_reference_counts(db, chamber_id)
    if calibration_refs:
        summary = "、".join(
            f"{table}={count}" for table, count in sorted(calibration_refs.items())
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"暗室已被校准历史引用（{summary}），"
                "为保留测量追溯性不允许删除。"
            ),
        )

    # 清理依赖后删暗室 (单事务)
    deleted_topos = db.query(SwitchTopology).filter(
        SwitchTopology.chamber_id == chamber_id
    ).delete(synchronize_session=False)
    deleted_probes = db.query(Probe).filter(
        Probe.chamber_config_id == chamber_id
    ).delete(synchronize_session=False)
    db.delete(chamber)
    db.commit()
    return {
        "message": "Chamber configuration deleted",
        "deleted_probes": deleted_probes,
        "deleted_topologies": deleted_topos,
    }


@router.get("/{chamber_id}/required-calibrations", response_model=RequiredCalibrationsResponse)
def get_required_calibrations(chamber_id: UUID, db: Session = Depends(get_db)):
    """
    获取暗室配置所需的校准项目

    根据暗室硬件配置自动推断需要执行的校准项目。
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    required = []
    optional = []

    # 基础校准 (所有配置都需要)
    required.append("probe_path_loss")  # 探头路损校准
    required.append("quiet_zone_uniformity")  # 静区均匀性

    # 上行链路校准 (如果有 LNA)
    if chamber.has_lna:
        required.append("ul_chain_gain")  # 上行链路增益 (含 LNA)
    else:
        optional.append("ul_chain_gain")

    # 下行链路校准 (如果有 PA)
    if chamber.has_pa:
        required.append("dl_chain_gain")  # 下行链路增益 (含 PA)
    else:
        optional.append("dl_chain_gain")

    # 双工器隔离度 (如果有双工器)
    if chamber.has_duplexer:
        required.append("duplexer_isolation")
    else:
        optional.append("duplexer_isolation")

    # 信道仿真器直通校准 (如果有信道仿真器)
    if chamber.has_channel_emulator:
        required.append("ce_bypass_calibration")
        if chamber.ce_bidirectional:
            required.append("ce_bidirectional_calibration")

    # 探头互耦 (MIMO OTA 需要)
    if chamber.supports_mimo_ota:
        required.append("probe_mutual_coupling")
    else:
        optional.append("probe_mutual_coupling")

    return RequiredCalibrationsResponse(
        chamber_id=chamber.id,
        chamber_name=chamber.name,
        required_calibrations=required,
        optional_calibrations=optional
    )


@router.get("/{chamber_id}/link-budget", response_model=LinkBudgetResponse)
def calculate_link_budget(
    chamber_id: UUID,
    db: Session = Depends(get_db),
    frequency_mhz: float = Query(3500.0, description="计算频率 (MHz)"),
    dut_tx_power_dbm: float = Query(20.0, description="DUT 发射功率 (dBm)"),
    dut_sensitivity_dbm: float = Query(-100.0, description="DUT 接收灵敏度 (dBm)"),
    ce_output_dbm: float = Query(-10.0, description="信道仿真器输出功率 (dBm)")
):
    """
    计算链路预算

    验证当前暗室配置是否满足链路预算要求。
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    # FSPL 计算: FSPL = 20*log10(d) + 20*log10(f_MHz) - 27.55
    fspl_at_radius = (
        20 * math.log10(chamber.chamber_radius_m) +
        20 * math.log10(frequency_mhz) - 27.55
    )

    # === 上行链路计算 ===
    ul_system_gain = chamber.probe_gain_dbi - chamber.typical_cable_loss_db
    if chamber.has_lna and chamber.lna_gain_db:
        ul_system_gain += chamber.lna_gain_db
    if chamber.has_duplexer and chamber.duplexer_insertion_loss_db:
        ul_system_gain -= chamber.duplexer_insertion_loss_db

    ul_ce_input = dut_tx_power_dbm - fspl_at_radius + ul_system_gain
    ul_margin = ul_ce_input - chamber.ce_min_input_dbm
    ul_max_fspl = dut_tx_power_dbm + ul_system_gain - chamber.ce_min_input_dbm
    ul_max_radius = 10 ** ((ul_max_fspl - 20 * math.log10(frequency_mhz) + 27.55) / 20)

    # === 下行链路计算 ===
    dl_system_gain = chamber.probe_gain_dbi - chamber.typical_cable_loss_db
    if chamber.has_pa and chamber.pa_gain_db:
        dl_system_gain += chamber.pa_gain_db
    if chamber.has_duplexer and chamber.duplexer_insertion_loss_db:
        dl_system_gain -= chamber.duplexer_insertion_loss_db

    dl_eirp = ce_output_dbm + dl_system_gain
    dl_power_at_dut = dl_eirp - fspl_at_radius
    dl_margin = dl_power_at_dut - dut_sensitivity_dbm

    # 建议
    recommendations = []
    if ul_margin < 10:
        recommendations.append(f"上行链路余量不足 ({ul_margin:.1f} dB)，建议增加 LNA 增益或减小暗室半径")
    if dl_margin < 10:
        recommendations.append(f"下行链路余量不足 ({dl_margin:.1f} dB)，建议增加 PA 增益")
    if chamber.chamber_radius_m > ul_max_radius:
        recommendations.append(f"当前暗室半径 ({chamber.chamber_radius_m:.1f}m) 超过上行最大支持半径 ({ul_max_radius:.1f}m)")

    return LinkBudgetResponse(
        chamber_id=chamber.id,
        ul_dut_tx_power_dbm=dut_tx_power_dbm,
        ul_system_gain_db=ul_system_gain,
        ul_max_fspl_db=ul_max_fspl,
        ul_max_radius_m=ul_max_radius,
        ul_margin_db=ul_margin,
        dl_ce_output_dbm=ce_output_dbm,
        dl_system_gain_db=dl_system_gain,
        dl_eirp_dbm=dl_eirp,
        dl_dut_sensitivity_dbm=dut_sensitivity_dbm,
        dl_margin_db=dl_margin,
        ul_feasible=ul_margin >= 0,
        dl_feasible=dl_margin >= 0,
        recommendations=recommendations
    )


@router.get("/{chamber_id}/probes", response_model=ProbesListResponse)
def get_chamber_probes(
    chamber_id: UUID,
    db: Session = Depends(get_db)
):
    """
    获取指定暗室配置关联的所有探头

    返回属于该暗室配置的探头列表。
    """
    # 验证暗室配置存在
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()
    if not chamber:
        raise HTTPException(status_code=404, detail="Chamber configuration not found")

    probes = db.query(Probe).filter(
        Probe.chamber_config_id == chamber_id
    ).order_by(Probe.probe_number).all()

    return ProbesListResponse(total=len(probes), probes=probes)
