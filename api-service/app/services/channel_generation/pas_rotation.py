"""
Automatic PAS Rotation (功率角度谱自动旋转对齐)

实现 GCM Tool 中 "Automatic PAS Rotation" 等价功能。

物理原理:
=========
在多探头暗室中，信道模型的多径簇 (Cluster) 在空间中有确定的到达方位角 (AoA)。
如果最强簇的 AoA 刚好落在两个物理探头之间的缝隙，暗室的空间采样误差将被放大，
导致静区中合成的电磁场出现显著畸变。

算法流程:
=========
1. 找到 CDL 模型中功率最大的簇 (strongest cluster)
2. 获取该簇的到达方位角 AoA_max
3. 在探头阵列中找到距离 AoA_max 最近的物理探头方位角 Probe_az
4. 计算旋转偏移量: Δφ = Probe_az - AoA_max
5. 将所有簇的 AoA 旋转 Δφ (整体平移)
6. 输出 Δφ 供转台进行反向补偿

参考:
=====
- Keysight PROPSIM F64 GCM Tool User Guide, Section "OTA Settings"
- 3GPP TR 37.977, Annex A: "MPAC probe placement considerations"
"""

import logging
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PASRotationResult:
    """PAS 旋转结果"""
    rotation_offset_deg: float
    strongest_cluster_index: int
    strongest_cluster_aoa_deg: float
    nearest_probe_azimuth_deg: float
    nearest_probe_id: int
    applied: bool = True

    def to_dict(self):
        return {
            "rotation_offset_deg": self.rotation_offset_deg,
            "strongest_cluster_index": self.strongest_cluster_index,
            "strongest_cluster_aoa_deg": self.strongest_cluster_aoa_deg,
            "nearest_probe_azimuth_deg": self.nearest_probe_azimuth_deg,
            "nearest_probe_id": self.nearest_probe_id,
            "applied": self.applied,
        }


def _angular_distance(a_deg: float, b_deg: float) -> float:
    """
    计算两个角度之间的最短弧度距离 (处理 0°/360° 边界)

    Returns:
        距离 (度), 范围 [0, 180]
    """
    diff = (a_deg - b_deg) % 360
    if diff > 180:
        diff = 360 - diff
    return diff


def _signed_angular_diff(target_deg: float, source_deg: float) -> float:
    """
    计算从 source 到 target 的带符号角度差

    Returns:
        差值 (度), 范围 [-180, 180]
    """
    diff = (target_deg - source_deg) % 360
    if diff > 180:
        diff -= 360
    return diff


def align_pas_to_nearest_probe(
    cluster_aoa_degs: List[float],
    cluster_powers_linear: List[float],
    probe_azimuths_deg: List[float],
    probe_ids: Optional[List[int]] = None,
) -> Tuple[List[float], PASRotationResult]:
    """
    将功率角度谱 (PAS) 旋转对齐到最近的物理探头。

    这是 GCM Tool "Automatic PAS Rotation" 的精确等价实现。

    Args:
        cluster_aoa_degs: 各簇的到达方位角列表 (度)
        cluster_powers_linear: 各簇的功率 (线性标度, 非 dB)
        probe_azimuths_deg: 物理探头的方位角列表 (度)
        probe_ids: 探头 ID 列表 (可选, 用于日志)

    Returns:
        (rotated_aoa_degs, result):
        - rotated_aoa_degs: 旋转后的各簇 AoA 列表
        - result: PASRotationResult 元数据

    Example:
        >>> aoas = [45.0, 120.0, 200.0]
        >>> powers = [0.5, 1.0, 0.3]  # 第2个簇最强
        >>> probes = [0, 22.5, 45, 67.5, 90, 112.5, 135, ...]
        >>> rotated, info = align_pas_to_nearest_probe(aoas, powers, probes)
        # 最强簇 AoA=120° 会被对齐到最近探头 112.5°
        # 旋转量 Δφ = 112.5 - 120 = -7.5°
    """
    if not cluster_aoa_degs or not cluster_powers_linear:
        logger.warning("[PAS Rotation] 空簇列表，跳过旋转")
        return cluster_aoa_degs, PASRotationResult(
            rotation_offset_deg=0.0,
            strongest_cluster_index=0,
            strongest_cluster_aoa_deg=0.0,
            nearest_probe_azimuth_deg=0.0,
            nearest_probe_id=0,
            applied=False,
        )

    if not probe_azimuths_deg:
        logger.warning("[PAS Rotation] 无探头方位角数据，跳过旋转")
        return cluster_aoa_degs, PASRotationResult(
            rotation_offset_deg=0.0,
            strongest_cluster_index=0,
            strongest_cluster_aoa_deg=cluster_aoa_degs[0],
            nearest_probe_azimuth_deg=0.0,
            nearest_probe_id=0,
            applied=False,
        )

    # --- Step 1: 找最强簇 ---
    max_power = -1.0
    strongest_idx = 0
    for i, power in enumerate(cluster_powers_linear):
        if power > max_power:
            max_power = power
            strongest_idx = i

    strongest_aoa = cluster_aoa_degs[strongest_idx]

    # --- Step 2: 找最近探头 ---
    min_dist = 999.0
    nearest_probe_idx = 0
    for i, probe_az in enumerate(probe_azimuths_deg):
        dist = _angular_distance(strongest_aoa, probe_az)
        if dist < min_dist:
            min_dist = dist
            nearest_probe_idx = i

    nearest_probe_az = probe_azimuths_deg[nearest_probe_idx]
    nearest_id = (probe_ids[nearest_probe_idx]
                  if probe_ids and nearest_probe_idx < len(probe_ids)
                  else nearest_probe_idx)

    # --- Step 3: 计算旋转偏移 ---
    rotation_offset = _signed_angular_diff(nearest_probe_az, strongest_aoa)

    # --- Step 4: 应用旋转 ---
    rotated_aoas = [
        (aoa + rotation_offset) % 360.0
        for aoa in cluster_aoa_degs
    ]

    result = PASRotationResult(
        rotation_offset_deg=rotation_offset,
        strongest_cluster_index=strongest_idx,
        strongest_cluster_aoa_deg=strongest_aoa,
        nearest_probe_azimuth_deg=nearest_probe_az,
        nearest_probe_id=nearest_id,
        applied=True,
    )

    logger.info(
        f"[PAS Rotation] 最强簇 #{strongest_idx} "
        f"(AoA={strongest_aoa:.1f}°, power={max_power:.4f}) "
        f"→ 对齐到探头 #{nearest_id} "
        f"(Az={nearest_probe_az:.1f}°), "
        f"旋转偏移 Δφ={rotation_offset:+.2f}°"
    )

    return rotated_aoas, result
