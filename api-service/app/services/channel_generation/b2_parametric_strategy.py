"""B-2 参数化 TDL 注入策略 (P2-14 — 能力门 + CE 聚类→参数表接线).

B-2 路: ChannelEgine `geometric_native_fit` 把 RT 射线聚成 native 可表示簇 + §6 路径
判决 → per-tap 参数表 (native 谱/质心/展宽/角度) → `.tap` → F64 硬件实时衰落
(绕开 F64 无 custom PSD, 免奈奎斯特覆盖全 f_D,max)。

落地分层:
  - 能力门: channelEmulator 须支持 `PARAMETRIC_TDL` 加载 (否则 fail-loud)。
  - 聚类 → 参数表 (PR-5): 提取 RT 射线 → CE 微服务 `cluster_b2_native` → per-tap 参数表。
  - `.tap` 字节生成 (**Channel Studio 专有格式**, 手册 §21: 无公开格式) + F64 加载在
    **现场**落地 (V1.0 §9); 真实 RT 射线数据接入也需 RT-Release / 现场。

设计: docs/design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md §6-§9。
"""

import logging
from typing import Any, Dict, List, TYPE_CHECKING

from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode
from app.services.channel_generation.base_generator import BaseChannelGenerator

if TYPE_CHECKING:
    # Lazy: 避免 channel_engine_client → channel_generation 循环 import
    from app.services.channel_engine_client import ChannelEngineClient

logger = logging.getLogger(__name__)


class B2ParametricTdlStrategy(BaseChannelGenerator):
    """B-2 参数化 TDL 策略: 能力门 + CE 聚类→参数表接线; .tap 字节 + F64 加载现场。"""

    def __init__(
        self,
        emulator: ChannelEmulatorDriver,
        ce_client: "ChannelEngineClient",
        chamber_config: Any,
        calibration_entries: List[Dict],
    ):
        super().__init__(emulator, chamber_config, calibration_entries)
        self.ce_client = ce_client

    def supports_parametric_tdl(self) -> bool:
        """channelEmulator 是否支持 PARAMETRIC_TDL (.tap/.rtc) 加载。"""
        return ChannelLoadMode.PARAMETRIC_TDL in self.emulator.get_supported_load_modes()

    @staticmethod
    def _extract_rt_rays(cdl_model_data: Dict[str, Any]) -> List[Dict]:
        """从 cdl_model_data 提取真实 RT 射线 (MPC)。真实 RT 子径需 RT-Release / 现场
        接入; 当前 standard CDL 路无子径 → 返回空 → 上层 fail-loud (不臆造假子径)。"""
        return cdl_model_data.get("rt_rays") or []

    async def generate_and_load(
        self,
        simulation_rules: Dict[str, Any],
        cdl_model_data: Dict[str, Any],
    ) -> bool:
        # ── 能力门: 仪器须支持参数化 TDL 加载 ──
        if not self.supports_parametric_tdl():
            supported = [m.value for m in self.emulator.get_supported_load_modes()]
            logger.error(
                "[B2ParametricTdl] channelEmulator (%s) 不支持 PARAMETRIC_TDL (.tap/.rtc); "
                "engine_mode=B2_PARAMETRIC_TDL 无法执行。支持的加载模式: %s",
                type(self.emulator).__name__, supported,
            )
            return False

        # ── RT 射线: B-2 native-fit 聚类的输入 (真实 RT 子径) ──
        rt_rays = self._extract_rt_rays(cdl_model_data)
        if not rt_rays:
            logger.error(
                "[B2ParametricTdl] B-2 需 RT 射线 (MPC) 做 native-fit 聚类, 但 cdl_model_data "
                "无 rt_rays — 真实 RT 子径数据需 RT-Release / 现场接入 (standard CDL 路无子径); "
                "session=%s model=%s",
                cdl_model_data.get("session_id"), cdl_model_data.get("model_name"),
            )
            return False

        # ── CE 微服务: RT 射线 → geometric_native_fit 聚类 + §6 判决 → per-tap 参数表 ──
        result = await self.ce_client.cluster_b2_native(
            rt_rays=rt_rays,
            ue_velocity_mps=simulation_rules.get("ue_velocity_mps") or (0.0, 0.0, 0.0),
            center_frequency_hz=simulation_rules.get("frequency_hz", 3.5e9),
            test_class=cdl_model_data.get("test_class", "throughput_psd"),
            f64_profile=cdl_model_data.get("f64_profile"),
        )
        if not result.success:
            logger.error("[B2ParametricTdl] CE B-2 聚类/判决失败: %s", result.message)
            return False

        # ── §6 判决分流 (Codex P2 #169): CE 返回 200 + 有效判决可能是 B1_baked /
        # GCM_native (如 isac_sensing 低质心, 或 throughput 超 tap budget 退烘焙路),
        # 此时 tap_params 为空、note 指向烘焙/GCM 路。这些是【有效的"不走 B-2"判决】,
        # 不能当 B-2 参数化成功 (否则日志自相矛盾 "参数表就绪 target_path=B1_baked 0 taps")。
        # 本 strategy 只负责 B-2 参数化路 → 非 B2_parametric 判决 fail-loud, 提示配置矛盾;
        # 完整动态跨路分流编排 (B1_baked→ASC / GCM_native→GCM) 见 roadmap P2-14 backlog。──
        if result.target_path != "B2_parametric":
            _hint = {"B1_baked": "mimo_first_asc",
                     "GCM_native": "keysight_gcm"}.get(result.target_path, "对应引擎")
            logger.error(
                "[B2ParametricTdl] §6 判决 target_path=%s (clustering=%s) 非 B2_parametric "
                "—— 该场景应走 %s 路, 但 TestCase engine_mode=b2_parametric_tdl 配置矛盾。请改 "
                "TestCase engine_mode=%s, 或等动态分流编排 (roadmap P2-14)。reason: %s",
                result.target_path, result.clustering_algo, result.target_path, _hint,
                result.reason,
            )
            return False

        # ── B2_parametric: 参数表就绪。.tap 字节 (Channel Studio 专有, 手册 §21) +
        # F64 加载 → 现场 ──
        logger.warning(
            "[B2ParametricTdl] B-2 参数表就绪: target_path=%s, %d taps (%s)。"
            ".tap 字节生成需现场 Channel Studio (手册 §21: .tap 专有格式无法离线生成) "
            "+ F64 加载; 当前不返回 True (现场落地)。note: %s",
            result.target_path, len(result.tap_params), result.clustering_algo, result.note,
        )
        return False
