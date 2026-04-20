"""
CAICT AMS8947 默认拓扑配置生成器

将 port_maps/caict_ams8947 中的静态映射转换为 TopologyService 可用的
标准拓扑 JSON 格式，包含 MIMO OTA 和 SISO 两大操作模式。
"""
from typing import Dict, Any, List
from app.hal.port_maps import CAICT_CHANNEL_MAP, CAICT_TOPOLOGY


def generate_caict_mimo_topology() -> Dict[str, Any]:
    """
    生成 CAICT 暗室的完整 MIMO OTA 拓扑配置。

    Returns:
        可直接存入 SwitchTopology.nodes / connections / operating_modes 的字典
    """
    nodes: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    mimo_conn_ids: List[str] = []

    # ========== 生成节点 ==========

    # CE 端口节点 (B1-B32)
    seen_ce = set()
    for ch in CAICT_CHANNEL_MAP:
        if ch.ce_port not in seen_ce:
            seen_ce.add(ch.ce_port)
            # 按 CE unit 分左右列
            x = 50 if ch.ce_unit == 1 else 700
            port_num = int(ch.ce_port[1:])
            y = 30 + ((port_num - 1) % 16) * 40
            nodes.append({
                "id": f"ce{ch.ce_unit}_{ch.ce_port.lower()}",
                "type": "ce_port",
                "label": f"Vertex{ch.ce_unit} {ch.ce_port}",
                "position": {"x": x, "y": y},
                "params": {
                    "ce_unit": ch.ce_unit,
                    "port": ch.ce_port,
                    "emquest_port": ch.emquest_net_port,
                },
            })

    # Switch Slot 节点 (S1-S8)
    seen_slots = set()
    for ch in CAICT_CHANNEL_MAP:
        if ch.switch_slot not in seen_slots:
            seen_slots.add(ch.switch_slot)
            y = 30 + (8 - ch.switch_slot) * 80
            nodes.append({
                "id": f"slot{ch.switch_slot}",
                "type": "switch_slot",
                "label": f"Slot {ch.switch_slot}",
                "position": {"x": 350, "y": y},
                "params": {
                    "slot_number": ch.switch_slot,
                    "pins": ["P1", "P2", "P3", "P4"],
                },
            })

    # Probe 节点 (1V, 1H, 2V, 2H, ... 16V, 16H)
    seen_probes = set()
    for ch in CAICT_CHANNEL_MAP:
        probe_key = f"{ch.probe_id}{ch.polarization.value}"
        if probe_key not in seen_probes:
            seen_probes.add(probe_key)
            x = 600 if ch.ce_unit == 1 else 1000
            pol_offset = 0 if ch.polarization.value == "V" else 20
            y = 30 + (ch.probe_id - 1) * 45 + pol_offset
            nodes.append({
                "id": f"probe{ch.probe_id}{ch.polarization.value.lower()}",
                "type": "probe",
                "label": f"Probe {ch.probe_id}{ch.polarization.value}",
                "position": {"x": x, "y": y},
                "params": {
                    "probe_id": ch.probe_id,
                    "polarization": ch.polarization.value,
                    "ring": "upper" if ch.probe_id <= 8 else "lower",
                },
            })

    # ========== 生成连线 ==========

    for ch in CAICT_CHANNEL_MAP:
        ce_node_id = f"ce{ch.ce_unit}_{ch.ce_port.lower()}"
        slot_node_id = f"slot{ch.switch_slot}"
        probe_node_id = f"probe{ch.probe_id}{ch.polarization.value.lower()}"

        # 输入端口: P2 输出对应 P1 输入, P4 输出对应 P3 输入
        input_pin = "P1" if ch.switch_pin == "P2" else "P3"

        # Connection 1: CE Port → Switch Slot Input
        conn1_id = f"conn_{ce_node_id}_to_{slot_node_id}_{input_pin}"
        connections.append({
            "id": conn1_id,
            "source": ce_node_id,
            "source_pin": "out",
            "target": slot_node_id,
            "target_pin": input_pin,
            "cable_type": "Phase-matched N-N",
            "cable_loss_db": 0.5,
            "cable_length_m": 3.0,
            "calibrated_loss_db": None,
            "calibrated_phase_deg": None,
            "modes": ["mimo_ota"],
        })
        mimo_conn_ids.append(conn1_id)

        # Connection 2: Switch Slot Output → Probe
        conn2_id = f"conn_{slot_node_id}_{ch.switch_pin}_to_{probe_node_id}"
        connections.append({
            "id": conn2_id,
            "source": slot_node_id,
            "source_pin": ch.switch_pin,
            "target": probe_node_id,
            "target_pin": "in",
            "cable_type": "Semi-rigid N-SMA",
            "cable_loss_db": 0.3,
            "cable_length_m": 2.0,
            "calibrated_loss_db": None,
            "calibrated_phase_deg": None,
            "modes": ["mimo_ota"],
        })
        mimo_conn_ids.append(conn2_id)

    # ========== 操作模式 ==========

    operating_modes = [
        {
            "id": "mimo_ota",
            "name": "MIMO OTA (5G NR)",
            "description": "32通道 MPAC 测量，2×Vertex → EMCenter S1-S8 → 16 Dual-Pol Probes",
            "active_connections": mimo_conn_ids,
            "required_instruments": ["channelEmulator", "baseStation"],
            "color": "#4CAF50",
        },
        {
            "id": "siso_trp",
            "name": "SISO TRP",
            "description": "发射总辐射功率测量，BSE RF1/RF3 → Slot4 SPDT → Combiner → Slot5 SP6T → Switched Probes",
            "active_connections": [],  # 待 SISO 模式配置后填充
            "required_instruments": ["signalAnalyzer"],
            "color": "#2196F3",
        },
        {
            "id": "siso_tis",
            "name": "SISO TIS",
            "description": "接收总全向灵敏度测量，NR TIS → SAM-Sub6G → Switched Probes",
            "active_connections": [],
            "required_instruments": ["baseStation", "signalAnalyzer"],
            "color": "#FF9800",
        },
        {
            "id": "siso_passive",
            "name": "Passive",
            "description": "无源天线方向图，Dedicated Theta/Phi → VNA S21",
            "active_connections": [],
            "required_instruments": ["vna"],
            "color": "#9C27B0",
        },
    ]

    return {
        "nodes": nodes,
        "connections": connections,
        "operating_modes": operating_modes,
    }


def generate_caict_topology_record() -> Dict[str, Any]:
    """生成完整的 SwitchTopology 记录数据 (可直接用于种子脚本)"""
    topo_data = generate_caict_mimo_topology()

    return {
        "name": f"{CAICT_TOPOLOGY['name']} - {CAICT_TOPOLOGY['system']}",
        "description": f"CAICT 暗室 MIMO OTA 系统拓扑 ({CAICT_TOPOLOGY['version']})",
        "version": CAICT_TOPOLOGY["version"],
        "site_name": CAICT_TOPOLOGY["location"],
        "system_model": CAICT_TOPOLOGY["system"],
        "nodes": topo_data["nodes"],
        "connections": topo_data["connections"],
        "operating_modes": topo_data["operating_modes"],
        "is_active": True,
        "is_default": True,
    }
