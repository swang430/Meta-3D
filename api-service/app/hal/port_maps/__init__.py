"""
CAICT 暗室 MIMO OTA 端口映射拓扑

基于 ETS-Lindgren AMS8947 系统拓扑图 V3.0 解析。
该配置描述了信道仿真器 (CE) 到暗室探头的完整信号链路:

    CE Output Port → EMCenter Switch Slot (P1/P3 input) → (P2/P4 output) → Probe V/H

拓扑适用于:
  - 2 × Spirent Vertex (16ch each, 原始配置)
  - 1 × Keysight PROPSIM F64 (32ch, Option B 替代)
  - 其他 32 通道 CE (只需重映射 ce_port)

使用方法:
    from app.hal.port_maps.caict_ams8947 import CAICT_TOPOLOGY, get_switch_commands_for_probe
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class Polarization(str, Enum):
    V = "V"
    H = "H"


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
# 完整的 32 通道端口映射 (从拓扑图 Page 2 精确解析)
# ============================================================

CAICT_CHANNEL_MAP: List[ProbeChannel] = [
    # ==================== Vertex1 / CE Unit 1 ====================
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

    # ==================== Vertex2 / CE Unit 2 ====================
    # Probe 5 (Slot 8)
    ProbeChannel(ce_unit=2, ce_port="B17", emquest_net_port=66, switch_slot=8, switch_pin="P2", probe_id=5,  polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B18", emquest_net_port=68, switch_slot=8, switch_pin="P4", probe_id=5,  polarization=Polarization.H),
    # Probe 13 (Slot 7)
    ProbeChannel(ce_unit=2, ce_port="B19", emquest_net_port=62, switch_slot=7, switch_pin="P2", probe_id=13, polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B20", emquest_net_port=64, switch_slot=7, switch_pin="P4", probe_id=13, polarization=Polarization.H),
    # Probe 6 (Slot 6)
    ProbeChannel(ce_unit=2, ce_port="B21", emquest_net_port=58, switch_slot=6, switch_pin="P2", probe_id=6,  polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B22", emquest_net_port=60, switch_slot=6, switch_pin="P4", probe_id=6,  polarization=Polarization.H),
    # Probe 14 (Slot 5)
    ProbeChannel(ce_unit=2, ce_port="B23", emquest_net_port=54, switch_slot=5, switch_pin="P2", probe_id=14, polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B24", emquest_net_port=56, switch_slot=5, switch_pin="P4", probe_id=14, polarization=Polarization.H),
    # Probe 7 (Slot 4)
    ProbeChannel(ce_unit=2, ce_port="B25", emquest_net_port=50, switch_slot=4, switch_pin="P2", probe_id=7,  polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B26", emquest_net_port=52, switch_slot=4, switch_pin="P4", probe_id=7,  polarization=Polarization.H),
    # Probe 15 (Slot 3)
    ProbeChannel(ce_unit=2, ce_port="B27", emquest_net_port=46, switch_slot=3, switch_pin="P2", probe_id=15, polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B28", emquest_net_port=48, switch_slot=3, switch_pin="P4", probe_id=15, polarization=Polarization.H),
    # Probe 8 (Slot 2)
    ProbeChannel(ce_unit=2, ce_port="B29", emquest_net_port=42, switch_slot=2, switch_pin="P2", probe_id=8,  polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B30", emquest_net_port=44, switch_slot=2, switch_pin="P4", probe_id=8,  polarization=Polarization.H),
    # Probe 16 (Slot 1)
    ProbeChannel(ce_unit=2, ce_port="B31", emquest_net_port=38, switch_slot=1, switch_pin="P2", probe_id=16, polarization=Polarization.V),
    ProbeChannel(ce_unit=2, ce_port="B32", emquest_net_port=40, switch_slot=1, switch_pin="P4", probe_id=16, polarization=Polarization.H),
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
# 拓扑元数据
# ============================================================

CAICT_TOPOLOGY = {
    "name": "CAICT (Beijing) BDA",
    "system": "ETS-Lindgren AMS8947",
    "project": "PJXXXX",
    "location": "Shaoyangcheng",
    "version": "V3.0",
    "total_probes": 16,
    "total_channels": 32,  # 16 probes × 2 polarizations
    "ce_units": 2,         # Vertex1 + Vertex2
    "switch_slots": 8,
    "calibration_paths": 16,   # 8 slots × 2 paths (P1→P2, P3→P4)
    "antenna_model": "AMS8900",
    "switch_model": "EMCenter (EMQuest NET)",
}
