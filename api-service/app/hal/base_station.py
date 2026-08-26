"""
Base Station Emulator HAL

Provides interface and mock implementation for base station emulators.
Supports both 5G NR (Keysight UXM) and LTE (R&S CMW500) base station emulators.

应用层统一调用 BaseStationDriver 抽象接口，无需关心底层使用哪种仪器。
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List, ClassVar, Literal
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BaseStationIdentity:
    """由已注册驱动提供的基站型号、固件与选件身份快照。"""

    adapter_id: Literal["uxm", "cmw500"]
    model: str
    firmware_version: str | None
    options: tuple[str, ...]


@dataclass(frozen=True)
class BaseStationRequestedConfig:
    """Vendor-neutral, RAT-aware PCell request owned by the execution layer.

    The request carries mutually exclusive NR/LTE channel numbers.  Adapter
    translation happens below this contract; callers never select a driver
    dialect or put LTE EARFCN into the legacy NR ``arfcn`` slot.
    """

    radio_technology: Literal["nr5g", "lte"]
    channel_kind: Literal["nr_arfcn", "lte_dl_earfcn"]
    frequency_mhz: float
    bandwidth_mhz: float
    band: str
    duplex: str | None
    nr_arfcn: int | None
    lte_dl_earfcn: int | None
    subcarrier_spacing_khz: int | None
    mimo_layers: int
    downlink_power_dbm: float
    downlink_power_dbm_per_bandwidth: float | None = None
    port_preset: str | None = None
    scheduler_algorithm: str | None = None
    csi_rs_ports: int | None = None

    def to_driver_payload(self) -> dict[str, Any]:
        """Translate the common request into the existing driver payload API."""

        payload: dict[str, Any] = {
            "radio_technology": self.radio_technology,
            "channel_kind": self.channel_kind,
            "frequency_mhz": self.frequency_mhz,
            "bandwidth_mhz": self.bandwidth_mhz,
            "band": self.band,
            "mimo_layers": self.mimo_layers,
            "dl_power_dbm": self.downlink_power_dbm,
        }
        if self.radio_technology == "nr5g":
            payload["nr_arfcn"] = self.nr_arfcn
            payload["arfcn"] = self.nr_arfcn
            payload["scs_khz"] = self.subcarrier_spacing_khz
        else:
            payload["lte_dl_earfcn"] = self.lte_dl_earfcn
            payload["earfcn"] = self.lte_dl_earfcn
            payload["duplex"] = self.duplex
        if self.downlink_power_dbm_per_bandwidth is not None:
            payload["dl_power_dbm_per_bw"] = self.downlink_power_dbm_per_bandwidth
        if self.port_preset is not None:
            payload["mimo_port_preset"] = self.port_preset
        if self.scheduler_algorithm is not None:
            payload["sched_algo"] = self.scheduler_algorithm
        if self.csi_rs_ports is not None:
            payload["csi_rs_ports"] = self.csi_rs_ports
        return payload


@dataclass(frozen=True)
class AppliedCellConfig:
    """UE 协商后实际可用的通用小区能力。"""

    ue_max_dl_layers: int | None = None
    ue_max_modulation_dl: str | None = None


@dataclass(frozen=True)
class BaseStationConfigResult:
    """基站配置请求与权威回读形成的应用结果。"""

    requested: dict[str, Any]
    applied: dict[str, Any] | None
    confirmed: bool
    reason: str


@dataclass(frozen=True)
class BaseStationCleanupResult:
    """MEASURE 阶段拥有的信令停止与 SAFE_IDLE 结果。"""

    stop_signaling_confirmed: bool
    safe_idle_confirmed: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class BaseStationRemoteSessionResult:
    """驱动成功建立真实 transport session 后返回的不可伪造身份。"""

    adapter_id: Literal["uxm", "cmw500"]
    session_token: str
    acquired_confirmed: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class BaseStationControlReleaseResult:
    """与单次 lease/attempt 绑定的基站控制会话释放结果。"""

    measurement_attempt_id: str | None
    lease_id: str
    adapter_id: Literal["uxm", "cmw500"]
    session_token: str
    remote_session_acquired_confirmed: bool
    transport_session_released_confirmed: bool
    front_panel_local_confirmed: bool | None
    warnings: tuple[str, ...]


# ===========================================================================
# 基站仿真器通用枚举
# ===========================================================================

class RadioTechnology(str, Enum):
    """基站支持的无线接入技术"""
    NR5G = "NR5G"
    LTE = "LTE"
    LTE_NR_NSA = "LTE_NR_NSA"  # LTE + NR 非独立组网 (EN-DC)


class CellState(str, Enum):
    """小区状态"""
    OFF = "OFF"          # 小区关闭 (未激活)
    ON = "ON"            # 小区已激活 (射频开启)
    IDLE = "IDLE"        # 等待 UE 接入
    CONNECTED = "CONN"   # UE 已连接 (RRC Connected)
    ERROR = "ERROR"


class ThroughputMetrics:
    """吞吐量测量结果。

    **口径 (2026-08-03 用户定)**: 这里存的是**仪表与终端上报的参数**,
    不是我们自己统计的传输数据量。

    ``*_throughput_mbps`` = 统计窗口内的**平均**吞吐量 (测试例的结论值);
    ``*_throughput_current_mbps`` = 查询时刻的**瞬时**吞吐量 (会随调度抖动,
    适合实时曲线, 不适合当结论)。两者都存, 因为一个回答"这次测出来多少",
    另一个回答"现在跑到多少"。
    """
    SCOPE_UNKNOWN = "unknown"
    SCOPE_PCELL = "pcell"
    SCOPE_NR_ALL_CELLS = "nr_all_cells"
    SCOPE_SIMULATED = "simulated"
    VALID_SCOPES = frozenset({
        SCOPE_UNKNOWN,
        SCOPE_PCELL,
        SCOPE_NR_ALL_CELLS,
        SCOPE_SIMULATED,
    })

    def __init__(
        self,
        dl_throughput_mbps: Optional[float] = None,
        ul_throughput_mbps: Optional[float] = None,
        dl_bler: float = 0.0,
        ul_bler: float = 0.0,
        cqi: int = 0,
        rank_indicator: int = 1,
        mcs_dl: int = 0,
        mcs_ul: int = 0,
        rsrp_dbm: float = -999.0,
        sinr_db: float = -999.0,
        dl_throughput_current_mbps: Optional[float] = None,
        ul_throughput_current_mbps: Optional[float] = None,
        kpi_valid: Optional[Dict[str, bool]] = None,
        throughput_scope: str = SCOPE_UNKNOWN,
    ):
        self.dl_throughput_mbps = dl_throughput_mbps
        self.ul_throughput_mbps = ul_throughput_mbps
        self.dl_bler = dl_bler
        self.ul_bler = ul_bler
        self.cqi = cqi
        self.rank_indicator = rank_indicator
        self.mcs_dl = mcs_dl
        self.mcs_ul = mcs_ul
        self.rsrp_dbm = rsrp_dbm
        self.sinr_db = sinr_db
        self.dl_throughput_current_mbps = dl_throughput_current_mbps
        self.ul_throughput_current_mbps = ul_throughput_current_mbps
        self.throughput_scope = (
            throughput_scope
            if throughput_scope in self.VALID_SCOPES
            else self.SCOPE_UNKNOWN
        )
        # 显式白名单：真实 0.0 是有效值；缺测 None 不是。真实驱动可以用
        # ``kpi_valid`` 覆盖/补充其余 KPI 的解析真值，正式调用方不得从数值大小猜。
        self.kpi_valid: Dict[str, bool] = {
            "dl_throughput": dl_throughput_mbps is not None,
            "ul_throughput": ul_throughput_mbps is not None,
            "dl_throughput_current": dl_throughput_current_mbps is not None,
            "ul_throughput_current": ul_throughput_current_mbps is not None,
        }
        if kpi_valid:
            self.kpi_valid.update({key: value is True for key, value in kpi_valid.items()})

    def is_valid(self, key: str) -> bool:
        """仅显式 ``True`` 才算可信 KPI；缺键与历史对象一律 fail-closed。"""
        return self.kpi_valid.get(key) is True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dl_throughput_mbps": self.dl_throughput_mbps,
            "ul_throughput_mbps": self.ul_throughput_mbps,
            "dl_throughput_current_mbps": self.dl_throughput_current_mbps,
            "ul_throughput_current_mbps": self.ul_throughput_current_mbps,
            "dl_bler": self.dl_bler,
            "ul_bler": self.ul_bler,
            "cqi": self.cqi,
            "rank_indicator": self.rank_indicator,
            "mcs_dl": self.mcs_dl,
            "mcs_ul": self.mcs_ul,
            "rsrp_dbm": self.rsrp_dbm,
            "sinr_db": self.sinr_db,
            "kpi_valid": dict(self.kpi_valid),
            "throughput_scope": self.throughput_scope,
        }


class BaseStationDriver(InstrumentDriver):
    """
    Abstract interface for Base Station Emulator (HAL Layer 2)

    定义了所有基站仿真器必须实现的标准化操作原语。
    无论底层是 Keysight UXM (5G NR) 还是 R&S CMW500 (LTE),
    应用层通过此接口统一操作。

    核心原语:
      - set_cell_config():     配置物理小区参数 (频率/带宽/SCS)
      - set_frc_config():      配置固定参考信道 (FRC)
      - set_downlink_power():  调节下行发射功率
      - start_signaling():     开启信令，等待 UE Attach
      - stop_signaling():      停止信令
      - get_throughput_metrics(): 轮询读取 MAC 吞吐量 + BLER + CQI
    """

    # Formal CA is opt-in: a driver may only allow SCell writes when it can
    # independently confirm the requested active SCell set. Real drivers keep
    # the fail-closed default until a vendor-documented readback is available.
    SCELL_ACTIVATION_READBACK_AUTHORITATIVE = False
    adapter_id: ClassVar[Literal["uxm", "cmw500"]]
    # 输入电平闭环是显式 opt-in 能力，不能因某驱动恰好实现同名方法而推断。
    # P1-73A 的 CMW500 功率能力尚未开放，保持默认 False。
    input_level_control_supported: ClassVar[bool] = False
    # RRC reconfiguration is opt-in.  The abstract method exists to define
    # the contract, so hasattr() cannot distinguish an implemented adapter.
    rrc_reconfiguration_supported: ClassVar[bool] = False
    max_bandwidth_mhz: ClassVar[float | None] = None
    max_mimo_layers: ClassVar[int | None] = None

    # ===================================================================
    # 小区配置
    # ===================================================================

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        """
        配置物理小区参数。

        Args:
            config: 小区配置字典, 支持以下字段:
                - band: str,          NR 频段 (e.g., "n78")
                - frequency_mhz: float, 中心频率
                - bandwidth_mhz: float, 信道带宽 (e.g., 100)
                - scs_khz: int,       子载波间隔 (15/30/60/120 kHz)
                - duplex: str,        双工模式 ("TDD" / "FDD")
                - mimo_layers: int,   MIMO 层数 (1/2/4)
                - cell_id: int,       物理小区 ID

        Returns:
            True if configuration successful
        """
        raise NotImplementedError

    async def apply_requested_config(
        self, requested: BaseStationRequestedConfig,
    ) -> bool:
        """Apply one typed request through the adapter's existing primitive."""

        if not isinstance(requested, BaseStationRequestedConfig):
            raise TypeError("requested must be BaseStationRequestedConfig")
        requested_technology = (
            RadioTechnology.NR5G
            if requested.radio_technology == "nr5g"
            else RadioTechnology.LTE
        )
        if requested_technology not in self.get_supported_technologies():
            logger.error(
                "[%s] Rejecting %s configuration: adapter %s does not support it",
                self.instrument_id,
                requested.radio_technology,
                self.adapter_id,
            )
            return False
        if (
            self.max_bandwidth_mhz is not None
            and requested.bandwidth_mhz > self.max_bandwidth_mhz
        ):
            logger.error(
                "[%s] Rejecting bandwidth %.3f MHz: adapter %s maximum is %.3f MHz",
                self.instrument_id,
                requested.bandwidth_mhz,
                self.adapter_id,
                self.max_bandwidth_mhz,
            )
            return False
        if (
            self.max_mimo_layers is not None
            and requested.mimo_layers > self.max_mimo_layers
        ):
            logger.error(
                "[%s] Rejecting %d MIMO layers: adapter %s maximum is %d",
                self.instrument_id,
                requested.mimo_layers,
                self.adapter_id,
                self.max_mimo_layers,
            )
            return False
        return await self.set_cell_config(requested.to_driver_payload())

    def get_mimo_route_snapshot(self, preset: str) -> Dict[str, Any]:
        """Optional physical connector projection for topology display.

        Drivers without an authoritative profile/readback return an empty
        snapshot. The application must warn and keep logical topology usable;
        it must not infer connector names from adapter/model identity.
        """

        return {}

    async def set_frc_config(
        self,
        frc_reference: str,
        modulation: Optional[str] = None,
        target_coding_rate: Optional[float] = None,
    ) -> bool:
        """
        配置固定参考信道 (FRC / Fixed Reference Channel)。

        按 3GPP TS 38.521-4 (NR) 或 TS 36.521 (LTE)
        定义的标准FRC进行配置。

        Args:
            frc_reference: FRC 参考名 (e.g., "G-FR1-A1-1", "R.0")
            modulation: 调制方式 (e.g., "256QAM", "64QAM")
            target_coding_rate: 目标编码率

        Returns:
            True if FRC configured successfully
        """
        raise NotImplementedError

    async def set_downlink_power(self, power_dbm: float) -> bool:
        """
        设置下行发射功率。

        Args:
            power_dbm: 下行功率 (dBm), 典型范围 -120 ~ 0

        Returns:
            True if power set successfully
        """
        raise NotImplementedError

    # ===================================================================
    # 信令控制
    # ===================================================================

    async def start_signaling(self, timeout_s: float = 60.0) -> bool:
        """
        开启物理小区信令, 激活小区并等待 UE Attach。

        等效于 "Cell ON" + 等待 RRC Connection + Attach Complete。

        Args:
            timeout_s: 等待 UE Attach 的超时时间 (秒)

        Returns:
            True if UE successfully attached within timeout
        """
        raise NotImplementedError

    async def stop_signaling(self) -> bool:
        """
        停止物理小区信令, 断开 UE 连接并关闭小区。

        Returns:
            True if signaling stopped successfully
        """
        raise NotImplementedError

    async def start_cell(self) -> bool:
        """Start base station transmission (alias for start_signaling)"""
        return await self.start_signaling()

    async def stop_cell(self) -> bool:
        """Stop base station transmission (alias for stop_signaling)"""
        return await self.stop_signaling()

    async def get_cell_state(self) -> CellState:
        """获取小区当前状态"""
        raise NotImplementedError

    # ===================================================================
    # 测量
    # ===================================================================

    async def get_throughput_metrics(
        self,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> ThroughputMetrics:
        """
        轮询读取 MAC 层吞吐量指标。

        返回当前的 DL/UL 吞吐量, BLER, CQI, Rank Indicator, MCS。
        建议采样间隔: 200ms。

        Returns:
            ThroughputMetrics 数据对象
        """
        raise NotImplementedError

    async def measure_throughput_window(
        self,
        window_s: float,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> ThroughputMetrics:
        """
        采集一个独立的 MAC 统计窗口 (Phase 2d 同步语义)。

        语义 = "建立独立统计边界 → 等待 window_s 秒 → 读一次"。
        每次调用对应一个独立的 i.i.d. 样本; 调用方循环 N 次得到 N 个独立样本,
        std/mean 才有意义。区别于 get_throughput_metrics() 的滑动窗口语义。

        默认实现 = sleep + 单次 get_throughput_metrics() — 适用于 mock 或
        不提供独立窗口控制的简单仿真器。真硬件必须按各自有厂商出处的能力
        override；无法确认窗口边界时应保守返回未验证值，不得照搬其他方言。

        Args:
            window_s: 窗口长度 (秒); 对应 stat_count 子帧数 (1ms/subframe)

        Returns:
            该窗口结束时的 ThroughputMetrics 快照
        """
        import asyncio as _asyncio
        await _asyncio.sleep(max(window_s, 0.0))
        return await self.get_throughput_metrics(
            throughput_scope=throughput_scope,
        )

    async def get_ue_info(self) -> Dict[str, Any]:
        """
        获取已连接 UE 的信息。

        Returns:
            UE 信息字典 (IMSI, IMEI, capabilities, etc.)
        """
        raise NotImplementedError

    async def query_ue_capability(self) -> Dict[str, Any]:
        """
        查询 UE 上报的 3GPP 能力 (Phase 2e)。

        4x4 MIMO 测试前必须确认 DUT 真支持 4 layer DL — 否则下行配置
        4 layer 但 UE 默认 2 layer attach, 跑出来的数据其实是 2 layer。

        典型返回字段(driver 各自填充):
            - max_dl_layers: int      (1/2/4/8)
            - max_ul_layers: int
            - max_modulation_dl: str  ('64QAM' / '256QAM' / '1024QAM')
            - max_modulation_ul: str
            - supported_bands: List[str]
            - ca_combinations: List[str]  (载波聚合组合, e.g. ['n78+n41'])
            - source: 'real_ue' | 'mock' | 'unavailable'

        Returns:
            能力字典; 至少必须有 'max_dl_layers' 和 'source'
        """
        raise NotImplementedError

    async def reconfigure_rrc(
        self,
        *,
        mimo_layers: Optional[int] = None,
        modulation: Optional[str] = None,
    ) -> bool:
        """
        触发 RRC reconfiguration, 把新参数下推给已 attach 的 UE。

        set_cell_config() 改的是基站内部配置, RRC 重配是把这些变化通知到
        UE 的 RadioBearer/PDSCH-Config。某些 UXM firmware 在 cell config
        变化时会自动触发 RRC reconfig; 其它需要显式调用本接口。

        Args:
            mimo_layers: 目标 DL layer 数 (1/2/4/8); None = 不改
            modulation: 'QPSK' | '16QAM' | '64QAM' | '256QAM' | '1024QAM'; None = 不改

        Returns:
            True if RRC reconfiguration completed (UE acked)
        """
        raise NotImplementedError

    # ===================================================================
    # 载波聚合 (Phase 2g)
    # ===================================================================

    async def add_secondary_cell(
        self,
        cc_index: int,
        cc_config: Dict[str, Any],
    ) -> bool:
        """
        添加 SCell (Secondary Cell)。

        NR-CA 中 PCell 走 set_cell_config (cc_index=0 隐式), SCell 走本接口
        (cc_index ≥ 1)。一次测试可以串多次 add_secondary_cell, 然后调
        activate_secondary_cells 一次性激活全部。

        Args:
            cc_index: SCell 序号, 从 1 开始 (PCell 是 0)
            cc_config: 与 set_cell_config 同结构, 至少含 frequency_mhz / bandwidth_mhz

        Returns:
            True if SCell add succeeded (基站接受配置, 但尚未激活)
        """
        raise NotImplementedError

    async def activate_secondary_cells(
        self,
        *,
        expected_indices: Optional[List[int]] = None,
    ) -> bool:
        """激活 SCell；仅在权威回读确认预期集合均已激活时返回 True。"""
        raise NotImplementedError

    async def remove_all_secondary_cells(self) -> bool:
        """移除所有 SCell (cleanup 用; 异常退出时避免下次测试碰到残留状态)。"""
        raise NotImplementedError

    # ===================================================================
    # 能力查询
    # ===================================================================

    def get_supported_technologies(self) -> List[RadioTechnology]:
        """
        声明该基站仿真器支持的无线接入技术。

        Returns:
            支持的 RadioTechnology 列表
        """
        return [RadioTechnology.LTE]  # 默认支持 LTE

    # ===================================================================
    # 配置文件管理 (一键配置)
    # ===================================================================

    async def load_state_file(self, filepath: str) -> bool:
        """
        从仪器本机加载已保存的配置文件，一次性恢复全部仪器状态。

        相比逐条 SCPI 配置的优势:
          - 消除参数顺序依赖 (如 Band 必须在 Duplex 之前)
          - 保证所有参数的完整性 (不会遗漏 TDD 配置、RF 路由等)
          - 可由工程师在仪器前面板手动调优后保存为模板

        Args:
            filepath: 仪器本机的文件路径

        Returns:
            True if state loaded successfully
        """
        raise NotImplementedError

    async def save_state_file(self, filepath: str) -> bool:
        """
        将仪器当前完整配置保存为文件。

        Args:
            filepath: 仪器本机的保存路径

        Returns:
            True if state saved successfully
        """
        raise NotImplementedError


# ===========================================================================
# Mock 实现 (开发/测试用)
# ===========================================================================

class MockBaseStation(BaseStationDriver):
    """Mock Base Station Emulator for development."""

    # The mock owns its complete in-memory SCell state and can compare the
    # requested index set exactly. Simulated measurements are still excluded
    # from formal KPI by the existing provenance gate.
    SCELL_ACTIVATION_READBACK_AUTHORITATIVE = True
    rrc_reconfiguration_supported = True

    driver_source = "mock"
    simulated = True

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._cell_running = False
        self._cell_state = CellState.OFF
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0
        self._scs_khz = 30
        self._dl_power_dbm = -50.0
        self._mimo_layers = 2
        self._frc = ""

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        await asyncio.sleep(0.3)
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def disconnect(self) -> bool:
        if self._cell_running:
            await self.stop_signaling()
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        return await self.set_cell_config(config)

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="5g_nr",
                description="5G NR support",
                supported=True,
                parameters={
                    "frequency_range": [450, 6000],
                    "max_bandwidth_mhz": 100,
                },
            ),
            InstrumentCapability(
                name="lte",
                description="LTE support",
                supported=True,
                parameters={
                    "frequency_range": [450, 3800],
                    "max_bandwidth_mhz": 20,
                },
            ),
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        tx_power = self._dl_power_dbm + random.uniform(-0.5, 0.5)
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "cell_running": self._cell_running,
                "cell_state": self._cell_state.value,
                "frequency_mhz": self._frequency_mhz,
                "bandwidth_mhz": self._bandwidth_mhz,
                "scs_khz": self._scs_khz,
                "tx_power_dbm": round(tx_power, 2),
                "mimo_layers": self._mimo_layers,
                "connected_ues": (
                    random.randint(0, 1) if self._cell_running else 0
                ),
            },
        )

    async def reset(self) -> bool:
        if self._cell_running:
            await self.stop_signaling()
        self._frequency_mhz = 3500.0
        self._bandwidth_mhz = 100.0
        self._scs_khz = 30
        self._dl_power_dbm = -50.0
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        if "frequency_mhz" in config:
            self._frequency_mhz = config["frequency_mhz"]
        if "bandwidth_mhz" in config:
            self._bandwidth_mhz = config["bandwidth_mhz"]
        if "scs_khz" in config:
            self._scs_khz = config["scs_khz"]
        if "mimo_layers" in config:
            self._mimo_layers = config["mimo_layers"]
        self._set_status(InstrumentStatus.READY)
        return True

    async def set_frc_config(
        self, frc_reference: str, modulation=None, target_coding_rate=None
    ) -> bool:
        self._frc = frc_reference
        return True

    async def set_downlink_power(self, power_dbm: float) -> bool:
        if power_dbm < -120 or power_dbm > 0:
            return False
        # 当前 Mock 仍模拟既有 UXM 方言；builder 归 UXM profile 所有，通用 HAL
        # 只在诊断写方调用同一真实命令拼装函数，不复制命令字面量。
        from app.hal.uxm_command_profiles import build_uxm_downlink_power_command

        self._simulate_scpi_write(
            build_uxm_downlink_power_command(self.config, power_dbm)
        )
        self._simulate_scpi_query("*OPC?", "1")
        self._dl_power_dbm = power_dbm
        return True

    async def start_signaling(self, timeout_s: float = 60.0) -> bool:
        self._set_status(InstrumentStatus.BUSY)
        self._cell_running = True
        self._cell_state = CellState.CONNECTED
        await asyncio.sleep(0.2)
        return True

    async def stop_signaling(self) -> bool:
        self._cell_running = False
        self._cell_state = CellState.OFF
        self._set_status(InstrumentStatus.READY)
        return True

    async def get_cell_state(self) -> CellState:
        return self._cell_state

    async def get_throughput_metrics(
        self,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_SIMULATED,
    ) -> ThroughputMetrics:
        if not self._cell_running:
            return ThroughputMetrics()
        return ThroughputMetrics(
            dl_throughput_mbps=420.0 + random.gauss(0, 15),
            ul_throughput_mbps=80.0 + random.gauss(0, 5),
            dl_bler=random.uniform(0, 0.05),
            ul_bler=random.uniform(0, 0.08),
            cqi=random.randint(12, 15),
            rank_indicator=min(self._mimo_layers, random.randint(1, 2)),
            mcs_dl=random.randint(24, 27),
            mcs_ul=random.randint(20, 24),
            throughput_scope=ThroughputMetrics.SCOPE_SIMULATED,
        )

    async def get_ue_info(self) -> Dict[str, Any]:
        return {
            "imsi": "001010000000001",
            "imei": "352099001761481",
            "ue_category": "NR-DC",
            "connected": self._cell_running,
        }

    async def query_ue_capability(self) -> Dict[str, Any]:
        """Phase 2e: mock UE that supports up to 4x4 256QAM on n78/n41."""
        return {
            "max_dl_layers": 4,
            "max_ul_layers": 2,
            "max_modulation_dl": "256QAM",
            "max_modulation_ul": "64QAM",
            "supported_bands": ["n78", "n41", "n77", "n79"],
            "ca_combinations": ["n78+n41", "n77+n79"],
            "source": "mock",
        }

    async def reconfigure_rrc(
        self,
        *,
        mimo_layers: Optional[int] = None,
        modulation: Optional[str] = None,
    ) -> bool:
        """Mock: pretend RRC reconfig succeeded."""
        if mimo_layers is not None:
            self._mimo_layers = mimo_layers
            logger.info("[MockBS] RRC reconfig: mimo_layers → %d", mimo_layers)
        if modulation is not None:
            logger.info("[MockBS] RRC reconfig: modulation → %s", modulation)
        return True

    async def add_secondary_cell(
        self,
        cc_index: int,
        cc_config: Dict[str, Any],
    ) -> bool:
        """Mock: track SCell list in memory."""
        if not hasattr(self, "_scells"):
            self._scells = {}
        self._scells[cc_index] = dict(cc_config)
        logger.info(
            "[MockBS] SCell %d added: freq=%.0f MHz BW=%.0f MHz band=%s",
            cc_index,
            cc_config.get("frequency_mhz", 0),
            cc_config.get("bandwidth_mhz", 0),
            cc_config.get("band"),
        )
        return True

    async def activate_secondary_cells(
        self,
        *,
        expected_indices: Optional[List[int]] = None,
    ) -> bool:
        scells = getattr(self, "_scells", {}) or {}
        actual = sorted(scells.keys())
        if expected_indices is not None and actual != sorted(expected_indices):
            logger.warning(
                "[MockBS] SCell set mismatch: expected=%s actual=%s",
                sorted(expected_indices),
                actual,
            )
            return False
        logger.info("[MockBS] Activating %d SCell(s): %s",
                    len(scells), actual)
        return True

    async def remove_all_secondary_cells(self) -> bool:
        n = len(getattr(self, "_scells", {}) or {})
        self._scells = {}
        logger.info("[MockBS] Removed %d SCell(s)", n)
        return True

    def get_supported_technologies(self) -> List[RadioTechnology]:
        return [RadioTechnology.NR5G, RadioTechnology.LTE]

    async def load_state_file(self, filepath: str) -> bool:
        """Mock: 模拟加载配置文件"""
        logger.info(f"[MockBS] load_state_file: {filepath}")
        self._set_status(InstrumentStatus.READY)
        return True

    async def save_state_file(self, filepath: str) -> bool:
        """Mock: 模拟保存配置文件"""
        logger.info(f"[MockBS] save_state_file: {filepath}")
        return True
