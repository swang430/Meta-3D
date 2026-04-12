"""
Chamber Configuration Schemas

暗室配置的 Pydantic 模型
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum


class ChamberTypeEnum(str, Enum):
    """暗室类型枚举"""
    TYPE_A = "type_a"
    TYPE_B = "type_b"
    TYPE_C = "type_c"
    TYPE_D = "type_d"
    CUSTOM = "custom"


class ChamberPresetInfo(BaseModel):
    """暗室预设信息"""
    type: str = Field(..., description="预设类型")
    name: str = Field(..., description="预设名称")
    description: str = Field(..., description="预设描述")
    chamber_radius_m: float = Field(..., description="暗室半径 (m)")
    num_probes: int = Field(..., description="探头数量")
    has_lna: bool = Field(..., description="是否有 LNA")
    has_pa: bool = Field(..., description="是否有 PA")
    has_duplexer: bool = Field(..., description="是否有双工器")
    supports_trp: bool = Field(..., description="支持 TRP")
    supports_tis: bool = Field(..., description="支持 TIS")
    supports_mimo_ota: bool = Field(..., description="支持 MIMO OTA")


class ChamberConfigurationBase(BaseModel):
    """暗室配置基础 Schema"""
    name: str = Field(..., description="暗室名称")
    description: Optional[str] = Field(None, description="暗室描述")
    chamber_type: str = Field(default="custom", description="暗室类型")

    # 物理参数
    chamber_radius_m: float = Field(..., ge=0.5, le=20.0, description="暗室半径 (m)")
    quiet_zone_diameter_m: Optional[float] = Field(None, ge=0.1, le=5.0, description="静区直径 (m)")
    num_probes: int = Field(default=32, ge=1, le=128, description="探头数量")
    num_polarizations: int = Field(default=2, ge=1, le=2, description="极化数量")
    num_rings: int = Field(default=5, ge=1, le=10, description="探头环数")

    # LNA 配置
    has_lna: bool = Field(default=False, description="是否配置 LNA")
    lna_gain_db: Optional[float] = Field(None, ge=0, le=40, description="LNA 增益 (dB)")
    lna_noise_figure_db: Optional[float] = Field(None, ge=0, le=10, description="LNA 噪声系数 (dB)")

    # PA 配置
    has_pa: bool = Field(default=False, description="是否配置 PA")
    pa_gain_db: Optional[float] = Field(None, ge=0, le=40, description="PA 增益 (dB)")
    pa_p1db_dbm: Optional[float] = Field(None, ge=0, le=40, description="PA P1dB (dBm)")

    # 双工器配置
    has_duplexer: bool = Field(default=False, description="是否配置双工器")
    duplexer_isolation_db: Optional[float] = Field(None, ge=0, le=60, description="双工器隔离度 (dB)")
    duplexer_insertion_loss_db: Optional[float] = Field(None, ge=0, le=5, description="双工器插损 (dB)")

    # 转台配置
    has_turntable: bool = Field(default=True, description="是否配置转台")
    turntable_max_load_kg: Optional[float] = Field(None, ge=0, description="转台最大负载 (kg)")

    # 信道仿真器配置
    has_channel_emulator: bool = Field(default=True, description="是否配置信道仿真器")
    ce_bidirectional: bool = Field(default=False, description="信道仿真器双向直通")
    ce_num_ota_ports: Optional[int] = Field(None, ge=1, le=256, description="信道仿真器 OTA 端口数")
    ce_min_input_dbm: float = Field(default=-30.0, ge=-60, le=0, description="信道仿真器最低输入 (dBm)")

    # 频率范围
    freq_min_mhz: float = Field(default=400.0, ge=100, le=10000, description="最低频率 (MHz)")
    freq_max_mhz: float = Field(default=7125.0, ge=100, le=100000, description="最高频率 (MHz)")

    # 支持的测试类型
    supports_trp: bool = Field(default=True, description="支持 TRP 测试")
    supports_tis: bool = Field(default=False, description="支持 TIS 测试")
    supports_mimo_ota: bool = Field(default=False, description="支持 MIMO OTA 测试")

    # 链路预算参数
    typical_cable_loss_db: float = Field(default=5.0, ge=0, le=20, description="典型电缆损耗 (dB)")
    probe_gain_dbi: float = Field(default=8.0, ge=0, le=20, description="探头增益 (dBi)")


class ChamberConfigurationCreate(ChamberConfigurationBase):
    """创建暗室配置"""
    pass


class ChamberConfigurationUpdate(BaseModel):
    """更新暗室配置 (所有字段可选)"""
    name: Optional[str] = None
    description: Optional[str] = None
    chamber_type: Optional[str] = None
    chamber_radius_m: Optional[float] = None
    quiet_zone_diameter_m: Optional[float] = None
    num_probes: Optional[int] = None
    num_polarizations: Optional[int] = None
    num_rings: Optional[int] = None
    has_lna: Optional[bool] = None
    lna_gain_db: Optional[float] = None
    lna_noise_figure_db: Optional[float] = None
    has_pa: Optional[bool] = None
    pa_gain_db: Optional[float] = None
    pa_p1db_dbm: Optional[float] = None
    has_duplexer: Optional[bool] = None
    duplexer_isolation_db: Optional[float] = None
    duplexer_insertion_loss_db: Optional[float] = None
    has_turntable: Optional[bool] = None
    turntable_max_load_kg: Optional[float] = None
    has_channel_emulator: Optional[bool] = None
    ce_bidirectional: Optional[bool] = None
    ce_num_ota_ports: Optional[int] = None
    ce_min_input_dbm: Optional[float] = None
    freq_min_mhz: Optional[float] = None
    freq_max_mhz: Optional[float] = None
    supports_trp: Optional[bool] = None
    supports_tis: Optional[bool] = None
    supports_mimo_ota: Optional[bool] = None
    typical_cable_loss_db: Optional[float] = None
    probe_gain_dbi: Optional[float] = None
    is_active: Optional[bool] = None


class ChamberConfigurationResponse(ChamberConfigurationBase):
    """暗室配置响应"""
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: Optional[str]

    # 计算属性
    supported_tests: List[str] = Field(default_factory=list, description="支持的测试类型列表")
    max_ul_radius_m: Optional[float] = Field(None, description="上行链路支持的最大半径 (m)")

    class Config:
        from_attributes = True


class ChamberFromPresetRequest(BaseModel):
    """从预设创建暗室配置请求"""
    preset_type: ChamberTypeEnum = Field(..., description="预设类型")
    name: Optional[str] = Field(None, description="自定义名称")

    # 允许覆盖预设的核心物理参数
    chamber_radius_m: Optional[float] = Field(None, ge=0.5, le=20.0, description="暗室半径 (m)，覆盖预设值")
    quiet_zone_diameter_m: Optional[float] = Field(None, ge=0.1, le=5.0, description="静区直径 (m)，覆盖预设值")
    num_probes: Optional[int] = Field(None, ge=1, le=128, description="探头数量，覆盖预设值")

    # 允许覆盖预设的 LNA/PA 参数
    lna_gain_db: Optional[float] = Field(None, ge=0, le=60, description="LNA 增益 (dB)，覆盖预设值")
    lna_noise_figure_db: Optional[float] = Field(None, ge=0, le=10, description="LNA 噪声系数 (dB)")
    pa_gain_db: Optional[float] = Field(None, ge=0, le=60, description="PA 增益 (dB)，覆盖预设值")
    pa_p1db_dbm: Optional[float] = Field(None, ge=-10, le=50, description="PA 1dB 压缩点 (dBm)")




class ChamberPresetsResponse(BaseModel):
    """暗室预设列表响应"""
    presets: List[ChamberPresetInfo]


class ChamberListResponse(BaseModel):
    """暗室配置列表响应"""
    items: List[ChamberConfigurationResponse]
    total: int


class RequiredCalibrationsResponse(BaseModel):
    """暗室配置所需的校准项目"""
    chamber_id: UUID
    chamber_name: str
    required_calibrations: List[str] = Field(..., description="需要的校准项目列表")
    optional_calibrations: List[str] = Field(..., description="可选的校准项目列表")


class LinkBudgetResponse(BaseModel):
    """链路预算计算结果"""
    chamber_id: UUID

    # 上行链路
    ul_dut_tx_power_dbm: float
    ul_system_gain_db: float
    ul_max_fspl_db: float
    ul_max_radius_m: float
    ul_margin_db: float

    # 下行链路
    dl_ce_output_dbm: float
    dl_system_gain_db: float
    dl_eirp_dbm: float
    dl_dut_sensitivity_dbm: float
    dl_margin_db: float

    # 评估
    ul_feasible: bool
    dl_feasible: bool
    recommendations: List[str]
