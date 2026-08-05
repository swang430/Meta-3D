"""Instrument database models"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.db.database import Base


class InstrumentStatus(str, enum.Enum):
    """Instrument Connection Status"""
    CONNECTED = "connected"  # 已连接
    DISCONNECTED = "disconnected"  # 未连接
    ERROR = "error"  # 错误状态
    UNKNOWN = "unknown"  # 未知状态


class InstrumentCategory(Base):
    """
    Instrument Category - 仪器类别

    定义系统中支持的仪器类别（信道仿真器、基站仿真器、转台等）。
    每个类别可以选择一个具体的型号作为当前使用的仪器。
    """
    __tablename__ = "instrument_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 类别标识
    category_key = Column(
        String(100),
        nullable=False,
        unique=True,
        comment="类别键名 (channelEmulator, baseStation, turntable, vna, etc.)"
    )
    category_name = Column(String(255), nullable=False, comment="类别中文名")
    category_name_en = Column(String(255), comment="类别英文名")

    # 当前选择的型号
    selected_model_id = Column(
        UUID(as_uuid=True),
        ForeignKey('instrument_models.id'),
        comment="当前选择的型号ID"
    )

    # 描述
    description = Column(Text, comment="类别描述")
    icon = Column(String(100), comment="图标名称")

    # 排序
    display_order = Column(Integer, default=0, comment="显示顺序")

    # 使用阶段标注（用户可在 UI 上随时覆盖）
    usage_phase = Column(
        JSON,
        default=list,
        comment='适用阶段列表: ["calibration","test"] 或 ["test"] 等'
    )

    # 驱动模式（仪器级别覆盖全局 HAL 模式）
    driver_mode = Column(
        String(10),
        default="auto",
        nullable=False,
        comment='驱动模式: "auto"(跟随全局) | "mock"(强制仿真) | "real"(强制真实)'
    )

    # 元数据
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用（当前会话中是否参与）")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    models = relationship("InstrumentModel", back_populates="category", foreign_keys="InstrumentModel.category_id")
    connection = relationship("InstrumentConnection", back_populates="category", uselist=False)


class InstrumentModel(Base):
    """
    Instrument Model - 仪器型号

    定义每个类别下支持的具体仪器型号及其技术规格。
    """
    __tablename__ = "instrument_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 所属类别
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey('instrument_categories.id'),
        nullable=False
    )

    # 型号信息
    vendor = Column(String(255), nullable=False, comment="厂商")
    model = Column(String(255), nullable=False, comment="型号")
    full_name = Column(String(500), comment="完整名称")

    # 技术规格
    capabilities = Column(JSON, nullable=False, comment="能力参数")
    # capabilities结构示例（根据不同类别有不同字段）:
    # {
    #   "channels": 8,                    # 信道数
    #   "bandwidth_mhz": 200,             # 带宽
    #   "frequency_range_ghz": [0.4, 6],  # 频率范围
    #   "interfaces": ["LAN", "USB"],     # 接口类型
    #   "max_power_dbm": 30,              # 最大功率
    #   "accuracy": "±0.1dB",             # 精度
    #   ...
    # }

    # 文档和链接
    datasheet_url = Column(String(500), comment="数据手册链接")
    manual_url = Column(String(500), comment="用户手册链接")

    # 排序
    display_order = Column(Integer, default=0, comment="显示顺序")

    # 元数据
    is_available = Column(Boolean, default=True, comment="是否可用")
    notes = Column(Text, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 关系
    category = relationship("InstrumentCategory", back_populates="models", foreign_keys=[category_id])


class InstrumentConnection(Base):
    """
    Instrument Connection - 仪器连接配置

    记录每个仪器类别的连接配置和状态。
    """
    __tablename__ = "instrument_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 所属类别
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey('instrument_categories.id'),
        nullable=False,
        unique=True
    )

    # 连接配置
    endpoint = Column(String(500), comment="连接端点 (IP:Port, URL, etc.)")
    controller_ip = Column(String(100), comment="控制器IP地址")
    port = Column(Integer, comment="端口号")
    protocol = Column(String(50), comment="协议类型 (SCPI, REST, VISA, etc.)")

    # 认证信息
    username = Column(String(100), comment="用户名")
    password_encrypted = Column(String(500), comment="加密的密码")

    # 连接状态
    status = Column(
        String(50),
        default=InstrumentStatus.UNKNOWN,
        comment="connected | disconnected | error | unknown"
    )
    last_connected_at = Column(DateTime, comment="最后连接时间")
    last_error = Column(Text, comment="最后错误信息")

    # 配置参数
    connection_params = Column(JSON, comment="其他连接参数")
    # connection_params示例:
    # {
    #   "timeout_sec": 30,
    #   "retry_count": 3,
    #   "keep_alive": true,
    #   ...
    # }

    # 备注
    notes = Column(Text, comment="备注")

    # 元数据
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), comment="创建者")

    # 关系
    category = relationship("InstrumentCategory", back_populates="connection")


# ⚠ P1-35 已删除 `InstrumentLog` 模型（原 `instrument_logs` 表）。
#
# 它是**说谎的死类型**：类名和表名都宣称"记录仪器的重要操作和状态变更历史"，
# 而实测**库里 0 行、全仓 0 个写入方、0 个读取方**（配套的
# `InstrumentLogCreate/Response/ListResponse` 三个 schema 同样零引用，
# 一并删除）。它的存在让人以为仪器操作在库里有留存 —— 没有。
#
# 仪器操作的**真实**留存在这两处，别再往库里另起一份：
#   · `diagnostic_runs` —— 诊断序列的参数 / 成败 / **仪器原始回复** / 耗时
#   · `scpi.log` —— SCPI 往返全文（AI 训练语料的主体）
#
# **表本身还在库里**（0 行）—— drop 需要 migration，而两台现场机器是
# brownfield 库，属另一类风险。已查证无害：`alembic/` 里零命中（这张表
# 从来不是任何迁移建的），baseline 走 `create_all` 故新库不会再有它。
# 待办条目见 `docs/roadmap-first-call.md` 的 Discovered 区，
# 搜「instrument_logs 孤儿表」。
