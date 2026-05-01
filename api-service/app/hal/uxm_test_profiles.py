"""
UXM 综测仪标准测试配置模板

提供预定义的 SISO / 2x2 MIMO / 4x4 MIMO 测试配置，
可直接传入 base_station.set_cell_config() 使用。

每个配置模板包含:
  - NR 物理小区参数 (频段/带宽/SCS/双工)
  - 功率设置 (DL/SSB)
  - MIMO 天线端口映射 (逻辑天线 → 物理 RF 端口)
  - FRC 参数 (调制/MCS)

使用方式:

    from app.hal.uxm_test_profiles import (
        get_profile, list_profiles, UxmTestProfile,
    )

    # 方式 1: 直接使用预定义配置
    profile = get_profile("caict_n78_2x2")
    await base_station.set_cell_config(profile.to_config_dict())

    # 方式 2: 基于预定义配置修改
    profile = get_profile("caict_n78_2x2")
    profile.dl_power_dbm = -60.0  # 修改功率
    await base_station.set_cell_config(profile.to_config_dict())

    # 方式 3: 使用仪器端配置文件 (一键恢复)
    await base_station.set_cell_config({
        "state_file": r"D:\\User Files\\CAICT_N78_100M_2x2.state"
    })
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)

# 配置文件存储路径
PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "uxm_profiles"
)


# ===========================================================================
# 测试配置模板数据类
# ===========================================================================

@dataclass
class UxmTestProfile:
    """
    UXM 综测仪测试配置模板

    一个 Profile 完整描述了一次测试所需的所有 UXM 参数。
    可序列化为 JSON，也可直接转换为 set_cell_config() 所需的 dict。
    """
    # --- 标识 ---
    profile_id: str = ""              # 唯一标识
    name: str = ""                    # 友好名称
    description: str = ""             # 描述
    category: str = "general"         # "siso" / "mimo" / "calibration"

    # --- NR 小区参数 ---
    band: str = "N78"
    frequency_mhz: float = 3500.0
    bandwidth_mhz: float = 100.0
    scs_khz: int = 30
    duplex: str = "TDD"
    arfcn: Optional[int] = None

    # --- MIMO 配置 ---
    mimo_layers: int = 2
    mimo_port_preset: str = "2x2"

    # --- 功率设置 ---
    dl_power_dbm: float = -50.0
    ssb_power_dbm: float = -50.0

    # --- FRC / 调制参数 ---
    modulation: str = "256QAM"
    target_mcs: int = 28              # 3GPP OTA 最高 MCS=28 (256QAM CR≈0.93)

    # ---------------------------------------------------------------
    # 3GPP MIMO OTA MAC 吞吐量测试专用参数
    # 参考: 3GPP TR 37.977 / CTIA OTA Test Plan
    # ---------------------------------------------------------------

    # PDSCH 调度算法: "FULLBUFFER" = 持续占满所有时隙（强制要求）
    sched_algo: str = "FULLBUFFER"

    # AMC 开关: False = 固定 MCS，结果可重复（3GPP 要求关闭）
    enable_amc: bool = False

    # TDD 时隙格式: DDDSU 在 5ms 周期内最大化下行占比
    tdd_pattern: str = "DDDSU"
    tdd_period: str = "5MS"

    # HARQ 参数: 3GPP 建议最大重传 4 次，16 个并行进程
    harq_max_trans: int = 4
    harq_processes: int = 16

    # CSI-RS 端口数: 须与 MIMO 层数对齐 (2L→4ports, 4L→8ports)
    # None = 由驱动自动推断
    csi_rs_ports: Optional[int] = None

    # 统计窗口: 3GPP 建议 ≥ 5000 子帧 (= 5 秒)
    stat_count: int = 5000

    # --- 小区标识 ---
    cell_id: str = "CELL0"

    # --- 仪器端配置文件 (可选, 优先级最高) ---
    state_file: Optional[str] = None

    # --- 备注 ---
    notes: str = ""

    def to_config_dict(self) -> Dict[str, Any]:
        """
        转换为 set_cell_config() 接受的完整参数字典。

        如果指定了 state_file，只返回 state_file (一键恢复)。
        """
        if self.state_file:
            return {"state_file": self.state_file}

        config: Dict[str, Any] = {
            # 基础小区参数
            "band":            self.band,
            "frequency_mhz":   self.frequency_mhz,
            "bandwidth_mhz":   self.bandwidth_mhz,
            "scs_khz":         self.scs_khz,
            "duplex":          self.duplex,
            "cell_id":         self.cell_id,
            # MIMO
            "mimo_layers":     self.mimo_layers,
            "mimo_port_preset": self.mimo_port_preset,
            # 功率
            "dl_power_dbm":    self.dl_power_dbm,
            "ssb_power_dbm":   self.ssb_power_dbm,
            # MCS
            "pdsch_mcs":       self.target_mcs,
            # 3GPP MAC 吞吐量测试参数
            "sched_algo":      self.sched_algo,
            "enable_amc":      self.enable_amc,
            "tdd_pattern":     self.tdd_pattern,
            "tdd_period":      self.tdd_period,
            "harq_max_trans":  self.harq_max_trans,
            "harq_processes":  self.harq_processes,
            "stat_count":      self.stat_count,
        }
        if self.arfcn is not None:
            config["arfcn"] = self.arfcn
        if self.csi_rs_ports is not None:
            config["csi_rs_ports"] = self.csi_rs_ports

        return config

    def to_mac_throughput_kwargs(self) -> Dict[str, Any]:
        """
        转换为 configure_mac_throughput_test() 所需的参数字典。

        在 set_cell_config() 之后调用，单独配置 MAC 测试专用参数。
        """
        return {
            "mimo_layers":    self.mimo_layers,
            "mcs":            self.target_mcs,
            "enable_amc":     self.enable_amc,
            "tdd_pattern":    self.tdd_pattern,
            "tdd_period":     self.tdd_period,
            "harq_max_trans": self.harq_max_trans,
            "harq_processes": self.harq_processes,
            "stat_count":     self.stat_count,
        }

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    def save(self, filepath: Optional[str] = None) -> str:
        """
        保存配置模板为 JSON 文件。

        Args:
            filepath: 自定义保存路径 (默认保存到 PROFILES_DIR)

        Returns:
            保存的文件路径
        """
        if not filepath:
            os.makedirs(PROFILES_DIR, exist_ok=True)
            filepath = os.path.join(PROFILES_DIR, f"{self.profile_id}.json")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

        logger.info(f"[UXM Profile] Saved: {filepath}")
        return filepath

    @classmethod
    def from_json(cls, filepath: str) -> "UxmTestProfile":
        """从 JSON 文件加载配置模板"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)


# ===========================================================================
# 预定义测试配置库
# ===========================================================================

# ---- SISO (1x1) 基线测试 ----
PROFILE_SISO_N78 = UxmTestProfile(
    profile_id="siso_n78_100m",
    name="SISO 基线测试 (N78 100MHz)",
    description="单天线基线测试，用于暗室调试和参考天线校准",
    category="siso",
    band="N78",
    frequency_mhz=3500.0,
    bandwidth_mhz=100.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=1,
    mimo_port_preset="siso",
    dl_power_dbm=-50.0,
    ssb_power_dbm=-50.0,
    modulation="64QAM",
    target_mcs=19,
    notes="RF1 OUT→F64 CH1→探头; RF1 IN←DUT UL",
)

PROFILE_SISO_N78_LOW_POWER = UxmTestProfile(
    profile_id="siso_n78_low_power",
    name="SISO 低功率基线 (N78 100MHz)",
    description="低功率 SISO 测试，用于灵敏度校准和底噪测量",
    category="siso",
    band="N78",
    frequency_mhz=3500.0,
    bandwidth_mhz=100.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=1,
    mimo_port_preset="siso",
    dl_power_dbm=-80.0,
    ssb_power_dbm=-80.0,
    modulation="QPSK",
    target_mcs=0,
    notes="用于 RSRP/SINR 灵敏度标定",
)

# ---- 2x2 MIMO (标准 OTA 测试) ----
PROFILE_2X2_N78 = UxmTestProfile(
    profile_id="caict_n78_2x2",
    name="CAICT 暗室 2x2 MIMO (N78 100MHz)",
    description="2x2 MIMO 标准 OTA 吞吐量测试 (3GPP TR 37.977)",
    category="mimo",
    band="N78",
    frequency_mhz=3500.0,
    bandwidth_mhz=100.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=2,
    mimo_port_preset="2x2",
    dl_power_dbm=-50.0,
    ssb_power_dbm=-50.0,
    modulation="256QAM",
    target_mcs=28,          # 3GPP 要求最高 MCS
    sched_algo="FULLBUFFER",
    enable_amc=False,        # 固定 MCS，结果可重复
    tdd_pattern="DDDSU",
    tdd_period="5MS",
    harq_max_trans=4,
    harq_processes=16,
    csi_rs_ports=4,          # 2x2 MIMO → 4 CSI-RS ports
    stat_count=5000,         # ≥5s 统计窗口
    notes=(
        "RF1 OUT→F64 CH1→探头天线 1~16 (V极化)\n"
        "RF2 OUT→F64 CH2→探头天线 1~16 (H极化)\n"
        "RF6 IN←暗室独立通信天线 (UL)"
    ),
)

PROFILE_2X2_N41 = UxmTestProfile(
    profile_id="caict_n41_2x2",
    name="CAICT 暗室 2x2 MIMO (N41 100MHz)",
    description="2x2 MIMO OTA 测试 - N41 频段 (2.6 GHz)",
    category="mimo",
    band="N41",
    frequency_mhz=2600.0,
    bandwidth_mhz=100.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=2,
    mimo_port_preset="2x2",
    dl_power_dbm=-50.0,
    ssb_power_dbm=-50.0,
    modulation="256QAM",
    target_mcs=28,
    sched_algo="FULLBUFFER",
    enable_amc=False,
    tdd_pattern="DDDSU",
    tdd_period="5MS",
    harq_max_trans=4,
    harq_processes=16,
    csi_rs_ports=4,
    stat_count=5000,
    notes="适用于 N41 频段车载天线测试",
)

# ---- 4x4 MIMO (高阶测试) ----
PROFILE_4X4_N78 = UxmTestProfile(
    profile_id="caict_n78_4x4",
    name="CAICT 暗室 4x4 MIMO (N78 100MHz)",
    description="4x4 MIMO OTA 高阶测试，需要 UXM 8 端口 (满配)",
    category="mimo",
    band="N78",
    frequency_mhz=3500.0,
    bandwidth_mhz=100.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=4,
    mimo_port_preset="4x4",
    dl_power_dbm=-50.0,
    ssb_power_dbm=-50.0,
    modulation="256QAM",
    target_mcs=28,
    sched_algo="FULLBUFFER",
    enable_amc=False,
    tdd_pattern="DDDSU",
    tdd_period="5MS",
    harq_max_trans=4,
    harq_processes=16,
    csi_rs_ports=8,          # 4x4 MIMO → 8 CSI-RS ports
    stat_count=5000,
    notes=(
        "需要满配 UXM (8 端口)\n"
        "RF1~RF4 OUT→F64 CH1~CH4→探头\n"
        "RF6 IN←暗室独立通信天线 (UL)"
    ),
)

# ---- 校准专用 ----
PROFILE_CAL_POWER = UxmTestProfile(
    profile_id="cal_power_sweep",
    name="功率扫描校准 (N78)",
    description="综测仪输出功率校准 - 用于 path loss 测量",
    category="calibration",
    band="N78",
    frequency_mhz=3500.0,
    bandwidth_mhz=100.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=1,
    mimo_port_preset="siso",
    dl_power_dbm=-30.0,
    ssb_power_dbm=-30.0,
    modulation="QPSK",
    target_mcs=0,
    notes="高功率输出用于 VNA/频谱仪 path loss 校准",
)

PROFILE_CAL_2X2_ALT = UxmTestProfile(
    profile_id="cal_2x2_alt_port",
    name="2x2 MIMO 备用端口校准 (RF3+RF4)",
    description="使用 RF3+RF4 端口进行 2x2 交叉校准验证",
    category="calibration",
    band="N78",
    frequency_mhz=3500.0,
    bandwidth_mhz=100.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=2,
    mimo_port_preset="2x2_alt",
    dl_power_dbm=-50.0,
    ssb_power_dbm=-50.0,
    modulation="256QAM",
    target_mcs=24,
    notes="验证 RF3+RF4 通路与 RF1+RF2 的一致性",
)


# ===========================================================================
# 配置库管理 API
# ===========================================================================

# 所有预定义配置注册表
_PROFILE_REGISTRY: Dict[str, UxmTestProfile] = {}


def _register_builtin_profiles() -> None:
    """注册所有内置配置模板"""
    for profile in [
        PROFILE_SISO_N78,
        PROFILE_SISO_N78_LOW_POWER,
        PROFILE_2X2_N78,
        PROFILE_2X2_N41,
        PROFILE_4X4_N78,
        PROFILE_CAL_POWER,
        PROFILE_CAL_2X2_ALT,
    ]:
        _PROFILE_REGISTRY[profile.profile_id] = profile


def get_profile(profile_id: str) -> UxmTestProfile:
    """
    获取预定义测试配置。

    Args:
        profile_id: 配置ID (e.g., "caict_n78_2x2")

    Returns:
        配置模板的深拷贝 (可安全修改)

    Raises:
        KeyError: 配置不存在
    """
    if not _PROFILE_REGISTRY:
        _register_builtin_profiles()

    if profile_id not in _PROFILE_REGISTRY:
        available = list(_PROFILE_REGISTRY.keys())
        raise KeyError(
            f"Profile '{profile_id}' not found. "
            f"Available: {available}"
        )

    return deepcopy(_PROFILE_REGISTRY[profile_id])


def list_profiles(category: Optional[str] = None) -> List[Dict[str, str]]:
    """
    列出所有可用的测试配置模板。

    Args:
        category: 过滤分类 ("siso" / "mimo" / "calibration" / None=全部)

    Returns:
        配置摘要列表
    """
    if not _PROFILE_REGISTRY:
        _register_builtin_profiles()

    results = []
    for pid, profile in _PROFILE_REGISTRY.items():
        if category and profile.category != category:
            continue
        results.append({
            "profile_id": pid,
            "name": profile.name,
            "category": profile.category,
            "band": profile.band,
            "mimo": profile.mimo_port_preset,
            "description": profile.description,
        })
    return results


def register_profile(profile: UxmTestProfile) -> None:
    """注册自定义配置模板"""
    if not _PROFILE_REGISTRY:
        _register_builtin_profiles()
    _PROFILE_REGISTRY[profile.profile_id] = profile
    logger.info(f"[UXM Profile] Registered: {profile.profile_id}")


def save_all_profiles() -> List[str]:
    """将所有配置模板导出为 JSON 文件"""
    if not _PROFILE_REGISTRY:
        _register_builtin_profiles()

    saved = []
    for profile in _PROFILE_REGISTRY.values():
        path = profile.save()
        saved.append(path)
    return saved
