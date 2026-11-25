"""从当前实验室的安装登记和实际采用的路径校准构造本次 OTA 输入。"""
import hashlib
import json
import math

from uuid import UUID

from app.schemas.topology_ports import resolve_port_direction
from app.models.probe import Probe
from app.models.switch_topology import SwitchTopology
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.services.chamber_resolution import resolve_current_chamber
from app.services.lab_resolution import LabResolutionError, resolve_lab_profile
from app.services.mimo_ota.route_calibration_freeze import resolve_effective_route_compensation


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def chamber_geometry(db, frequency_mhz, tx_ports, installation=None):
    try:
        lab_id = (installation or {}).get("lab_profile_id")
        lab = resolve_lab_profile(db, UUID(str(lab_id)) if lab_id else None)
    except LabResolutionError as exc:
        raise ValueError("请在实验室配置中选择唯一的当前实验室") from exc
    chamber = resolve_current_chamber(db, lab.id)
    probes = db.query(Probe).filter_by(chamber_config_id=chamber.id, is_active=True).all()
    if not probes:
        raise ValueError(f"{chamber.name} 没有启用的探头")
    disconnected = sorted(p.probe_number for p in probes if p.is_connected is not True)
    if disconnected:
        raise ValueError(f"{chamber.name} 的启用探头尚未确认连接：" + "、".join(map(str, disconnected)))
    if installation is None:
        installation = (lab.extra_metadata or {}).get("mpdb_ota_installation") or {}
    if installation.get("chamber_id") != str(chamber.id):
        raise ValueError(f"{chamber.name} 缺少与本暗室对应的探头极化安装登记")
    snapshot = resolve_effective_route_compensation(db, lab.id, "mimo_ota", frequency_mhz, lock_sources=False)
    topology = db.get(SwitchTopology, UUID(snapshot["topology_id"])) if snapshot["topology_id"] else None
    if topology is None:
        raise ValueError("缺少当前实验室的射频拓扑")
    snapshot["input_wiring"] = input_wiring(topology)
    return assemble_geometry(chamber, probes, installation, snapshot, tx_ports)


def input_wiring(topology):
    modes = [m for m in topology.operating_modes or [] if m.get("id") == "mimo_ota"]
    if len(modes) != 1:
        raise ValueError("拓扑未唯一确定 MIMO OTA 接线模式")
    edges = set(modes[0].get("active_connections") or [e["id"] for e in topology.connections or []
                                                        if "mimo_ota" in e.get("modes", [])])
    nodes = {n["id"]: n for n in topology.nodes or []}
    result = {}
    for e in topology.connections or []:
        if e["id"] not in edges or nodes.get(e["target"], {}).get("type") != "channel_emulator":
            continue
        source = nodes.get(e["source"], {})
        if source.get("type") not in ("communication_tester", "bse_port"):
            continue
        port_direction, _ = resolve_port_direction(source, e.get("source_pin"))
        edge_direction = e.get("direction")
        if edge_direction not in (None, "DL") or port_direction == "input":
            continue
        if edge_direction is None and port_direction != "output":
            continue
        port = e.get("target_pin")
        if not port or not e.get("source_pin") or port in result:
            raise ValueError("基站到信道仿真器的下行输入接线缺失或重复")
        result[port] = {k:e[k] for k in ("id","source","source_pin","target","target_pin")}
    return result


def assemble_geometry(chamber, probes, installation, snapshot, tx_ports):
    if snapshot["chamber_id"] != str(chamber.id) or not snapshot["topology_id"]:
        raise ValueError("当前暗室缺少有效射频拓扑")
    if (installation.get("topology_id") != snapshot["topology_id"]
            or installation.get("lab_profile_id") != snapshot["lab_profile_id"]):
        raise ValueError("安装登记与当前实验室或射频拓扑不一致")
    inputs = installation.get("tx_inputs") or {}
    tx_inputs = {str(t): inputs.get(str(t)) for t in tx_ports}
    for tx, port in tx_inputs.items():
        if not isinstance(port, str) or port not in snapshot["input_wiring"]:
            raise ValueError(f"源发射端口 {tx} 没有与当前拓扑一致的 F64 下行输入接线")
    if len(set(tx_inputs.values())) != len(tx_inputs):
        raise ValueError("多个源发射端口登记到同一个 F64 输入口")
    bindings = installation.get("feeds")
    if not isinstance(bindings, dict) or set(bindings) != {str(p.id) for p in probes}:
        raise ValueError("安装登记必须逐一对应当前所有启用探头的标识，请核对停用或新增的探头")
    by_chain = {row["chain_id"]: row for row in snapshot["route_entries"]}
    from app.services.probe_pattern.consumer import infer_rf_chain_probe_id_base
    base = infer_rf_chain_probe_id_base(chamber.num_probes, [row["probe_id"] for row in by_chain.values()])
    if base is None:
        raise ValueError("当前拓扑无法确认探头位置编号从 0 或 1 开始")
    occupied = set()
    groups = {}
    for p in sorted(probes, key=lambda item: item.probe_number):
        binding = bindings[str(p.id)]
        if not isinstance(binding, dict):
            raise ValueError(f"探头 {p.probe_number} 缺少安装通路")
        row = by_chain.get(binding.get("chain_id"))
        basis = binding.get("basis")
        if (row is None or row["polarization"] != p.polarization or
                binding.get("ce_port") != row.get("ce_port") or
                basis not in ("theta", "phi") or not row.get("ce_port")):
            raise ValueError(f"探头 {p.probe_number} 的通路或安装极化方向未确认")
        if binding.get("positive_basis_confirmed") is not True:
            raise ValueError(f"探头 {p.probe_number} 的安装轴正方向未确认，倾斜或反向接线需先核准")
        if p.status in ("error", "calibrating"):
            raise ValueError(f"探头 {p.probe_number} 当前处于故障或校准状态")
        output = int(RealPropsimF64Driver._ce_port_to_output_num(row["ce_port"]))
        expected = (row["probe_id"] - base) * chamber.num_polarizations + (1 if p.polarization == "V" else 2)
        if p.polarization not in ("V", "H") or expected != p.probe_number or output != p.channel_port:
            raise ValueError(f"探头 {p.probe_number} 的实物编号、登记输出与采用校准的通路不一致")
        if output in occupied:
            raise ValueError(f"探头 {p.probe_number} 重复使用输出 {row['ce_port']}")
        occupied.add(output)
        if (row["measurement_provenance"] != "real" or row["reason"] != "selected"
                or not _finite(row["value_db"]) or not row["source_id"]):
            raise ValueError(f"探头 {p.probe_number}、输出 {row['ce_port']} 在 {snapshot['frequency_mhz']} MHz 缺少有效的实测路径校准")
        pos = p.position or {}
        az, el, radius = (pos.get(k) for k in ("azimuth", "elevation", "radius"))
        if not all(map(_finite, (az, el, radius))) or not -90 <= el <= 90 or radius <= 0:
            raise ValueError(f"探头 {p.probe_number} 的位置无效")
        feeds = groups.setdefault((az % 360, 90 - el, radius), {})
        if basis in feeds:
            raise ValueError(f"探头 {p.probe_number} 在同一位置重复登记极化 {basis}")
        feeds[basis] = dict(probe_number=p.probe_number, probe_uuid=str(p.id), **row)
    locations = sorted(groups)
    for loc in locations:
        if set(groups[loc]) != {"theta", "phi"}:
            raise ValueError(f"方位 {loc[0]}°、天顶角 {loc[1]}° 缺少配对极化，当前引擎需要双极化通路")
    def points(key):
        rows = installation.get(key)
        if not isinstance(rows, list) or not rows or not all(
            isinstance(v, list) and len(v) == 3 and all(map(_finite, v)) for v in rows
        ):
            raise ValueError("请登记本暗室的拟合点和独立核对点（三维坐标，米）")
        return rows
    layout = dict(geometry_source="current_chamber_installation", field_model="plane_wave",
                chamber_id=str(chamber.id), chamber_name=chamber.name,
                lab_profile_id=snapshot["lab_profile_id"], topology_id=snapshot["topology_id"],
                tx_inputs=tx_inputs, input_wiring={p:snapshot["input_wiring"][p] for p in tx_inputs.values()}, frequency_mhz=snapshot["frequency_mhz"], selected_at=snapshot["selected_at"],
                compensation="ASC 未施加路径路损补偿，播放准备须另行核对并只施加一次",
                probe_azimuth_zenith_deg=[list(loc[:2]) for loc in locations],
                probe_connections=[dict(index=i, radius_m=loc[2], feeds=groups[loc]) for i, loc in enumerate(locations)],
                fit_points_m=points("fit_points_m"), check_points_m=points("check_points_m"))
    if set(map(tuple, layout["fit_points_m"])) & set(map(tuple, layout["check_points_m"])):
        raise ValueError("拟合点与独立核对点不能重合")
    stable = {key: value for key, value in layout.items() if key != "selected_at"}
    layout["configuration_sha256"] = hashlib.sha256(json.dumps(
        stable, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return layout
