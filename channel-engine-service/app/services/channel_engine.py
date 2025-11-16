"""
ChannelEngine Service Wrapper
Provides high-level interface to ChannelEngine for OTA testing
"""

import sys
import os
from typing import Dict, List, Tuple, Optional
import numpy as np

# Add ChannelEgine to Python path
CHANNEL_ENGINE_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../../ChannelEgine"
)
sys.path.insert(0, os.path.abspath(CHANNEL_ENGINE_PATH))

from channel_model_38901.simulator import ChannelSimulator
from app.models.ota_models import (
    ProbeWeightRequest,
    ProbeWeightResponse,
    ProbeWeight,
    ComplexWeight,
    ChannelStatistics
)


class ChannelEngineService:
    """
    ChannelEngine服务封装类
    负责调用ChannelEngine并计算探头权重
    """

    def __init__(self):
        """初始化服务"""
        self.version = "1.0.0"
        # 保存原始工作目录
        self.original_cwd = os.getcwd()
        # ChannelEgine工作目录（包含参数文件）
        self.channel_engine_cwd = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../ChannelEgine")
        )

    def _run_in_channel_engine_context(self, func):
        """在ChannelEngine工作目录上下文中运行函数"""
        original_dir = os.getcwd()
        try:
            os.chdir(self.channel_engine_cwd)
            return func()
        finally:
            os.chdir(original_dir)

    def check_availability(self) -> bool:
        """检查ChannelEngine是否可用"""
        def _check():
            try:
                # 尝试创建一个简单的模拟器实例
                simulator = ChannelSimulator(
                    scenario_name='UMa',
                    center_frequency_hz=3.5e9
                )
                return True
            except Exception as e:
                print(f"ChannelEngine不可用: {e}")
                return False

        return self._run_in_channel_engine_context(_check)

    def generate_probe_weights(
        self,
        request: ProbeWeightRequest
    ) -> ProbeWeightResponse:
        """
        生成探头权重

        算法概述:
        1. 使用ChannelEngine生成3GPP信道模型
        2. 提取簇的AoA/AoD信息
        3. 计算每个探头与簇方向的匹配度
        4. 归一化权重

        Args:
            request: 探头权重请求

        Returns:
            ProbeWeightResponse: 计算结果
        """
        def _generate():
            try:
                # 1. 创建ChannelEngine模拟器
                frequency_hz = request.scenario.frequency_mhz * 1e6

                simulator = ChannelSimulator(
                    scenario_name=request.scenario.scenario_type,
                    cluster_model_name=request.scenario.cluster_model,
                    center_frequency_hz=frequency_hz,
                    use_median_lsps=request.scenario.use_median_lsps
                )

                # 2. 运行信道仿真
                results = simulator.run()

                # 3. 提取信道统计信息
                channel_stats = self._extract_channel_statistics(results)

                # 4. 计算探头权重
                probe_weights = self._calculate_probe_weights(
                    request.probe_array,
                    results,
                    request.mimo_config
                )

                return ProbeWeightResponse(
                    probe_weights=probe_weights,
                    channel_statistics=channel_stats,
                    success=True,
                    message=f"成功生成 {len(probe_weights)} 个探头权重"
                )

            except Exception as e:
                # 错误处理：返回失败响应
                return ProbeWeightResponse(
                    probe_weights=[],
                    channel_statistics=ChannelStatistics(
                        pathloss_db=0.0,
                        num_clusters=0
                    ),
                    success=False,
                    message=f"权重计算失败: {str(e)}"
                )

        return self._run_in_channel_engine_context(_generate)

    def _extract_channel_statistics(
        self,
        results: Dict
    ) -> ChannelStatistics:
        """从ChannelEngine结果中提取统计信息"""

        # 提取基本信息
        pathloss_db = results.get('pathloss_db', 0.0)

        # 提取LSP信息（如果可用）
        lsp = results.get('lsp', {})
        rms_delay_spread_ns = lsp.get('rms_delay_spread', None)
        if rms_delay_spread_ns is not None:
            rms_delay_spread_ns *= 1e9  # 转换为纳秒

        angular_spread_deg = lsp.get('azimuth_spread_arrival', None)

        # 信道条件
        condition = results.get('los_condition', 'UNKNOWN')

        # 簇数量
        cluster_powers = results.get('cluster_powers', [])
        num_clusters = len(cluster_powers) if cluster_powers is not None else 0

        return ChannelStatistics(
            pathloss_db=float(pathloss_db),
            rms_delay_spread_ns=float(rms_delay_spread_ns) if rms_delay_spread_ns else None,
            angular_spread_deg=float(angular_spread_deg) if angular_spread_deg else None,
            condition=condition,
            num_clusters=num_clusters
        )

    def _calculate_probe_weights(
        self,
        probe_array,
        channel_results: Dict,
        mimo_config
    ) -> List[ProbeWeight]:
        """
        计算探头权重

        简化算法（Phase 1 MVP）:
        1. 提取簇的角度信息（AoA）
        2. 计算每个探头与簇的角度匹配度
        3. 基于匹配度分配权重

        未来增强:
        - 考虑极化匹配
        - 多径相位对齐
        - 功率归一化优化
        """

        # 提取簇信息
        cluster_aoa_deg = channel_results.get('cluster_aoa_deg', [])
        cluster_powers = channel_results.get('cluster_powers', [])

        # 如果没有簇信息，使用均匀权重
        if not cluster_aoa_deg or not cluster_powers:
            return self._uniform_weights(probe_array)

        probe_weights = []

        for probe_pos in probe_array.probe_positions:
            # 计算探头权重
            weight_magnitude, weight_phase = self._compute_single_probe_weight(
                probe_theta=probe_pos.theta,
                probe_phi=probe_pos.phi,
                cluster_aoa_deg=cluster_aoa_deg,
                cluster_powers=cluster_powers
            )

            probe_weights.append(ProbeWeight(
                probe_id=probe_pos.probe_id,
                polarization=probe_pos.polarization,
                weight=ComplexWeight(
                    magnitude=weight_magnitude,
                    phase_deg=weight_phase
                ),
                enabled=True
            ))

        # 归一化权重
        probe_weights = self._normalize_weights(probe_weights)

        return probe_weights

    def _compute_single_probe_weight(
        self,
        probe_theta: float,
        probe_phi: float,
        cluster_aoa_deg: List[float],
        cluster_powers: List[float]
    ) -> Tuple[float, float]:
        """
        计算单个探头的权重

        Args:
            probe_theta: 探头天顶角 (degrees)
            probe_phi: 探头方位角 (degrees)
            cluster_aoa_deg: 簇的到达角 (degrees)
            cluster_powers: 簇的功率 (linear)

        Returns:
            (magnitude, phase_deg): 权重幅度和相位
        """

        # 计算探头与每个簇的角度差异
        total_weight = 0.0
        weighted_phase = 0.0

        for aoa, power in zip(cluster_aoa_deg, cluster_powers):
            # 简化：只考虑方位角差异
            angle_diff = abs(probe_phi - aoa)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff

            # 角度匹配因子（越小越好）
            # 使用高斯函数：exp(-(angle_diff/sigma)^2)
            sigma = 30.0  # 角度标准差
            match_factor = np.exp(-(angle_diff / sigma) ** 2)

            # 权重 = 功率 × 匹配因子
            weight_contribution = power * match_factor
            total_weight += weight_contribution

            # 相位：基于角度差异的简化相位
            # 实际实现中应考虑波长和距离
            phase_contribution = angle_diff * (power / sum(cluster_powers))
            weighted_phase += phase_contribution

        # 归一化
        magnitude = min(total_weight / max(cluster_powers), 1.0)
        phase_deg = weighted_phase % 360

        return magnitude, phase_deg

    def _uniform_weights(self, probe_array) -> List[ProbeWeight]:
        """生成均匀权重（后备方案）"""
        uniform_magnitude = 1.0 / np.sqrt(probe_array.num_probes)

        weights = []
        for probe_pos in probe_array.probe_positions:
            weights.append(ProbeWeight(
                probe_id=probe_pos.probe_id,
                polarization=probe_pos.polarization,
                weight=ComplexWeight(
                    magnitude=uniform_magnitude,
                    phase_deg=0.0
                ),
                enabled=True
            ))

        return weights

    def _normalize_weights(
        self,
        probe_weights: List[ProbeWeight]
    ) -> List[ProbeWeight]:
        """归一化探头权重，使总功率为1"""

        # 计算总功率
        total_power = sum(w.weight.magnitude ** 2 for w in probe_weights)

        if total_power == 0:
            return probe_weights

        # 归一化因子
        norm_factor = np.sqrt(total_power)

        # 应用归一化
        for weight in probe_weights:
            weight.weight.magnitude /= norm_factor

        return probe_weights
