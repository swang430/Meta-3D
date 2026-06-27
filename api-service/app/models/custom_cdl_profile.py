"""CustomCDLProfile Model — 操作员自定义 CDL 信道 (簇级参数可编辑)。

P2-15: 补齐"软件定义信道"在 GUI 的最后一截。标称 CDL (CDL-A~E) 是 38.901 内置固定表;
本实体让 operator 编辑自定义 CDL 的簇级参数 (每簇 delay/角度/功率/AS/XPR/相位), 持久化为
可复用实体, 测试时选它 → 后端 input_mode=custom → ChannelEgine 合成反映自定义簇。

平行 DUTProfile/SIMProfile (实体声明 + 单一真值源)。簇列表存 JSONB (跟 DUTProfile
.supported_bands 先例一致, 避免 N:M 子表)。字段映射 ChannelEgine CustomCDLProfile /
CDLClusterSpec (cdl_schema.py)。
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.database import Base

_JSON_PG_OR_SQLITE = JSONB().with_variant(JSON(), "sqlite")


class CustomCDLProfile(Base):
    """操作员自定义 CDL 信道档案 (簇级参数可编辑, 喂 input_mode=custom)。"""

    __tablename__ = "custom_cdl_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True, index=True,
                  comment='自定义 CDL 标识, e.g. "UMa 改-双簇加强"')
    description = Column(Text)

    # —— CDL 顶层物理 (None = profile 未定, 测试时由 TestStep 绑) ——
    center_frequency_hz = Column(Float, comment="中心频率 Hz")
    pathloss_db = Column(Float, comment="自由空间 + 遮挡路损 dB")
    is_los = Column(Boolean, comment="视距条件")
    k_factor_db = Column(Float, comment="Ricean K 因子 dB (LOS)")
    ue_velocity_mps = Column(_JSON_PG_OR_SQLITE, comment="UE 速度矢量 [x,y,z] m/s")

    # —— 簇列表 (核心: 每簇 delay/角度/功率/AS/XPR/相位; 映射 CDLClusterSpec) ——
    clusters = Column(
        _JSON_PG_OR_SQLITE, nullable=False,
        comment="簇列表 [{delay_s, power_linear, aoa_deg, ...}], 映射 ChannelEgine CDLClusterSpec")

    is_active = Column(Boolean, default=True, nullable=False, index=True,
                       comment="软停用标志; 历史执行仍有效")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100))
