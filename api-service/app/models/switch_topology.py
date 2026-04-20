"""
Switch Topology Database Model

存储 RF Switch Matrix 的安装拓扑配置。
拓扑数据绑定到 Switch 实例（不是型号、不是暗室、不是 CE），
因为 Switch 是物理上连接 CE、暗室探头和校准系统的交汇点。

核心概念：
  - Node: 拓扑中的一个设备端口 (CE端口、Slot、探头、放大器等)
  - Connection: 两个 Node 之间的物理连线 (含电缆参数和校准数据)
  - OperatingMode: 一组活跃 Connection 的集合 (MIMO OTA / SISO TRP / TIS / Passive)
"""
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
import uuid
import enum

from app.db.database import Base


class SwitchTopology(Base):
    """
    Switch Topology — RF Switch 安装拓扑

    每条记录代表一个 Switch 实例在特定暗室中的完整接线配置。
    同一个 Switch 型号在不同暗室中会有不同的 topology 记录。
    """
    __tablename__ = "switch_topologies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联的 RF Switch 仪器类别
    switch_category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("instrument_categories.id"),
        nullable=False,
        comment="关联的 rfSwitch 仪器类别 ID"
    )

    # 关联的暗室
    chamber_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chamber_configurations.id"),
        nullable=True,
        comment="关联的暗室配置 ID (可选)"
    )

    # 基本信息
    name = Column(
        String(255),
        nullable=False,
        comment="拓扑名称 (e.g. 'CAICT Beijing AMS8947 v3.0')"
    )
    description = Column(Text, comment="拓扑描述")
    version = Column(String(50), default="1.0", comment="版本号")

    # 安装信息
    site_name = Column(String(255), comment="安装地点 (e.g. 'CAICT Beijing BDA')")
    system_model = Column(String(255), comment="系统型号 (e.g. 'ETS-Lindgren AMS8947')")
    installed_date = Column(DateTime, comment="安装日期")
    installed_by = Column(String(100), comment="安装工程师")

    # ============ 核心拓扑数据 (JSONB) ============

    # 节点定义
    nodes = Column(
        JSONB,
        nullable=False,
        default=list,
        comment="""
        节点列表, 每个节点:
        {
            "id": "ce1_b1",
            "type": "ce_port|switch_slot|probe|amplifier|combiner|pad|antenna|bse_port|sa_port|termination",
            "label": "Vertex1 B1",
            "position": {"x": 50, "y": 100},
            "params": {...}
        }
        """
    )

    # 连线定义
    connections = Column(
        JSONB,
        nullable=False,
        default=list,
        comment="""
        连线列表, 每条连线:
        {
            "id": "conn_xxx",
            "source": "node_id",
            "source_pin": "out|P1|P2|...",
            "target": "node_id",
            "target_pin": "in|P1|P2|...",
            "cable_type": "Phase-matched N-N",
            "cable_loss_db": 0.5,
            "cable_length_m": 3.0,
            "calibrated_loss_db": null,
            "calibrated_phase_deg": null,
            "modes": ["mimo_ota", "siso_trp"]
        }
        """
    )

    # 操作模式定义
    operating_modes = Column(
        JSONB,
        nullable=False,
        default=list,
        comment="""
        操作模式列表:
        {
            "id": "mimo_ota",
            "name": "MIMO OTA (5G NR)",
            "description": "...",
            "active_connections": ["conn_id1", "conn_id2"],
            "required_instruments": ["channelEmulator", "baseStation"],
            "color": "#4CAF50"
        }
        """
    )

    # ============ 状态与元数据 ============

    is_active = Column(Boolean, default=True, comment="是否为当前活跃拓扑")
    is_default = Column(Boolean, default=False, comment="是否为默认拓扑")

    # 统计摘要 (自动计算, 用于列表快速展示)
    total_nodes = Column(Integer, default=0, comment="节点总数")
    total_connections = Column(Integer, default=0, comment="连线总数")
    total_probes = Column(Integer, default=0, comment="探头数量")
    total_channels = Column(Integer, default=0, comment="通道总数 (探头×极化)")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100), comment="创建者")

    def update_statistics(self):
        """根据 nodes/connections 自动更新统计摘要"""
        nodes_list = self.nodes or []
        conns_list = self.connections or []

        self.total_nodes = len(nodes_list)
        self.total_connections = len(conns_list)
        self.total_probes = sum(
            1 for n in nodes_list if n.get("type") == "probe"
        )
        # 通道数 = 连接到探头的连线数
        probe_ids = {n["id"] for n in nodes_list if n.get("type") == "probe"}
        self.total_channels = sum(
            1 for c in conns_list if c.get("target") in probe_ids
        )
