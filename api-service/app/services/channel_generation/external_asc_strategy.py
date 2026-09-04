"""
外部 ASC 路径策略 (Operator-Provided .asc Bundle, debug-only)

操作员在本机跑 ChannelEgine `app.py` (Streamlit) 或 `gui.py` (Tkinter) 产出
一组 `channel_InX_OutY.asc` 文件; 这条策略跳过 channel-engine-service 直接
读那个目录, 通过 HAL 统一接口上传到信道仿真器。

用途 (2026-05-18 P0-7):
- 调试隔离: 出 bug 时操作员用 ChannelEgine GUI 产 known-good .asc 喂进
  MIMO-First, 立刻分辨问题在 MIMO-First 端还是集成链路
- 应急兜底: channel-engine-service 不可用时仍能完成 commissioning
- 厂区灵活性: 操作员不需要每改一次 CDL 都重启微服务

跟 ExternalWaveformStrategy 区别: 那条策略调微服务自动生成, 这条策略读
操作员手工产出的本地目录。metadata 都要填 (audit trail), 但 ExternalAsc
不传 metadata 给 ChannelEgine (因为根本不调用)。
"""

import logging
import os
from typing import Any, Dict, List

from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode
from app.services.channel_generation.base_generator import BaseChannelGenerator

logger = logging.getLogger(__name__)


class ExternalAscPathStrategy(BaseChannelGenerator):
    """读操作员本机 .asc 目录, 通过 HAL 装载, 不调微服务."""

    def __init__(
        self,
        emulator: ChannelEmulatorDriver,
        chamber_config: Any,
        calibration_entries: List[Dict],
        asc_source_path: str,
        *,
        operation_recorder: Any | None = None,
    ):
        super().__init__(emulator, chamber_config, calibration_entries)
        self.asc_source_path = asc_source_path
        self._operation_recorder = operation_recorder

    async def _invoke_channel_operation(self, **kwargs: Any) -> Any:
        if self._operation_recorder is None:
            return await kwargs["invoke"]()
        return await self._operation_recorder(**kwargs)

    async def generate_and_load(
        self,
        simulation_rules: Dict[str, Any],
        cdl_model_data: Dict[str, Any],
    ) -> bool:
        logger.info(
            f"[ExternalAscPath Strategy] Reading operator-provided ASC bundle "
            f"from {self.asc_source_path}"
        )

        # 路径校验在 schema validator 已经做了 (config.py), 这里再做一遍
        # 防御性 check 因为 schema 校验可能被绕过 (legacy migration / raw POST)
        if not os.path.isdir(self.asc_source_path):
            logger.error(
                f"[ExternalAscPath Strategy] asc_source_path is not a directory: "
                f"{self.asc_source_path!r}"
            )
            return False

        asc_files = [
            f for f in os.listdir(self.asc_source_path) if f.endswith(".asc")
        ]
        if not asc_files:
            logger.error(
                f"[ExternalAscPath Strategy] No .asc files in "
                f"{self.asc_source_path!r}"
            )
            return False

        logger.info(
            f"[ExternalAscPath Strategy] Found {len(asc_files)} .asc files; "
            f"handing off to HAL EXTERNAL_WAVEFORM load"
        )

        # HAL load — 跟 ExternalWaveformStrategy 走同一接口, 只是 waveform_dir
        # 来源不同。F64 driver 内部用 FTP 上传到 D:\User Emulations\<session>\
        model_name = cdl_model_data.get("model_name", "external-asc-bundle")
        scenario = cdl_model_data.get("scenario", "operator-supplied")
        success = await self._invoke_channel_operation(
            phase="load",
            operation="load_channel",
            requested={
                "load_mode": ChannelLoadMode.EXTERNAL_WAVEFORM.value,
                "model_name": model_name,
                "scenario": scenario,
                "waveform_dir": self.asc_source_path,
            },
            invoke=lambda: self.emulator.load_channel(
                mode=ChannelLoadMode.EXTERNAL_WAVEFORM,
                model_name=model_name,
                scenario=scenario,
                parameters=simulation_rules,
                waveform_dir=self.asc_source_path,
            ),
        )

        if success:
            logger.info(
                f"[ExternalAscPath Strategy] Operator ASC bundle staged in "
                f"emulator (source: {self.asc_source_path})"
            )
        else:
            logger.error(
                f"[ExternalAscPath Strategy] HAL load_channel returned False "
                f"for {self.asc_source_path}"
            )
        return success
