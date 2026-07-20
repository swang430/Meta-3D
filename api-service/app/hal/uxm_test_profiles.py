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
        get_profile, list_profiles, UxmTopologyProfile,
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
class UxmTopologyProfile:
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

    # --- P2-1 Phase 1: Test App 兼容性声明 ---
    #
    # 拓扑 profile 在哪个 / 哪些 Test App 下工作。Test App 决定 UXM SCPI
    # 命令词汇 (CONFig:NR5G:* vs BSE:CONFig:NR5G:*) + cell index 编码
    # (CELL0 vs CELL1) + 带宽值形式 (40 vs "BW40"), 拓扑里 ``cell_id`` 等
    # 字段必须跟运行中的 Test App 匹配, 否则发命令会得到 -113 Undefined
    # Header 或操作到不存在的 cell.
    #
    # 空列表 = 兼容所有 Test App (类似 "any"); 显式列出代表"只跟这些 app
    # 兼容"。操作员在 GUI 选拓扑时, 跟 detected_test_app 不匹配的会被
    # ``RealUxmDriver.apply_topology_profile`` refuse (返回结构化错误,
    # 不进入 SCPI 路径); 同时 GUI 可读这个字段灰化不兼容选项.
    #
    # 当前 7 个 built-in template 用的都是 cell_id="CELL0" + 直接数字
    # 带宽, 仅在 5G_NR_Test 下工作; 显式声明这点比依赖 cell_id 形式推断
    # 更稳健 (未来加 IRAT 拓扑时不会因为 cell_id 改成 "CELL1" 就被认为
    # 通用兼容).
    compatible_test_apps: List[str] = field(default_factory=list)

    # --- 备注 ---
    notes: str = ""

    def is_compatible_with(self, test_app_name: Optional[str]) -> bool:
        """P2-1: 这个拓扑能在 ``test_app_name`` 标识的 Test App 下安全运行吗?

        - ``compatible_test_apps`` 空 = 兼容任何 (含 None / 未知)
        - ``test_app_name`` 是 None = "未检测到 Test App", 当兼容处理
          (Mock 模式 / 离线模式 / 刚 boot HAL 但还没 connect 都属于这种)
        - 否则: ``test_app_name`` 落在声明的 ``compatible_test_apps`` 里
          (大小写不敏感, 精确字符串相等; substring 匹配交给 Test App 层
          自己的 ``APP_NAME_MATCH`` registry 做, 拓扑层就读最终 profile 名)
        """
        if not self.compatible_test_apps:
            return True
        if test_app_name is None:
            return True
        target = test_app_name.upper()
        return any(allowed.upper() == target for allowed in self.compatible_test_apps)

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
    def from_json(cls, filepath: str) -> "UxmTopologyProfile":
        """从 JSON 文件加载配置模板"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)


# ===========================================================================
# 预定义测试配置库
# ===========================================================================

# ---- SISO (1x1) 基线测试 ----
PROFILE_SISO_N78 = UxmTopologyProfile(
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
    compatible_test_apps=["5G_NR_Test"],
    notes="RF1 OUT→F64 CH1→探头; RF1 IN←DUT UL",
)

PROFILE_SISO_N78_LOW_POWER = UxmTopologyProfile(
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
    compatible_test_apps=["5G_NR_Test"],
    notes="用于 RSRP/SINR 灵敏度标定",
)

# ---- 2x2 MIMO (标准 OTA 测试) ----
PROFILE_2X2_N78 = UxmTopologyProfile(
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
    compatible_test_apps=["5G_NR_Test"],
    notes=(
        "RF1 OUT→F64 CH1→探头天线 1~16 (V极化)\n"
        "RF2 OUT→F64 CH2→探头天线 1~16 (H极化)\n"
        "RF6 IN←暗室独立通信天线 (UL)"
    ),
)

PROFILE_2X2_N41 = UxmTopologyProfile(
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
    compatible_test_apps=["5G_NR_Test"],
    notes="适用于 N41 频段车载天线测试",
)

# ---- 4x4 MIMO (高阶测试) ----
PROFILE_4X4_N78 = UxmTopologyProfile(
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
    compatible_test_apps=["5G_NR_Test"],
    notes=(
        "需要满配 UXM (8 端口)\n"
        "RF1~RF4 OUT→F64 CH1~CH4→探头\n"
        "RF6 IN←暗室独立通信天线 (UL)"
    ),
)

# ---- 4x4 MIMO @ 3600M (fresh-start 系统默认, 对齐 F64 默认 .smu) ----
# P1-17: F64 默认 .smu = 3GPP_FR1_OTA_CDLC_UMa_3600M (N78, 4-input, 3600 MHz)。
# UXM fresh-start 默认必须跟它**同频** (否则 BS 发 3600 而现有 3500M profile 让
# BS 发 3500 → 跟 F64 信道频率打架)。这个 profile 专门对齐 F64 默认, 作为
# UXM_DEFAULT_TOPOLOGY_PROFILE_ID。现有 caict_n78_4x4 (3500M) 保留不动 (其它
# 引用/测试可能依赖)。
PROFILE_4X4_N78_3600 = UxmTopologyProfile(
    profile_id="caict_n78_3600_4x4",
    name="CAICT 暗室 4x4 MIMO (N78 3600MHz, F64 默认对齐)",
    description=(
        "4x4 MIMO OTA 高阶测试 @ 3600 MHz — 频率/MIMO 对齐 F64 默认 .smu "
        "(3GPP_FR1_OTA_CDLC_UMa_3600M, N78 4-input)。P1-17 fresh-start 系统默认, "
        "保证 UXM 一键就位时跟 F64 默认信道同频。"
    ),
    category="mimo",
    band="N78",
    frequency_mhz=3600.0,
    # ⚠️ arfcn 必须显式设 (Codex on PR #107)! UXM 真正用 ARFCN 定频, 不是
    # frequency_mhz。缺省 (None) 时 set_cell_config fallback 走 band 查表
    # (agent R6 F3 起 = EMQuest 基线, N78→636666=3549.99 MHz), 让"对齐 F64
    # 3600M"的本 profile 实际驱动 UXM 到 3549.99 → 依然没对齐。
    # 640000 = 3600.0 MHz 的精确 NR-ARFCN (FR1 range2: 600000+(F−3000)/0.015)。
    arfcn=640000,
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
    compatible_test_apps=["5G_NR_Test"],
    notes=(
        "fresh-start 系统默认 (P1-17), 对齐 F64 默认 3600M .smu (arfcn=640000)。\n"
        "⚠ 2026-07-20 起不再是系统默认 (频率是文件名标称, 工程真值 3549.99 —\n"
        "见 caict_n78_3550_4x4_baseline); 保留供历史引用。\n"
        "需要满配 UXM (8 端口)\n"
        "RF1~RF4 OUT→F64 CH1~CH4→探头\n"
        "RF6 IN←暗室独立通信天线 (UL)"
    ),
)

# ---- 4x4 MIMO @ 3549.99M (EMQuest n78 基线, 2026-07-20 起系统默认) ----
# 门审 #216 F1: 旧默认 caict_n78_3600_4x4 的 3600/640000/BW100/-50 全是 stale —
# "3600M" 是 .smu 文件名标称 (会说谎, 2026-07-03 SMB 实测工程真值 3549.99 MHz
# = ARFCN 636666 = UXM Test App 自带默认 = EMQuest n78 基线, 厂商三方配套)。
# BW40/-46 = EMQuest 灵敏度基线 (2026-07-20 拍板)。auto-apply 生效场景
# (5G_NR_Test) 下, 重载驱动即对齐基线而非冲到错值; IRAT 现场不受影响
# (compatible_test_apps 兼容门拒 apply, 重载不动 UXM 小区 — 07-03 实录佐证)。
PROFILE_4X4_N78_3550_BASELINE = UxmTopologyProfile(
    profile_id="caict_n78_3550_4x4_baseline",
    name="CAICT 暗室 4x4 MIMO (N78 3549.99MHz, EMQuest 基线)",
    description=(
        "4x4 MIMO OTA @ 3549.99 MHz (ARFCN 636666) — F64 UMa_3600M 工程真值 / "
        "UXM Test App 自带默认 / EMQuest n78 基线三方配套 (2026-07-03 实证)。"
        "BW40 + RS EPRE -46 dBm/SCS = EMQuest 灵敏度基线 (2026-07-20 拍板)。"
        "P1-17 fresh-start 系统默认。"
    ),
    category="mimo",
    band="N78",
    frequency_mhz=3549.99,
    # 636666 = 3549.99 MHz 精确 NR-ARFCN (EMQuest prm 破译 + .smu 工程实测双源)
    arfcn=636666,
    bandwidth_mhz=40.0,
    scs_khz=30,
    duplex="TDD",
    mimo_layers=4,
    mimo_port_preset="4x4",
    dl_power_dbm=-46.0,
    ssb_power_dbm=-46.0,
    modulation="256QAM",
    target_mcs=28,
    sched_algo="FULLBUFFER",
    enable_amc=False,
    tdd_pattern="DDDSU",
    tdd_period="5MS",
    harq_max_trans=4,
    harq_processes=16,
    csi_rs_ports=8,
    stat_count=5000,
    compatible_test_apps=["5G_NR_Test"],
    notes=(
        "系统默认 (P1-17, 2026-07-20 起替代 caict_n78_3600_4x4)。\n"
        "频率/BW/功率对齐 EMQuest n78 基线 (636666/BW40/-46)。\n"
        "需要满配 UXM (8 端口)\n"
        "RF1~RF4 OUT→F64 CH1~CH4→探头\n"
        "RF6 IN←暗室独立通信天线 (UL)"
    ),
)

# ---- 校准专用 ----
PROFILE_CAL_POWER = UxmTopologyProfile(
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
    compatible_test_apps=["5G_NR_Test"],
    notes="高功率输出用于 VNA/频谱仪 path loss 校准",
)

PROFILE_CAL_2X2_ALT = UxmTopologyProfile(
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
    compatible_test_apps=["5G_NR_Test"],
    notes="验证 RF3+RF4 通路与 RF1+RF2 的一致性",
)


# ===========================================================================
# 配置库管理 API
# ===========================================================================

# 所有预定义配置注册表
_PROFILE_REGISTRY: Dict[str, UxmTopologyProfile] = {}


def _register_builtin_profiles() -> None:
    """注册所有内置配置模板"""
    for profile in [
        PROFILE_SISO_N78,
        PROFILE_SISO_N78_LOW_POWER,
        PROFILE_2X2_N78,
        PROFILE_2X2_N41,
        PROFILE_4X4_N78,
        PROFILE_4X4_N78_3600,   # 历史保留 (2026-07-20 起非默认, 3600 是文件名标称)
        PROFILE_4X4_N78_3550_BASELINE,  # P1-17 系统默认 (EMQuest 基线 636666/BW40/-46)
        PROFILE_CAL_POWER,
        PROFILE_CAL_2X2_ALT,
    ]:
        _PROFILE_REGISTRY[profile.profile_id] = profile


def get_profile(profile_id: str) -> UxmTopologyProfile:
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


def register_profile(profile: UxmTopologyProfile) -> None:
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
