"""
Switch Topology Service

拓扑解析业务逻辑。从 SwitchTopology 记录中解析信号链路,
提供路径查询、校准矩阵生成和拓扑验证功能。

用法:
    svc = TopologyService(topology_record)
    paths = svc.resolve_paths("mimo_ota")
    loss = svc.get_end_to_end_loss("ce1_b1", "probe1v")
    matrix = svc.get_calibration_matrix("mimo_ota")
"""
import logging
from typing import List, Dict, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================

@dataclass
class TopologyNode:
    """拓扑节点"""
    id: str
    type: str               # ce_port, switch_slot, probe, amplifier, combiner, pad, ...
    label: str
    position: Dict[str, float] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TopologyConnection:
    """拓扑连线"""
    id: str
    source: str             # 源节点 ID
    source_pin: str         # 源端口 (out, P1, P2, ...)
    target: str             # 目标节点 ID
    target_pin: str         # 目标端口 (in, P1, P2, ...)
    cable_type: str = ""
    cable_loss_db: float = 0.0
    cable_length_m: float = 0.0
    calibrated_loss_db: Optional[float] = None
    calibrated_phase_deg: Optional[float] = None
    modes: List[str] = field(default_factory=list)


@dataclass
class SignalPath:
    """一条从源到目的的完整信号路径"""
    path_id: str
    source_node: TopologyNode
    target_node: TopologyNode
    hops: List[Tuple[TopologyNode, TopologyConnection]]  # 中间跳: (节点, 到达它的连线)
    total_loss_db: float
    total_phase_deg: float
    calibration_status: str  # "valid" | "expired" | "missing"


@dataclass
class ValidationIssue:
    """拓扑验证问题"""
    severity: str   # "error" | "warning" | "info"
    node_id: Optional[str]
    connection_id: Optional[str]
    message: str


# ============================================================
# TopologyService
# ============================================================

class TopologyService:
    """
    拓扑解析服务

    从 SwitchTopology 的 JSONB 数据中构建内存图，
    提供路径查询、损耗计算、校准矩阵和拓扑验证。
    """

    def __init__(self, topology_data: Dict[str, Any]):
        """
        Args:
            topology_data: 包含 nodes, connections, operating_modes 的字典,
                           通常从 SwitchTopology 模型解析而来
        """
        self._raw = topology_data

        # 构建节点索引
        self._nodes: Dict[str, TopologyNode] = {}
        for n in topology_data.get("nodes", []):
            node = TopologyNode(
                id=n["id"],
                type=n.get("type", "unknown"),
                label=n.get("label", n["id"]),
                position=n.get("position", {}),
                params=n.get("params", {}),
            )
            self._nodes[node.id] = node

        # 构建连线索引
        self._connections: Dict[str, TopologyConnection] = {}
        for c in topology_data.get("connections", []):
            conn = TopologyConnection(
                id=c["id"],
                source=c["source"],
                source_pin=c.get("source_pin", "out"),
                target=c["target"],
                target_pin=c.get("target_pin", "in"),
                cable_type=c.get("cable_type", ""),
                cable_loss_db=c.get("cable_loss_db", 0.0),
                cable_length_m=c.get("cable_length_m", 0.0),
                calibrated_loss_db=c.get("calibrated_loss_db"),
                calibrated_phase_deg=c.get("calibrated_phase_deg"),
                modes=c.get("modes", []),
            )
            self._connections[conn.id] = conn

        # 构建操作模式索引
        self._modes: Dict[str, Dict[str, Any]] = {}
        for m in topology_data.get("operating_modes", []):
            self._modes[m["id"]] = m

        # 构建邻接表 (source_id → [(connection, target_id)])
        self._adjacency: Dict[str, List[Tuple[TopologyConnection, str]]] = defaultdict(list)
        for conn in self._connections.values():
            self._adjacency[conn.source].append((conn, conn.target))

        logger.info(
            f"TopologyService initialized: "
            f"{len(self._nodes)} nodes, {len(self._connections)} connections, "
            f"{len(self._modes)} modes"
        )

    # ============================================================
    # 路径解析
    # ============================================================

    def resolve_paths(self, mode: str) -> List[SignalPath]:
        """
        给定操作模式，返回所有活跃的完整信号路径（从源端到探头/终端）。

        算法: 从所有"源节点"（CE端口、BSE端口等）出发，沿活跃连线做 DFS，
        直到到达"终端节点"（探头、天线、终端负载等）。

        Args:
            mode: 操作模式 ID (e.g. "mimo_ota", "siso_trp")

        Returns:
            所有完整信号路径列表
        """
        if mode not in self._modes:
            logger.warning(f"Unknown operating mode: {mode}")
            return []

        mode_config = self._modes[mode]
        active_conn_ids = set(mode_config.get("active_connections", []))

        # 如果 active_connections 为空，则使用该模式标记的所有连线
        if not active_conn_ids:
            active_conn_ids = {
                c.id for c in self._connections.values()
                if mode in c.modes
            }

        # 找到所有源节点 (没有入边的节点 = 信号源)
        source_types = {"ce_port", "bse_port", "sa_port"}
        source_nodes = [
            n for n in self._nodes.values()
            if n.type in source_types
        ]

        # 终端节点类型
        terminal_types = {"probe", "antenna", "termination"}

        paths = []
        for source in source_nodes:
            # DFS
            self._dfs_paths(
                current=source,
                visited=set(),
                path_hops=[],
                active_conn_ids=active_conn_ids,
                terminal_types=terminal_types,
                results=paths,
            )

        logger.info(f"Resolved {len(paths)} paths for mode '{mode}'")
        return paths

    def _dfs_paths(
        self,
        current: TopologyNode,
        visited: Set[str],
        path_hops: List[Tuple[TopologyNode, TopologyConnection]],
        active_conn_ids: Set[str],
        terminal_types: Set[str],
        results: List[SignalPath],
    ):
        """DFS 遍历图，收集从源到终端的所有路径"""
        visited.add(current.id)

        # 如果当前节点是终端且路径非空，记录路径
        if current.type in terminal_types and path_hops:
            source_node = path_hops[0][0] if path_hops else current
            # 真正的源是第一个 hop 之前的节点
            # 回溯找源: path_hops[0] 的连线的 source
            first_conn = path_hops[0][1]
            source_node = self._nodes.get(first_conn.source, current)

            total_loss = sum(
                h[1].calibrated_loss_db if h[1].calibrated_loss_db is not None
                else h[1].cable_loss_db
                for h in path_hops
            )
            total_phase = sum(
                h[1].calibrated_phase_deg or 0.0
                for h in path_hops
            )

            # 计算校准状态
            cal_statuses = []
            for _, conn in path_hops:
                if conn.calibrated_loss_db is not None:
                    cal_statuses.append("valid")
                else:
                    cal_statuses.append("missing")

            if all(s == "valid" for s in cal_statuses):
                cal_status = "valid"
            elif any(s == "missing" for s in cal_statuses):
                cal_status = "missing"
            else:
                cal_status = "expired"

            results.append(SignalPath(
                path_id=f"{source_node.id}_to_{current.id}",
                source_node=source_node,
                target_node=current,
                hops=list(path_hops),
                total_loss_db=total_loss,
                total_phase_deg=total_phase,
                calibration_status=cal_status,
            ))
        else:
            # 继续遍历邻居
            for conn, neighbor_id in self._adjacency.get(current.id, []):
                if conn.id not in active_conn_ids:
                    continue
                if neighbor_id in visited:
                    continue
                neighbor = self._nodes.get(neighbor_id)
                if not neighbor:
                    continue

                path_hops.append((neighbor, conn))
                self._dfs_paths(
                    current=neighbor,
                    visited=visited,
                    path_hops=path_hops,
                    active_conn_ids=active_conn_ids,
                    terminal_types=terminal_types,
                    results=results,
                )
                path_hops.pop()

        visited.discard(current.id)

    # ============================================================
    # 损耗计算
    # ============================================================

    def get_end_to_end_loss(self, source_id: str, target_id: str) -> Optional[float]:
        """
        计算两个节点之间的总路径损耗（沿最短路径）。

        使用校准值优先，校准值不存在时使用标称电缆损耗。

        Returns:
            总损耗 (dB)，如果路径不存在返回 None
        """
        path = self._find_shortest_path(source_id, target_id)
        if path is None:
            return None

        total = 0.0
        for conn in path:
            if conn.calibrated_loss_db is not None:
                total += conn.calibrated_loss_db
            else:
                total += conn.cable_loss_db
        return total

    def _find_shortest_path(
        self, source_id: str, target_id: str
    ) -> Optional[List[TopologyConnection]]:
        """BFS 寻找最短路径"""
        from collections import deque

        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        queue = deque([(source_id, [])])
        visited = {source_id}

        while queue:
            current, path = queue.popleft()
            if current == target_id:
                return path

            for conn, neighbor_id in self._adjacency.get(current, []):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [conn]))

        return None

    # ============================================================
    # 校准矩阵
    # ============================================================

    def get_calibration_matrix(self, mode: str) -> Dict[str, Dict[str, Any]]:
        """
        为指定模式生成校准补偿矩阵。

        返回每条活跃路径的补偿值，用于运行时校正信号链路损耗。

        Returns:
            { "path_id": { "loss_db": float, "phase_deg": float, "status": str } }
        """
        paths = self.resolve_paths(mode)
        matrix = {}
        for path in paths:
            matrix[path.path_id] = {
                "source": path.source_node.id,
                "target": path.target_node.id,
                "source_label": path.source_node.label,
                "target_label": path.target_node.label,
                "total_loss_db": path.total_loss_db,
                "total_phase_deg": path.total_phase_deg,
                "compensation_db": -path.total_loss_db,  # 补偿值 = 负损耗
                "calibration_status": path.calibration_status,
                "hop_count": len(path.hops),
            }
        return matrix

    def get_calibration_summary(self) -> Dict[str, Any]:
        """获取所有模式的校准状态摘要"""
        summary = {}
        for mode_id in self._modes:
            paths = self.resolve_paths(mode_id)
            total = len(paths)
            valid = sum(1 for p in paths if p.calibration_status == "valid")
            missing = sum(1 for p in paths if p.calibration_status == "missing")

            summary[mode_id] = {
                "mode_name": self._modes[mode_id].get("name", mode_id),
                "total_paths": total,
                "calibrated": valid,
                "uncalibrated": missing,
                "coverage_pct": (valid / total * 100) if total > 0 else 0,
            }
        return summary

    # ============================================================
    # 拓扑验证
    # ============================================================

    def validate(self) -> List[ValidationIssue]:
        """
        验证拓扑完整性。

        检查项:
        1. 悬空节点 (没有任何连线)
        2. 悬空连线 (引用不存在的节点)
        3. 环路检测
        4. 模式引用不存在的连线
        5. 探头缺少双极化
        """
        issues = []

        # 1. 悬空节点
        connected_nodes = set()
        for conn in self._connections.values():
            connected_nodes.add(conn.source)
            connected_nodes.add(conn.target)

        for node_id, node in self._nodes.items():
            if node_id not in connected_nodes:
                issues.append(ValidationIssue(
                    severity="warning",
                    node_id=node_id,
                    connection_id=None,
                    message=f"节点 '{node.label}' 没有任何连线",
                ))

        # 2. 悬空连线
        for conn in self._connections.values():
            if conn.source not in self._nodes:
                issues.append(ValidationIssue(
                    severity="error",
                    node_id=None,
                    connection_id=conn.id,
                    message=f"连线 '{conn.id}' 引用了不存在的源节点 '{conn.source}'",
                ))
            if conn.target not in self._nodes:
                issues.append(ValidationIssue(
                    severity="error",
                    node_id=None,
                    connection_id=conn.id,
                    message=f"连线 '{conn.id}' 引用了不存在的目标节点 '{conn.target}'",
                ))

        # 3. 模式引用不存在的连线
        for mode_id, mode in self._modes.items():
            for conn_id in mode.get("active_connections", []):
                if conn_id not in self._connections:
                    issues.append(ValidationIssue(
                        severity="error",
                        node_id=None,
                        connection_id=conn_id,
                        message=f"模式 '{mode.get('name', mode_id)}' 引用了不存在的连线 '{conn_id}'",
                    ))

        # 4. 探头缺少双极化检查
        probe_nodes = [n for n in self._nodes.values() if n.type == "probe"]
        probe_by_id = defaultdict(list)
        for p in probe_nodes:
            pid = p.params.get("probe_id")
            if pid is not None:
                probe_by_id[pid].append(p.params.get("polarization", "?"))

        for pid, pols in probe_by_id.items():
            if len(pols) < 2:
                issues.append(ValidationIssue(
                    severity="warning",
                    node_id=None,
                    connection_id=None,
                    message=f"探头 {pid} 只有 {pols} 极化，缺少双极化配对",
                ))

        # 5. 连线损耗合理性
        for conn in self._connections.values():
            if conn.cable_loss_db < 0:
                issues.append(ValidationIssue(
                    severity="warning",
                    node_id=None,
                    connection_id=conn.id,
                    message=f"连线 '{conn.id}' 的电缆损耗为负值 ({conn.cable_loss_db} dB)",
                ))
            if conn.cable_loss_db > 10.0:
                issues.append(ValidationIssue(
                    severity="warning",
                    node_id=None,
                    connection_id=conn.id,
                    message=f"连线 '{conn.id}' 的电缆损耗异常高 ({conn.cable_loss_db} dB > 10 dB)",
                ))

        return issues

    # ============================================================
    # 查询辅助
    # ============================================================

    def get_nodes_by_type(self, node_type: str) -> List[TopologyNode]:
        """按类型查询节点"""
        return [n for n in self._nodes.values() if n.type == node_type]

    def get_connections_for_node(self, node_id: str) -> List[TopologyConnection]:
        """获取与某节点相关的所有连线（入边 + 出边）"""
        result = []
        for conn in self._connections.values():
            if conn.source == node_id or conn.target == node_id:
                result.append(conn)
        return result

    def get_available_modes(self) -> List[Dict[str, Any]]:
        """获取所有可用的操作模式"""
        return list(self._modes.values())

    def get_mode_connections(self, mode: str) -> List[TopologyConnection]:
        """获取指定模式下的所有活跃连线"""
        if mode not in self._modes:
            return []

        mode_config = self._modes[mode]
        active_ids = set(mode_config.get("active_connections", []))

        if not active_ids:
            active_ids = {c.id for c in self._connections.values() if mode in c.modes}

        return [c for c in self._connections.values() if c.id in active_ids]

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典（可序列化为 JSON）"""
        return {
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type,
                    "label": n.label,
                    "position": n.position,
                    "params": n.params,
                }
                for n in self._nodes.values()
            ],
            "connections": [
                {
                    "id": c.id,
                    "source": c.source,
                    "source_pin": c.source_pin,
                    "target": c.target,
                    "target_pin": c.target_pin,
                    "cable_type": c.cable_type,
                    "cable_loss_db": c.cable_loss_db,
                    "cable_length_m": c.cable_length_m,
                    "calibrated_loss_db": c.calibrated_loss_db,
                    "calibrated_phase_deg": c.calibrated_phase_deg,
                    "modes": c.modes,
                }
                for c in self._connections.values()
            ],
            "operating_modes": list(self._modes.values()),
        }
