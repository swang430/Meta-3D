"""Probe database models"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from app.db.database import Base


class ProbePolarization(str, enum.Enum):
    """Probe Polarization"""
    VERTICAL = "V"  # 垂直极化
    HORIZONTAL = "H"  # 水平极化


class Probe(Base):
    """
    Probe - 探头天线

    MPAC系统中的32个双极化探头天线，用于OTA测试中的信号发射和接收。
    探头分为4个环（ring），每个ring在不同的高度/角度位置。
    """
    __tablename__ = "probes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 暗室配置关联
    chamber_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chamber_configurations.id", ondelete="SET NULL"),
        nullable=True,
        comment="所属暗室配置 ID"
    )
    chamber_config = relationship("ChamberConfiguration", back_populates="probes")

    # 基本标识
    probe_number = Column(Integer, nullable=False, unique=True, comment="探头编号 (1-32)")
    name = Column(String(100), comment="探头名称，如 'Probe 1-V'")

    # 位置信息
    ring = Column(Integer, nullable=False, comment="环编号 (1-5，基于仰角: 1=顶层>60°, 2=上层30-60°, 3=中层±30°, 4=下层-60~-30°, 5=底层<-60°)")
    polarization = Column(
        String(10),
        nullable=False,
        comment="极化方向: V (垂直) | H (水平)"
    )

    # 3D空间坐标
    position = Column(JSON, nullable=False, comment="位置坐标 {azimuth, elevation, radius}")
    # position结构:
    # {
    #   "azimuth": 0-360,      # 方位角（度）
    #   "elevation": -90-90,   # 仰角（度）
    #   "radius": float        # 半径（米）
    # }

    # 状态
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    is_connected = Column(Boolean, default=False, comment="是否已连接")
    status = Column(
        String(50),
        default="idle",
        comment="当前状态: idle | active | error | calibrating"
    )

    # 硬件信息
    hardware_id = Column(String(100), comment="硬件序列号")
    channel_port = Column(Integer, comment="信道仿真器端口号")

    # 校准信息
    last_calibration_date = Column(DateTime, comment="最后校准日期")
    calibration_status = Column(
        String(50),
        default="unknown",
        comment="校准状态: valid | expired | invalid | unknown"
    )
    calibration_data = Column(JSON, comment="校准数据 {frequency, gain_offset, phase_offset}")

    # 性能参数
    frequency_range_mhz = Column(JSON, comment="频率范围 {min, max}")
    max_power_dbm = Column(Float, comment="最大功率 (dBm)")
    gain_db = Column(Float, comment="增益 (dB)")

    # 元数据
    notes = Column(Text, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), comment="创建者")


class ProbeConfiguration(Base):
    """
    Probe Configuration - 探头配置版本

    用于保存和管理不同的探头阵列配置，支持配置的导入/导出和版本管理。
    """
    __tablename__ = "probe_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 暗室配置关联
    chamber_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chamber_configurations.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的暗室配置 ID"
    )

    # 基本信息
    name = Column(String(255), nullable=False, comment="配置名称")
    description = Column(Text, comment="配置描述")
    version = Column(String(50), default="1.0", comment="版本号")

    # 配置数据
    probe_data = Column(JSON, nullable=False, comment="完整的探头配置数据数组")
    # probe_data结构: Array<ProbeResponse>

    # 元数据
    is_active = Column(Boolean, default=False, comment="是否为当前活动配置")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), nullable=False, comment="创建者")

    # 导入/导出
    imported_from = Column(String(255), comment="导入来源文件名")
    exported_at = Column(DateTime, comment="导出时间")
