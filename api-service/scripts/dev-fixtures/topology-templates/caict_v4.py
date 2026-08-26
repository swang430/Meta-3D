"""CAICT (Beijing) BDA — ETS-Lindgren AMS8947 V4.0 拓扑模板.

本文件是 **dev-fixture 拓扑模板**, 非商用代码. 描述 CAICT 暗室的具体接线:

    CE Output Port → EMCenter Switch Slot (P1/P3 input) → (P2/P4 output) → Probe V/H

* 水平环 (16 探头, MIMO OTA): CE F64 → EMCenter 集成 PA → 直连, 不经过 Switch.
* 垂直环 (24 探头, TRP/TIS/Passive): UXM RF5 或 VNA → EMCenter Switch → V/H split.

由 ``/api/v1/switch-topologies/import/from-template?switch_category_id=<uuid>&lab_profile_id=<uuid>&template_id=caict_v4``
端点（P1-57 起 lab_profile_id 必填, 目标暗室由 LabProfile 派生）通过 ``importlib.util.spec_from_file_location`` 在运行时按文件路径加载.
模板必须导出 ``generate_topology_record() -> Dict[str, Any]``.

新场地接入流程: 拷贝本文件改名 (如 ``foo_lab_v1.py``), 改 ``CAICT_*`` 常量与
``generate_topology_record`` 的 ``site_name`` / ``system_model`` 字段, 然后通过
GUI「重导入」按钮 (template_id=foo_lab_v1) 落入 DB. 商用代码本身零模板.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class Polarization(str, Enum):
    V = "V"
    H = "H"


class ProbeRing(str, Enum):
    """探头所在环"""
    HORIZONTAL = "horizontal"  # 水平环 — 16 探头, 3GPP MIMO OTA
    VERTICAL = "vertical"      # 垂直环 — 24 探头, TRP / TIS / 无源


@dataclass(frozen=True)
class ProbeChannel:
    """一条从 CE 端口到暗室探头的完整信号通道"""
    ce_unit: int            # CE 编号 (1=Vertex1, 2=Vertex2)
    ce_port: str            # CE 输出端口名 (e.g. "B1", "B17")
    emquest_net_port: int   # EMQuest NET 端口编号
    switch_slot: int        # EMCenter Slot 编号 (1-8)
    switch_pin: str         # Slot 内端口 (P2=V输出, P4=H输出)
    probe_id: int           # 探头编号 (1-16)
    polarization: Polarization  # V 或 H


# ============================================================
# 完整的 32 通道端口映射
# F64 单台 32 端口 (RF 1-32) → 集成PA → 水平环 16 探头 (H+V)
# ============================================================

CAICT_CHANNEL_MAP: List[ProbeChannel] = [
    # ==================== F64 Port 1-16 ====================
    # Probe 1 (Slot 8)
    ProbeChannel(ce_unit=1, ce_port="B1",  emquest_net_port=30, switch_slot=8, switch_pin="P2", probe_id=1,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B2",  emquest_net_port=32, switch_slot=8, switch_pin="P4", probe_id=1,  polarization=Polarization.H),
    # Probe 9 (Slot 7)
    ProbeChannel(ce_unit=1, ce_port="B3",  emquest_net_port=28, switch_slot=7, switch_pin="P2", probe_id=9,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B4",  emquest_net_port=26, switch_slot=7, switch_pin="P4", probe_id=9,  polarization=Polarization.H),
    # Probe 2 (Slot 6)
    ProbeChannel(ce_unit=1, ce_port="B5",  emquest_net_port=22, switch_slot=6, switch_pin="P2", probe_id=2,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B6",  emquest_net_port=24, switch_slot=6, switch_pin="P4", probe_id=2,  polarization=Polarization.H),
    # Probe 10 (Slot 5)
    ProbeChannel(ce_unit=1, ce_port="B7",  emquest_net_port=18, switch_slot=5, switch_pin="P2", probe_id=10, polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B8",  emquest_net_port=20, switch_slot=5, switch_pin="P4", probe_id=10, polarization=Polarization.H),
    # Probe 3 (Slot 4)
    ProbeChannel(ce_unit=1, ce_port="B9",  emquest_net_port=10, switch_slot=4, switch_pin="P2", probe_id=3,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B10", emquest_net_port=14, switch_slot=4, switch_pin="P4", probe_id=3,  polarization=Polarization.H),
    # Probe 11 (Slot 3)
    ProbeChannel(ce_unit=1, ce_port="B11", emquest_net_port=16, switch_slot=3, switch_pin="P2", probe_id=11, polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B12", emquest_net_port=12, switch_slot=3, switch_pin="P4", probe_id=11, polarization=Polarization.H),
    # Probe 4 (Slot 2)
    ProbeChannel(ce_unit=1, ce_port="B13", emquest_net_port=8,  switch_slot=2, switch_pin="P2", probe_id=4,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B14", emquest_net_port=6,  switch_slot=2, switch_pin="P4", probe_id=4,  polarization=Polarization.H),
    # Probe 12 (Slot 1)
    ProbeChannel(ce_unit=1, ce_port="B15", emquest_net_port=2,  switch_slot=1, switch_pin="P2", probe_id=12, polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B16", emquest_net_port=4,  switch_slot=1, switch_pin="P4", probe_id=12, polarization=Polarization.H),

    # ==================== F64 Port 17-32 ====================
    # Probe 5 (Slot 8)
    ProbeChannel(ce_unit=1, ce_port="B17", emquest_net_port=66, switch_slot=8, switch_pin="P2", probe_id=5,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B18", emquest_net_port=68, switch_slot=8, switch_pin="P4", probe_id=5,  polarization=Polarization.H),
    # Probe 13 (Slot 7)
    ProbeChannel(ce_unit=1, ce_port="B19", emquest_net_port=62, switch_slot=7, switch_pin="P2", probe_id=13, polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B20", emquest_net_port=64, switch_slot=7, switch_pin="P4", probe_id=13, polarization=Polarization.H),
    # Probe 6 (Slot 6)
    ProbeChannel(ce_unit=1, ce_port="B21", emquest_net_port=58, switch_slot=6, switch_pin="P2", probe_id=6,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B22", emquest_net_port=60, switch_slot=6, switch_pin="P4", probe_id=6,  polarization=Polarization.H),
    # Probe 14 (Slot 5)
    ProbeChannel(ce_unit=1, ce_port="B23", emquest_net_port=54, switch_slot=5, switch_pin="P2", probe_id=14, polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B24", emquest_net_port=56, switch_slot=5, switch_pin="P4", probe_id=14, polarization=Polarization.H),
    # Probe 7 (Slot 4)
    ProbeChannel(ce_unit=1, ce_port="B25", emquest_net_port=50, switch_slot=4, switch_pin="P2", probe_id=7,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B26", emquest_net_port=52, switch_slot=4, switch_pin="P4", probe_id=7,  polarization=Polarization.H),
    # Probe 15 (Slot 3)
    ProbeChannel(ce_unit=1, ce_port="B27", emquest_net_port=46, switch_slot=3, switch_pin="P2", probe_id=15, polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B28", emquest_net_port=48, switch_slot=3, switch_pin="P4", probe_id=15, polarization=Polarization.H),
    # Probe 8 (Slot 2)
    ProbeChannel(ce_unit=1, ce_port="B29", emquest_net_port=42, switch_slot=2, switch_pin="P2", probe_id=8,  polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B30", emquest_net_port=44, switch_slot=2, switch_pin="P4", probe_id=8,  polarization=Polarization.H),
    # Probe 16 (Slot 1)
    ProbeChannel(ce_unit=1, ce_port="B31", emquest_net_port=38, switch_slot=1, switch_pin="P2", probe_id=16, polarization=Polarization.V),
    ProbeChannel(ce_unit=1, ce_port="B32", emquest_net_port=40, switch_slot=1, switch_pin="P4", probe_id=16, polarization=Polarization.H),
]


# ============================================================
# EMCenter Slot 内部结构
# ============================================================

SLOT_PIN_ROLES = {
    "P1": "CE 输入 (V-path analog input)",
    "P2": "探头输出 V 极化",
    "P3": "CE 输入 (H-path analog input)",
    "P4": "探头输出 H 极化",
}

# Vertex1 模拟端口 → EMCenter Slot 输入端口
VERTEX1_ANALOG_MAP = {
    "A1": {"slot": 8, "pin": "P1"},   # UXM P1 → Vertex1 A1 → S8 P1
    "A3": {"slot": 7, "pin": "P1"},   # UXM P3 → Vertex1 A3 → S7 P1
    "A2": {"slot": 8, "pin": "P3"},   # UXM P2 → Vertex1 A2 → S8 P3
    "A4": {"slot": 7, "pin": "P3"},   # UXM P4 → Vertex1 A4 → S7 P3
}

VERTEX2_ANALOG_MAP = {
    "A1": {"slot": 8, "pin": "P1"},
    "A3": {"slot": 7, "pin": "P1"},
    "A2": {"slot": 8, "pin": "P3"},
    "A4": {"slot": 7, "pin": "P3"},
}


# ============================================================
# 校准路径定义
# ============================================================

@dataclass
class CalibrationPath:
    """一条需要校准的 Switch 通道"""
    path_id: str                 # 唯一路径标识
    slot: int                    # EMCenter Slot
    input_pin: str               # 输入端口 (P1 or P3)
    output_pin: str              # 输出端口 (P2 or P4)
    probe_id: int                # 目标探头
    polarization: Polarization   # V or H
    description: str             # 人可读描述


def generate_calibration_paths() -> List[CalibrationPath]:
    """
    基于拓扑图生成所有需要校准的 Switch 路径。

    每个 Slot 有 2 条路径:
      - P1 → P2 (V 极化通路)
      - P3 → P4 (H 极化通路)

    共 8 Slots × 2 paths × 2 CE units = 32 条路径。
    但 Slot 是物理共享的 (Vertex1 和 Vertex2 共用同一个 Slot 的不同时隙),
    所以物理上只需校准 8 Slots × 2 paths = 16 条路径。
    """
    paths = []
    # 从 channel map 中提取唯一的 (slot, pin) 组合
    seen = set()
    for ch in CAICT_CHANNEL_MAP:
        # 推导输入端口: P2 输出对应 P1 输入, P4 输出对应 P3 输入
        input_pin = "P1" if ch.switch_pin == "P2" else "P3"
        key = (ch.switch_slot, input_pin, ch.switch_pin)
        if key not in seen:
            seen.add(key)
            paths.append(CalibrationPath(
                path_id=f"S{ch.switch_slot}_{input_pin}_{ch.switch_pin}",
                slot=ch.switch_slot,
                input_pin=input_pin,
                output_pin=ch.switch_pin,
                probe_id=ch.probe_id,
                polarization=ch.polarization,
                description=f"Slot {ch.switch_slot}: {input_pin}→{ch.switch_pin} → Probe {ch.probe_id}{ch.polarization.value}",
            ))
    return sorted(paths, key=lambda p: (p.slot, p.input_pin))


# ============================================================
# 查询辅助函数
# ============================================================

def get_channels_for_probe(probe_id: int) -> List[ProbeChannel]:
    """获取指定探头的所有通道 (V + H)"""
    return [ch for ch in CAICT_CHANNEL_MAP if ch.probe_id == probe_id]


def get_channel_by_ce_port(ce_port: str) -> Optional[ProbeChannel]:
    """根据 CE 输出端口名查找通道"""
    for ch in CAICT_CHANNEL_MAP:
        if ch.ce_port == ce_port:
            return ch
    return None


def get_switch_command_for_channel(channel: ProbeChannel) -> str:
    """
    生成 EMCenter Switch 的 SCPI 路由命令。

    ETS-Lindgren EMCenter 使用类似:
        Write <slot>:EXT_RELAY_<position>
    或通过 EMQuest NET Port 直接寻址。
    """
    return f"{channel.switch_slot}:EXT_RELAY_{channel.switch_pin}_{channel.emquest_net_port}"


def get_emcenter_calibration_sequence(
    slot: int,
    input_pin: str,
    output_pin: str,
) -> Dict[str, str]:
    """
    生成某条校准路径的完整 SCPI 指令序列。

    返回一个包含 switch_route、vna_setup、vna_trigger、vna_read 等
    步骤的指令字典。

    Args:
        slot: EMCenter Slot 编号
        input_pin: 输入端口 (P1 or P3)
        output_pin: 输出端口 (P2 or P4)

    Returns:
        dict of step_name -> SCPI command string
    """
    return {
        # Step 1: 路由 Switch 到目标路径
        "switch_route": f"Write {slot}:EXT_RELAY_{input_pin}_TO_{output_pin}",
        # Step 2: 配置 VNA (R&S ZNA / Keysight ENA 通用)
        "vna_reset": "*RST",
        "vna_set_start": "SENSe1:FREQuency:STARt 3.3E9",       # 3.3 GHz
        "vna_set_stop": "SENSe1:FREQuency:STOP 3.7E9",          # 3.7 GHz (n78 band)
        "vna_set_points": "SENSe1:SWEep:POINts 401",
        "vna_set_meas": "CALCulate1:PARameter:SDEFine 'Trc1', 'S21'",
        "vna_set_format": "FORMat:DATA ASCii",
        # Step 3: 触发测量
        "vna_single_sweep": "INITiate1:CONTinuous OFF",
        "vna_trigger": "INITiate1:IMMediate; *OPC?",
        # Step 4: 读取数据
        "vna_read_sdata": "CALCulate1:DATA? SDATa",
    }


# ============================================================
# 垂直环探头定义 (24 个双极化探头, TRP / TIS)
# ============================================================

@dataclass(frozen=True)
class VerticalProbe:
    """垂直环探头定义"""
    probe_id: int              # V1 - V24
    elevation_deg: float       # 仰角 (度)
    ring: str = "vertical"     # 固定为垂直环


# 垂直环 24 个探头, 均匀分布在 -90° 到 +90° 弧面上
# 每个探头有 V + H 双极化 (共 48 个天线端口)
CAICT_VERTICAL_PROBES: List[VerticalProbe] = [
    VerticalProbe(probe_id=i + 1, elevation_deg=-82.5 + i * (165.0 / 23))
    for i in range(24)
]


def get_vertical_probe(probe_id: int) -> Optional[VerticalProbe]:
    """获取指定编号的垂直环探头"""
    for vp in CAICT_VERTICAL_PROBES:
        if vp.probe_id == probe_id:
            return vp
    return None


# ============================================================
# 信号源定义
# ============================================================

CAICT_SIGNAL_SOURCES = {
    "uxm": {
        "name": "Keysight UXM 5G Test Platform",
        "model": "E7515B",
        "ports": {
            "RF1": {"role": "bs_emulator", "target": "ce_input_1",
                    "description": "BS 仿真 → CE Input 1"},
            "RF2": {"role": "bs_emulator", "target": "ce_input_2",
                    "description": "BS 仿真 → CE Input 2"},
            "RF3": {"role": "bs_emulator", "target": "ce_input_3",
                    "description": "BS 仿真 → CE Input 3"},
            "RF4": {"role": "bs_emulator", "target": "ce_input_4",
                    "description": "BS 仿真 → CE Input 4"},
            "RF5": {"role": "trp_tis", "target": "emcenter_switch",
                    "description": "TRP/TIS → EMCenter Switch → V/H split → 垂直环"},
        },
    },
    "ce": {
        "name": "Keysight PROPSIM F64",
        "model": "F8800A",
        "inputs": 4,     # 来自 UXM RF1-RF4
        "outputs": 32,   # → EMCenter 32 路集成 PA → 水平环
    },
    "vna": {
        "name": "Vector Network Analyzer",
        "ports": {
            "Port1": {"role": "source", "description": "无源测试信号源 / 校准"},
            "Port2": {"role": "receiver", "description": "接收端 (SGH)"},
        },
    },
    "fsva3000": {
        "name": "R&S FSVA3000 Signal Analyzer",
        "role": "receiver",
        "description": "校准接收端, 连接 SGH",
    },
}


# ============================================================
# EMCenter 双模功能定义
# ============================================================

CAICT_EMCENTER = {
    "model": "ETS-Lindgren EMCenter (EMQuest NET)",
    "modes": {
        "mimo_ota": {
            "function": "integrated_pa",
            "description": "32 路集成 PA, CE→PA→水平环固定连接, 不做切换",
            "channels": 32,
            "target_ring": "horizontal",
        },
        "trp_tis": {
            "function": "rf_switch",
            "description": "1:N 射频开关, UXM RF5 → V/H split → 垂直环探头逐个切换",
            "input_ports": 1,  # UXM RF5 (split to V+H internally)
            "output_ports": 48,  # 24 probes × 2 polarizations
            "target_ring": "vertical",
        },
        "passive": {
            "function": "rf_switch",
            "description": "VNA S21 → 垂直环探头切换",
            "target_ring": "vertical",
        },
    },
}


# ============================================================
# 拓扑元数据
# ============================================================

CAICT_TOPOLOGY = {
    "name": "CAICT (Beijing) BDA",
    "system": "ETS-Lindgren AMS8947",
    "project": "PJXXXX",
    "location": "Shaoyangcheng",
    "version": "V4.0",
    # 探头总数
    "horizontal_probes": 16,     # 水平环, MIMO OTA
    "vertical_probes": 24,       # 垂直环, TRP/TIS/无源
    "total_probes": 40,          # 16 + 24
    "total_channels": 32,        # MIMO OTA: 16 probes × 2 pol
    "total_vertical_channels": 48,  # TRP/TIS: 24 probes × 2 pol
    # CE
    "ce_model": "Keysight PROPSIM F64",
    "ce_inputs": 4,              # 来自 UXM RF1-RF4
    "ce_outputs": 32,            # → 水平环
    # EMCenter
    "switch_model": "EMCenter (EMQuest NET)",
    "switch_slots": 8,
    "emcenter_pa_channels": 32,  # 集成 PA 通道数
    # 仪表
    "bs_emulator": "Keysight UXM E7515B",
    "signal_analyzer": "R&S FSVA3000",
    "antenna_model": "AMS8900",
}


# ============================================================
# CAICT 暗室完整 RF 拓扑配置生成器 (V4.0)
# ============================================================
#
# 基于 CAICT 暗室实际配置, 包含两套独立的探头环和信号链路:
#
# 1. 水平环 (MIMO OTA):
#    UXM RF1-RF4 → CE (F64, 4in/32out) → EMCenter 集成 PA → 16 水平探头 (32路固定连接)
#    ★ 不经过 RF Switch, CE 到探头是一对一直连
#
# 2. 垂直环 (TRP / TIS / 无源):
#    UXM RF5 → EMCenter Switch → V/H split → 24 垂直探头 (逐个切换 + 转台扫描)
#    VNA → EMCenter Switch → 垂直探头 (无源天线方向图)
#
# 3. 校准链路:
#    CE CW → EMCenter PA → 水平探头 → 自由空间 → SGH → FSVA3000
#
# 数据常量 (CAICT_CHANNEL_MAP / CAICT_VERTICAL_PROBES / CAICT_TOPOLOGY /
# CAICT_SIGNAL_SOURCES / CAICT_EMCENTER) 在本文件上半部分定义, 这里直接引用.

from typing import Any


# ============================================================
# 节点布局常量 (ReactFlow 画布坐标)
# ============================================================

# 列 X 坐标
_COL_SOURCE = 0          # 信号源列 (UXM, VNA)
_COL_CE = 250            # CE 列
_COL_EMCENTER = 520      # EMCenter (PA / Switch)
_COL_HPROBE = 800        # 水平环探头列
_COL_VPROBE = 800        # 垂直环探头列 (与水平环同列, Y 偏移)
_COL_QZ = 1100           # 静区 (SGH, DUT)
_COL_RECEIVER = 1350     # 接收仪表 (FSVA3000)

# 垂直环 Y 起点 (在水平环下方)
_VPROBE_Y_OFFSET = 800


def _generate_nodes() -> List[Dict[str, Any]]:
    """生成所有节点 (信号源、CE、EMCenter、探头、接收端)"""
    nodes = []

    # ── 1. MIMO OTA 逻辑基站（物理 connector 由运行时 profile 映射）──
    nodes.append({
        "id": "baseStation",
        "type": "communication_tester",
        "label": "Base Station Emulator",
        "position": {"x": _COL_SOURCE, "y": 120},
        "params": {
            "ports": ["DL1", "DL2", "DL3", "DL4", "UL1"],
            "port_roles": {
                "DL1": "dl", "DL2": "dl", "DL3": "dl", "DL4": "dl",
                "UL1": "ul",
            },
            "physical_port_display": {},
            "visible_modes": ["mimo_ota"],
            "description": "逻辑端口；物理口来自所选 BaseStation route snapshot",
        },
    })

    # ── 1b. UXM 物理节点（保留给 TRP/TIS 等非 MIMO 路径）──
    nodes.append({
        "id": "uxm",
        "type": "communication_tester",
        "label": "UXM E7515B",
        "position": {"x": _COL_SOURCE, "y": 200},
        "params": {
            "model": "E7515B",
            "vendor": "Keysight",
            "ports": ["RF1", "RF2", "RF3", "RF4", "RF5", "RF6"],
            "port_roles": {
                "RF1": "dl", "RF2": "dl", "RF3": "dl", "RF4": "dl",
                "RF5": "dl", "RF6": "ul",
            },
            "roles": {
                "RF1-RF4": "BS Emulator → CE 4 路输入",
                "RF5": "TRP/TIS → EMCenter Switch → 垂直环",
                "RF6": "Uplink RX ← 通信天线",
            },
        },
    })

    # ── 2. CE (F64) ──
    nodes.append({
        "id": "ce_f64",
        "type": "channel_emulator",
        "label": "PROPSIM F64",
        "position": {"x": _COL_CE, "y": 100},
        "params": {
            "model": "F8800A",
            "vendor": "Keysight",
            "inputs": 4,
            "outputs": 32,
            "description": "4 路 BaseStation 输入 → 32 路 OTA 输出",
        },
    })

    # ── 3. EMCenter (仅 TRP/TIS/Passive 模式: RF Switch) ──
    # MIMO OTA 模式下 PA 是透明的, 不作为节点出现
    nodes.append({
        "id": "emcenter",
        "type": "emcenter",
        "label": "EMCenter (Switch)",
        "position": {"x": _COL_EMCENTER, "y": _VPROBE_Y_OFFSET + 200},
        "params": {
            "model": "EMCenter (EMQuest NET)",
            "vendor": "ETS-Lindgren",
            "slots": 8,
            "function": "rf_switch",
            "description": "TRP/TIS/Passive: RF Switch 1:N → 垂直环探头切换",
            "visible_modes": ["siso_trp", "siso_tis", "passive"],
        },
    })

    # ── 4. 水平环探头 (16 × 2pol = 32 端口) ──
    for ch in CAICT_CHANNEL_MAP:
        probe_key = f"hprobe_{ch.probe_id}{ch.polarization.value.lower()}"
        # 去重: 同一个探头极化只生成一次
        if any(n["id"] == probe_key for n in nodes):
            continue
        pol_offset = 0 if ch.polarization.value == "V" else 18
        nodes.append({
            "id": probe_key,
            "type": "probe",
            "label": f"H{ch.probe_id}-{ch.polarization.value}",
            "position": {
                "x": _COL_HPROBE,
                "y": 30 + (ch.probe_id - 1) * 45 + pol_offset
            },
            "params": {
                "probe_id": ch.probe_id,
                "polarization": ch.polarization.value,
                "ring": "horizontal",
                "ce_port": ch.ce_port,
                "switch_slot": ch.switch_slot,
                "switch_pin": ch.switch_pin,
            },
        })

    # ── 5. 垂直环探头 (24 × 2pol = 48 端口) ──
    for vp in CAICT_VERTICAL_PROBES:
        for pol in ["V", "H"]:
            pol_offset = 0 if pol == "V" else 18
            nodes.append({
                "id": f"vprobe_{vp.probe_id}{pol.lower()}",
                "type": "probe",
                "label": f"V{vp.probe_id}-{pol}",
                "position": {
                    "x": _COL_VPROBE,
                    "y": _VPROBE_Y_OFFSET + (vp.probe_id - 1) * 40 + pol_offset,
                },
                "params": {
                    "probe_id": vp.probe_id,
                    "polarization": pol,
                    "ring": "vertical",
                    "elevation_deg": round(vp.elevation_deg, 1),
                },
            })

    # ── 6. 辅助天线 / 校准天线 ──
    nodes.append({
        "id": "sgh",
        "type": "reference_antenna",
        "label": "标准增益喇叭 (SGH)",
        "position": {"x": 1000, "y": -400},
        "params": {
            "gain_dbi": 15.0,
            "visible_modes": ["passive", "calibration_e2e"]
        }
    })
    nodes.append({
        "id": "link_antenna",
        "type": "reference_antenna",
        "label": "通信天线 (Uplink)",
        "position": {"x": 1000, "y": 600},
        "params": {
            "gain_dbi": 3.0,
            "visible_modes": ["mimo_ota", "siso_trp", "siso_tis"]
        }
    })

    # ── 7. FSVA3000 (频谱仪, 校准接收端) ──
    nodes.append({
        "id": "fsva3000",
        "type": "signal_analyzer",
        "label": "FSVA3000",
        "position": {"x": _COL_RECEIVER, "y": 400},
        "params": {
            "model": "FSVA3000",
            "vendor": "R&S",
            "description": "校准接收端, 连接 SGH",
        },
    })

    # ── 8. VNA (矢网, 无源测试 + 精密校准) ──
    nodes.append({
        "id": "vna",
        "type": "vna",
        "label": "VNA",
        "position": {"x": _COL_SOURCE, "y": _VPROBE_Y_OFFSET + 500},
        "params": {
            "ports": ["Port1", "Port2"],
            "description": "无源测试 + 精密校准",
        },
    })

    return nodes


def _generate_connections() -> Dict[str, List[Dict[str, Any]]]:
    """
    生成所有连线, 按操作模式分组返回。

    Returns:
        {
            "mimo_ota": [...],      CE → PA → 水平环 (固定连接)
            "trp_tis": [...],       UXM RF5 → Switch → 垂直环
            "passive": [...],       VNA → Switch → 垂直环
            "calibration": [...],   CE CW → PA → 水平环 → SGH → FSVA
            "shared": [...],        跨模式共享 (UXM → CE)
        }
    """
    conns: Dict[str, List[Dict[str, Any]]] = {
        "shared": [],
        "mimo_ota": [],
        "trp_tis": [],
        "passive": [],
        "calibration": [],
    }

    # ── MIMO OTA: 逻辑 BaseStation DL1-4 → CE 输入 ──
    for i in range(1, 5):
        conns["shared"].append({
            "id": f"conn_base_station_dl{i}_to_ce",
            "source": "baseStation",
            "source_pin": f"DL{i}",
            "target": "ce_f64",
            "target_pin": f"in{i}",
            "cable_type": "Phase-matched SMA-SMA",
            "cable_loss_db": 0.3,
            "cable_length_m": 2.0,
            "calibrated_loss_db": None,
            "calibrated_phase_deg": None,
            "modes": ["mimo_ota"],
        })

    # ── MIMO OTA: CE → [集成PA] → 水平环探头 (32 路固定一对一直连, 无 Switch) ──
    # PA 是透明的, 作为连线属性嵌入, 不作为独立节点
    for ch in CAICT_CHANNEL_MAP:
        probe_node = f"hprobe_{ch.probe_id}{ch.polarization.value.lower()}"

        conns["mimo_ota"].append({
            "id": f"conn_ce_{ch.ce_port.lower()}_to_{probe_node}",
            "source": "ce_f64",
            "source_pin": "out",             # 匹配 CE 节点 Handle ID
            "target": probe_node,
            "target_pin": "in",
            "cable_type": "Phase-matched N-N + 集成PA + Semi-rigid",
            "cable_loss_db": 0.8,             # 电缆总损耗 (CE→PA入 + PA出→探头)
            "pa_gain_db": 20.0,               # 集成 PA 增益 (典型值)
            "ce_port": ch.ce_port,            # CE 端口标识 (B1-B32)
            "cable_length_m": 5.0,            # CE出口到探头总长度
            "calibrated_loss_db": None,       # 待 E2E 校准填充 (含 PA 后的净增益)
            "calibrated_phase_deg": None,
            "direction": "DL",
            "modes": ["mimo_ota", "calibration"],
        })

    # MIMO OTA Uplink
    conns["mimo_ota"].append({
        "id": "conn_link_antenna_to_base_station_mimo",
        "source": "link_antenna",
        "source_pin": "rf",
        "target": "baseStation",
        "target_pin": "UL1",
        "cable_type": "Low-loss N-SMA",
        "cable_loss_db": 1.2,
        "cable_length_m": 6.0,
        "calibrated_loss_db": None,
        "calibrated_phase_deg": None,
        "direction": "UL",
        "modes": ["mimo_ota"],
    })

    # ── TRP/TIS: UXM RF5 → EMCenter Switch → 垂直环探头 ──
    # UXM RF5 → EMCenter
    conns["trp_tis"].append({
        "id": "conn_uxm_rf5_to_switch",
        "source": "uxm",
        "source_pin": "RF5",
        "target": "emcenter",
        "target_pin": "switch_in",
        "cable_type": "SMA-N",
        "cable_loss_db": 0.4,
        "cable_length_m": 2.5,
        "calibrated_loss_db": None,
        "calibrated_phase_deg": None,
        "direction": "DL",
        "modes": ["trp_tis"],
    })

    # TRP Uplink
    conns["trp_tis"].append({
        "id": "conn_link_antenna_to_uxm_trp",
        "source": "link_antenna",
        "source_pin": "rf",
        "target": "uxm",
        "target_pin": "RF6",
        "cable_type": "Low-loss N-SMA",
        "cable_loss_db": 1.2,
        "cable_length_m": 6.0,
        "calibrated_loss_db": None,
        "calibrated_phase_deg": None,
        "direction": "UL",
        "modes": ["siso_trp", "siso_tis"],
    })

    # EMCenter Switch → 垂直环探头 (24 × 2pol)
    for vp in CAICT_VERTICAL_PROBES:
        for pol in ["V", "H"]:
            probe_node = f"vprobe_{vp.probe_id}{pol.lower()}"
            conns["trp_tis"].append({
                "id": f"conn_switch_to_{probe_node}",
                "source": "emcenter",
                "source_pin": "sw_out",       # 匹配 EMCenter 节点 Handle ID
                "target": probe_node,
                "target_pin": "in",
                "switch_port": f"v{vp.probe_id}{pol.lower()}",  # 开关端口标识
                "cable_type": "Semi-rigid N-SMA",
                "cable_loss_db": 0.3,
                "cable_length_m": 2.0,
                "calibrated_loss_db": None,
                "calibrated_phase_deg": None,
                "modes": ["trp_tis", "passive"],
            })

    # ── Passive: VNA → EMCenter Switch → 垂直环探头 ──
    conns["passive"].append({
        "id": "conn_vna_p1_to_switch",
        "source": "vna",
        "source_pin": "Port1",
        "target": "emcenter",
        "target_pin": "switch_in",
        "cable_type": "Phase-matched SMA-N",
        "cable_loss_db": 0.3,
        "cable_length_m": 2.0,
        "calibrated_loss_db": None,
        "calibrated_phase_deg": None,
        "modes": ["passive"],
    })
    # VNA Port2 → SGH
    conns["passive"].append({
        "id": "conn_vna_p2_to_sgh",
        "source": "vna",
        "source_pin": "Port2",
        "target": "sgh",
        "target_pin": "rf",
        "cable_type": "Phase-matched SMA-N",
        "cable_loss_db": 0.2,
        "cable_length_m": 1.5,
        "calibrated_loss_db": None,
        "calibrated_phase_deg": None,
        "modes": ["passive", "calibration"],
    })

    # ── Calibration: SGH → FSVA3000 ──
    conns["calibration"].append({
        "id": "conn_sgh_to_fsva",
        "source": "sgh",
        "source_pin": "rf",
        "target": "fsva3000",
        "target_pin": "rf_in",
        "cable_type": "Phase-matched SMA-SMA",
        "cable_loss_db": 0.2,
        "cable_length_m": 1.5,
        "calibrated_loss_db": None,
        "calibrated_phase_deg": None,
        "modes": ["calibration"],
    })

    return conns


def generate_caict_mimo_topology() -> Dict[str, Any]:
    """
    生成 CAICT 暗室的完整 RF 拓扑配置 (V4.0)。

    Returns:
        可直接存入 SwitchTopology.nodes / connections / operating_modes 的字典
    """
    nodes = _generate_nodes()
    conns_by_mode = _generate_connections()

    # 将所有连线合并为一个扁平列表
    all_connections = []
    seen_ids = set()
    for mode_conns in conns_by_mode.values():
        for c in mode_conns:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                all_connections.append(c)

    # 各模式的活跃连线 ID — 基于连线 modes 标签匹配
    def _conn_ids_by_tag(*mode_tags: str) -> List[str]:
        """从所有连线中, 找出 modes 标签包含指定模式的连线 ID"""
        ids = []
        for c in all_connections:
            c_modes = set(c.get("modes") or [])
            if c_modes & set(mode_tags):
                ids.append(c["id"])
        return list(dict.fromkeys(ids))  # 去重保序

    operating_modes = [
        {
            "id": "mimo_ota",
            "name": "MIMO OTA (5G NR)",
            "description": (
                "BaseStation DL1-4 → CE F64 (4in/32out) → EMCenter 集成PA → "
                "16 水平探头 (32路固定连接, 不经过 Switch)"
            ),
            "active_connections": _conn_ids_by_tag("mimo_ota"),
            "required_instruments": ["channelEmulator", "baseStation"],
            "color": "#4CAF50",
        },
        {
            "id": "siso_trp",
            "name": "TRP (发射总辐射功率)",
            "description": (
                "DUT 发射 → 垂直环探头接收 → EMCenter Switch 切换 → "
                "FSVA3000 / UXM 测量 | 转台水平扫描"
            ),
            "active_connections": _conn_ids_by_tag("trp_tis"),
            "required_instruments": ["signalAnalyzer", "baseStation"],
            "color": "#2196F3",
        },
        {
            "id": "siso_tis",
            "name": "TIS (接收总全向灵敏度)",
            "description": (
                "UXM RF5 → EMCenter Switch → V/H split → 垂直环探头 → "
                "辐射到 DUT | 转台水平扫描"
            ),
            "active_connections": _conn_ids_by_tag("trp_tis"),
            "required_instruments": ["baseStation"],
            "color": "#FF9800",
        },
        {
            "id": "passive",
            "name": "Passive (无源天线方向图)",
            "description": (
                "VNA Port1 → EMCenter Switch → 垂直环探头 → S21 → "
                "SGH → VNA Port2 | 转台水平扫描"
            ),
            "active_connections": _conn_ids_by_tag("passive"),
            "required_instruments": ["vna"],
            "color": "#9C27B0",
        },
        {
            "id": "calibration_e2e",
            "name": "E2E 校准 (MIMO OTA)",
            "description": (
                "CE CW 信号源 → EMCenter PA → 水平探头 → 自由空间 → "
                "SGH → FSVA3000 接收 | 32 路逐端口自动校准"
            ),
            "active_connections": _conn_ids_by_tag("mimo_ota", "calibration"),
            "required_instruments": ["channelEmulator", "signalAnalyzer"],
            "color": "#F44336",
        },
    ]

    return {
        "nodes": nodes,
        "connections": all_connections,
        "operating_modes": operating_modes,
    }


def generate_topology_record() -> Dict[str, Any]:
    """模板入口: 返回可直接写入 ``SwitchTopology.{nodes,connections,operating_modes,...}``
    的 dict.

    这是 ``/import/from-template`` 端点期望的统一契约 — 任何新模板都必须
    导出一个同名零参函数, 返回相同 schema 的 dict.
    """
    topo_data = generate_caict_mimo_topology()

    return {
        "name": f"{CAICT_TOPOLOGY['name']} - {CAICT_TOPOLOGY.get('system', 'AMS8947')}",
        "description": (
            f"CAICT 暗室完整 RF 拓扑 ({CAICT_TOPOLOGY['version']}): "
            f"水平环 {CAICT_TOPOLOGY['horizontal_probes']} 探头 (MIMO OTA) + "
            f"垂直环 {CAICT_TOPOLOGY['vertical_probes']} 探头 (TRP/TIS)"
        ),
        "version": CAICT_TOPOLOGY["version"],
        "site_name": CAICT_TOPOLOGY["location"],
        "system_model": CAICT_TOPOLOGY.get("system", "AMS8947"),
        "nodes": topo_data["nodes"],
        "connections": topo_data["connections"],
        "operating_modes": topo_data["operating_modes"],
        "is_active": True,
        "is_default": True,
    }
