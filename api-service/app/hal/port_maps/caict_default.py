"""
CAICT 暗室完整 RF 拓扑配置生成器 (V4.0)

基于 CAICT 暗室实际配置重构, 包含两套独立的探头环和信号链路:

1. 水平环 (MIMO OTA):
   UXM RF1-RF4 → CE (F64, 4in/32out) → EMCenter 集成 PA → 16 水平探头 (32路固定连接)
   ★ 不经过 RF Switch, CE 到探头是一对一直连

2. 垂直环 (TRP / TIS / 无源):
   UXM RF5 → EMCenter Switch → V/H split → 24 垂直探头 (逐个切换 + 转台扫描)
   VNA → EMCenter Switch → 垂直探头 (无源天线方向图)

3. 校准链路:
   CE CW → EMCenter PA → 水平探头 → 自由空间 → SGH → FSVA3000
"""
from typing import Dict, Any, List
from app.hal.port_maps import (
    CAICT_CHANNEL_MAP,
    CAICT_TOPOLOGY,
    CAICT_VERTICAL_PROBES,
    CAICT_SIGNAL_SOURCES,
    CAICT_EMCENTER,
)


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

    # ── 1. UXM (综测仪) ──
    nodes.append({
        "id": "uxm",
        "type": "communication_tester",
        "label": "UXM E7515B",
        "position": {"x": _COL_SOURCE, "y": 200},
        "params": {
            "model": "E7515B",
            "vendor": "Keysight",
            "ports": ["RF1", "RF2", "RF3", "RF4", "RF5", "RF6"],
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
            "description": "4 路 UXM 输入 → 32 路 OTA 输出",
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

    # ── Shared: UXM RF1-4 → CE 输入 ──
    for i in range(1, 5):
        conns["shared"].append({
            "id": f"conn_uxm_rf{i}_to_ce",
            "source": "uxm",
            "source_pin": f"RF{i}",
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
        "id": "conn_link_antenna_to_uxm_mimo",
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
                "UXM RF1-4 → CE F64 (4in/32out) → EMCenter 集成PA → "
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


def generate_caict_topology_record() -> Dict[str, Any]:
    """生成完整的 SwitchTopology 记录数据 (可直接用于种子脚本)"""
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
