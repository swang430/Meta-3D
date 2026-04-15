"""
Chamber Configuration Models

暗室配置模型 - 支持不同类型的暗室配置（小型/大型、单向/双向）
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.database import Base


class ChamberType(str, enum.Enum):
    """暗室类型预设"""
    TYPE_A = "type_a"  # 小型无源 - 手机/模块 TRP 测试
    TYPE_B = "type_b"  # 小型 MIMO - 手机 MIMO OTA 测试
    TYPE_C = "type_c"  # 大型单向 - 车载 MIMO OTA 测试
    TYPE_D = "type_d"  # 大型双向 - 车载全功能测试
    CUSTOM = "custom"  # 自定义配置


class ChamberConfiguration(Base):
    """
    暗室配置模型

    存储暗室的物理参数和硬件配置，用于校准流程和测量补偿。
    支持预设模板（Type A/B/C/D）和自定义配置。
    """
    __tablename__ = "chamber_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基本信息
    name = Column(String(255), nullable=False, comment="暗室名称")
    description = Column(Text, comment="暗室描述")
    chamber_type = Column(
        String(50),
        default=ChamberType.CUSTOM.value,
        comment="暗室类型: type_a, type_b, type_c, type_d, custom"
    )
    is_active = Column(Boolean, default=True, comment="是否为当前激活配置")

    # === 物理参数 ===
    chamber_radius_m = Column(Float, nullable=False, comment="暗室半径 (m)")
    quiet_zone_diameter_m = Column(Float, comment="静区直径 (m)")
    num_probes = Column(Integer, nullable=False, default=32, comment="探头数量")
    num_polarizations = Column(Integer, default=2, comment="极化数量: 1=单极化, 2=双极化")
    num_rings = Column(Integer, default=5, comment="探头环数")

    # === 硬件配置 (可选组件) ===
    has_lna = Column(Boolean, default=False, comment="是否配置 LNA (低噪放)")
    lna_gain_db = Column(Float, comment="LNA 增益 (dB)")
    lna_noise_figure_db = Column(Float, comment="LNA 噪声系数 (dB)")

    has_pa = Column(Boolean, default=False, comment="是否配置 PA (功率放大器)")
    pa_gain_db = Column(Float, comment="PA 增益 (dB)")
    pa_p1db_dbm = Column(Float, comment="PA 1dB 压缩点 (dBm)")

    has_duplexer = Column(Boolean, default=False, comment="是否配置双工器")
    duplexer_isolation_db = Column(Float, comment="双工器隔离度 (dB)")
    duplexer_insertion_loss_db = Column(Float, comment="双工器插损 (dB)")

    has_turntable = Column(Boolean, default=True, comment="是否配置转台")
    turntable_max_load_kg = Column(Float, comment="转台最大负载 (kg)")

    # === 信道仿真器配置 ===
    has_channel_emulator = Column(Boolean, default=True, comment="是否配置信道仿真器")
    ce_bidirectional = Column(Boolean, default=False, comment="信道仿真器是否支持双向直通")
    ce_num_ota_ports = Column(Integer, comment="信道仿真器 OTA 端口数")
    ce_min_input_dbm = Column(Float, default=-30.0, comment="信道仿真器最低输入电平 (dBm)")

    # === 频率范围 ===
    freq_min_mhz = Column(Float, default=400.0, comment="最低工作频率 (MHz)")
    freq_max_mhz = Column(Float, default=7125.0, comment="最高工作频率 (MHz)")

    # === 支持的测试类型 (自动推断或手动指定) ===
    supports_trp = Column(Boolean, default=True, comment="支持 TRP 测试")
    supports_tis = Column(Boolean, default=False, comment="支持 TIS 测试")
    supports_mimo_ota = Column(Boolean, default=False, comment="支持 MIMO OTA 测试")

    # === 链路预算参数 ===
    typical_cable_loss_db = Column(Float, default=5.0, comment="典型电缆损耗 (dB)")
    probe_gain_dbi = Column(Float, default=8.0, comment="探头增益 (dBi)")

    # === 元数据 ===
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String(100))

    # === 关联关系 ===
    probes = relationship("Probe", back_populates="chamber_config", lazy="dynamic")

    def get_supported_tests(self) -> list:
        """返回支持的测试类型列表"""
        tests = []
        if self.supports_trp:
            tests.append("TRP")
        if self.supports_tis:
            tests.append("TIS")
        if self.supports_mimo_ota:
            tests.append("MIMO_OTA")
        return tests

    def calculate_max_radius_for_ul(self, dut_tx_power_dbm: float = 20.0) -> float:
        """
        计算上行链路支持的最大暗室半径

        基于链路预算: P_CE_in = P_DUT + G_probe - FSPL - Cable_loss + G_LNA
        要求 P_CE_in >= ce_min_input_dbm
        """
        import math

        # 系统增益
        system_gain = self.probe_gain_dbi - self.typical_cable_loss_db
        if self.has_lna and self.lna_gain_db:
            system_gain += self.lna_gain_db
        if self.has_duplexer and self.duplexer_insertion_loss_db:
            system_gain -= self.duplexer_insertion_loss_db

        # 允许的最大 FSPL
        max_fspl = dut_tx_power_dbm + system_gain - self.ce_min_input_dbm

        # FSPL = 20*log10(d) + 20*log10(f_MHz) - 27.55
        # 使用 3.5 GHz 作为典型频率
        freq_mhz = 3500
        max_distance = 10 ** ((max_fspl - 20 * math.log10(freq_mhz) + 27.55) / 20)

        return max_distance


# === 预设模板常量 ===
CHAMBER_PRESETS = {
    ChamberType.TYPE_A.value: {
        "name": "小型无源暗室",
        "description": "适用于手机/模块 TRP 测试，无有源器件，暗室半径小于 2m",
        "chamber_type": ChamberType.TYPE_A.value,
        "chamber_radius_m": 1.5,
        "quiet_zone_diameter_m": 0.5,
        "num_probes": 16,
        "num_polarizations": 2,
        "num_rings": 3,
        "has_lna": False,
        "has_pa": False,
        "has_duplexer": False,
        "has_turntable": True,
        "has_channel_emulator": False,
        "ce_bidirectional": False,
        "freq_min_mhz": 700.0,
        "freq_max_mhz": 6000.0,
        "supports_trp": True,
        "supports_tis": False,
        "supports_mimo_ota": False,
        "typical_cable_loss_db": 3.0,
        "probe_gain_dbi": 6.0,
    },
    ChamberType.TYPE_B.value: {
        "name": "小型 MIMO 暗室",
        "description": "适用于手机 MIMO OTA 测试，配置信道仿真器",
        "chamber_type": ChamberType.TYPE_B.value,
        "chamber_radius_m": 1.5,
        "quiet_zone_diameter_m": 0.5,
        "num_probes": 16,
        "num_polarizations": 2,
        "num_rings": 3,
        "has_lna": False,
        "has_pa": False,
        "has_duplexer": False,
        "has_turntable": True,
        "has_channel_emulator": True,
        "ce_bidirectional": False,
        "ce_num_ota_ports": 32,
        "ce_min_input_dbm": -30.0,
        "freq_min_mhz": 700.0,
        "freq_max_mhz": 6000.0,
        "supports_trp": True,
        "supports_tis": False,
        "supports_mimo_ota": True,
        "typical_cable_loss_db": 3.0,
        "probe_gain_dbi": 6.0,
    },
    ChamberType.TYPE_C.value: {
        "name": "大型单向暗室",
        "description": "适用于车载 MIMO OTA 测试，配置 PA 补偿下行链路损耗",
        "chamber_type": ChamberType.TYPE_C.value,
        "chamber_radius_m": 4.0,
        "quiet_zone_diameter_m": 2.0,
        "num_probes": 16,
        "num_polarizations": 2,
        "num_rings": 1,  # 指代单环 (Ring-3)
        "has_lna": False,
        "has_pa": True,
        "pa_gain_db": 20.0,
        "pa_p1db_dbm": 20.0,
        "has_duplexer": False,
        "has_turntable": True,
        "turntable_max_load_kg": 3000.0,
        "has_channel_emulator": True,
        "ce_bidirectional": False,
        "ce_num_ota_ports": 32,
        "ce_min_input_dbm": -30.0,
        "freq_min_mhz": 400.0,
        "freq_max_mhz": 7125.0,
        "supports_trp": True,
        "supports_tis": False,
        "supports_mimo_ota": True,
        "typical_cable_loss_db": 5.0,
        "probe_gain_dbi": 8.0,
    },
    ChamberType.TYPE_D.value: {
        "name": "大型双向暗室",
        "description": "车载全功能测试，支持 TRP/TIS/MIMO OTA，配置 LNA + PA + 双工器",
        "chamber_type": ChamberType.TYPE_D.value,
        "chamber_radius_m": 4.0,
        "quiet_zone_diameter_m": 2.0,
        "num_probes": 32,
        "num_polarizations": 2,
        "num_rings": 5,
        "has_lna": True,
        "lna_gain_db": 20.0,
        "lna_noise_figure_db": 2.0,
        "has_pa": True,
        "pa_gain_db": 20.0,
        "pa_p1db_dbm": 20.0,
        "has_duplexer": True,
        "duplexer_isolation_db": 25.0,
        "duplexer_insertion_loss_db": 1.0,
        "has_turntable": True,
        "turntable_max_load_kg": 3000.0,
        "has_channel_emulator": True,
        "ce_bidirectional": True,
        "ce_num_ota_ports": 64,
        "ce_min_input_dbm": -30.0,
        "freq_min_mhz": 400.0,
        "freq_max_mhz": 7125.0,
        "supports_trp": True,
        "supports_tis": True,
        "supports_mimo_ota": True,
        "typical_cable_loss_db": 5.0,
        "probe_gain_dbi": 8.0,
    },
}


def create_chamber_from_preset(
    preset_type: str, 
    name: str = None,
    chamber_radius_m: float = None,
    quiet_zone_diameter_m: float = None,
    num_probes: int = None,
    lna_gain_db: float = None,
    lna_noise_figure_db: float = None,
    pa_gain_db: float = None,
    pa_p1db_dbm: float = None
) -> ChamberConfiguration:
    """
    从预设模板创建暗室配置

    Args:
        preset_type: 预设类型 (type_a, type_b, type_c, type_d)
        name: 自定义名称，如果不提供则使用预设名称
        chamber_radius_m: 暗室半径覆盖值 (m)
        quiet_zone_diameter_m: 静区直径覆盖值 (m)
        num_probes: 探头数量覆盖值
        lna_gain_db: LNA 增益覆盖值 (dB)
        lna_noise_figure_db: LNA 噪声系数覆盖值 (dB)
        pa_gain_db: PA 增益覆盖值 (dB)
        pa_p1db_dbm: PA 1dB 压缩点覆盖值 (dBm)

    Returns:
        ChamberConfiguration 实例
    """
    if preset_type not in CHAMBER_PRESETS:
        raise ValueError(f"Unknown preset type: {preset_type}")

    preset = CHAMBER_PRESETS[preset_type].copy()
    if name:
        preset["name"] = name

    chamber = ChamberConfiguration(**preset)
    
    # 应用核心物理参数覆盖
    if chamber_radius_m is not None:
        chamber.chamber_radius_m = chamber_radius_m
    if quiet_zone_diameter_m is not None:
        chamber.quiet_zone_diameter_m = quiet_zone_diameter_m
    if num_probes is not None:
        chamber.num_probes = num_probes

    # 应用 LNA/PA 参数覆盖
    if lna_gain_db is not None:
        chamber.lna_gain_db = lna_gain_db
    if lna_noise_figure_db is not None:
        chamber.lna_noise_figure_db = lna_noise_figure_db
    if pa_gain_db is not None:
        chamber.pa_gain_db = pa_gain_db
    if pa_p1db_dbm is not None:
        chamber.pa_p1db_dbm = pa_p1db_dbm
    
    return chamber

