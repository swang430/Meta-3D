"""P2-16 S2: ChannelAsset 前置解析层 — channel_asset_id → engine_mode + 现有信道字段。

**方案 A 最小侵入**: 只在 `config.channel_asset_id` 显式给时介入; 旧 cdl_profile_id/scd_id
走现状 (一行不改下游 engine dispatch / strategy)。`source_type → engine_mode` 是**静态查表**
(S2: 一对一映射, 非智能判决 —— §6 判决路由 / ACP 装配 / F4/F5 接线全是 S3)。

解析结果翻译成现有 config 字段 (cdl_model_name / scd_id) + cdl_model_data clusters, 让
measure 下游 if/elif engine dispatch 和各 strategy **原封不动**跑。vendor_file 靠"复用 id"
(asset.id == 旧 scd_id, 旧 SCD 表保留) 透传 scd_id 走老 resolve_emulation_for_measure。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.channel_asset_service import (
    ChannelAssetNotFound,
    _has_verified_smu_project_truth,
    get_channel_asset,
    normalize_vendor_scd_config,
    vendor_scd_frequency_identity,
)
from app.hal.nr_arfcn import FrequencyIdentity
from app.services.channel_generation.base_generator import EngineMode

# source_type → engine_mode 静态查表 (一对一; 非 §6 判决, 那是 S3)
_SOURCE_TO_ENGINE = {
    "standard_3gpp": EngineMode.ASC_SYNTHESIS.value,   # → mimo_first_asc
    "custom_static": EngineMode.ASC_SYNTHESIS.value,   # → mimo_first_asc
    "vendor_file": EngineMode.GCM_NATIVE.value,        # → keysight_gcm
    "rt_dynamic": EngineMode.B2_PARAMETRIC_TDL.value,  # → b2 (现恒 fail-loud=现场半)
}


def engine_mode_for_channel_asset_source_type(source_type: str) -> str:
    """Return the executable engine selected by one frozen asset source type."""

    try:
        return _SOURCE_TO_ENGINE[source_type]
    except KeyError as exc:
        raise ChannelAssetResolveError(
            f"未知 source_type: {source_type!r}"
        ) from exc


def engine_mode_for_channel_asset(asset: Any) -> str:
    """Return the currently executable engine selected by an asset source.

    Commissioning uses the same lookup before persisting a session so the
    operator's requested engine cannot be silently replaced later in measure.
    """
    return engine_mode_for_channel_asset_source_type(asset.source_type)


@dataclass(frozen=True)
class ResolvedChannelAsset:
    """解析结果: engine_mode 覆盖 + 翻译到现有 config/cdl_model_data 字段。"""
    engine_mode: str
    asset: Any
    cdl_model_name: Optional[str] = None      # standard_3gpp/vendor_file → config.cdl_model_name
    emulation_file: Optional[str] = None      # vendor_file → config.emulation_file (不依赖 SCD twin)
    clusters_payload: Optional[List[dict]] = None  # custom_static → cdl_model_data["clusters"]
    rt_rays_payload: Optional[List[dict]] = None  # rt_dynamic → cdl_model_data["rt_rays"] (单快照)
    scd_freq_identity: Any = None  # vendor_file/rt_dynamic 声明频率 → 频率一致性网 (Codex #174 复查 P2)
    ue_velocity_mps: Any = None  # rt_dynamic 顶层速度 → B2 sim_rules 多普勒上下文 (Codex 9d4e758 P2)
    scenario: Optional[str] = None  # vendor_file scd_config 的显式场景真值


class ChannelAssetResolveError(ValueError):
    """解析失败 (资产不存在 / source_type 未知); caller 映射 FAILED。"""


def resolve_channel_asset(db: Session, config: Any) -> Optional[ResolvedChannelAsset]:
    """方案 A: 仅 config.channel_asset_id 显式给时解析; 否则 None (走旧字段路, 下游不变)。"""
    aid = getattr(config, "channel_asset_id", None)
    if not aid:
        return None
    try:
        asset = get_channel_asset(db, UUID(str(aid)))
    except (ChannelAssetNotFound, ValueError) as e:
        raise ChannelAssetResolveError(f"channel_asset_id={aid} 无效/不存在: {e}")
    if asset.is_active is not True:
        raise ChannelAssetResolveError(
            f"channel_asset_id={aid} 已退役，不能用于新的 MEASURE 执行"
        )

    st = asset.source_type
    engine = engine_mode_for_channel_asset(asset)

    if st == "custom_static":
        snapshots = (asset.payload or {}).get("snapshots") or [{}]
        clusters = snapshots[0].get("clusters") if isinstance(snapshots[0], dict) else None
        return ResolvedChannelAsset(engine_mode=engine, asset=asset, clusters_payload=clusters)
    if st == "standard_3gpp":
        # 顶层声明频率 → 频率一致性网 (Codex 0ea6cca P2: 否则标准资产存一个 band 被别频率
        # TestCase 引用不报错; 对称 rt/vendor 透传 scd_freq_identity)。
        freq_id = None
        if asset.center_frequency_hz is not None and asset.bandwidth_mhz is not None:
            freq_id = FrequencyIdentity.from_center_freq_mhz(
                asset.center_frequency_hz / 1e6, asset.bandwidth_mhz)
        return ResolvedChannelAsset(
            engine_mode=engine, asset=asset,
            cdl_model_name=(asset.payload or {}).get("cdl_model_name"),
            scd_freq_identity=freq_id)
    if st == "vendor_file":
        # vendor_file 不依赖 SCD twin (Codex #174 P2: 新建的 vendor_file 经 ChannelAsset API
        # 没有同 id 的 SCD 行, 不能透传 scd_id 走查 SCD 表的老路): 直接从 ChannelAsset 提供
        # .smu (associated_file_path)。declared_only (None) → GCM 分支 emulation_file_gate
        # strict fail-loud (没指定 .smu 不能真跑 GCM), 与现状 (裸 emulation_file 缺失) 一致。
        raw_scd = (asset.payload or {}).get("scd_config") or {}
        try:
            # Read-time compatibility is deliberately narrow: only complete
            # pre-P1-73 NR payloads may acquire the missing RAT/kind labels.
            scd = normalize_vendor_scd_config(raw_scd, allow_legacy_nr=True)
            freq_id = vendor_scd_frequency_identity(
                raw_scd, allow_legacy_nr=True
            )
        except ValueError as exc:
            raise ChannelAssetResolveError(
                f"vendor_file scd_config 频率身份非法: {exc}"
            ) from exc
        # 文件名 vs scd_config.arfcn 交叉校验 (Codex a0ef389: resolver 直接返回 associated_file_path
        # 绕过老 SCD 关联路的 check_channel_filename_freq; 声明 ARFCN 跟 TestCase 一致但 .smu 实为别
        # ARFCN 的 MF_ 标准名文件 → F64 fallback 不解析 MF 文件名, 错 .smu 静默加载且频率门不报)。
        # MF_ 可解析名不一致 → fail-loud; 厂商名 (loose) / 解析不出 → 放行留给声明频率门
        # (厂商文件名频率是标称会说谎, 2026-07-03 实证; 真值 = scd_config 声明的工程实测)。
        afp = asset.associated_file_path
        if (afp and scd["radio_technology"] == "nr5g"
                and not _has_verified_smu_project_truth(
                    asset.payload, afp, asset.center_frequency_hz,
                )):
            from app.services.standard_channel_service import check_channel_filename_freq
            chk = check_channel_filename_freq(afp, int(scd["arfcn"]))
            if chk.must_fail:
                raise ChannelAssetResolveError(chk.failure_reason())
        return ResolvedChannelAsset(
            engine_mode=engine, asset=asset,
            cdl_model_name=scd.get("model"),
            emulation_file=asset.associated_file_path,
            scd_freq_identity=freq_id,
            scenario=scd.get("scenario"),
        )
    # rt_dynamic: 透传单快照 rays 到 B2 (对称 custom clusters 透传; 多快照轨迹/ACP 装配是 S3)。
    # Codex #174 复查 P2: 否则 rt_dynamic 资产路由到 B2 但 rays 没接, B2 误用 legacy rt_rays。
    snapshots = (asset.payload or {}).get("snapshots") or []
    # 多快照 = 轨迹 RT; 执行装配 (时空跟踪 → 逐快照 B2/B1) 是 P2-16 S5, resolver 当前只透传单
    # 快照 rays。多快照若静默取 snapshots[0] → 用户 (S4-4 编辑器) 建轨迹信道却只按首快照测量
    # (Codex #184 P1)。fail-loud 而非静默截断, 待 S5 轨迹执行路接通 (GUI 编辑器同步 Alert 警示)。
    if len(snapshots) > 1:
        raise ChannelAssetResolveError(
            f"rt_dynamic 资产 '{asset.name}' 含 {len(snapshots)} 个快照 (多快照轨迹); 多快照"
            f"轨迹执行 (时空跟踪装配) 尚未接线 (P2-16 S5)。当前仅支持单快照 rt_dynamic 执行 — "
            f"请用单快照资产, 或等 S5 轨迹执行路接通。")
    rays = snapshots[0].get("rays") if snapshots and isinstance(snapshots[0], dict) else None
    # 顶层声明 center_frequency_hz/bandwidth_mhz → 频率一致性网 (Codex #174 复查 P2: 复用为别
    # band 抓的 RT 射线会在错误载频聚类, 频率门无资产源可比对; 对称 vendor scd_freq_identity)。
    freq_id = None
    if asset.center_frequency_hz is not None and asset.bandwidth_mhz is not None:
        freq_id = FrequencyIdentity.from_center_freq_mhz(
            asset.center_frequency_hz / 1e6, asset.bandwidth_mhz)
    return ResolvedChannelAsset(
        engine_mode=engine, asset=asset, rt_rays_payload=rays, scd_freq_identity=freq_id,
        ue_velocity_mps=asset.ue_velocity_mps)
