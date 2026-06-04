"""DUT Profile Model — DUT 自声明能力档案 (declared capability)。

DUTProfile 之于 DUT, 平行 LabProfile 之于 chamber: 操作员规划期填写 DUT 的声明能力
(max DL/UL layers、支持频段、最大调制、UE category、双工), 让测试在 attach 真 DUT 前就能
拿 TestCase 请求跟声明能力比 —— 请求 > 声明 (e.g. TestCase 请求 4 层但 DUT 声明 max 2)
可提前 fail, 不浪费一次真跑。

三层能力体系 (用户 2026-06-01 提出):
- 声明 (本实体, 规划期): operator 填的 DUT spec, 最早可得 (未 attach / 未上硬件即可校验)。
- 协商 (UXM query_ue_capability, attach 后): Phase 6 cell_config 一致性用, "actual/negotiated"。
- 运行时 (CSI RI, 测量中): 实时。
声明 vs 协商交叉校验 (后续 PR): 不一致 = DUT 实际行为跟 spec 声明不符, 本身是有用发现。
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.database import Base

_JSON_PG_OR_SQLITE = JSONB().with_variant(JSON(), "sqlite")


class DUTProfile(Base):
    """DUT 自声明能力档案 (规划期声明层, 平行 LabProfile)。"""

    __tablename__ = "dut_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True, index=True,
                  comment='DUT 标识, e.g. "Model-X 车载 T-Box"')
    description = Column(Text)
    manufacturer = Column(String(255), comment="DUT 厂商")
    model_name = Column(String(255), comment="DUT 型号")

    # —— 声明能力 (capability spec); None = 该项未声明, 校验时跳过 ——
    max_dl_layers = Column(Integer, comment="最大 DL MIMO 层数 (声明)")
    max_ul_layers = Column(Integer, comment="最大 UL MIMO 层数 (声明)")
    max_modulation_dl = Column(String(20), comment='最大 DL 调制, e.g. "256QAM"')
    max_modulation_ul = Column(String(20), comment='最大 UL 调制, e.g. "64QAM"')
    ue_category = Column(String(40), comment="UE category, e.g. 'NR Cat ...' / LTE Cat 20")
    duplex_mode = Column(String(10), comment='双工: "TDD" / "FDD" / "both"')
    supported_bands = Column(
        _JSON_PG_OR_SQLITE,
        comment='支持频段列表, e.g. ["N78", "N41", "N1"]',
    )

    extra_metadata = Column(
        _JSON_PG_OR_SQLITE,
        comment="自由字段: IMEI/SIM 信息、固件版本、天线配置等",
    )

    is_active = Column(Boolean, default=True, nullable=False, index=True,
                       comment="软停用标志; 历史执行仍有效")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100))
