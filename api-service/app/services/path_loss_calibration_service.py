"""
Path Loss and RF Chain Calibration Services

探头路损校准和 RF 链路增益校准业务逻辑。

CAL-02: 探头路损校准 (SGH → 探头空间路损)
CAL-03: 上行链路校准 (含 LNA)
CAL-04: 下行链路校准 (含 PA)

参考: docs/design/MPAC-OTA-Chamber-Topology.md
"""
import math
import numpy as np
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging
import statistics

from app.models.probe_calibration import (
    ProbePathLossCalibration,
    RFChainCalibration,
    MultiFrequencyPathLoss,
    CalibrationStatus,
)
from app.models.chamber import ChamberConfiguration
from app.schemas.probe_calibration import (
    PolarizationType,
    CalibrationJobStatus,
    ChainTypeEnum,
)
# Note: LabProfile + rf_chain_resolver are imported lazily inside
# `start_calibration_for_lab_profile`. They transitively pull in SwitchTopology,
# which uses Postgres JSONB and breaks SQLite-based unit tests of the legacy
# chamber-keyed entrypoint that doesn't need them.

logger = logging.getLogger("app.calibration.path_loss")


def select_latest_path_loss_by_mode(base_query, operating_mode: Optional[str]):
    """P2-11 Phase 3 (Codex on PR #111): 在已 filter chamber/status[/freq] 的 query 上
    按请求的 switch operating_mode 选最新 cert。

    多 operating mode 同频校准的 lab 里, 不按 mode 过滤会让一个 '2x2' run 静默拿到最新
    的 'mimo_ota' / 'cal_power_sweep' cert → per-chain 线损来自错的 RF 通路 (或退 chamber
    平均)。这里:
    - operating_mode=None: 不过滤 (调用方未声明 mode, 保持旧行为)。
    - 否则: **精确匹配优先** (operating_mode == 请求值); 找不到再退回 **legacy 未标记**
      cert (operating_mode IS NULL —— mode-tagging 之前的 chamber-only 入口留 NULL, 向后
      兼容)。**绝不**返回 tagged-不同-mode 的 cert (这正是 Codex 指的静默错配)。
    """
    order = desc(ProbePathLossCalibration.calibrated_at)
    if operating_mode is None:
        return base_query.order_by(order).first()
    exact = (
        base_query.filter(ProbePathLossCalibration.operating_mode == operating_mode)
        .order_by(order)
        .first()
    )
    if exact is not None:
        return exact
    return (
        base_query.filter(ProbePathLossCalibration.operating_mode.is_(None))
        .order_by(order)
        .first()
    )


# ==================== 校准常数 ====================

# 路损校准有效期 (天)
PATH_LOSS_VALIDITY_DAYS = 180  # 6 个月

# RF 链路校准有效期 (天)
RF_CHAIN_VALIDITY_DAYS = 90  # 3 个月

# 多频点校准有效期 (天)
MULTI_FREQ_VALIDITY_DAYS = 180

# 路损不确定度阈值 (dB)
PATH_LOSS_UNCERTAINTY_THRESHOLD_DB = 1.0

# 增益测量不确定度阈值 (dB)
GAIN_UNCERTAINTY_THRESHOLD_DB = 0.5

# 探头数量
NUM_PROBES = 32
NUM_POLARIZATIONS = 2


# ==================== 数据类 ====================


def _reject_simulated_instrument(driver, category: str, what: str) -> None:
    """通用版：要求「真测」时，任何模拟驱动一律拒绝。"""
    from app.services.instrument_hal_service import is_mock_driver

    if driver is None:
        raise RuntimeError(f"HAL 里没有 {category} 驱动 — 无法执行{what}。")
    if is_mock_driver(driver):
        raise RuntimeError(
            f"HAL 里的 {category} 是模拟驱动（{type(driver).__name__}）— 拒绝执行{what}。"
            f"它造出来的数不是实测值，据此出的校准证书会被后续所有测试当成真校准使用。"
            f"**请换成真实驱动**。"
        )


def _reject_simulated_vna(vna, what: str) -> None:
    """调用方要求「真测」时，模拟的 VNA 驱动一律拒绝。

    ⚠️ 这里原先**只判 vna 是不是 None**，而这个方法的 docstring 自己就把
    ``MockVNA`` 列在候选驱动里 —— 于是 MockVNA 在位时，它 ``np.random`` 造出来的
    扫描数据会被当成实测，算出一个路损值，**挂着真型号名落库成一张有效的校准证书**。

    后果比「报告里印了个假数字」严重得多：报告里的「路损验证」是由
    「有没有证书」派生的，所以这张证书会把一处诚实的「未验证」**翻成「已验证」**；
    而校准证书还会被后续所有测试拿去做补偿 —— 假数据从这里扩散出去。

    拒绝的方向是安全的：调用方的异常处理会直接返回失败，**不落库、不出证书**。
    """
    from app.services.instrument_hal_service import is_mock_driver

    if vna is None:
        raise RuntimeError(
            f"HAL 里没有 VNA 驱动 — 无法执行{what}。"
            f"请先配置一台可连接的 VNA（R&S ZNA / Keysight ENA）。"
        )
    if is_mock_driver(vna):
        raise RuntimeError(
            f"HAL 里的 VNA 是模拟驱动（{type(vna).__name__}）— 拒绝执行{what}。"
            f"模拟驱动造出来的扫描数据不是实测值，据此出的校准证书会被后续所有测试"
            f"当成真校准使用。**请换成真实 VNA 驱动**。"
        )
        # ⚠️ 这里原先还写了第二条出路「明确以 use_mock=True 调用，那样会被标成非实测」——
        #    **那句话是错的，已删**（外审 P1）：`use_mock=True` 走 mock 测量之后，
        #    证书**仍然写成 VALID**；`vna_model="Mock VNA"` 只是个文本标记。
        #    P1-27 修复前，latest 读取方会把它当成验证与补偿来源；当前正式消费方
        #    已改为 explicit-real 白名单，但这里仍应在生产端拒绝伪造实测证书。


class PathLossMeasurement:
    """单个路损测量结果"""
    def __init__(
        self,
        probe_id: int,
        polarization: str,
        path_loss_db: float,
        uncertainty_db: float = 0.5
    ):
        self.probe_id = probe_id
        self.polarization = polarization
        self.path_loss_db = path_loss_db
        self.uncertainty_db = uncertainty_db


class ChainGainMeasurement:
    """RF 链路增益测量结果"""
    def __init__(
        self,
        total_gain_db: float,
        lna_gain_db: Optional[float] = None,
        pa_gain_db: Optional[float] = None,
        duplexer_loss_db: Optional[float] = None,
        cable_loss_db: Optional[float] = None
    ):
        self.total_gain_db = total_gain_db
        self.lna_gain_db = lna_gain_db
        self.pa_gain_db = pa_gain_db
        self.duplexer_loss_db = duplexer_loss_db
        self.cable_loss_db = cable_loss_db


class CalibrationResult:
    """校准结果"""
    def __init__(
        self,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None
    ):
        self.success = success
        self.message = message
        self.data = data or {}
        self.warnings = warnings or []


# ==================== 路损计算函数 ====================

def calculate_fspl(frequency_mhz: float, distance_m: float) -> float:
    """
    计算自由空间路径损耗

    FSPL = 20*log10(d) + 20*log10(f) - 27.55  (d in m, f in MHz)

    Args:
        frequency_mhz: 频率 (MHz)
        distance_m: 距离 (m)

    Returns:
        路径损耗 (dB)，正值
    """
    if distance_m <= 0 or frequency_mhz <= 0:
        raise ValueError("Distance and frequency must be positive")

    fspl_db = 20 * np.log10(distance_m) + 20 * np.log10(frequency_mhz) - 27.55
    return fspl_db


def calculate_measured_path_loss(
    received_power_dbm: float,
    transmitted_power_dbm: float,
    sgh_gain_dbi: float,
    probe_gain_dbi: float,
    cable_loss_db: float = 0.0
) -> float:
    """
    根据 S21 测量计算实际路损

    PathLoss = P_tx - P_rx + G_sgh + G_probe - CableLoss

    Args:
        received_power_dbm: 接收功率 (dBm) 或 S21 (dB)
        transmitted_power_dbm: 发射功率 (dBm)，通常为 0
        sgh_gain_dbi: SGH 增益 (dBi)
        probe_gain_dbi: 探头增益 (dBi)
        cable_loss_db: 电缆损耗 (dB)

    Returns:
        路损 (dB)，正值
    """
    # 对于 VNA S21 测量: S21 = -PathLoss + G_sgh + G_probe - CableLoss
    # 因此: PathLoss = -S21 + G_sgh + G_probe - CableLoss
    path_loss = transmitted_power_dbm - received_power_dbm + sgh_gain_dbi + probe_gain_dbi - cable_loss_db
    return abs(path_loss)


# ==================== 探头路损校准服务 ====================

class ProbePathLossCalibrationService:
    """
    探头路损校准服务

    测量 SGH 到每个探头的空间路径损耗。

    校准方法:
    1. 将 SGH 置于静区中心 (转台位置)
    2. 使用 VNA 测量 SGH 到每个探头的 S21
    3. 计算每个探头的路损: PathLoss = |S21| + G_sgh + G_probe - CableLoss
    4. 记录双极化数据 (V/H)
    """

    def __init__(self, db: Session, use_mock: bool = True):
        """
        初始化服务

        Args:
            db: 数据库会话
            use_mock: 是否使用 mock 数据 (开发模式)
        """
        self.db = db
        self.use_mock = use_mock
        # Codex #206 R3: acquire 的清理失败警告收集器 (finally 无法经 3 元组
        # 返回传播; 外层校准循环 extend 进 CalibrationResult.warnings 后清)
        self._last_acquire_warnings: List[str] = []

    def _harvest_acquire_warnings(self, warnings: List[str], label: str) -> None:
        """把 acquire 清理失败收集器排入证书 warnings (带来源标签), 排后清空。

        acquire 的 finally 只 append 不上抛 (清理失败不应掩盖测量结果);
        两个校准入口在每次测量后与失败返回前都调本方法收割, 保证成功 /
        异常任一出口都不丢 (agent #206 F1/F3)。

        共享 primitive 的借用方通过 warning_sink + warning_label 在每次调用的
        finally 中收割；这样下一次 acquire 开头清零前，上一点的告警已经进入
        外层 CalibrationResult.warnings。
        """
        if self._last_acquire_warnings:
            warnings.extend(f"{label}: {w}" for w in self._last_acquire_warnings)
            self._last_acquire_warnings = []

    async def start_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        sgh_model: str,
        sgh_gain_dbi: float,
        sgh_serial: Optional[str] = None,
        vna_id: Optional[str] = None,
        cable_loss_db: float = 0.0,
        probe_ids: Optional[List[int]] = None,
        polarizations: Optional[List[PolarizationType]] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        启动探头路损校准

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 测量频率 (MHz)
            sgh_model: SGH 型号
            sgh_gain_dbi: SGH 标定增益 (dBi)
            sgh_serial: SGH 序列号
            vna_id: VNA 设备 ID
            cable_loss_db: 测量电缆损耗 (dB)
            probe_ids: 要校准的探头 ID 列表，None 表示所有
            polarizations: 要校准的极化类型
            calibrated_by: 校准人员

        Returns:
            CalibrationResult
        """
        # 验证暗室配置
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 默认校准所有探头
        if probe_ids is None:
            probe_ids = list(range(chamber.num_probes))

        # 默认双极化
        if polarizations is None:
            polarizations = [PolarizationType.V, PolarizationType.H]

        warnings = []
        probe_path_losses = {}
        # agent #206 F2: 服务实例可能被 orchestrator 复用, 入口清零防上一轮
        # acquire 残留被本轮第一个探头错误吸收
        self._last_acquire_warnings = []

        import contextlib
        from app.services.instrument_test_lease import instrument_test_lease

        # P2-30: 作业级租约（条件 = 会走 CE+SA 路径）—— 整个 probe×pol 循环
        # 只真取/放一次 F64 控制权；循环内单点测量自带的租约圈在嵌套下自动
        # no-op（hold() 引用计数），此前 32 探头 × 2 极化 = 64 次 socket 建拆。
        # mock 与 legacy VNA 分支拿 nullcontext，行为零变化；条件错配的最坏
        # 后果只是退化回逐点取放（内层 wrapper 自己的租约圈保持不动）。
        job_lease = (
            instrument_test_lease(
                f"path-loss-calibration:{frequency_mhz:g}MHz",
                control_f64=True,
                control_uxm=False,
                enable_monitoring=False,
            )
            if not self.use_mock and chamber.cable_sgh_to_sa_loss_db is not None
            else contextlib.nullcontext()
        )
        async with job_lease:
            # 遍历每个探头
            for probe_id in probe_ids:
                probe_data = {
                    "path_loss_db": 0.0,
                    "uncertainty_db": 0.5,
                    "pol_v_db": None,
                    "pol_h_db": None
                }

                for pol in polarizations:
                    try:
                        if self.use_mock:
                            measurement = self._mock_path_loss_measurement(
                                probe_id, pol, frequency_mhz,
                                chamber.chamber_radius_m, sgh_gain_dbi,
                                chamber.probe_gain_dbi
                            )
                        elif chamber.cable_sgh_to_sa_loss_db is not None:
                            # CE+SA primary path (no VNA, no relay swaps).
                            # cable_loss_db comes from chamber, ce_tx_power_dbm uses
                            # a sensible default (-20 dBm) which sits comfortably
                            # above SA noise floor and below CE OTA-port saturation.
                            measurement = await self._real_path_loss_measurement_via_ce_sa(
                                probe_id=probe_id,
                                polarization=pol,
                                frequency_mhz=frequency_mhz,
                                ce_tx_power_dbm=-20.0,
                                sgh_gain_dbi=sgh_gain_dbi,
                                probe_gain_dbi=chamber.probe_gain_dbi,
                                cable_sgh_to_sa_loss_db=chamber.cable_sgh_to_sa_loss_db,
                            )
                        else:
                            # Legacy VNA + manual cable_loss path. Kept for chambers
                            # without CE+SA wiring; deprecated, will be removed once
                            # all production chambers populate cable_sgh_to_sa_loss_db.
                            measurement = await self._real_path_loss_measurement(
                                probe_id, pol, frequency_mhz, vna_id,
                                sgh_gain_dbi, chamber.probe_gain_dbi, cable_loss_db
                            )

                        # 存储极化数据
                        if pol == PolarizationType.V:
                            probe_data["pol_v_db"] = measurement.path_loss_db
                        else:
                            probe_data["pol_h_db"] = measurement.path_loss_db

                        # 更新不确定度
                        probe_data["uncertainty_db"] = max(
                            probe_data["uncertainty_db"],
                            measurement.uncertainty_db
                        )

                        # 检查不确定度
                        if measurement.uncertainty_db > PATH_LOSS_UNCERTAINTY_THRESHOLD_DB:
                            warnings.append(
                                f"Probe {probe_id} pol {pol.value}: uncertainty "
                                f"{measurement.uncertainty_db:.2f} dB exceeds threshold"
                            )

                    except Exception as e:
                        logger.error(f"Path loss measurement failed for probe {probe_id}: {e}")
                        # agent #206 F3: 失败提前返回也收割清理警告 — acquire 的
                        # finally 可能刚 append 了 stop_tx/clear_passthrough 失败
                        self._harvest_acquire_warnings(
                            warnings, f"probe {probe_id} pol {pol.value}"
                        )
                        return CalibrationResult(
                            success=False,
                            message=f"Measurement failed for probe {probe_id}: {str(e)}",
                            warnings=warnings,
                        )

                    # agent #206 F1: legacy 路径对称补收割 (同 for_lab_profile 的
                    # chain 版) — 清理失败进证书 warnings, 不再只沉驱动日志
                    self._harvest_acquire_warnings(
                        warnings, f"probe {probe_id} pol {pol.value}"
                    )

                # 计算平均路损
                valid_losses = [v for v in [probe_data["pol_v_db"], probe_data["pol_h_db"]] if v is not None]
                if valid_losses:
                    probe_data["path_loss_db"] = statistics.mean(valid_losses)

                probe_path_losses[str(probe_id)] = probe_data

        # 计算统计数据
        all_losses = [float(d["path_loss_db"]) for d in probe_path_losses.values() if d["path_loss_db"]]
        avg_loss = float(statistics.mean(all_losses)) if all_losses else 0.0
        max_loss = float(max(all_losses)) if all_losses else 0.0
        min_loss = float(min(all_losses)) if all_losses else 0.0
        std_dev = float(statistics.stdev(all_losses)) if len(all_losses) > 1 else 0.0

        # 创建校准记录
        calibration = ProbePathLossCalibration(
            chamber_id=chamber_id,
            frequency_mhz=frequency_mhz,
            use_mock=self.use_mock,
            probe_path_losses=probe_path_losses,
            sgh_model=sgh_model,
            sgh_serial=sgh_serial,
            sgh_gain_dbi=sgh_gain_dbi,
            vna_model="Mock VNA" if self.use_mock else vna_id,
            cable_loss_db=cable_loss_db,
            measurement_distance_m=chamber.chamber_radius_m,
            avg_path_loss_db=avg_loss,
            max_path_loss_db=max_loss,
            min_path_loss_db=min_loss,
            std_dev_db=std_dev,
            warnings=list(warnings),
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=PATH_LOSS_VALIDITY_DAYS),
            status=CalibrationStatus.VALID.value
        )

        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return CalibrationResult(
            success=True,
            message=f"Path loss calibration completed for {len(probe_ids)} probes",
            data={
                "calibration_id": str(calibration.id),
                "avg_path_loss_db": avg_loss,
                "max_path_loss_db": max_loss,
                "min_path_loss_db": min_loss,
                "std_dev_db": std_dev,
                "num_probes": len(probe_ids)
            },
            warnings=warnings
        )

    async def start_calibration_for_lab_profile(
        self,
        lab_profile_id: UUID,
        operating_mode: str,
        frequency_mhz: float,
        sgh_model: str,
        sgh_gain_dbi: float,
        sgh_serial: Optional[str] = None,
        vna_id: Optional[str] = None,
        calibrated_by: str = "System",
    ) -> CalibrationResult:
        """P0 entrypoint: calibrate per RFChain declared by SwitchTopology.

        Iterates over RFChainSpec entries (one per probe×polarization actually
        wired in the requested operating mode) instead of doing
        `for probe in range(num_probes)`. Per-connection cable_loss from the
        topology is added to the spatial SGH→probe loss to produce
        `total_insertion_loss_db` per chain — what measure.py wants on the DL
        signal path.

        Falls through to the legacy `start_calibration` path when:
        - the LabProfile has no chamber bound (raises),
        - the topology resolver returns no chains (returns failure with the
          resolver's warnings — caller is expected to seed the topology
          before retrying).
        """
        # Lazy: pulls in SwitchTopology (JSONB) which breaks SQLite tests of
        # the legacy chamber-keyed path that don't exercise this method.
        from app.models.lab_profile import LabProfile
        from app.services.calibration.rf_chain_resolver import resolve_rf_chains

        lab = self.db.query(LabProfile).filter(LabProfile.id == lab_profile_id).first()
        if lab is None:
            return CalibrationResult(success=False, message=f"LabProfile {lab_profile_id} not found")
        if lab.chamber_config_id is None:
            return CalibrationResult(
                success=False,
                message=f"LabProfile {lab.name} has no chamber_config — bind one before calibrating",
            )

        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == lab.chamber_config_id
        ).first()
        if chamber is None:
            return CalibrationResult(
                success=False,
                message=f"Chamber {lab.chamber_config_id} referenced by lab not found",
            )

        try:
            resolution = resolve_rf_chains(self.db, lab_profile_id, operating_mode)
        except ValueError as e:
            return CalibrationResult(success=False, message=str(e))

        if not resolution.success:
            return CalibrationResult(
                success=False,
                message=(
                    f"No RF chains resolved for lab '{lab.name}' mode '{operating_mode}'. "
                    "Seed SwitchTopology + operating_mode.active_connections before calibrating."
                ),
                warnings=resolution.warnings,
            )

        warnings: List[str] = list(resolution.warnings)
        probe_path_losses: Dict[str, Dict[str, Any]] = {}
        path_loss_db_by_rf_chain: Dict[str, Dict[str, Any]] = {}
        # agent #206 F2: 入口清零防跨轮残留 (同 start_calibration)
        self._last_acquire_warnings = []

        import contextlib
        from app.services.instrument_test_lease import instrument_test_lease

        # P2-30: 作业级租约（同 start_calibration，条件 = 会走 CE+SA 路径）——
        # 整个 chain 循环只真取/放一次 F64 控制权。
        job_lease = (
            instrument_test_lease(
                f"path-loss-calibration:lab:{operating_mode}",
                control_f64=True,
                control_uxm=False,
                enable_monitoring=False,
            )
            if not self.use_mock and chamber.cable_sgh_to_sa_loss_db is not None
            else contextlib.nullcontext()
        )
        async with job_lease:
            for chain in resolution.chains:
                try:
                    pol_enum = PolarizationType(chain.polarization)
                except ValueError:
                    warnings.append(
                        f"chain {chain.chain_id}: unknown polarization {chain.polarization!r}, skipped"
                    )
                    continue

                try:
                    if self.use_mock:
                        measurement = self._mock_path_loss_measurement(
                            chain.probe_id, pol_enum, frequency_mhz,
                            chamber.chamber_radius_m, sgh_gain_dbi, chamber.probe_gain_dbi,
                        )
                        measurement_path = "mock"
                    elif chamber.cable_sgh_to_sa_loss_db is not None:
                        # CE+SA primary path with topology-driven auto-routing.
                        # ce_port + chain_id flow from RFChainSpec, so the right
                        # probe lights up and (if rfSwitch bound) the matrix is
                        # driven automatically. Measurement returns end-to-end
                        # path-loss including the chain's own cable.
                        measurement = await self._real_path_loss_measurement_via_ce_sa(
                            probe_id=chain.probe_id,
                            polarization=pol_enum,
                            frequency_mhz=frequency_mhz,
                            ce_tx_power_dbm=-20.0,
                            sgh_gain_dbi=sgh_gain_dbi,
                            probe_gain_dbi=chamber.probe_gain_dbi,
                            cable_sgh_to_sa_loss_db=chamber.cable_sgh_to_sa_loss_db,
                            ce_port=chain.ce_port,
                            route_target=chain.chain_id,
                        )
                        measurement_path = "ce_sa"
                    else:
                        measurement = await self._real_path_loss_measurement(
                            chain.probe_id, pol_enum, frequency_mhz, vna_id,
                            sgh_gain_dbi, chamber.probe_gain_dbi, chain.cable_loss_db,
                        )
                        measurement_path = "vna"
                except Exception as e:
                    logger.error(
                        "Path-loss measurement failed for chain %s probe %d %s: %s",
                        chain.chain_id, chain.probe_id, chain.polarization, e,
                    )
                    # agent #206 F3: 失败返回也收割 — 本 chain 的清理失败不丢
                    self._harvest_acquire_warnings(warnings, f"chain {chain.chain_id}")
                    return CalibrationResult(
                        success=False,
                        message=f"Measurement failed for chain {chain.chain_id}: {e}",
                        warnings=warnings,
                    )

                # Per-probe aggregate (legacy structure — keeps get_path_loss_for_probe working).
                pid_key = str(chain.probe_id)
                entry = probe_path_losses.setdefault(
                    pid_key,
                    {"path_loss_db": 0.0, "uncertainty_db": 0.5, "pol_v_db": None, "pol_h_db": None},
                )
                if pol_enum == PolarizationType.V:
                    entry["pol_v_db"] = measurement.path_loss_db
                else:
                    entry["pol_h_db"] = measurement.path_loss_db
                entry["uncertainty_db"] = max(entry["uncertainty_db"], measurement.uncertainty_db)
                valid_losses = [v for v in (entry["pol_v_db"], entry["pol_h_db"]) if v is not None]
                if valid_losses:
                    entry["path_loss_db"] = float(statistics.mean(valid_losses))

                # Per-chain breakdown — measurement semantics differ by path:
                #   - VNA / mock: returns spatial loss only (cable already subtracted),
                #     so total_insertion = space + cable.
                #   - CE+SA: returns end-to-end including the chain cable, so the
                #     measurement IS total_insertion; space_loss = total - cable.
                # Both paths produce the same fields for downstream consumers.
                if measurement_path == "ce_sa":
                    total_insertion_loss_db = float(measurement.path_loss_db)
                    space_loss_db = total_insertion_loss_db - float(chain.cable_loss_db)
                else:
                    space_loss_db = float(measurement.path_loss_db)
                    total_insertion_loss_db = space_loss_db + float(chain.cable_loss_db)
                path_loss_db_by_rf_chain[chain.chain_id] = {
                    "probe_id": chain.probe_id,
                    "polarization": chain.polarization,
                    "ce_port": chain.ce_port,
                    "space_loss_db": space_loss_db,
                    "cable_loss_db": float(chain.cable_loss_db),
                    "total_insertion_loss_db": total_insertion_loss_db,
                    "uncertainty_db": float(measurement.uncertainty_db),
                    "measurement_path": measurement_path,
                }

                if measurement.uncertainty_db > PATH_LOSS_UNCERTAINTY_THRESHOLD_DB:
                    warnings.append(
                        f"chain {chain.chain_id} probe {chain.probe_id} {chain.polarization}: "
                        f"uncertainty {measurement.uncertainty_db:.2f} dB exceeds threshold"
                    )

                # Codex #206 R3: acquire 的清理失败 (tone 停不掉 / CE 留直通) 并入
                # 证书 warnings — 操作员可见, 不再只沉驱动日志
                self._harvest_acquire_warnings(warnings, f"chain {chain.chain_id}")

        all_losses = [
            float(d["total_insertion_loss_db"]) for d in path_loss_db_by_rf_chain.values()
        ]
        avg_loss = float(statistics.mean(all_losses)) if all_losses else 0.0
        max_loss = float(max(all_losses)) if all_losses else 0.0
        min_loss = float(min(all_losses)) if all_losses else 0.0
        std_dev = float(statistics.stdev(all_losses)) if len(all_losses) > 1 else 0.0

        calibration = ProbePathLossCalibration(
            chamber_id=chamber.id,
            frequency_mhz=frequency_mhz,
            use_mock=self.use_mock,
            probe_path_losses=probe_path_losses,
            path_loss_db_by_rf_chain=path_loss_db_by_rf_chain,
            lab_profile_id=lab.id,
            operating_mode=operating_mode,
            topology_id=UUID(resolution.topology_id) if resolution.topology_id else None,
            sgh_model=sgh_model,
            sgh_serial=sgh_serial,
            sgh_gain_dbi=sgh_gain_dbi,
            vna_model="Mock VNA" if self.use_mock else vna_id,
            cable_loss_db=0.0,  # per-chain values now hold the real cable loss
            measurement_distance_m=chamber.chamber_radius_m,
            avg_path_loss_db=avg_loss,
            max_path_loss_db=max_loss,
            min_path_loss_db=min_loss,
            std_dev_db=std_dev,
            warnings=list(warnings),
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=PATH_LOSS_VALIDITY_DAYS),
            status=CalibrationStatus.VALID.value,
        )
        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return CalibrationResult(
            success=True,
            message=(
                f"Path-loss calibration completed for {len(resolution.chains)} RF chains "
                f"(lab='{lab.name}', mode='{operating_mode}')"
            ),
            data={
                "calibration_id": str(calibration.id),
                "lab_profile_id": str(lab.id),
                "topology_id": resolution.topology_id,
                "operating_mode": operating_mode,
                "num_chains": len(resolution.chains),
                "num_probes": len(probe_path_losses),
                "avg_total_insertion_loss_db": avg_loss,
                "max_total_insertion_loss_db": max_loss,
                "min_total_insertion_loss_db": min_loss,
                "std_dev_db": std_dev,
            },
            warnings=warnings,
        )

    def _mock_path_loss_measurement(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_mhz: float,
        chamber_radius_m: float,
        sgh_gain_dbi: float,
        probe_gain_dbi: float
    ) -> PathLossMeasurement:
        """生成 mock 路损测量数据"""
        # 计算理论 FSPL
        fspl = calculate_fspl(frequency_mhz, chamber_radius_m)

        # 添加探头位置相关的变化 (±2 dB)
        position_variation = np.sin(probe_id * 0.3) * 2.0

        # 添加极化相关的变化 (±0.5 dB)
        pol_variation = 0.5 if polarization == PolarizationType.V else -0.3

        # 添加随机噪声
        noise = np.random.normal(0, 0.3)

        # 总路损
        path_loss = fspl + position_variation + pol_variation + noise

        # 不确定度
        uncertainty = 0.3 + abs(noise) * 0.5

        return PathLossMeasurement(
            probe_id=probe_id,
            polarization=polarization.value,
            path_loss_db=float(path_loss),
            uncertainty_db=float(uncertainty)
        )

    async def _real_path_loss_measurement_via_ce_sa(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_mhz: float,
        ce_tx_power_dbm: float,
        sgh_gain_dbi: float,
        probe_gain_dbi: float,
        cable_sgh_to_sa_loss_db: float,
        ce_port: Optional[str] = None,
        route_target: Optional[str] = None,
        warning_sink: Optional[List[str]] = None,
        warning_label: Optional[str] = None,
    ) -> PathLossMeasurement:
        """CE+SA 路损测量 — 自动按 CE driver capability 选 D / B 路径。

        两条物理可行路径都支持 (HAL 抽象), 服务层透明选:

        - **D 路径 (INTERNAL_CW_GENERATOR)**: CE 自己出 CW (PROPSIM Internal
          Interference Generator option 等). 单仪器, 最干净。
        - **B 路径 (PASSTHROUGH_ONLY)**: 上游 SG/BSE 出 CW + CE 透传。需要
          LabProfile 上额外绑 SG 或 BSE driver, 也是 fallback 给没买
          interference generator option 的 PROPSIM。

        信号路径 (两条共同 — 跟生产测试链路完全一致, 不动任何东西):
            [tone source] → CE_OUT → switch → PA → probe → 自由空间 → SGH → SA_IN

        算式 (两条共用, 改变的只是 ce_tx_power 来源):
            path_loss_db = ce_tx_dbm - sa_rx_dbm + G_sgh + G_probe - cable_sgh_to_sa

        前置条件:
          - chamber.cable_sgh_to_sa_loss_db 已 commissioning 标定 (一次性)
          - SGH 永久挂在 SA 一个输入端口 (零接触)
          - rf_switch 已路由到 (probe_id, polarization) — 当前需要外部编排,
            topology-derived 自动路由是 follow-up

        Args:
            probe_id, polarization: 当前测的探头 + 极化
            frequency_mhz: 测试频点
            ce_tx_power_dbm: CE 输出 tone 功率, 推荐 -20 dBm (远离 CE 饱和 +
                高于 SA 底噪 ~80 dB 余量). 在 B 路径里是上游 SG 设的功率
                (CE 透传 0 dB), 在 D 路径里是 CE 内置 generator 设的功率。
            sgh_gain_dbi: SGH 标定增益 (LabProfile 或 chamber config)
            probe_gain_dbi: 探头标称增益 (datasheet)
            cable_sgh_to_sa_loss_db: SGH→SA 那一根 cable 的损耗

        Returns:
            PathLossMeasurement(probe_id, polarization, path_loss_db, uncertainty_db)
        """
        sa_rx_mean_dbm, sa_rx_std_db, tone_source_label = await self.acquire_sa_power_via_ce_tone(
            frequency_mhz=frequency_mhz,
            ce_tx_power_dbm=ce_tx_power_dbm,
            ce_port=ce_port,
            route_target=route_target,
            probe_id=probe_id,
            polarization=polarization,
            warning_sink=warning_sink,
            warning_label=warning_label,
        )

        # path_loss = CE_TX - SA_RX + G_sgh + G_probe - cable_sgh_to_sa
        # (signs: TX higher = more loss; subtract antenna gains both sides;
        #  subtract the SGH→SA cable that's NOT in the production signal path)
        path_loss_db = (
            ce_tx_power_dbm - sa_rx_mean_dbm
            + sgh_gain_dbi + probe_gain_dbi
            - cable_sgh_to_sa_loss_db
        )
        # Uncertainty: SA reading noise + 0.3 dB SGH gain calibration ref unc.
        uncertainty_db = sa_rx_std_db + 0.3

        logger.info(
            "[PathLoss CE+SA src=%s] probe=%d pol=%s freq=%.1fMHz "
            "CE_TX=%.1f SA_RX=%.2f±%.2f → PL=%.2f dB",
            tone_source_label, probe_id, polarization.value, frequency_mhz,
            ce_tx_power_dbm, sa_rx_mean_dbm, sa_rx_std_db, path_loss_db,
        )

        return PathLossMeasurement(
            probe_id=probe_id,
            polarization=polarization.value,
            path_loss_db=float(abs(path_loss_db)),
            uncertainty_db=float(uncertainty_db),
        )

    async def acquire_sa_power_via_ce_tone(
        self,
        frequency_mhz: float,
        ce_tx_power_dbm: float = -20.0,
        ce_port: Optional[str] = None,
        route_target: Optional[str] = None,
        probe_id: int = 0,
        polarization: PolarizationType = PolarizationType.V,
        warning_sink: Optional[List[str]] = None,
        warning_label: Optional[str] = None,
    ) -> Tuple[float, float, str]:
        """[shared primitive] CE+SA 测一次 SA 功率读数 — D/B 自动 dispatch.

        Returns (sa_mean_dbm, sa_std_db, tone_source_label).

        通用 measurement primitive — 把 D/B capability dispatch + BSE 优先 +
        finally-stop + auto-routing 集中在一处. 给 path_loss 的算式步骤,
        和 QZ field uniformity / XPD / 任何"已知 CE tone, 测 SA 功率"流程
        共用. probe_id / polarization 仅用于 log + 错误信息, 不参与算式.

        前置: HAL 必须绑 channelEmulator + signalAnalyzer; CE driver 必须
        声明 ≥1 个 CalibrationToneCapability.

        ⚠ **本方法自己取仪表租约**（2026-08-07 内审 F2）。HAL 初始化/重载后
        `park_idle_instruments()` 会把 F64 停回 Local 并立门，此后所有 F64 SCPI
        直接抛 `F64LocalControlReservedError`。而校准链**不走 commissioning
        的相位租约**，于是「后端启动 → 操作员点路损校准」必然报
        "已交还本地控制" —— 错误文本跟操作员正在做的事完全对不上。
        租约加在这个共用 primitive 上而不是三个调用方各加一次：
        `quiet_zone_validation_service`(3 处) / `probe_calibration_service`(1 处)
        / 本服务自己，都经这里碰 CE。
        ⚠ 本方法**可以安全嵌套**在外层租约里（`hold()` 用引用计数：内层复用
        外层那份控制权、退出不拆）。所以调用方要减少 socket 建拆开销时，
        直接在作业入口（一次探头方向图 / 一次 QZ 校验 / 一次 path-loss 作业）
        外面再包一圈租约即可，本方法这圈会自动变成 no-op。
        ⚠ 唯一会抛的情况：外层持的控制权**比内层要的窄**（例如外层只取了 UXM，
        内层要 F64）—— 那台 F64 根本没被 acquire，照跑会在第一条 SCPI 上撞
        Local 门，所以 fail-loud 不静默降级。
        （⚠ 此处一度写着"租约不可嵌套、会当场抛" —— 那是 `hold()` 改成引用
        计数**之前**的说法，同一个 commit 里没跟着改，内审 F7 抓出。）
        """
        from app.services.instrument_test_lease import instrument_test_lease

        if warning_sink is not None:
            # sink 调用必须只接收本次 acquire 的 cleanup 事实；即使租约在
            # inner reset 前失败，也不能把同一 service 上的陈旧值错标到本次。
            self._last_acquire_warnings = []
        try:
            async with instrument_test_lease(
                f"path-loss-tone:probe{probe_id}:{polarization.value}",
                control_f64=True,
                control_uxm=False,   # B 路会用 BSE 出 tone，但那是 SG 角色不是 UXM 小区
                enable_monitoring=False,
            ):
                return await self._acquire_sa_power_via_ce_tone_inner(
                    frequency_mhz=frequency_mhz,
                    ce_tx_power_dbm=ce_tx_power_dbm,
                    ce_port=ce_port,
                    route_target=route_target,
                    probe_id=probe_id,
                    polarization=polarization,
                )
        finally:
            if warning_sink is not None:
                self._harvest_acquire_warnings(
                    warning_sink,
                    warning_label
                    or f"probe {probe_id} pol {polarization.value}",
                )

    async def _acquire_sa_power_via_ce_tone_inner(
        self,
        frequency_mhz: float,
        ce_tx_power_dbm: float = -20.0,
        ce_port: Optional[str] = None,
        route_target: Optional[str] = None,
        probe_id: int = 0,
        polarization: PolarizationType = PolarizationType.V,
    ) -> Tuple[float, float, str]:
        """`acquire_sa_power_via_ce_tone` 的实体，**已在租约内**。"""
        # Codex #206 R3: 清理失败 (tone 停不掉 / CE 留直通) 不得只沉日志。
        # 实例收集器在 finally 失败时 append；public wrapper 若收到
        # warning_sink 会立即 drain，否则由 path-loss 证书外层循环收割。
        self._last_acquire_warnings = []

        # Lazy import — avoid circular and SQLite-test-killing pulls.
        from app.hal.channel_emulator import CalibrationToneCapability
        from app.services.instrument_hal_service import get_hal_service

        hal = get_hal_service()
        ce = hal.drivers.get("channelEmulator")
        sa = hal.drivers.get("signalAnalyzer")
        if ce is None or sa is None:
            missing = []
            if ce is None:
                missing.append("channelEmulator")
            if sa is None:
                missing.append("signalAnalyzer")
            raise RuntimeError(
                f"CE+SA tone acquisition requires HAL drivers: {missing}. "
                "Bind both on the active LabProfile."
            )

        # ⚠️ 这条 CE+SA 才是**主路径**（暗室配了 cable_sgh_to_sa_loss_db 就走它），
        #    我上一版只拦了那条 DEPRECATED 的 VNA 旧路径，主路径完全绕过去了（外审 P1）。
        #    MockSignalAnalyzer 的 measure_channel_power() 返回随机值，
        #    MockChannelEmulator 也不发真的 tone —— 两者都会被当成真机，
        #    结果照样以 valid 证书落库。
        _reject_simulated_instrument(ce, "channelEmulator", "CE+SA 真测路损")
        _reject_simulated_instrument(sa, "signalAnalyzer", "CE+SA 真测路损")

        # Capability-based dispatch: prefer D (single-instrument) when CE
        # supports it, else fall through to B (needs upstream SG/BSE).
        caps = ce.get_calibration_tone_capabilities()
        if not caps:
            raise RuntimeError(
                f"CE driver {type(ce).__name__} declares no calibration-tone "
                "capabilities. Override get_calibration_tone_capabilities() "
                "to return INTERNAL_CW_GENERATOR and/or PASSTHROUGH_ONLY."
            )

        # Switch routing — drive rfSwitch to (probe, pol) when caller gave us
        # a route_target (typically the SwitchTopology chain_id). Three cases:
        #   1. route_target + rfSwitch driver bound → set_mapped_path(chain_id),
        #      driver looks up port_maps to translate to (switch_id, output_port).
        #      Failure → loud RuntimeError, can't measure on the wrong probe.
        #   2. route_target without rfSwitch driver → fixed-cabling site
        #      (CAICT-Lab-1 style: every CE port is permanently wired to one
        #      probe, no relays). Skip silently with debug log; CE port
        #      selection alone determines which probe is energized.
        #   3. No route_target → legacy chamber-keyed entry point with no
        #      topology info. Operator pre-routed manually; warn so it doesn't
        #      get missed in production.
        if route_target is not None:
            await self._route_switch_to_chain(
                hal, route_target, probe_id, polarization,
            )
        else:
            logger.warning(
                "[CE+SA tone] probe=%d pol=%s — no route_target supplied, "
                "assuming RF switch already routed manually. Pass a chain_id "
                "via lab_profile entrypoint for auto-routing.",
                probe_id, polarization.value,
            )

        if CalibrationToneCapability.INTERNAL_CW_GENERATOR in caps:
            sa_rx_mean_dbm, sa_rx_std_db = await self._measure_via_ce_internal_tone(
                ce, sa, probe_id, polarization, frequency_mhz, ce_tx_power_dbm,
                ce_port=ce_port,
            )
            return sa_rx_mean_dbm, sa_rx_std_db, "CE-internal"

        if CalibrationToneCapability.PASSTHROUGH_ONLY in caps:
            # Prefer BSE over a standalone SG: every chamber has a BSE
            # (it's the throughput-test master), most chambers don't have
            # a separate SG. Using BSE also keeps the signal path 100%
            # identical between calibration (BSE in CW testmode) and
            # production (BSE in LTE/5G mode) — that's the whole point of
            # B path vs VNA. SG is only used as fallback for benches that
            # actually have one but no BSE driver bound (rare).
            source = hal.drivers.get("baseStation") or hal.drivers.get("signalGenerator")
            if source is None:
                raise RuntimeError(
                    f"CE {type(ce).__name__} only supports PASSTHROUGH_ONLY for "
                    "calibration tone, but no upstream baseStation / "
                    "signalGenerator driver is bound on this LabProfile. Bind "
                    "the BSE (preferred — keeps cal/test path identical) or "
                    "an SG, both must implement set_cw / start_tx / stop_tx, "
                    "or use a CE with INTERNAL_CW_GENERATOR capability."
                )
            # ⚠️ 上游信号源同样只判了 None（外审 P1）：CE/SA 是真机、
            #    但 BSE/SG 绑的是模拟驱动时，它的 set_cw / start_tx 会「成功」，
            #    SA 读数照样算成 VALID 证书。
            _reject_simulated_instrument(
                source, "baseStation/signalGenerator", "CE+SA 真测路损（B 路径）")

            sa_rx_mean_dbm, sa_rx_std_db = await self._measure_via_ce_passthrough(
                ce, sa, source, probe_id, polarization, frequency_mhz, ce_tx_power_dbm,
                ce_port=ce_port,
            )
            return sa_rx_mean_dbm, sa_rx_std_db, f"passthrough({type(source).__name__})"

        raise RuntimeError(
            f"CE driver {type(ce).__name__} declared capabilities {caps} "
            "but none match INTERNAL_CW_GENERATOR / PASSTHROUGH_ONLY."
        )

    async def _route_switch_to_chain(
        self,
        hal: Any,
        route_target: str,
        probe_id: int,
        polarization: PolarizationType,
    ) -> None:
        """Drive rfSwitch driver to the given chain_id, if a driver is bound.

        Fixed-cabling chambers (CAICT-Lab-1 style) don't bind an rfSwitch
        driver — every CE output is permanently wired, so this becomes a
        debug log + no-op. Sites with relay matrices bind a real driver
        whose port_maps was seeded with chain_id keys at commissioning.
        """
        rf_switch = hal.drivers.get("rfSwitch")
        if rf_switch is None:
            logger.debug(
                "[PathLoss CE+SA] route_target=%s but no rfSwitch driver bound "
                "— assuming fixed cabling (probe=%d pol=%s).",
                route_target, probe_id, polarization.value,
            )
            return

        # ⚠️ 模拟开关会返回 True 但物理矩阵**根本没切**（外审 P1）——
        #    于是我们测的是当前那条错通路，结果却签成目标 chain/probe 的有效证书。
        #    固定布线的暗室不绑 rfSwitch 驱动，走上面那条 no-op 分支，不受影响。
        _reject_simulated_instrument(rf_switch, "rfSwitch", "真测路损的通道切换")

        ok = await rf_switch.set_mapped_path(route_target)
        if not ok:
            raise RuntimeError(
                f"rfSwitch.set_mapped_path({route_target!r}) returned False "
                f"(probe={probe_id} pol={polarization.value}). Check the "
                f"driver's port_maps config — chain_id {route_target!r} must "
                "be keyed in port_maps with switch_id + output_port."
            )
        logger.info(
            "[PathLoss CE+SA] rfSwitch routed to chain_id=%s (probe=%d pol=%s)",
            route_target, probe_id, polarization.value,
        )

    async def _measure_via_ce_internal_tone(
        self,
        ce: Any,
        sa: Any,
        probe_id: int,
        polarization: PolarizationType,
        frequency_mhz: float,
        ce_tx_power_dbm: float,
        ce_port: Optional[str] = None,
    ) -> Tuple[float, float]:
        """[D 路径] CE 自己出 CW, SA 读 — returns (mean_dbm, std_db).

        ce_port: 指定 CE 输出口 (e.g. "B1.1") — PROPSIM 的
        OUTPut:INTERFerence:ADD <ce_port>, ... 必填. None → driver 默认主端口.
        """
        center_hz = frequency_mhz * 1e6
        rx_powers_dbm: list[float] = []
        try:
            if not await ce.set_calibration_tone(center_hz, ce_tx_power_dbm, ce_port=ce_port):
                raise RuntimeError(
                    f"CE set_calibration_tone failed (probe={probe_id} pol={polarization.value})"
                )
            if not await sa.setup_spectrum(center_hz, 1e6, 10e3):
                raise RuntimeError(
                    f"SA setup_spectrum failed (probe={probe_id} pol={polarization.value})"
                )
            for _ in range(5):
                rx = await sa.measure_channel_power(1e6)
                if rx is not None:
                    rx_powers_dbm.append(rx)
        finally:
            # agent #206 F1 域枚举顺带: D 路清理失败与 B 路对称进收集器 —
            # tone 停不掉 (False/异常) 同样污染后续测量, 不许只沉日志
            try:
                if not await ce.stop_calibration_tone():
                    msg = (
                        "[PathLoss D] stop_calibration_tone 被拒 — CE 可能仍在发"
                        " tone, 影响后续测量"
                    )
                    logger.warning(msg)
                    self._last_acquire_warnings.append(msg)
            except Exception as e:  # noqa: BLE001
                msg = f"[PathLoss D] stop_calibration_tone failed (残留 tone 影响后续测量): {e}"
                logger.warning(msg)
                self._last_acquire_warnings.append(msg)

        if not rx_powers_dbm:
            raise RuntimeError(
                f"SA returned no readings (probe={probe_id} pol={polarization.value})"
            )
        return (
            statistics.mean(rx_powers_dbm),
            statistics.stdev(rx_powers_dbm) if len(rx_powers_dbm) > 1 else 0.0,
        )

    async def _measure_via_ce_passthrough(
        self,
        ce: Any,
        sa: Any,
        source: Any,
        probe_id: int,
        polarization: PolarizationType,
        frequency_mhz: float,
        ce_tx_power_dbm: float,
        ce_port: Optional[str] = None,
    ) -> Tuple[float, float]:
        """[B 路径] 上游 SG/BSE 出 CW → CE 透传 → SA. returns (mean_dbm, std_db).

        约定: CE 透传按 0 dB 增益, 所以 SG 输出功率 = CE 输出功率 = ce_tx_power_dbm.
        如果未来要用非零透传 attenuation, 由 driver 内部补偿后再 expose 给上层.

        ce_port: 指定 CE 输出口 (e.g. "B1.1") — 透传到这个端口的探头. None → 默认.
        """
        center_hz = frequency_mhz * 1e6
        rx_powers_dbm: list[float] = []
        passthrough_set = False
        tx_started = False
        try:
            if not await ce.set_passthrough_mode(ce_port=ce_port):
                raise RuntimeError(
                    f"CE set_passthrough_mode failed (probe={probe_id} pol={polarization.value})"
                )
            passthrough_set = True

            if not await source.set_cw(center_hz, ce_tx_power_dbm):
                raise RuntimeError(
                    f"{type(source).__name__}.set_cw failed at {frequency_mhz} MHz / {ce_tx_power_dbm} dBm"
                )
            if not await source.start_tx():
                raise RuntimeError(
                    f"{type(source).__name__}.start_tx failed (probe={probe_id} pol={polarization.value})"
                )
            tx_started = True

            if not await sa.setup_spectrum(center_hz, 1e6, 10e3):
                raise RuntimeError(
                    f"SA setup_spectrum failed (probe={probe_id} pol={polarization.value})"
                )
            for _ in range(5):
                rx = await sa.measure_channel_power(1e6)
                if rx is not None:
                    rx_powers_dbm.append(rx)
        finally:
            if tx_started:
                try:
                    # agent 复审 F1: 真驱动 (MXG/SMW) 把异常吞成 False — False
                    # 是它们唯一失败形态, 只留 except 分支等于永不触发
                    if not await source.stop_tx():
                        msg = (
                            f"[PathLoss B] {type(source).__name__}.stop_tx 被拒 —"
                            " 上游源可能仍在发 CW, 影响后续测量"
                        )
                        logger.warning(msg)
                        self._last_acquire_warnings.append(msg)
                except Exception as e:  # noqa: BLE001
                    msg = f"[PathLoss B] source.stop_tx failed (残留 tone 影响后续测量): {e}"
                    logger.warning(msg)
                    self._last_acquire_warnings.append(msg)
            if passthrough_set:
                try:
                    # Codex #206 R2/R3: False 带真实语义 (STATIC 0 被拒, CE 留
                    # 直通) — 进 warnings 通道让证书可见, 不只沉日志
                    if not await ce.clear_passthrough_mode():
                        msg = (
                            "[PathLoss B] clear_passthrough_mode 被拒 — CE 可能留在"
                            " STATIC 直通, 后续校准/测试或在非衰落路径上跑"
                            " (下次 GO 前置清会兜底)"
                        )
                        logger.warning(msg)
                        self._last_acquire_warnings.append(msg)
                except Exception as e:  # noqa: BLE001
                    msg = f"[PathLoss B] clear_passthrough_mode failed: {e}"
                    logger.warning(msg)
                    self._last_acquire_warnings.append(msg)

        if not rx_powers_dbm:
            raise RuntimeError(
                f"SA returned no readings (probe={probe_id} pol={polarization.value})"
            )
        return (
            statistics.mean(rx_powers_dbm),
            statistics.stdev(rx_powers_dbm) if len(rx_powers_dbm) > 1 else 0.0,
        )

    async def _real_path_loss_measurement(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_mhz: float,
        vna_id: str,
        sgh_gain_dbi: float,
        probe_gain_dbi: float,
        cable_loss_db: float
    ) -> PathLossMeasurement:
        """
        [DEPRECATED] Legacy VNA-based path-loss measurement.

        新部署应该用 _real_path_loss_measurement_via_ce_sa (零额外硬件, 跟
        生产链路一致). 本方法保留是因为某些没装 SA 或 SGH 不固定的暗室
        仍依赖 VNA + 手动 cable_loss_db. 等所有生产暗室填了
        chamber.cable_sgh_to_sa_loss_db 之后可以删除.

        通过 HAL 中的 VNA 驱动 (RealRsZnaDriver / RealKeysightEnaDriver / MockVNA)
        测量 SGH→探头的 S21, 反算路损。

        工艺前提: 调用方需保证 RF switch matrix 已切换到 probe_id+polarization
        对应的物理通道。当前 P2 范围内 switch matrix 控制不做编排,
        生产部署时由 RFSwitchCalibrationService 配套驱动负责。

        测量方案:
          - 围绕 frequency_mhz 设 1 MHz span, 11 个采样点 (近 CW 测量,
            可平均掉数据噪声但避开 zero-span 的 IF 残留)
          - S21 复数 → magnitude_db = 20*log10(|S21|)
          - PathLoss = -mean(S21_dB) + G_sgh + G_probe - CableLoss
        """
        from app.services.instrument_hal_service import get_hal_service

        hal = get_hal_service()
        vna = hal.drivers.get("vna")
        _reject_simulated_vna(vna, "real path-loss measurement")

        center_hz = frequency_mhz * 1e6
        span_hz = 1e6
        points = 11

        if not await vna.setup_sweep(center_hz - span_hz / 2, center_hz + span_hz / 2, points):
            raise RuntimeError(f"VNA setup_sweep failed for probe {probe_id}")
        if not await vna.measure_s_param("S21"):
            raise RuntimeError(f"VNA S21 measurement failed for probe {probe_id}")

        trace = await vna.get_trace_data()
        if not trace:
            raise RuntimeError(f"VNA returned empty trace for probe {probe_id}")

        magnitudes_db = [20.0 * math.log10(abs(c)) for c in trace if abs(c) > 0]
        if not magnitudes_db:
            raise RuntimeError(f"VNA trace had no non-zero magnitudes for probe {probe_id}")

        s21_mean_db = statistics.mean(magnitudes_db)
        s21_std_db = statistics.stdev(magnitudes_db) if len(magnitudes_db) > 1 else 0.0

        # PathLoss = -S21 + G_sgh + G_probe - CableLoss  (ref calculate_measured_path_loss)
        path_loss_db = -s21_mean_db + sgh_gain_dbi + probe_gain_dbi - cable_loss_db
        # 总不确定度 = 测量噪声(std) + 标定参考天线增益不确定度 (典型 0.3 dB)
        uncertainty_db = s21_std_db + 0.3

        logger.info(
            "[PathLoss] vna=%s probe=%d pol=%s freq=%.1f MHz S21=%.2f±%.2f dB → PL=%.2f dB",
            vna_id or "default", probe_id, polarization.value, frequency_mhz,
            s21_mean_db, s21_std_db, path_loss_db,
        )

        return PathLossMeasurement(
            probe_id=probe_id,
            polarization=polarization.value,
            path_loss_db=float(abs(path_loss_db)),
            uncertainty_db=float(uncertainty_db),
        )

    def get_latest_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None,
        operating_mode: Optional[str] = None,
        *,
        require_real: bool = False,
    ) -> Optional[ProbePathLossCalibration]:
        """获取最新的路损校准数据。

        P2-11 Phase 3 (Codex on PR #111): operating_mode 非 None 时按请求的 switch
        operating mode 过滤 cert (精确匹配优先, 退回 legacy 未标记), 否则多 mode 同频
        校准的 lab 会拿错 RF 通路的 per-chain 线损。见 select_latest_path_loss_by_mode。
        """
        query = self.db.query(ProbePathLossCalibration).filter(
            ProbePathLossCalibration.chamber_id == chamber_id,
            ProbePathLossCalibration.status == CalibrationStatus.VALID.value,
            ProbePathLossCalibration.valid_until > datetime.utcnow(),
        )
        if require_real:
            # 正式补偿只从 explicit-real 白名单中挑“最新”。不能先选任意来源
            # 的最新证书再拒绝，否则一次更新的 mock 演练会遮住仍有效的真实证书。
            query = query.filter(ProbePathLossCalibration.use_mock.is_(False))

        if frequency_mhz:
            # 查找最接近的频率
            query = query.filter(
                ProbePathLossCalibration.frequency_mhz.between(
                    frequency_mhz * 0.95, frequency_mhz * 1.05
                )
            )

        return select_latest_path_loss_by_mode(query, operating_mode)

    def get_path_loss_for_probe(
        self,
        chamber_id: UUID,
        probe_id: int,
        polarization: str = "V",
        frequency_mhz: Optional[float] = None
    ) -> Optional[float]:
        """
        获取特定探头的路损值

        用于测量补偿。

        Args:
            chamber_id: 暗室配置 ID
            probe_id: 探头 ID
            polarization: 极化类型 ("V" 或 "H")
            frequency_mhz: 频率 (MHz)，用于查找最接近的校准

        Returns:
            路损值 (dB) 或 None
        """
        calibration = self.get_latest_calibration(
            chamber_id,
            frequency_mhz,
            require_real=not self.use_mock,
        )
        if not calibration:
            return None
        if not self.use_mock and calibration.use_mock is not False:
            provenance = "simulated" if calibration.use_mock is True else "unknown"
            logger.warning(
                "Refusing %s path-loss calibration %s for real compensation",
                provenance,
                calibration.id,
            )
            return None

        probe_data = calibration.probe_path_losses.get(str(probe_id))
        if not probe_data:
            return None

        if polarization.upper() == "V":
            return probe_data.get("pol_v_db") or probe_data.get("path_loss_db")
        else:
            return probe_data.get("pol_h_db") or probe_data.get("path_loss_db")


# ==================== RF 链路增益校准服务 ====================

class RFChainCalibrationService:
    """
    RF 链路增益校准服务

    校准有源器件 (LNA, PA) 的增益和链路总增益。

    上行链路 (UL): 探头 → 双工器 → LNA → 电缆 → 信道仿真器
    下行链路 (DL): 信道仿真器 → 电缆 → PA → 双工器 → 探头
    """

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock

    async def calibrate_uplink(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        vna_id: Optional[str] = None,
        power_meter_id: Optional[str] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        校准上行链路

        测量: 探头 → LNA → 信道仿真器 的总增益

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 测量频率
            vna_id: VNA 设备 ID
            power_meter_id: 功率计设备 ID
            calibrated_by: 校准人员
        """
        # 获取暗室配置
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 检查是否需要上行链路校准
        if not chamber.has_lna:
            return CalibrationResult(
                success=True,
                message="Chamber does not have LNA, no uplink calibration needed",
                data={"has_lna": False}
            )

        try:
            if self.use_mock:
                measurement = self._mock_uplink_measurement(chamber)
            else:
                measurement = await self._real_uplink_measurement(
                    chamber, frequency_mhz, vna_id, power_meter_id
                )

            # 创建校准记录
            calibration = RFChainCalibration(
                chamber_id=chamber_id,
                use_mock=self.use_mock,
                chain_type=ChainTypeEnum.UPLINK.value,
                frequency_mhz=frequency_mhz,
                has_lna=True,
                lna_gain_measured_db=measurement.lna_gain_db,
                has_duplexer=chamber.has_duplexer,
                duplexer_insertion_loss_db=measurement.duplexer_loss_db,
                cable_loss_to_ce_db=measurement.cable_loss_db,
                total_chain_gain_db=measurement.total_gain_db,
                vna_model="Mock VNA" if self.use_mock else vna_id,
                power_meter_model="Mock PM" if self.use_mock else power_meter_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=RF_CHAIN_VALIDITY_DAYS),
                status=CalibrationStatus.VALID.value
            )

            self.db.add(calibration)
            self.db.commit()
            self.db.refresh(calibration)

            return CalibrationResult(
                success=True,
                message="Uplink chain calibration completed",
                data={
                    "calibration_id": str(calibration.id),
                    "lna_gain_db": measurement.lna_gain_db,
                    "total_chain_gain_db": measurement.total_gain_db
                }
            )

        except Exception as e:
            logger.error(f"Uplink calibration failed: {e}")
            return CalibrationResult(
                success=False,
                message=f"Uplink calibration failed: {str(e)}"
            )

    async def calibrate_downlink(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        vna_id: Optional[str] = None,
        power_meter_id: Optional[str] = None,
        signal_generator_id: Optional[str] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        校准下行链路

        测量: 信道仿真器 → PA → 探头 的总增益
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 检查是否需要下行链路校准
        if not chamber.has_pa:
            return CalibrationResult(
                success=True,
                message="Chamber does not have PA, no downlink calibration needed",
                data={"has_pa": False}
            )

        try:
            if self.use_mock:
                measurement = self._mock_downlink_measurement(chamber)
            else:
                measurement = await self._real_downlink_measurement(
                    chamber, frequency_mhz, vna_id, power_meter_id, signal_generator_id
                )

            calibration = RFChainCalibration(
                chamber_id=chamber_id,
                use_mock=self.use_mock,
                chain_type=ChainTypeEnum.DOWNLINK.value,
                frequency_mhz=frequency_mhz,
                has_pa=True,
                pa_gain_measured_db=measurement.pa_gain_db,
                has_duplexer=chamber.has_duplexer,
                duplexer_insertion_loss_db=measurement.duplexer_loss_db,
                cable_loss_to_probe_db=measurement.cable_loss_db,
                total_chain_gain_db=measurement.total_gain_db,
                vna_model="Mock VNA" if self.use_mock else vna_id,
                power_meter_model="Mock PM" if self.use_mock else power_meter_id,
                signal_generator_model="Mock SG" if self.use_mock else signal_generator_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=RF_CHAIN_VALIDITY_DAYS),
                status=CalibrationStatus.VALID.value
            )

            self.db.add(calibration)
            self.db.commit()
            self.db.refresh(calibration)

            return CalibrationResult(
                success=True,
                message="Downlink chain calibration completed",
                data={
                    "calibration_id": str(calibration.id),
                    "pa_gain_db": measurement.pa_gain_db,
                    "total_chain_gain_db": measurement.total_gain_db
                }
            )

        except Exception as e:
            logger.error(f"Downlink calibration failed: {e}")
            return CalibrationResult(
                success=False,
                message=f"Downlink calibration failed: {str(e)}"
            )

    def _mock_uplink_measurement(self, chamber: ChamberConfiguration) -> ChainGainMeasurement:
        """生成 mock 上行链路测量数据"""
        # LNA 增益 (基于配置 + 随机变化)
        lna_gain = chamber.lna_gain_db or 20.0
        lna_gain_measured = lna_gain + np.random.normal(0, 0.3)

        # 双工器损耗
        duplexer_loss = chamber.duplexer_insertion_loss_db or 0.0
        if chamber.has_duplexer:
            duplexer_loss += np.random.normal(0, 0.1)

        # 电缆损耗
        cable_loss = chamber.typical_cable_loss_db + np.random.normal(0, 0.2)

        # 总增益 = LNA - 双工器 - 电缆
        total_gain = lna_gain_measured - duplexer_loss - cable_loss

        return ChainGainMeasurement(
            total_gain_db=total_gain,
            lna_gain_db=lna_gain_measured,
            duplexer_loss_db=duplexer_loss,
            cable_loss_db=cable_loss
        )

    def _mock_downlink_measurement(self, chamber: ChamberConfiguration) -> ChainGainMeasurement:
        """生成 mock 下行链路测量数据"""
        # PA 增益
        pa_gain = chamber.pa_gain_db or 20.0
        pa_gain_measured = pa_gain + np.random.normal(0, 0.3)

        # 双工器损耗
        duplexer_loss = chamber.duplexer_insertion_loss_db or 0.0
        if chamber.has_duplexer:
            duplexer_loss += np.random.normal(0, 0.1)

        # 电缆损耗
        cable_loss = chamber.typical_cable_loss_db + np.random.normal(0, 0.2)

        # 总增益 = PA - 双工器 - 电缆
        total_gain = pa_gain_measured - duplexer_loss - cable_loss

        return ChainGainMeasurement(
            total_gain_db=total_gain,
            pa_gain_db=pa_gain_measured,
            duplexer_loss_db=duplexer_loss,
            cable_loss_db=cable_loss
        )

    async def _real_uplink_measurement(
        self,
        chamber: ChamberConfiguration,
        frequency_mhz: float,
        vna_id: str,
        power_meter_id: str
    ) -> ChainGainMeasurement:
        """Phase 2k: 执行上行链路 (LNA) 真实测量。

        测量链路: 探头 → 双工器 → LNA → 电缆 → 信道仿真器(假定 CE 已替换为
        VNA Port2 作为接收基准)。VNA Port1 注入测试信号, Port2 接 LNA 输出,
        S21 = LNA_gain - duplexer_loss - cable_loss。

        工艺前提: 调用方需保证 RF switch 已切到 LNA path (uplink mode);
        Power Meter 用于交叉校验 (S21 单值 ↔ 绝对功率).

        Returns ChainGainMeasurement 含 lna_gain_db / duplexer_loss_db /
        cable_loss_db, 由公式拆解 (依赖 chamber.has_duplexer / typical_cable_loss_db).
        """
        from app.services.instrument_hal_service import get_hal_service

        hal = get_hal_service()
        vna = hal.drivers.get("vna")
        pm = hal.drivers.get("powerMeter")
        _reject_simulated_vna(vna, "real uplink measurement")

        center_hz = frequency_mhz * 1e6
        span_hz = 1e6
        points = 11

        if not await vna.setup_sweep(center_hz - span_hz / 2, center_hz + span_hz / 2, points):
            raise RuntimeError(f"VNA setup_sweep failed @ {frequency_mhz} MHz")
        if not await vna.measure_s_param("S21"):
            raise RuntimeError(f"VNA S21 measurement failed @ {frequency_mhz} MHz")
        trace = await vna.get_trace_data()
        if not trace:
            raise RuntimeError("VNA returned empty trace")

        magnitudes_db = [20.0 * math.log10(abs(c)) for c in trace if abs(c) > 0]
        if not magnitudes_db:
            raise RuntimeError("VNA trace had no non-zero magnitudes")

        s21_total_db = statistics.mean(magnitudes_db)
        # S21 = LNA_gain - duplexer_loss - cable_loss
        # → LNA_gain = S21 + duplexer_loss + cable_loss
        duplexer_loss = chamber.duplexer_insertion_loss_db or 0.0
        cable_loss = chamber.typical_cable_loss_db or 0.0
        lna_gain_db = s21_total_db + duplexer_loss + cable_loss

        # Cross-check with Power Meter if available (informational only — VNA is authoritative)
        if pm is not None and hasattr(pm, "measure_average_power"):
            try:
                pm_pwr = await pm.measure_average_power()
                logger.info(
                    "[RFChain UL] vna=%s pm=%s freq=%.0f MHz S21=%.2f dB → LNA=%.2f dB (PM xref=%.1f dBm)",
                    vna_id or "default", power_meter_id or "default",
                    frequency_mhz, s21_total_db, lna_gain_db, pm_pwr,
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("[RFChain UL] PM xref skipped: %s", e)
        else:
            logger.info(
                "[RFChain UL] vna=%s freq=%.0f MHz S21=%.2f dB → LNA=%.2f dB",
                vna_id or "default", frequency_mhz, s21_total_db, lna_gain_db,
            )

        return ChainGainMeasurement(
            total_gain_db=s21_total_db,
            lna_gain_db=lna_gain_db,
            duplexer_loss_db=duplexer_loss,
            cable_loss_db=cable_loss,
        )

    async def _real_downlink_measurement(
        self,
        chamber: ChamberConfiguration,
        frequency_mhz: float,
        vna_id: str,
        power_meter_id: str,
        signal_generator_id: str
    ) -> ChainGainMeasurement:
        """Phase 2k: 执行下行链路 (PA) 真实测量。

        测量链路: 信道仿真器 → 电缆 → PA → 双工器 → 探头。SG 注入信号代替
        CE (避免 CE 进入瞬态), VNA Port2 测量探头端功率(或 PM 直接测).

        S21 = PA_gain - duplexer_loss - cable_loss (相对 SG 输出参考)
        """
        from app.services.instrument_hal_service import get_hal_service

        hal = get_hal_service()
        vna = hal.drivers.get("vna")
        sg = hal.drivers.get("signalGenerator")
        _reject_simulated_vna(vna, "real downlink measurement")

        # SG 配置 (仅在 driver 提供该方法时调用; 否则假定 SG 已被运维预置)
        if sg is not None:
            for method, kwargs in (
                ("set_frequency", {"frequency_hz": frequency_mhz * 1e6}),
                ("set_power", {"power_dbm": -30.0}),  # 安全低功率激励
                ("rf_on", {}),
            ):
                if hasattr(sg, method):
                    try:
                        await getattr(sg, method)(**kwargs)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[RFChain DL] sg.%s skipped: %s", method, e)

        try:
            center_hz = frequency_mhz * 1e6
            if not await vna.setup_sweep(center_hz - 0.5e6, center_hz + 0.5e6, 11):
                raise RuntimeError("VNA setup_sweep failed")
            if not await vna.measure_s_param("S21"):
                raise RuntimeError("VNA S21 measurement failed")
            trace = await vna.get_trace_data()
            if not trace:
                raise RuntimeError("VNA returned empty trace")
            magnitudes_db = [20.0 * math.log10(abs(c)) for c in trace if abs(c) > 0]
            if not magnitudes_db:
                raise RuntimeError("VNA trace had no non-zero magnitudes")
            s21_total_db = statistics.mean(magnitudes_db)

            duplexer_loss = chamber.duplexer_insertion_loss_db or 0.0
            cable_loss = chamber.typical_cable_loss_db or 0.0
            pa_gain_db = s21_total_db + duplexer_loss + cable_loss

            logger.info(
                "[RFChain DL] vna=%s sg=%s freq=%.0f MHz S21=%.2f dB → PA=%.2f dB",
                vna_id or "default", signal_generator_id or "default",
                frequency_mhz, s21_total_db, pa_gain_db,
            )

            return ChainGainMeasurement(
                total_gain_db=s21_total_db,
                pa_gain_db=pa_gain_db,
                duplexer_loss_db=duplexer_loss,
                cable_loss_db=cable_loss,
            )
        finally:
            # 关 SG 输出避免长时间打信号
            if sg is not None and hasattr(sg, "rf_off"):
                try:
                    await sg.rf_off()
                except Exception as e:  # noqa: BLE001
                    logger.debug("[RFChain DL] sg.rf_off skipped: %s", e)

    def get_latest_uplink_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None
    ) -> Optional[RFChainCalibration]:
        """获取最新的上行链路校准"""
        query = self.db.query(RFChainCalibration).filter(
            RFChainCalibration.chamber_id == chamber_id,
            RFChainCalibration.chain_type == ChainTypeEnum.UPLINK.value,
            RFChainCalibration.status == CalibrationStatus.VALID.value
        )

        if not self.use_mock:
            query = query.filter(
                RFChainCalibration.use_mock.is_(False),
                RFChainCalibration.valid_until > datetime.utcnow(),
            )

        if frequency_mhz:
            query = query.filter(
                RFChainCalibration.frequency_mhz.between(
                    frequency_mhz * 0.95, frequency_mhz * 1.05
                )
            )

        return query.order_by(desc(RFChainCalibration.calibrated_at)).first()

    def get_latest_downlink_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None
    ) -> Optional[RFChainCalibration]:
        """获取最新的下行链路校准"""
        query = self.db.query(RFChainCalibration).filter(
            RFChainCalibration.chamber_id == chamber_id,
            RFChainCalibration.chain_type == ChainTypeEnum.DOWNLINK.value,
            RFChainCalibration.status == CalibrationStatus.VALID.value
        )

        if not self.use_mock:
            query = query.filter(
                RFChainCalibration.use_mock.is_(False),
                RFChainCalibration.valid_until > datetime.utcnow(),
            )

        if frequency_mhz:
            query = query.filter(
                RFChainCalibration.frequency_mhz.between(
                    frequency_mhz * 0.95, frequency_mhz * 1.05
                )
            )

        return query.order_by(desc(RFChainCalibration.calibrated_at)).first()

    def get_uplink_gain(self, chamber_id: UUID, frequency_mhz: Optional[float] = None) -> Optional[float]:
        """获取上行链路总增益"""
        cal = self.get_latest_uplink_calibration(chamber_id, frequency_mhz)
        return cal.total_chain_gain_db if cal else None

    def get_downlink_gain(self, chamber_id: UUID, frequency_mhz: Optional[float] = None) -> Optional[float]:
        """获取下行链路总增益"""
        cal = self.get_latest_downlink_calibration(chamber_id, frequency_mhz)
        return cal.total_chain_gain_db if cal else None


# ==================== 多频点路损校准服务 ====================

class MultiFrequencyPathLossService:
    """
    多频点路损校准服务

    存储扫频校准的路损数据，支持频率插值。
    """

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock

    async def calibrate_frequency_sweep(
        self,
        chamber_id: UUID,
        probe_ids: List[int],
        polarization: PolarizationType,
        freq_start_mhz: float,
        freq_stop_mhz: float,
        freq_step_mhz: float,
        sgh_model: str,
        sgh_gain_dbi: float,
        vna_id: Optional[str] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        执行多频点扫频校准

        Args:
            chamber_id: 暗室配置 ID
            probe_ids: 探头 ID 列表
            polarization: 极化类型
            freq_start_mhz: 起始频率
            freq_stop_mhz: 终止频率
            freq_step_mhz: 频率步进
            sgh_model: SGH 型号
            sgh_gain_dbi: SGH 增益
            vna_id: VNA 设备 ID
            calibrated_by: 校准人员
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 生成频率点
        num_points = int((freq_stop_mhz - freq_start_mhz) / freq_step_mhz) + 1
        frequency_points = [freq_start_mhz + i * freq_step_mhz for i in range(num_points)]

        calibration_ids = []
        warnings: List[str] = []

        import contextlib
        from app.services.instrument_test_lease import instrument_test_lease

        # P2-30: 作业级租约（同上，条件 = 会走 CE+SA 路径）—— 整个
        # probe × 频点扫频只真取/放一次 F64 控制权。
        job_lease = (
            instrument_test_lease(
                f"path-loss-sweep:{freq_start_mhz:g}-{freq_stop_mhz:g}MHz",
                control_f64=True,
                control_uxm=False,
                enable_monitoring=False,
            )
            if not self.use_mock and chamber.cable_sgh_to_sa_loss_db is not None
            else contextlib.nullcontext()
        )
        async with job_lease:
            for probe_id in probe_ids:
                try:
                    if self.use_mock:
                        path_losses, uncertainties = self._mock_frequency_sweep(
                            probe_id, polarization, frequency_points,
                            chamber.chamber_radius_m, chamber.probe_gain_dbi
                        )
                    elif chamber.cable_sgh_to_sa_loss_db is not None:
                        # CE+SA real sweep — delegates each frequency point to
                        # ProbePathLossCalibrationService._real_path_loss_measurement
                        # _via_ce_sa, so D/B capability dispatch, BSE preference,
                        # finally-stop, etc., are handled identically to single-freq.
                        path_losses, uncertainties = await self._real_frequency_sweep_via_ce_sa(
                            probe_id=probe_id,
                            polarization=polarization,
                            frequency_points=frequency_points,
                            sgh_gain_dbi=sgh_gain_dbi,
                            probe_gain_dbi=chamber.probe_gain_dbi,
                            cable_sgh_to_sa_loss_db=chamber.cable_sgh_to_sa_loss_db,
                            warnings=warnings,
                        )
                    else:
                        return CalibrationResult(
                            success=False,
                            message=(
                                f"Multi-freq real sweep requires CE+SA wiring: set "
                                f"chamber.cable_sgh_to_sa_loss_db (commissioning measured) "
                                f"on chamber {chamber_id}, or call with use_mock=True."
                            ),
                        )

                    calibration = MultiFrequencyPathLoss(
                        chamber_id=chamber_id,
                        use_mock=self.use_mock,
                        probe_id=probe_id,
                        polarization=polarization.value,
                        freq_start_mhz=freq_start_mhz,
                        freq_stop_mhz=freq_stop_mhz,
                        freq_step_mhz=freq_step_mhz,
                        num_points=num_points,
                        frequency_points_mhz=frequency_points,
                        path_loss_db=path_losses,
                        uncertainty_db=uncertainties,
                        calibrated_at=datetime.utcnow(),
                        calibrated_by=calibrated_by,
                        valid_until=datetime.utcnow() + timedelta(days=MULTI_FREQ_VALIDITY_DAYS),
                        status=CalibrationStatus.VALID.value
                    )

                    self.db.add(calibration)
                    self.db.flush()
                    calibration_ids.append(str(calibration.id))

                except Exception as e:
                    logger.error(f"Multi-freq calibration failed for probe {probe_id}: {e}")
                    return CalibrationResult(
                        success=False,
                        message=f"Calibration failed for probe {probe_id}: {str(e)}",
                        warnings=warnings,
                    )

        self.db.commit()

        return CalibrationResult(
            success=True,
            message=f"Multi-frequency calibration completed for {len(probe_ids)} probes",
            data={
                "calibration_ids": calibration_ids,
                "num_probes": len(probe_ids),
                "num_freq_points": num_points,
                "freq_range": f"{freq_start_mhz}-{freq_stop_mhz} MHz"
            },
            warnings=warnings,
        )

    def _mock_frequency_sweep(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_points: List[float],
        chamber_radius_m: float,
        probe_gain_dbi: float
    ) -> Tuple[List[float], List[float]]:
        """生成 mock 扫频数据"""
        path_losses = []
        uncertainties = []

        for freq in frequency_points:
            # 基础 FSPL
            fspl = calculate_fspl(freq, chamber_radius_m)

            # 频率相关变化
            freq_variation = 0.5 * np.sin((freq - frequency_points[0]) * 0.01)

            # 探头位置变化
            position_variation = np.sin(probe_id * 0.3) * 1.5

            # 极化变化
            pol_variation = 0.3 if polarization == PolarizationType.V else -0.2

            # 随机噪声
            noise = np.random.normal(0, 0.2)

            path_loss = fspl + freq_variation + position_variation + pol_variation + noise
            uncertainty = 0.3 + abs(noise) * 0.3

            path_losses.append(path_loss)
            uncertainties.append(uncertainty)

        return path_losses, uncertainties

    async def _real_frequency_sweep_via_ce_sa(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_points: List[float],
        sgh_gain_dbi: float,
        probe_gain_dbi: float,
        cable_sgh_to_sa_loss_db: float,
        warnings: List[str],
    ) -> Tuple[List[float], List[float]]:
        """[A3] CE+SA 真测多频点扫频 — delegates each freq to single-freq path.

        Reuses ProbePathLossCalibrationService._real_path_loss_measurement_via
        _ce_sa per-frequency, so we inherit the full D/B capability dispatch
        (CE-internal CW gen vs BSE+passthrough), the BSE-over-SG preference,
        the finally-stop guarantees, and the rfSwitch auto-routing logic for
        free. Total operator action: 0 (same as single-freq).

        ce_port + route_target left None: this entry point is chamber-keyed
        (no RFChainSpec available). Multi-freq + topology-derived auto-routing
        is a follow-up — would route once per (probe, pol) and sweep all freqs
        on the same routed chain (more efficient than re-routing per freq, but
        also more code).
        """
        # In-file delegation; both services live in this module so no import.
        pl_service = ProbePathLossCalibrationService(self.db, use_mock=False)

        path_losses: List[float] = []
        uncertainties: List[float] = []
        for freq_mhz in frequency_points:
            m = await pl_service._real_path_loss_measurement_via_ce_sa(
                probe_id=probe_id,
                polarization=polarization,
                frequency_mhz=freq_mhz,
                ce_tx_power_dbm=-20.0,
                sgh_gain_dbi=sgh_gain_dbi,
                probe_gain_dbi=probe_gain_dbi,
                cable_sgh_to_sa_loss_db=cable_sgh_to_sa_loss_db,
                warning_sink=warnings,
                warning_label=(
                    f"sweep probe {probe_id} {polarization.value} "
                    f"{freq_mhz:.1f} MHz"
                ),
            )
            path_losses.append(m.path_loss_db)
            uncertainties.append(m.uncertainty_db)

        return path_losses, uncertainties

    async def _real_frequency_sweep(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_points: List[float],
        vna_id: str,
        sgh_gain_dbi: float,
        probe_gain_dbi: float
    ) -> Tuple[List[float], List[float]]:
        """[DEPRECATED] Legacy VNA-based sweep — never implemented.

        New deployments use _real_frequency_sweep_via_ce_sa (CE+SA), which is
        the path `calibrate_frequency_sweep` dispatches to when
        `chamber.cable_sgh_to_sa_loss_db` is populated. Kept only so the API
        signature doesn't break for anyone wiring legacy.
        """
        raise NotImplementedError(
            "Legacy VNA frequency sweep was never implemented. Set "
            "chamber.cable_sgh_to_sa_loss_db so calibrate_frequency_sweep "
            "routes to the CE+SA implementation instead."
        )

    def get_path_loss_at_frequency(
        self,
        chamber_id: UUID,
        probe_id: int,
        polarization: str,
        frequency_mhz: float
    ) -> Optional[float]:
        """
        获取指定频率的路损 (支持插值)

        Args:
            chamber_id: 暗室 ID
            probe_id: 探头 ID
            polarization: 极化类型
            frequency_mhz: 目标频率

        Returns:
            插值后的路损值
        """
        calibration = self.db.query(MultiFrequencyPathLoss).filter(
            MultiFrequencyPathLoss.chamber_id == chamber_id,
            MultiFrequencyPathLoss.probe_id == probe_id,
            MultiFrequencyPathLoss.polarization == polarization,
            MultiFrequencyPathLoss.status == CalibrationStatus.VALID.value,
            MultiFrequencyPathLoss.freq_start_mhz <= frequency_mhz,
            MultiFrequencyPathLoss.freq_stop_mhz >= frequency_mhz
        )
        if not self.use_mock:
            calibration = calibration.filter(
                MultiFrequencyPathLoss.use_mock.is_(False),
                MultiFrequencyPathLoss.valid_until > datetime.utcnow(),
            )
        calibration = calibration.order_by(desc(MultiFrequencyPathLoss.calibrated_at)).first()

        if not calibration:
            return None

        # 线性插值
        freq_points = calibration.frequency_points_mhz
        path_losses = calibration.path_loss_db

        return float(np.interp(frequency_mhz, freq_points, path_losses))
