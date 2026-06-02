"""P2-12 slice 2: Standard Channel Definition (SCD) — 软件掌控的标准信道文件定义。

用户 2026-06-01 确立 (见 docs/architecture/testcase-driven-instrument-config.md §9):
**命名标准是我们软件的, 不是 F64 的**。SCD = 规范配置 (真值) + 我们掌控的标准名;
实际 .smu 用三路满足 (SCPI 生成 / 手工按标准 / 关联已有)。

Schema 选 flat columns (非单个 JSON blob), 跟 InstrumentTopologyProfile / Chamber 一致:
``SELECT ... WHERE arfcn=640000`` 便宜 + Pydantic 映射直接。

字段分两组:
- **规范配置** (真值, 进标准名): band / arfcn / bandwidth_mhz / model / scenario /
  mimo / polarization / version。
- **关联** (synced projection): instrument_connection_id (所属 F64 绑定) +
  associated_file_path (实际 .smu, CALC:FILT:FILE 加载这个; declared_only 时 NULL) +
  association_source。
"""
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.database import Base


class StandardChannelDefinition(Base):
    """一个标准信道定义 = 规范配置 + 标准名 + (可选) 关联的实际 .smu 文件。

    唯一性: (instrument_connection_id, standard_name) —— 同一标准信道在一个 F64 绑定上
    只一份; 同一规范配置可在多个 F64 绑定上各有一份 (回答"一个配置多个物理文件" =
    每绑定一个)。版本号是规范配置一部分 (重标/重生成递增), 不同 version = 不同标准名 =
    不同 SCD。
    """

    __tablename__ = "standard_channel_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ---- 规范配置 (真值, 进标准名; 字段 alnum 无下划线/连字符) ----
    band = Column(String(16), nullable=False, comment="NR 频段, e.g. N78")
    arfcn = Column(Integer, nullable=False, comment="中心 ARFCN (频率规范真值, 非 frequency_mhz)")
    bandwidth_mhz = Column(Integer, nullable=False, comment="带宽 MHz")
    model = Column(String(32), nullable=False, comment="信道模型 filename-safe, e.g. CDLC")
    scenario = Column(String(32), nullable=False, comment="场景, e.g. UMa")
    mimo = Column(String(16), nullable=False, comment="MIMO 拓扑, e.g. 4x4")
    polarization = Column(String(8), nullable=False, comment="极化 V/H/DP (MIMO OTA 核心)")
    version = Column(Integer, nullable=False, default=1, comment="版本号 (重标/重生成递增)")

    # ---- 标准名 (派生; denormalized 供查找/显示, 真值仍是上面的规范配置) ----
    standard_name = Column(
        String(255), nullable=False, index=True,
        comment="format_standard_channel_filename(规范配置) 的输出, e.g. "
        "MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu",
    )

    # ---- 关联 (synced projection 源) ----
    instrument_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("instrument_connections.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="所属 F64 绑定 (synced projection 更新它的 available_channel_models)",
    )
    associated_file_path = Column(
        String(512), nullable=True,
        comment="实际 .smu 文件 (CALC:FILT:FILE 加载); a/b=标准名, c=厂商真文件; "
        "declared_only 时 NULL",
    )
    association_source = Column(
        String(32), nullable=False, default="declared_only",
        comment="declared_only (只定义) | standard_generated (路径 a/b) | "
        "vendor_associated (路径 c 关联已有)",
    )

    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "instrument_connection_id", "standard_name",
            name="uq_scd_binding_standard_name",
        ),
    )
