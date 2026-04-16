"""
3GPP Static MIMO OTA Commissioning Service

首次暗室验证的 5 阶段编排引擎。
复用已有成熟组件: HAL, ChannelEngineClient, 校准服务, 补偿计算。

阶段:
1. 系统预检 (仪器 + 校准 + QZ)
2. 参考天线基线测量
3. 静态 MIMO 吞吐量测试 (核心)
4. 数据分析与 CTIA 判定
5. 报告生成与归档
"""

import asyncio
import logging
import math
import random
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.models.chamber import ChamberConfiguration
from app.models.probe_calibration import ProbePathLossCalibration, CalibrationStatus
from sqlalchemy.orm import Session

from app.services.commissioning_config import (
    CommissioningPhase,
    PhaseStatus,
    Verdict,
    StaticMIMOConfig,
    CTIACriteria,
    CommissioningState,
    PrecheckResult,
    ReferenceMeasurement,
    AzimuthMeasurement,
    MIMOTestResult,
    AnalysisResult,
)

logger = logging.getLogger(__name__)

# 全局会话存储 (内存, 单实例)
_sessions: Dict[str, CommissioningState] = {}


class CommissioningService:
    """
    3GPP 静态 MIMO OTA 首测编排服务

    每个会话 (session) 跟踪一次完整的首测流程。
    各阶段可逐步手动触发, 也可一键执行全流程。
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    # ==================== 会话管理 ====================

    def create_session(
        self,
        config: Optional[StaticMIMOConfig] = None,
        criteria: Optional[CTIACriteria] = None,
    ) -> CommissioningState:
        """创建新的首测会话"""
        session_id = str(uuid.uuid4())[:8]
        state = CommissioningState(
            session_id=session_id,
            config=config or StaticMIMOConfig(),
            criteria=criteria or CTIACriteria(),
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        _sessions[session_id] = state
        logger.info(f"Commissioning session created: {session_id}")
        return state

    def get_session(self, session_id: str) -> Optional[CommissioningState]:
        """获取会话状态"""
        return _sessions.get(session_id)

    def list_sessions(self):
        """列出所有会话"""
        return list(_sessions.values())

    # ==================== Phase 1: 系统预检 ====================

    async def phase1_system_precheck(
        self, session_id: str
    ) -> PrecheckResult:
        """
        阶段 1: 系统预检

        检查项:
        - 仪器连通性 (HAL health check)
        - 校准有效性 (path loss, phase calibration)
        - 静区质量 (QZ ripple)
        """
        state = self._get_state(session_id)
        state.phase = CommissioningPhase.PRECHECK
        state.phase_statuses[CommissioningPhase.PRECHECK] = PhaseStatus.RUNNING

        result = PrecheckResult()
        messages = []

        try:
            # --- 查询数据库中的暗室系统配置 ---
            if not self.db:
                raise ValueError("Database session is required to query chamber config")
                
            chamber = self.db.query(ChamberConfiguration).filter(
                ChamberConfiguration.is_active == True
            ).first()
            
            if not chamber:
                result.overall_pass = False
                result.messages.append("错误: 数据库中未找到任何活跃的暗室配置 (ChamberConfiguration)！")
                state.precheck = result
                state.phase_statuses[CommissioningPhase.PRECHECK] = PhaseStatus.FAILED
                return result
                
            result.chamber_id = chamber.name
            messages.append(f"暗室配置就绪: {chamber.name} ({chamber.num_probes} probes)")

            # --- 仪器连通性检查 (Mock) ---
            await asyncio.sleep(0.1)  # simulate HAL check
            result.instruments_online = {
                "base_station_emulator": True,
                "channel_emulator": True,
                "signal_analyzer": True,
                "positioner": True,  # 转台: 已接入 IPositioner
            }
            online_count = sum(1 for v in result.instruments_online.values() if v)
            total_count = len(result.instruments_online)
            messages.append(
                f"仪器状态: {online_count}/{total_count} 在线"
            )

            # --- 校准有效性检查 (实查 DB) ---
            from sqlalchemy import desc
            # SQLite 存储 UUID 为不带连字符的 hex 字符串，需要统一格式
            chamber_id_hex = chamber.id.hex if hasattr(chamber.id, 'hex') else str(chamber.id).replace('-', '')
            latest_cal = self.db.query(ProbePathLossCalibration).filter(
                ProbePathLossCalibration.chamber_id == chamber_id_hex,
                ProbePathLossCalibration.status == CalibrationStatus.VALID.value
            ).order_by(desc(ProbePathLossCalibration.calibrated_at)).first()
            
            if latest_cal:
                result.calibration_valid = True
                age_hours = (datetime.utcnow() - latest_cal.calibrated_at).total_seconds() / 3600.0
                result.calibration_age_hours = age_hours
                messages.append(
                    f"校准数据: 已关联真实数据 (距上次校准 {result.calibration_age_hours:.1f}h)"
                )
            else:
                result.calibration_valid = False
                messages.append(
                    f"警告: 该暗室没有有效的校准数据，将 Fallback 到系统默认线缆衰减！"
                )

            # --- 静区质量检查 (Mock) ---
            await asyncio.sleep(0.1)
            result.quiet_zone_ripple_db = 0.7  # Mock: +/-0.7 dB
            result.quiet_zone_pass = (
                result.quiet_zone_ripple_db <= state.criteria.max_quiet_zone_ripple_db
            )
            messages.append(
                f"静区质量: ripple = +/-{result.quiet_zone_ripple_db:.1f} dB "
                f"({'PASS' if result.quiet_zone_pass else 'FAIL'}, "
                f"门限 +/-{state.criteria.max_quiet_zone_ripple_db:.1f} dB)"
            )

            # --- 总判定 ---
            critical_instruments = ["base_station_emulator", "channel_emulator"]
            critical_online = all(
                result.instruments_online.get(k, False)
                for k in critical_instruments
            )
            result.overall_pass = (
                critical_online
                and result.calibration_valid
                and result.quiet_zone_pass
            )

            result.messages = messages
            state.precheck = result
            state.phase_statuses[CommissioningPhase.PRECHECK] = (
                PhaseStatus.COMPLETED if result.overall_pass else PhaseStatus.FAILED
            )

            logger.info(
                f"[{session_id}] Phase 1 complete: "
                f"{'PASS' if result.overall_pass else 'FAIL'}"
            )

        except Exception as e:
            logger.exception(f"[{session_id}] Phase 1 failed: {e}")
            result.overall_pass = False
            result.messages.append(f"异常: {str(e)}")
            state.phase_statuses[CommissioningPhase.PRECHECK] = PhaseStatus.FAILED
            state.precheck = result

        return result

    # ==================== Phase 2: 参考测量 ====================

    async def phase2_wait_for_antenna(
        self, session_id: str
    ) -> ReferenceMeasurement:
        """
        阶段 2 (第一步): 进入等待状态, 提示工程师手动安装标准增益喇叭天线
        """
        state = self._get_state(session_id)
        state.phase = CommissioningPhase.REFERENCE
        state.phase_statuses[CommissioningPhase.REFERENCE] = PhaseStatus.WAITING

        result = ReferenceMeasurement(
            antenna_model=state.config.reference_antenna_model,
            antenna_gain_dbi=state.config.reference_antenna_gain_dbi,
            confirmed=False,
        )
        state.reference = result
        logger.info(f"[{session_id}] Phase 2: WAITING for reference antenna installation")
        return result

    async def phase2_reference_measurement(
        self, session_id: str
    ) -> ReferenceMeasurement:
        """
        阶段 2 (第二步): 工程师确认后，进行参考天线基线测量
        """
        state = self._get_state(session_id)
        state.phase = CommissioningPhase.REFERENCE
        state.phase_statuses[CommissioningPhase.REFERENCE] = PhaseStatus.RUNNING

        result = state.reference or ReferenceMeasurement(
            antenna_model=state.config.reference_antenna_model,
            antenna_gain_dbi=state.config.reference_antenna_gain_dbi,
        )

        try:
            # 模拟 TRP 测量
            await asyncio.sleep(1.0)

            # Mock: 参考 TRP 测量值
            result.measured_trp_dbm = 23.5 + random.gauss(0, 0.3)
            result.compensation_factor_db = (
                result.antenna_gain_dbi - (result.measured_trp_dbm - 23.0)
            )
            result.confirmed = True

            state.reference = result
            state.phase_statuses[CommissioningPhase.REFERENCE] = PhaseStatus.COMPLETED

            logger.info(
                f"[{session_id}] Phase 2 complete: "
                f"TRP={result.measured_trp_dbm:.1f} dBm, "
                f"compensation={result.compensation_factor_db:.1f} dB"
            )

        except Exception as e:
            logger.exception(f"[{session_id}] Phase 2 failed: {e}")
            state.phase_statuses[CommissioningPhase.REFERENCE] = PhaseStatus.FAILED
            state.reference = result

        return result

    # ==================== Phase 3: MIMO 测试 (核心) ====================

    async def phase3_static_mimo_test(
        self, session_id: str
    ) -> MIMOTestResult:
        """
        阶段 3: 静态 MIMO 吞吐量测试

        流程:
        1. 调用 ChannelEngineClient 生成 CDL-C .asc 文件
        2. HAL 上传 .asc 到信道仿真器
        3. 配置基站仿真器
        4. 逐方位测量 KPI (调用 IPositioner 控制转台)
        """
        state = self._get_state(session_id)
        config = state.config
        state.phase = CommissioningPhase.MIMO_TEST
        state.phase_statuses[CommissioningPhase.MIMO_TEST] = PhaseStatus.RUNNING

        from app.hal.positioner import MockPositioner
        from app.services.channel_engine_client import ChannelEngineClient, CDLCluster
        
        positioner = MockPositioner(None, "MOCK_POS")
        await positioner.initialize()

        if not self.db:
            state.phase_statuses[CommissioningPhase.MIMO_TEST] = PhaseStatus.FAILED
            raise ValueError("Database session is required to run Channel Engine")
            
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.is_active == True
        ).first()
        
        if not chamber:
            state.phase_statuses[CommissioningPhase.MIMO_TEST] = PhaseStatus.FAILED
            raise ValueError("No active chamber configuration found in DB")

        result = MIMOTestResult(
            cdl_model_name=config.cdl_model_name,
            frequency_ghz=config.frequency_hz / 1e9,
            mimo_config=f"{config.mimo_layers}x{config.mimo_layers}",
        )

        try:
            # --- Step 1: Real Channel Generation Pipeline (Parallel Mechanism) ---
            logger.info(f"[{session_id}] Requesting Channel Generation pipeline [Mode: {config.engine_mode}] for CDL model: {config.cdl_model_name}")
            
            from app.hal.propsim_f64 import PropsimF64Controller
            from app.services.channel_generation.gcm_strategy import PropsimNativeGCMStrategy
            from app.services.channel_generation.asc_strategy import MimoEngineASCStrategy
            from app.services.channel_generation.base_generator import EngineMode
            
            ce_client = ChannelEngineClient(self.db)
            f64_controller = PropsimF64Controller()
            
            # Retrieve calibration entries prior to passing to generators
            calibration_entries = ce_client._query_calibration_entries(chamber.id, config.frequency_hz, chamber)
            
            generator = None
            if config.engine_mode == EngineMode.GCM_NATIVE:
                generator = PropsimNativeGCMStrategy(f64_controller, chamber, calibration_entries)
            else:
                generator = MimoEngineASCStrategy(f64_controller, ce_client, chamber, calibration_entries)
            
            # Execute physical generation and load
            sim_rules_dict = {
                "frequency_hz": config.frequency_hz,
                "target_tx_power_dbm": config.target_tx_power_dbm,
                "target_rsrp_dbm": config.target_rsrp_dbm,
                "target_snr_db": config.target_snr_db,
            }
            cdl_model_data_dict = {
                "model_name": config.cdl_model_name,
                "session_id": session_id
            }
            generation_success = await generator.generate_and_load(sim_rules_dict, cdl_model_data_dict)
            
            if not generation_success:
                error_msg = f"Channel Generation Failed for Mode: {config.engine_mode}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
            logger.info(f"[{session_id}] CE Success! Hardware loaded in {config.engine_mode} mode.")
            result.asc_files_loaded = True
            
            # 使用目标 RSRP 作为后续数学模拟的基准线
            ce_base_rsrp = config.target_rsrp_dbm

            # --- Step 2: 逐方位测量 ---
            start_time = asyncio.get_event_loop().time()

            for azimuth in config.azimuths_deg:
                logger.info(f"[{session_id}] Moving positioner to azimuth {azimuth}°")

                # 调用 IPositioner
                await positioner.move_to_azimuth(azimuth)
                await positioner.wait_until_settled(timeout_s=10.0)
                
                # 模拟信道稳定
                await asyncio.sleep(config.settling_time_s)

                # 模拟 KPI 采样
                samples_rsrp = []
                samples_sinr = []
                samples_tput = []
                samples_ri = []

                for _ in range(min(config.num_samples_per_azimuth, 20)):
                    # 根据真实的 CE 目标功率做偏移模拟
                    az_factor = math.cos(math.radians(azimuth)) * 0.1
                    rsrp = ce_base_rsrp + az_factor * 5 + random.gauss(0, 0.5)
                    sinr = config.target_snr_db + az_factor * 3 + random.gauss(0, 0.8)
                    tput = max(0, 420.0 + az_factor * 30 + random.gauss(0, 15))
                    ri = min(2.0, max(1.0, 1.9 + random.gauss(0, 0.1)))

                    samples_rsrp.append(rsrp)
                    samples_sinr.append(sinr)
                    samples_tput.append(tput)
                    samples_ri.append(ri)

                    await asyncio.sleep(0.02)  # 模拟采样间隔

                # 汇总
                az_result = AzimuthMeasurement(
                    azimuth_deg=azimuth,
                    rsrp_dbm=sum(samples_rsrp) / len(samples_rsrp),
                    sinr_db=sum(samples_sinr) / len(samples_sinr),
                    throughput_mbps=sum(samples_tput) / len(samples_tput),
                    rank_indicator=sum(samples_ri) / len(samples_ri),
                    num_samples=len(samples_rsrp),
                    rsrp_std_db=self._std(samples_rsrp),
                    sinr_std_db=self._std(samples_sinr),
                    throughput_std_mbps=self._std(samples_tput),
                )
                result.azimuth_results.append(az_result)

                logger.info(
                    f"  azimuth={azimuth}°: RSRP={az_result.rsrp_dbm:.1f}, "
                    f"SINR={az_result.sinr_db:.1f}, "
                    f"Tput={az_result.throughput_mbps:.0f} Mbps, "
                    f"RI={az_result.rank_indicator:.1f}"
                )

            await positioner.disconnect()
            end_time = asyncio.get_event_loop().time()
            result.total_duration_s = end_time - start_time

            state.mimo_test = result
            state.phase_statuses[CommissioningPhase.MIMO_TEST] = PhaseStatus.COMPLETED

            logger.info(
                f"[{session_id}] Phase 3 complete: "
                f"{len(result.azimuth_results)} azimuths, "
                f"{result.total_duration_s:.1f}s"
            )

        except Exception as e:
            logger.exception(f"[{session_id}] Phase 3 failed: {e}")
            state.phase_statuses[CommissioningPhase.MIMO_TEST] = PhaseStatus.FAILED
            state.mimo_test = result

        return result

    # ==================== Phase 4: 分析判定 ====================

    async def phase4_analysis(
        self, session_id: str
    ) -> AnalysisResult:
        """
        阶段 4: CTIA Pass/Fail 判定

        对比 Phase 3 测量数据与 CTIA 门限。
        """
        state = self._get_state(session_id)
        criteria = state.criteria
        state.phase = CommissioningPhase.ANALYSIS
        state.phase_statuses[CommissioningPhase.ANALYSIS] = PhaseStatus.RUNNING

        result = AnalysisResult()

        try:
            mimo = state.mimo_test
            if not mimo or not mimo.azimuth_results:
                result.details.append("无 MIMO 测试数据, 无法分析")
                state.phase_statuses[CommissioningPhase.ANALYSIS] = PhaseStatus.FAILED
                state.analysis = result
                return result

            # --- 吞吐量分析 ---
            tputs = [az.throughput_mbps for az in mimo.azimuth_results]
            result.avg_throughput_mbps = sum(tputs) / len(tputs)
            peak = state.config.theoretical_peak_throughput_mbps
            result.throughput_ratio = result.avg_throughput_mbps / peak
            result.throughput_pass = (
                result.throughput_ratio >= criteria.min_throughput_ratio
                and result.avg_throughput_mbps >= criteria.min_throughput_mbps
            )
            result.details.append(
                f"吞吐量: {result.avg_throughput_mbps:.0f} Mbps "
                f"({result.throughput_ratio:.0%} of {peak:.0f}), "
                f"{'PASS' if result.throughput_pass else 'FAIL'}"
            )

            # --- RSRP 一致性 ---
            rsrps = [az.rsrp_dbm for az in mimo.azimuth_results]
            result.rsrp_variance_db = max(rsrps) - min(rsrps)
            result.rsrp_pass = result.rsrp_variance_db <= criteria.max_rsrp_variance_db
            result.details.append(
                f"RSRP 一致性: variance = {result.rsrp_variance_db:.1f} dB "
                f"(门限 {criteria.max_rsrp_variance_db:.1f}), "
                f"{'PASS' if result.rsrp_pass else 'FAIL'}"
            )

            # --- SINR ---
            sinrs = [az.sinr_db for az in mimo.azimuth_results]
            result.avg_sinr_db = sum(sinrs) / len(sinrs)
            result.sinr_pass = result.avg_sinr_db >= criteria.min_sinr_db
            result.details.append(
                f"SINR: avg = {result.avg_sinr_db:.1f} dB "
                f"(门限 {criteria.min_sinr_db:.1f}), "
                f"{'PASS' if result.sinr_pass else 'FAIL'}"
            )

            # --- Rank Indicator ---
            ris = [az.rank_indicator for az in mimo.azimuth_results]
            result.avg_rank_indicator = sum(ris) / len(ris)
            result.rank_pass = result.avg_rank_indicator >= criteria.min_avg_rank_indicator
            result.details.append(
                f"Rank Indicator: avg = {result.avg_rank_indicator:.1f} "
                f"(门限 {criteria.min_avg_rank_indicator:.1f}), "
                f"{'PASS' if result.rank_pass else 'FAIL'}"
            )

            # --- QZ ---
            result.qz_pass = (
                state.precheck is not None and state.precheck.quiet_zone_pass
            )

            # --- 总判定 ---
            all_pass = all([
                result.throughput_pass,
                result.rsrp_pass,
                result.sinr_pass,
                result.rank_pass,
                result.qz_pass,
            ])

            if all_pass:
                # 计算最小裕量
                margins = [
                    result.throughput_ratio - criteria.min_throughput_ratio,
                    criteria.max_rsrp_variance_db - result.rsrp_variance_db,
                    result.avg_sinr_db - criteria.min_sinr_db,
                    result.avg_rank_indicator - criteria.min_avg_rank_indicator,
                ]
                result.margin_db = min(margins)
                result.verdict = (
                    Verdict.PASS if result.margin_db > 0.1 else Verdict.MARGINAL
                )
            else:
                result.verdict = Verdict.FAIL

            result.details.append(f"总判定: {result.verdict.value}")

            state.analysis = result
            state.phase_statuses[CommissioningPhase.ANALYSIS] = PhaseStatus.COMPLETED

            logger.info(f"[{session_id}] Phase 4: {result.verdict.value}")

        except Exception as e:
            logger.exception(f"[{session_id}] Phase 4 failed: {e}")
            state.phase_statuses[CommissioningPhase.ANALYSIS] = PhaseStatus.FAILED
            state.analysis = result

        return result

    # ==================== Phase 5: 报告 ====================

    async def phase5_report(self, session_id: str) -> str:
        """
        阶段 5: 生成报告并归档

        返回 report_id
        """
        state = self._get_state(session_id)
        state.phase = CommissioningPhase.REPORT
        state.phase_statuses[CommissioningPhase.REPORT] = PhaseStatus.RUNNING

        try:
            await asyncio.sleep(0.5)  # 模拟报告生成

            report_id = f"COM-{session_id}-{datetime.now().strftime('%Y%m%d%H%M')}"
            state.report_id = report_id
            state.completed_at = datetime.now(timezone.utc).isoformat()
            state.phase_statuses[CommissioningPhase.REPORT] = PhaseStatus.COMPLETED

            logger.info(f"[{session_id}] Phase 5: report={report_id}")
            return report_id

        except Exception as e:
            logger.exception(f"[{session_id}] Phase 5 failed: {e}")
            state.phase_statuses[CommissioningPhase.REPORT] = PhaseStatus.FAILED
            return ""

    # ==================== 全流程一键执行 ====================

    async def run_all(self, session_id: str) -> CommissioningState:
        """一键执行全部 5 个阶段"""
        await self.phase1_system_precheck(session_id)
        state = self._get_state(session_id)
        if not state.precheck or not state.precheck.overall_pass:
            return state

        await self.phase2_reference_measurement(session_id)
        await self.phase3_static_mimo_test(session_id)
        await self.phase4_analysis(session_id)
        await self.phase5_report(session_id)
        return state

    # ==================== 工具方法 ====================

    def _get_state(self, session_id: str) -> CommissioningState:
        state = _sessions.get(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")
        return state

    @staticmethod
    def _std(values: list) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)
