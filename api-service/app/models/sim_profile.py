"""SIM Profile Model — SIM/eSIM 身份 + 鉴权声明 (P2-13 阶段 1)。

SIMProfile 之于"卡", 平行 DUTProfile 之于"设备能力" / LabProfile 之于 chamber:
operator 规划期登记测试卡的身份 (IMSI/PLMN) + 鉴权凭据 (Ki/OPc/算法), 让系统在 attach 前
就能校验 SIM↔UXM 一致性, 并在 attach 后拿实测认证 IMSI 跟声明核对 (防对错卡)。

为什么独立于 DUTProfile (不内嵌): DUT↔SIM 是**多对多** —— 一张测试卡在多个 DUT 间复用 /
一个 DUT 换多张卡测不同运营商配置。内嵌会逼每个 DUT 重抄卡的 Ki→stale。SIM 更像 LabProfile
那样的实验室基建 (卡池库存)。TestCase 引用 sim_profile_id (跟 lab/dut 并列, 单一真值源驱动)。

⚠️ Ki/OPc 是凭据: API 响应/日志脱敏 (只显后 4 位), 仅 test_sim/operator_test 卡存;
card_kind=commercial 不存 Ki (商用卡 Ki 运营商保密不可得, 标"不可鉴权用测试卡")。
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.database import Base

_JSON_PG_OR_SQLITE = JSONB().with_variant(JSON(), "sqlite")


class SIMProfile(Base):
    """SIM/eSIM 身份 + 鉴权声明 (规划期, 平行 DUTProfile)。"""

    __tablename__ = "sim_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True, index=True,
                  comment='卡标识, e.g. "TestSIM-OperatorX-46000"')
    description = Column(Text)

    # —— 身份 ——
    imsi = Column(String(20), comment="IMSI (15 位, MCC+MNC+MSIN)")
    iccid = Column(String(25), comment="卡序列号 ICCID (选填)")
    mcc = Column(String(3), comment="移动国家码 (3 位); 校验=IMSI 前缀")
    mnc = Column(String(3), comment="移动网络码 (2-3 位); 校验=IMSI 前缀")

    # —— 鉴权凭据 (脱敏; commercial 不存 ki) ——
    ki = Column(String(64), comment="订户密钥 Ki (32 hex / 128-bit); 凭据, 脱敏")
    opc = Column(String(64), comment="运营商变体 OPc (32 hex); 凭据, 脱敏")
    auth_algorithm = Column(String(20), comment='鉴权算法: "MILENAGE" / "TUAK" / "XOR"')

    # —— 类型 ——
    card_kind = Column(String(20), comment='"test_sim" / "operator_test" / "commercial" (当鉴权可行性门)')
    sim_form = Column(String(10), comment='"usim" (物理卡) / "esim" (eSIM profile)')

    # —— eSIM (一个 profile = 一行; 同 eid = 同芯片多 profile) ——
    eid = Column(String(40), comment="eUICC 芯片标识 EID (eSIM, 选填)")
    esim_profile_id = Column(String(64), comment="eSIM profile 标识 / ICCID (选填)")

    extra_metadata = Column(
        _JSON_PG_OR_SQLITE,
        comment="自由字段: TUAK 冷门参数 (TOP/长度)、SQN 方案备注等",
    )

    is_active = Column(Boolean, default=True, nullable=False, index=True,
                       comment="软停用标志; 历史执行仍有效")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100))
