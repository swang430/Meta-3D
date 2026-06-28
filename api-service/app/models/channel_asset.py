"""ChannelAsset Model — P2-16 信道资产多态化。

把四种信道源 (GCM .smu / B-1 ASC / B-2 TDL / RT 动态) 统一为单一多态实体, 对 TestCase
暴露 channel_asset_id (取代 scd_id / cdl_profile_id / asc_source_path / 裸 RT dict)。

判别键 source_type 决定 payload 形态 (判别联合体, 非大一统扁平表; payload 存"资产原始
输入", 非聚类后的合成中间表示):
- standard_3gpp: {cdl_model_name}                           标称 CDL, 瞬态合成
- custom_static: {snapshots:[{clusters:[...]}]}             手编簇 (= CustomCDLProfile 退化, 单快照)
- rt_dynamic:    {snapshots:[{rays:[MPCInput...]}], ...}     原始 MPDB 射线 (多快照, 非聚类后 CDL)
- vendor_file:   {scd_config:{...}} (+ associated_file_path)  厂商 .smu (GCM 黑盒)

设计见 docs/design/channel-asset-polymorphism-design_V0.1.md。allowed_targets 从 source_type
派生 (§3.1 路径亲和性, gcm_native 限 artifact-backed); canonical_name 确定性派生 (§3.2 命名
三族, S2 填充)。平行 CustomCDLProfile / DUTProfile / SIMProfile (实体声明 + 单一真值源)。
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.database import Base

_JSON_PG_OR_SQLITE = JSONB().with_variant(JSON(), "sqlite")


class ChannelAsset(Base):
    """多态信道资产 (四源统一; TestCase 引 channel_asset_id)。"""

    __tablename__ = "channel_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True, index=True,
                  comment="资产 human label (operator 可读, 唯一)")
    description = Column(Text)

    # 判别键: 决定 payload 形态 + allowed_targets
    source_type = Column(String(32), nullable=False, index=True,
                         comment="standard_3gpp / custom_static / rt_dynamic / vendor_file")

    # 命名 (§3.2): canonical_name 确定性派生 (vendor/standard/rt 有, custom null; S2 填充)
    canonical_name = Column(String(512), nullable=True, unique=True, index=True,
                            comment="确定性派生名 (MF_/RT_; 去重/审计/确定性引用); custom 为 null")
    derived_from = Column(String(512), nullable=True,
                          comment="provenance (custom 另存来源 / rt 快照固化出身)")

    # 路径亲和性 (§3.1): 从 source_type 派生, 判决在此集内选
    allowed_targets = Column(
        _JSON_PG_OR_SQLITE, nullable=False,
        comment="可落地路径集 (asc_baked/b2_parametric/gcm_native), 派生自 source_type")

    # 声明物理 (一致性网用, 全 nullable)
    center_frequency_hz = Column(Float, comment="中心频率 Hz")
    bandwidth_mhz = Column(Float, comment="带宽 MHz")
    is_los = Column(Boolean, comment="视距条件")
    k_factor_db = Column(Float, comment="Ricean K 因子 dB (LOS)")
    ue_velocity_mps = Column(_JSON_PG_OR_SQLITE, comment="UE 速度矢量 [x,y,z] m/s")

    # 多态主体 (按 source_type; 存资产原始输入, 非聚类后合成中间表示)
    payload = Column(_JSON_PG_OR_SQLITE, nullable=False,
                     comment="多态 payload (按 source_type, 见模块 docstring)")

    # vendor_file 专用 (S2 收口 SCD 时接 FK; S1 先 nullable 列不加约束)
    instrument_connection_id = Column(
        UUID(as_uuid=True), nullable=True,
        comment="vendor_file: SCD 的 channelEmulator 连接归属 (FK 约束 S2 加)")
    associated_file_path = Column(
        String(1024), nullable=True,
        comment="vendor_file .smu / 未来 b2 现场 .tap 关联路径")

    is_active = Column(Boolean, default=True, nullable=False, index=True,
                       comment="软停用标志; 历史执行仍有效")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100))
