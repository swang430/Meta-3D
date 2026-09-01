"""P2-53：BaseStation adapter 接入认证套件（模板 + 第三 adapter 夹具）。

把 uxm / cmw500 两家分散在 test_p2_43/47/48/49/51/52 与 test_p1_73b/73c 里的
认证形态收敛为**以 adapter 为参数**的模板函数；同一套模板由三方跑：

- ``uxm`` / ``cmw500``：既有测试原样保留（G5/G6 精神），模板是收敛入口不是替换；
- ``certfake``：本模块自带的第三 adapter 认证夹具，证明厂商接入只需五件套 ——
  adapter 实现、manifest v2、profile/schema、手册来源、认证测试 ——
  即可完成 HAL/诊断认证；当前零修改实证仅覆盖 manifest 注册、计划 resolve 与
  MEASURE 原生窗口。正式 binding/profile-freeze/evidence 的封闭 adapter 枚举
  不在本套件认证边界内，已在 P2-53 计划 §5 登记平台缺口。

十类认证维度（条目点名）→ 模板函数：

===  ====================  ==========================================
 #   维度                  模板函数
===  ====================  ==========================================
 1   fake transport        certify_fake_transport_exchange_provenance
 2   部分回读              certify_partial_readback_receipt
 3   错误队列              certify_error_queue_consultation
 4   超时 / 取消           certify_attach_timeout_returns_receipt /
                           certify_cancellation_propagates
 5   Attach 阶段           certify_attach_stage_truth
 6   窗口                  certify_measurement_window_contract
 7   逐指标 trust          certify_metric_registry_trust
 8   SAFE_IDLE             certify_safe_idle_boundary
 9   release               certify_release_token_boundary
10   模拟排除              certify_simulated_exclusion
——   五件套 / 已实证零修改门 certify_registration_gate /
                           certify_execution_plan_neutrality /
                           certify_common_consumer_native_window
===  ====================  ==========================================

模板断言全部提炼自既有测试的**真实断言**（出处见各函数 docstring），
不发明新契约；方言深断言（uxm 恰两次 -113 判据、cmw EBLer 七条 wire 序列等）
留在各自原测试文件。

⚠ ``CertFakeBaseStationDriver`` 是**认证夹具，不是真实仪器**：
  - 类名不以 Mock 开头（``diagnostics/protocol.py`` 与 ``api/instrument.py``
    按 ``__name__.startswith("Mock")`` 判 mock，撞名会被误判）；
  - 不注册进生产 HAL（``instrument_hal_service`` 注册表零改动；
    ``test_p1_73a_base_station_contract`` 的封闭集门继续守生产注册表）；
  - 其 manifest 的 ``manual_sources`` / ``source_reference`` 是**如实标注的
    占位**（指向本文件的夹具契约），不冒充厂商手册。
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, Literal, Optional
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ConfigDict

from app.hal.base_station import (
    BASE_STATION_ATTACH_STAGES,
    BASE_STATION_MEASUREMENT_WINDOW_STAGES,
    BaseStationApplyReceipt,
    BaseStationAttachReceipt,
    BaseStationAttachStageReceipt,
    BaseStationDriver,
    BaseStationFieldReceipt,
    BaseStationMeasurementStageReceipt,
    BaseStationMeasurementWindow,
    BaseStationMeasurementWindowRequest,
    BaseStationMeasurementWindowTrust,
    BaseStationRemoteSessionResult,
    BaseStationControlReleaseResult,
    BaseStationRequestedConfig,
    CellState,
    ThroughputMetrics,
    _EXECUTION_PLAN_DIMENSIONS,
    resolve_base_station_execution_plan,
)
from app.hal.base_station_manifest import (
    BaseStationAdapterManifest,
    BaseStationAdapterRegistration,
    BaseStationAttachStageCapability,
    BaseStationConfigFieldCapability,
    BaseStationMeasurementCapability,
    BaseStationMetricCapability,
    BaseStationProfileFieldManifest,
    BaseStationRatCapability,
    validate_base_station_adapter_registrations,
)
from app.hal.scpi_evidence import capture_scpi_exchanges


# ═══════════════════════════════════════════════════════════════════
# 通用脚本会话（收编自 test_p02_uxm_truth_source._FakeUxmSession 形态，
# 补齐 close()——uxm disconnect 会调 session.close()，缺了 release 场景假红）
# ═══════════════════════════════════════════════════════════════════


class ScriptedScpiSession:
    """回复表驱动的假 VISA 会话；replies 按「查询串包含的子串 → 回复」匹配。"""

    def __init__(self, replies: Dict[str, str]):
        self.replies = dict(replies)
        self.written: list[str] = []
        self.queried: list[str] = []
        self.timeout = 5000
        self.closed = False

    def write(self, cmd: str) -> None:
        self.written.append(cmd.strip())

    def query(self, cmd: str) -> str:
        c = cmd.strip()
        self.queried.append(c)
        for needle, reply in self.replies.items():
            if needle in c:
                return reply
        return ""

    def close(self) -> None:
        self.closed = True


# ═══════════════════════════════════════════════════════════════════
# 第三 adapter 夹具：certfake（五件套齐备）
# ═══════════════════════════════════════════════════════════════════

_CERTFAKE_SOURCE = (
    "tests/base_station_certification_kit.py::CertFakeBaseStationDriver "
    "loopback contract（认证夹具占位，非真实仪器手册）"
)


class CertFakeAdapterProfile(BaseModel):
    """certfake 的持久化 profile schema（五件套之 profile/schema）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    adapter: Literal["certfake"]
    loopback_route: str


def _certfake_config_fields() -> tuple[BaseStationConfigFieldCapability, ...]:
    rows: tuple[tuple[str, str, str, str, Optional[str]], ...] = (
        (
            "bandwidth_mhz",
            "authoritative",
            "authoritative",
            "loopback wire echoes the applied bandwidth",
            _CERTFAKE_SOURCE,
        ),
        (
            "frequency_mhz",
            "authoritative",
            "authoritative",
            "loopback wire echoes the applied frequency",
            _CERTFAKE_SOURCE,
        ),
        (
            "radio_technology",
            "diagnostic_only",
            "unavailable",
            "NR5G is selected by the adapter manifest, not independently read back",
            None,
        ),
        (
            "channel_kind",
            "diagnostic_only",
            "unavailable",
            "request shape is application-owned",
            None,
        ),
        (
            "band",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "duplex",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "nr_arfcn",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "lte_dl_earfcn",
            "not_applicable",
            "not_applicable",
            "LTE EARFCN is outside the certfake NR5G contract",
            None,
        ),
        (
            "lte_transmission_mode",
            "not_applicable",
            "not_applicable",
            "LTE transmission mode is outside the certfake NR5G contract",
            None,
        ),
        (
            "subcarrier_spacing_khz",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "mimo_layers",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "downlink_power_dbm",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "downlink_power_dbm_per_bandwidth",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "port_preset",
            "diagnostic_only",
            "unavailable",
            "certfake loopback keeps only bandwidth/frequency readback",
            None,
        ),
        (
            "scheduler_algorithm",
            "diagnostic_only",
            "unavailable",
            "certfake has no scheduler dimension",
            None,
        ),
        (
            "csi_rs_ports",
            "diagnostic_only",
            "unavailable",
            "certfake has no CSI-RS dimension",
            None,
        ),
    )
    return tuple(
        BaseStationConfigFieldCapability(
            field=name,
            support=support,
            readback=readback,
            reason=reason,
            source_reference=source,
        )
        for name, support, readback, reason, source in rows
    )


CERTFAKE_MANIFEST = BaseStationAdapterManifest(
    schema_version=2,
    adapter_id="certfake",
    model_name="CERTFAKE-3000",
    vendor="Certification Fixture Works",
    rat_capabilities=(
        BaseStationRatCapability(
            rat="nr5g",
            source_reference=_CERTFAKE_SOURCE,
        ),
    ),
    operations=(
        "identity",
        "config",
        "cell_attach",
        "safe_idle_release",
        "measurement_window",
    ),
    config_fields=_certfake_config_fields(),
    attach_stages=tuple(
        BaseStationAttachStageCapability(
            stage=stage,
            evidence="authoritative",
            reason="loopback wire reports each milestone explicitly",
            source_reference=_CERTFAKE_SOURCE,
        )
        for stage in BASE_STATION_ATTACH_STAGES
    ),
    measurement=BaseStationMeasurementCapability(
        cardinality="requested",
        scopes=("pcell", "all_cells"),
        lifecycle="authoritative_closed",
        metrics=(
            BaseStationMetricCapability(
                key="dl_throughput_mbps",
                direction="downlink",
                unit="mbps",
                scopes=("pcell", "all_cells"),
                evidence="authoritative",
                source_reference=_CERTFAKE_SOURCE,
            ),
            BaseStationMetricCapability(
                key="ul_throughput_mbps",
                direction="uplink",
                unit="mbps",
                scopes=("pcell",),
                evidence="authoritative",
                source_reference=_CERTFAKE_SOURCE,
            ),
        ),
        source_reference=_CERTFAKE_SOURCE,
    ),
    profile_requirement="required",
    profile_schema_version=1,
    profile_fields=(
        BaseStationProfileFieldManifest(
            path="loopback_route",
            label="Loopback route",
            required=True,
            placeholder="LOOP1",
            description="certfake 夹具的回环路由标识（认证演示用）",
        ),
    ),
    manual_sources=(_CERTFAKE_SOURCE,),
    diagnostic_supported=True,
    formal_gate="site_certification",
)

CERTFAKE_SAMPLE_PROFILE = {
    "schema_version": 1,
    "adapter": "certfake",
    "loopback_route": "LOOP1",
}

_CERTFAKE_ATTACH_PROGRESS = {
    "CELL_READY": 1,
    "REGISTERED": 2,
    "RRC": 3,
    "BEARER": 4,
}


class CertFakeBaseStationDriver(BaseStationDriver):
    """第三 adapter 认证夹具（loopback wire；**非真实仪器**）。

    传输层：override ``_do_write`` / ``_do_query``（与 cmw 系测试同为 L2
    打桩层），让所有往返经 ``base.py`` 的**真实传输模板**产生 exchange
    记账（P2-52 内审 F1 成因门形态：wire token = "command"/"query" 同源，
    不手工 record）。
    """

    adapter_id = "certfake"
    metric_registry_profile_id = "certfake_loopback"
    adapter_profile_model = CertFakeAdapterProfile
    adapter_manifest = CERTFAKE_MANIFEST
    measurement_window_cardinality = "requested"
    max_bandwidth_mhz = 100.0
    max_mimo_layers = 4

    def __init__(
        self,
        instrument_id: str,
        config: Dict[str, Any],
        *,
        simulated: bool = False,
        reject_writes: tuple[str, ...] = (),
        attach_script: tuple[str, ...] = (
            "CELL_READY",
            "REGISTERED",
            "RRC",
            "BEARER",
        ),
        cell_state_reply: str = "OFF",
    ) -> None:
        super().__init__(instrument_id, config)
        # 与真驱动同形态：有传输才允许 wire 往返（fake transport 维度前置）。
        self._visa_session: Any = object()
        self.simulated = simulated
        self.reject_writes = set(reject_writes)
        self._attach_script = deque(attach_script)
        self._attach_last_stage = attach_script[-1] if attach_script else "IDLE"
        self._cell_state_reply = cell_state_reply
        self._session_token: str | None = None
        self.writes: list[str] = []
        self.queries: list[str] = []
        self.state: Dict[str, str] = {}
        self.pending_errors: deque[str] = deque()

    # ── loopback wire（L2 打桩层，经真实传输模板记账） ──────────

    def _do_write(self, cmd: str) -> None:
        self.writes.append(cmd)
        header, _, value = cmd.partition(" ")
        if header in self.reject_writes:
            self.pending_errors.append('-113,"Undefined header"')
            return
        self.state[header] = value
        if header == "CERT:CELL:STATe":
            self._cell_state_reply = "CONN" if value == "ON" else "OFF"

    def _do_query(self, cmd: str) -> str:
        self.queries.append(cmd)
        if cmd == "SYST:ERR?":
            if self.pending_errors:
                return self.pending_errors.popleft()
            return '0,"No error"'
        if cmd == "CERT:CELL:STATe?":
            return self._cell_state_reply
        if cmd == "CERT:ATTach:STAGe?":
            if self._attach_script:
                self._attach_last_stage = self._attach_script.popleft()
            return self._attach_last_stage
        if cmd == "CERT:MEAS:READY?":
            return "1"
        if cmd == "CERT:MEAS:DL?":
            return "42.0"
        if cmd == "CERT:MEAS:UL?":
            return "8.0"
        if cmd.endswith("?"):
            return self.state.get(cmd[:-1], "")
        return ""

    def _drain_wire_errors(self) -> list[str]:
        """每次写操作后读错误队列（诊断序列纪律的驱动侧对应物）。"""

        errors: list[str] = []
        for _ in range(8):
            raw = str(self._query("SYST:ERR?")).strip()
            if raw.startswith("0"):
                break
            errors.append(raw)
        return errors

    def _confirmed_write(self, command: str) -> tuple[bool, tuple[str, ...]]:
        """发一条写命令并回读错误队列；返回 (无错误, 本次写的 exchange ids)。"""

        with capture_scpi_exchanges() as exchanges:
            self._write(command)
        errors = self._drain_wire_errors()
        return not errors, tuple(item.exchange_id for item in exchanges)

    # ── 连接 / 会话 ────────────────────────────────────────────

    async def connect(self) -> bool:
        from app.hal.base import InstrumentStatus

        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        return await self.set_cell_config(config)

    async def get_capabilities(self) -> list:
        return []

    async def get_metrics(self):
        from app.hal.base import InstrumentMetrics

        return InstrumentMetrics()

    async def reset(self) -> bool:
        self.state.clear()
        self.pending_errors.clear()
        return True

    async def disconnect(self) -> bool:
        from app.hal.base import InstrumentStatus

        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def acquire_remote_control(self) -> BaseStationRemoteSessionResult:
        from uuid import uuid4

        await self.connect()
        self._session_token = uuid4().hex
        return BaseStationRemoteSessionResult(
            adapter_id=self.adapter_id,
            session_token=self._session_token,
            acquired_confirmed=True,
            warnings=(),
        )

    async def release_remote_session(
        self,
        expected_session_token: str,
        *,
        measurement_attempt_id: str | None = None,
        lease_id: str = "",
    ) -> BaseStationControlReleaseResult:
        matched = (
            bool(expected_session_token)
            and expected_session_token == self._session_token
        )
        if matched:
            await self.disconnect()
            self._session_token = None
        return BaseStationControlReleaseResult(
            measurement_attempt_id=measurement_attempt_id,
            lease_id=lease_id,
            adapter_id=self.adapter_id,
            session_token=expected_session_token,
            remote_session_acquired_confirmed=matched,
            transport_session_released_confirmed=matched,
            front_panel_local_confirmed=None,
            warnings=() if matched else ("certfake session token mismatch",),
        )

    async def release_to_local_control(self) -> bool:
        self._session_token = None
        return await self.disconnect() is True

    # ── 配置（部分回读 + 错误队列） ─────────────────────────────

    async def set_cell_config(self, config: Dict[str, Any]) -> bool:
        ok = True
        for key, command in (
            ("bandwidth_mhz", "CERT:CONF:BWIDth"),
            ("frequency_mhz", "CERT:CONF:FREQuency"),
        ):
            if config.get(key) is None:
                continue
            write_ok, _ = self._confirmed_write(f"{command} {config[key]}")
            ok = ok and write_ok
        return ok

    async def apply_config(
        self,
        requested: BaseStationRequestedConfig,
    ) -> BaseStationApplyReceipt:
        """部分回读样本：bandwidth/frequency 权威回读，其余如实 unknown。"""

        if not isinstance(requested, BaseStationRequestedConfig):
            raise TypeError("requested must be BaseStationRequestedConfig")
        payload = requested.receipt_payload()
        authoritative_commands = {
            "bandwidth_mhz": "CERT:CONF:BWIDth",
            "frequency_mhz": "CERT:CONF:FREQuency",
        }
        fields: list[BaseStationFieldReceipt] = []
        operation_ok = True
        for name, value in payload.items():
            command = authoritative_commands.get(name)
            if command is None:
                fields.append(
                    BaseStationFieldReceipt(
                        field=name,
                        requested=value,
                        applied=None,
                        status="unknown",
                        reason=(
                            "certfake exposes authoritative readback only for "
                            "bandwidth/frequency"
                        ),
                    )
                )
                continue
            with capture_scpi_exchanges() as exchanges:
                self._write(f"{command} {value}")
                raw = str(self._query(f"{command}?")).strip()
            errors = self._drain_wire_errors()
            exchange_ids = tuple(item.exchange_id for item in exchanges)
            applied: float | None
            try:
                applied = float(raw)
            except ValueError:
                applied = None
            if not errors and applied == value:
                fields.append(
                    BaseStationFieldReceipt(
                        field=name,
                        requested=value,
                        applied=value,
                        status="confirmed",
                        reason="loopback wire echoed the applied value",
                        exchange_ids=exchange_ids,
                    )
                )
            else:
                operation_ok = not errors and operation_ok
                fields.append(
                    BaseStationFieldReceipt(
                        field=name,
                        requested=value,
                        applied=None,
                        status="unknown",
                        reason=(
                            f"wire rejected the write: {errors[0]}"
                            if errors
                            else "loopback readback did not match the request"
                        ),
                    )
                )
        return BaseStationApplyReceipt(
            schema_version=1,
            operation="config",
            fields=tuple(fields),
            reason=(
                "certfake loopback config applied"
                if operation_ok
                else "certfake wire rejected part of the configuration"
            ),
            simulated=self.simulated is True,
            operation_succeeded=operation_ok,
        )

    # ── attach（阶段 / 超时 / 取消） ────────────────────────────

    async def attach(self, timeout_s: float = 60.0) -> BaseStationAttachReceipt:
        if self.simulated is True:
            return BaseStationAttachReceipt(
                schema_version=1,
                adapter_id=self.adapter_id,
                stages=tuple(
                    BaseStationAttachStageReceipt(
                        stage=stage,
                        requested=True,
                        applied=None,
                        status="unknown",
                        evidence="diagnostic_only",
                        reason="simulated certfake attach carries no wire truth",
                    )
                    for stage in BASE_STATION_ATTACH_STAGES
                ),
                reason="simulated certfake attach",
                simulated=True,
                operation_succeeded=True,
            )
        evidence_by_stage = {
            item.stage: item.evidence
            for item in self.adapter_manifest.attach_stages
        }
        self._write("CERT:CELL:STATe ON")
        reached: dict[str, tuple[str, ...]] = {}
        attempts = max(1, int(float(timeout_s) / 0.05))
        for _ in range(attempts):
            with capture_scpi_exchanges() as exchanges:
                raw = str(self._query("CERT:ATTach:STAGe?")).strip()
            exchange_ids = tuple(item.exchange_id for item in exchanges)
            count = _CERTFAKE_ATTACH_PROGRESS.get(raw, 0)
            for stage in BASE_STATION_ATTACH_STAGES[:count]:
                reached.setdefault(stage, exchange_ids)
            if count == len(BASE_STATION_ATTACH_STAGES):
                break
            await asyncio.sleep(0.05)
        errors = self._drain_wire_errors()
        stages = tuple(
            BaseStationAttachStageReceipt(
                stage=stage,
                requested=True,
                applied=True if stage in reached and not errors else None,
                status="confirmed" if stage in reached and not errors else "unknown",
                evidence=evidence_by_stage[stage],
                reason=(
                    "loopback wire reported the milestone"
                    if stage in reached and not errors
                    else "attach did not reach this milestone within the timeout"
                ),
                exchange_ids=reached[stage] if stage in reached and not errors else (),
            )
            for stage in BASE_STATION_ATTACH_STAGES
        )
        return BaseStationAttachReceipt(
            schema_version=1,
            adapter_id=self.adapter_id,
            stages=stages,
            reason=(
                "certfake attach completed"
                if len(reached) == len(BASE_STATION_ATTACH_STAGES) and not errors
                else "certfake attach did not complete"
            ),
            simulated=False,
            operation_succeeded=None,
        )

    async def stop_signaling(self) -> bool:
        ok, _ = self._confirmed_write("CERT:CELL:STATe OFF")
        return ok

    async def get_cell_state(self) -> CellState:
        raw = str(self._query("CERT:CELL:STATe?")).strip().upper()
        mapping = {
            "OFF": CellState.OFF,
            "ON": CellState.ON,
            "IDLE": CellState.IDLE,
            "CONN": CellState.CONNECTED,
        }
        return mapping.get(raw, CellState.ERROR)

    # ── 测量（窗口 / 逐指标 trust / 模拟排除） ──────────────────

    async def get_throughput_metrics(
        self,
        *,
        throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    ) -> ThroughputMetrics:
        dl = float(str(self._query("CERT:MEAS:DL?")).strip() or "0")
        ul = float(str(self._query("CERT:MEAS:UL?")).strip() or "0")
        return ThroughputMetrics(
            dl_throughput_mbps=dl,
            ul_throughput_mbps=ul,
            throughput_scope=throughput_scope,
            registered_values={
                "dl_throughput_mbps": dl,
                "ul_throughput_mbps": ul,
            },
        )

    async def measure_base_station_window(
        self,
        window_s: float,
        *,
        request: BaseStationMeasurementWindowRequest,
    ) -> BaseStationMeasurementWindow:
        if not isinstance(request, BaseStationMeasurementWindowRequest):
            raise TypeError("certfake measurement requires a frozen window request")
        started_at = datetime.now(timezone.utc)
        if self.simulated is True:
            metrics = ThroughputMetrics(
                dl_throughput_mbps=42.0,
                ul_throughput_mbps=8.0,
                throughput_scope=ThroughputMetrics.SCOPE_SIMULATED,
                kpi_valid={"dl_throughput": False, "ul_throughput": False},
            )
            metrics.kpi_valid = {key: False for key in metrics.kpi_valid}
            registry = self.resolve_metric_registry()
            trust = BaseStationMeasurementWindowTrust(
                schema_version=1,
                request=request,
                request_digest=request.digest,
                stages=tuple(
                    BaseStationMeasurementStageReceipt(
                        stage=stage,
                        status="unavailable",
                        reason="simulated certfake window has no wire lifecycle",
                    )
                    for stage in BASE_STATION_MEASUREMENT_WINDOW_STAGES
                ),
                simulated=True,
                exchange_ids=(),
                reason="simulated certfake window; excluded from formal KPI",
                context_confirmed=False,
            )
            observations = self.build_metric_observations(
                registry=registry,
                metrics=metrics,
                scope=request.scope,
                exchanges=(),
                query_commands={},
                simulated=True,
            )
            return BaseStationMeasurementWindow(
                window_id=f"certfake-simulated-{id(request)}",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                metrics=metrics,
                preclear_off_confirmed=False,
                running_confirmed=False,
                ready_confirmed=False,
                closed_off_confirmed=False,
                evidence=(),
                confirmed=False,
                reason="simulated certfake window; excluded from formal KPI",
                trust=trust,
                metric_registry=registry,
                metric_observations=observations,
            )
        if (
            request.lifecycle != "authoritative_closed"
            or request.cardinality != "requested"
        ):
            raise ValueError(
                "certfake window request disagrees with its frozen manifest"
            )
        registry = self.resolve_metric_registry()
        with capture_scpi_exchanges() as window_exchanges:
            clear_ok, clear_ids = self._confirmed_write("CERT:MEAS:CLEar")
            run_ok, run_ids = self._confirmed_write("CERT:MEAS:STATe ON")
            await asyncio.sleep(max(float(window_s), 0.0))
            with capture_scpi_exchanges() as ready_exchanges:
                ready_raw = str(self._query("CERT:MEAS:READY?")).strip()
            ready_ok = ready_raw == "1"
            ready_ids = tuple(item.exchange_id for item in ready_exchanges)
            metrics = await self.get_throughput_metrics(
                throughput_scope=(
                    ThroughputMetrics.SCOPE_PCELL
                    if request.scope == "pcell"
                    else ThroughputMetrics.SCOPE_NR_ALL_CELLS
                ),
            )
            closed_write_ok, closed_write_ids = self._confirmed_write(
                "CERT:MEAS:STATe OFF"
            )
            with capture_scpi_exchanges() as closed_exchanges:
                closed_raw = str(self._query("CERT:MEAS:STATe?")).strip()
            closed_ok = closed_write_ok and closed_raw == "OFF"
            closed_ids = closed_write_ids + tuple(
                item.exchange_id for item in closed_exchanges
            )
        stage_results = {
            "clear": (clear_ok, clear_ids),
            "run": (run_ok, run_ids),
            "ready": (ready_ok, ready_ids),
            "closed": (closed_ok, closed_ids),
        }
        stages = tuple(
            BaseStationMeasurementStageReceipt(
                stage=stage,
                status="confirmed" if ok and ids else "unavailable",
                reason=(
                    "loopback wire confirmed the stage"
                    if ok and ids
                    else "loopback wire did not confirm the stage"
                ),
                exchange_ids=ids if ok and ids else (),
            )
            for stage, (ok, ids) in stage_results.items()
        )
        all_confirmed = all(item.status == "confirmed" for item in stages)
        trust = BaseStationMeasurementWindowTrust(
            schema_version=1,
            request=request,
            request_digest=request.digest,
            stages=stages,
            simulated=False,
            exchange_ids=tuple(item.exchange_id for item in window_exchanges),
            reason=(
                "certfake authoritative closed window"
                if all_confirmed
                else "certfake window lifecycle incomplete"
            ),
            context_confirmed=all_confirmed,
        )
        observations = self.build_metric_observations(
            registry=registry,
            metrics=metrics,
            scope=request.scope,
            exchanges=window_exchanges,
            query_commands={
                "dl_throughput_mbps": "CERT:MEAS:DL?",
                "ul_throughput_mbps": "CERT:MEAS:UL?",
            },
            simulated=False,
        )
        return BaseStationMeasurementWindow(
            window_id=f"certfake-{trust.request_digest[:8]}-{request.window_index}",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            metrics=metrics,
            preclear_off_confirmed=stages[0].status == "confirmed",
            running_confirmed=stages[1].status == "confirmed",
            ready_confirmed=stages[2].status == "confirmed",
            closed_off_confirmed=stages[3].status == "confirmed",
            evidence=(),
            confirmed=trust.formally_confirmed,
            reason=trust.reason,
            trust=trust,
            metric_registry=registry,
            metric_observations=observations,
        )


# ═══════════════════════════════════════════════════════════════════
# 认证对象声明
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AdapterCertificationSubject:
    """一家 adapter 的认证接入声明（五件套 + 各维度离线场景构造器）。"""

    label: str
    model_name: str
    driver_class: type
    profile_model: type | None
    sample_profile: dict | None
    error_queue_command: str
    sleep_patch_target: str
    expect_attach_formally_confirmed: bool
    expect_window_formally_confirmed: bool
    requested_config: BaseStationRequestedConfig
    build_offline_driver: Callable[[], Any]
    build_attach_ready_driver: Callable[[], Any]
    build_attach_never_ready_driver: Callable[[], Any]
    build_cancelled_attach_driver: Callable[[], Any]
    build_window_driver: Callable[[], Any]
    build_partial_config_driver: Callable[[], Any]
    build_rejected_config_driver: Callable[[], Any]
    build_safe_idle_driver: Callable[[bool], Any]
    build_release_driver: Callable[[], Any]
    build_simulated_driver: Callable[[], Any]
    transport_probe: Callable[[Any], Awaitable[Any]]
    get_recorded_queries: Callable[[Any], list]


# patch(subject.sleep_patch_target) 实际替换的是全局 asyncio.sleep 属性
# （各驱动模块的 ``asyncio`` 就是同一个模块对象），所以替身必须持有真 sleep
# 的引用，否则替身调用自己造成无限递归（test_p2_47 同形态）。
_REAL_SLEEP = asyncio.sleep


async def _instant_sleep(_seconds: float) -> None:
    await _REAL_SLEEP(0)


# ═══════════════════════════════════════════════════════════════════
# 模板函数（十类 + 五件套 / 零修改门）
# ═══════════════════════════════════════════════════════════════════


async def certify_fake_transport_exchange_provenance(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 1（fake transport）。

    提炼自 test_p2_52_uxm_window_boundary.py:347（内审 F1 成因门）：
    离线认证的 wire 往返必须经**真实传输模板**记账 —— exchange 的
    operation token 只能是生产 base.py 写的 "command"/"query"，
    simulated 恒 False；手工 record 出来的 "write" 之类假 token 当场红。
    """

    driver = subject.build_offline_driver()
    assert getattr(driver, "_visa_session", None) is not None, (
        f"{subject.label}: 离线认证驱动必须携带传输会话（可为占位对象）"
    )
    with capture_scpi_exchanges() as exchanges:
        await subject.transport_probe(driver)
    assert exchanges, f"{subject.label}: 传输探针必须产生至少一次 wire 往返"
    assert all(
        item.operation in {"command", "query"} for item in exchanges
    ), f"{subject.label}: exchange operation token 必须来自真实传输模板"
    assert all(item.simulated is False for item in exchanges), (
        f"{subject.label}: 离线认证 exchange 不得标记 simulated"
    )


async def certify_partial_readback_receipt(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 2（部分回读）。

    提炼自 test_p2_43(_partial_config_receipt) 与
    test_p1_73b_cmw_state_machine.py:106（部分权威回读时 confirmed=False、
    unknown 字段不携 applied、操作接受与证据完备分离）。
    """

    driver = subject.build_partial_config_driver()
    receipt = await driver.apply_config(subject.requested_config)
    assert isinstance(receipt, BaseStationApplyReceipt)
    assert receipt.operation == "config"
    assert receipt.simulated is False
    assert {item.field for item in receipt.fields} == set(
        subject.requested_config.receipt_payload()
    ), f"{subject.label}: receipt 必须覆盖冻结请求的全部字段"
    unknown = [item for item in receipt.fields if item.status == "unknown"]
    assert unknown, f"{subject.label}: 共同请求必然存在无权威回读的字段"
    assert all(item.applied is None for item in unknown)
    assert receipt.confirmed is False
    assert receipt.operation_succeeded is True
    assert receipt.diagnostic_execution_allowed is True


async def certify_error_queue_consultation(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 3（错误队列）。

    提炼自 test_p1_41_uxm_error_queue_bound / test_p1_73b:177 /
    test_p2_51:346：被拒操作不得整体 confirmed，且 adapter 必须在操作后
    读过错误队列（read-after-write 纪律）。方言深判据（恰两次 -113、
    预排水序）留在原测试。
    """

    driver = subject.build_rejected_config_driver()
    with patch(subject.sleep_patch_target, _instant_sleep):
        receipt = await driver.apply_config(subject.requested_config)
    assert isinstance(receipt, BaseStationApplyReceipt)
    assert receipt.confirmed is False, (
        f"{subject.label}: 被 wire 拒绝的配置不得整体 confirmed"
    )
    queries = [str(item) for item in subject.get_recorded_queries(driver)]
    assert any(
        subject.error_queue_command in item for item in queries
    ), f"{subject.label}: 操作后必须查询错误队列 {subject.error_queue_command!r}"


async def certify_attach_timeout_returns_receipt(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 4a（超时）。

    提炼自 test_p02_uxm_truth_source.py:117（状态恒不达标时 attach 在
    timeout 内返回、不挂死不抛）与 attach receipt 契约。
    """

    driver = subject.build_attach_never_ready_driver()
    with patch(subject.sleep_patch_target, _instant_sleep):
        receipt = await driver.attach(timeout_s=0.4)
    assert isinstance(receipt, BaseStationAttachReceipt)
    assert receipt.simulated is False
    assert receipt.diagnostic_execution_allowed is False
    assert receipt.formally_confirmed is False


async def certify_cancellation_propagates(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 4b（取消）。

    提炼自 test_p1_73b_cmw_state_machine.py:762 与
    test_uxm_cell_config_orchestration.py:232：取消必须向上传播，
    不得被吞成一个"成功/失败"布尔；生命周期随后必须调用并确认
    stop_signaling，认证本身也不得把 RF 留在开启态。方言级深断言
    （还原 timeout、具体 OFF 写形与权威回读）仍留在各自原测试。
    """

    driver = subject.build_cancelled_attach_driver()

    async def _cancel(_seconds: float) -> None:
        raise asyncio.CancelledError()

    cleanup_confirmed = False
    try:
        with patch(subject.sleep_patch_target, _cancel):
            with pytest.raises(asyncio.CancelledError):
                await driver.attach(timeout_s=30.0)
    finally:
        # attach 只负责把取消信号原样交回；执行生命周期负责无条件收口。
        # 认证器也必须履行相同所有权，不能让失败的认证把 RF 留在开启态。
        cleanup_confirmed = await asyncio.shield(driver.stop_signaling())
    assert cleanup_confirmed is True, (
        f"{subject.label}: 取消传播后必须由生命周期确认 SAFE cleanup"
    )


async def certify_attach_stage_truth(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 5（Attach 阶段）。

    提炼自 test_p2_47_uxm_attach_receipt.py:33 与
    test_p2_47_cmw_attach_receipt.py:35：四阶段有序；每阶段 evidence
    与 manifest.attach_stages 声明**逐字相等**（uxm/cmw 实现都从
    manifest 取 evidence —— uxm_base_station.py:3328 / cmw:2382）；
    confirmed 阶段携 wire exchange。
    """

    driver = subject.build_attach_ready_driver()
    with patch(subject.sleep_patch_target, _instant_sleep):
        receipt = await driver.attach(timeout_s=4.0)
    assert isinstance(receipt, BaseStationAttachReceipt)
    assert tuple(item.stage for item in receipt.stages) == BASE_STATION_ATTACH_STAGES
    declared = {
        item.stage: item.evidence
        for item in subject.driver_class.adapter_manifest.attach_stages
    }
    for stage in receipt.stages:
        assert stage.evidence == declared[stage.stage], (
            f"{subject.label}: attach 阶段 {stage.stage} 的 evidence "
            f"{stage.evidence!r} 偏离 manifest 声明 {declared[stage.stage]!r}"
        )
    assert receipt.simulated is False
    confirmed = [item for item in receipt.stages if item.status == "confirmed"]
    assert confirmed, f"{subject.label}: 成功 attach 必须确认至少一个阶段"
    assert receipt.exchange_ids, f"{subject.label}: 确认阶段必须携 wire 证据"
    assert receipt.diagnostic_execution_allowed is True
    assert (
        receipt.formally_confirmed is subject.expect_attach_formally_confirmed
    ), (
        f"{subject.label}: formally_confirmed 应为 "
        f"{subject.expect_attach_formally_confirmed}（由 manifest evidence 档位决定）"
    )


def _window_request_for(
    subject: AdapterCertificationSubject,
    *,
    requested_sample_count: int = 1,
) -> tuple[BaseStationMeasurementWindowRequest, ...]:
    """用生产构造器冻结窗口请求（不发明第二个构造器）。"""

    from app.services.mimo_ota.executors.measure import MeasureExecutor

    return MeasureExecutor._measurement_window_requests(
        subject.driver_class.adapter_manifest,
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=requested_sample_count,
        simulated_diagnostic=False,
        statistical_basis_subframes=5000,
    )


async def certify_measurement_window_contract(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 6（窗口）。

    提炼自 test_p2_48_adapter_window_truth.py:118/154 与
    test_p2_52_uxm_window_boundary.py:340：窗口尊重冻结请求
    （digest 一致、漂移请求拒绝）、trust 与镜像一致、真实窗口携 wire
    证据；formally_confirmed 由 manifest lifecycle 决定。
    """

    driver = subject.build_window_driver()
    request = _window_request_for(subject)[0]
    with patch(subject.sleep_patch_target, _instant_sleep):
        window = await driver.measure_base_station_window(0.0, request=request)
    assert isinstance(window, BaseStationMeasurementWindow)
    assert window.trust is not None
    assert window.trust.request_digest == request.digest
    assert window.trust.simulated is False
    assert window.trust.exchange_ids, (
        f"{subject.label}: 真实窗口必须携 wire exchange 证据"
    )
    assert (
        window.trust.formally_confirmed
        is subject.expect_window_formally_confirmed
    ), (
        f"{subject.label}: 窗口 formally_confirmed 应为 "
        f"{subject.expect_window_formally_confirmed}（由 manifest lifecycle 决定）"
    )
    drifted = BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope=request.scope,
        lifecycle=(
            "clear_read_only"
            if request.lifecycle != "clear_read_only"
            else "authoritative_closed"
        ),
        cardinality=request.cardinality,
        requested_window_count=request.requested_window_count,
        expected_window_count=request.expected_window_count,
        window_index=request.window_index,
    )
    fresh_driver = subject.build_window_driver()
    with patch(subject.sleep_patch_target, _instant_sleep):
        with pytest.raises(ValueError):
            await fresh_driver.measure_base_station_window(0.0, request=drifted)


def certify_metric_registry_trust(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 7（逐指标 trust）。

    提炼自 test_p2_49_adapter_metric_registry.py:17（registry 解析零
    仪器 I/O）与 test_p2_49_metric_observations.py:61（值绑回产生它的
    query exchange，未取到的值不借用别人的 exchange）。
    """

    driver = subject.build_offline_driver()
    with patch.object(
        type(driver),
        "_query",
        side_effect=AssertionError("registry resolution must not query"),
    ):
        registry = driver.resolve_metric_registry()
        second = driver.resolve_metric_registry()
    assert registry.adapter_id == driver.adapter_id
    assert registry.metrics, f"{subject.label}: metric registry 不得为空"
    assert registry.digest == second.digest, (
        f"{subject.label}: registry digest 必须稳定"
    )
    probe_key = registry.metrics[0].key
    probe_scope = registry.metrics[0].scopes[0]
    # 只有 probe_key 真正取到值；其余指标 value=None（P2-49 契约：有值必须
    # 绑定产生它的 exchange，None 值不携 exchange）。
    metrics = ThroughputMetrics(registered_values={probe_key: 1.0})
    exchange = SimpleNamespace(exchange_id="kit-probe-1", command="KIT:PROBE?")
    observations = driver.build_metric_observations(
        registry=registry,
        metrics=metrics,
        scope=probe_scope,
        exchanges=[exchange],
        query_commands={probe_key: "KIT:PROBE?"},
        simulated=False,
    )
    by_key = {item.key: item for item in observations}
    assert by_key[probe_key].exchange_ids == ("kit-probe-1",)
    assert by_key[probe_key].value == 1.0
    for key, item in by_key.items():
        if key != probe_key:
            assert item.value is None
            assert item.exchange_ids == (), (
                f"{subject.label}: 无 query 命令的指标不得借用他人 exchange"
            )


async def certify_safe_idle_boundary(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 8（SAFE_IDLE）。

    提炼自 test_p1_73b_cmw_state_machine.py:282 参数化：可确认 OFF →
    True；状态不可知 → False（不许把"没读到"当安全）。
    """

    off_driver = subject.build_safe_idle_driver(True)
    assert await off_driver.ensure_safe_idle() is True
    unknown_driver = subject.build_safe_idle_driver(False)
    assert await unknown_driver.ensure_safe_idle() is False


async def certify_release_token_boundary(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 9（release）。

    提炼自 test_p1_73c_base_station_control_release.py:72/193 与
    test_p1_73b:228：release 与本次会话 token 绑定 —— 正确 token 确认
    释放；错误/过期 token 不得报告已确认释放。
    """

    driver = subject.build_release_driver()
    acquired = await driver.acquire_remote_control()
    assert isinstance(acquired, BaseStationRemoteSessionResult)
    assert acquired.acquired_confirmed is True
    assert acquired.adapter_id == subject.driver_class.adapter_id
    token = acquired.session_token
    assert token
    released = await driver.release_remote_session(
        token, measurement_attempt_id="kit-attempt", lease_id="kit-lease"
    )
    assert isinstance(released, BaseStationControlReleaseResult)
    assert released.transport_session_released_confirmed is True
    assert released.session_token == token
    assert released.adapter_id == subject.driver_class.adapter_id
    stale = await driver.release_remote_session(
        token, measurement_attempt_id="kit-attempt-2", lease_id="kit-lease"
    )
    assert stale.transport_session_released_confirmed is False, (
        f"{subject.label}: 过期 token 不得报告已确认释放"
    )


async def certify_simulated_exclusion(
    subject: AdapterCertificationSubject,
) -> None:
    """维度 10（模拟排除）。

    提炼自 test_p2_43:222 / test_p2_48:164 / test_p2_49:148：
    simulated 驱动的窗口 trust 恒 simulated、不 formally_confirmed、
    无 confirmed 阶段、KPI 全部无效、apply receipt 标 simulated。
    """

    driver = subject.build_simulated_driver()
    assert getattr(driver, "simulated", False) is True
    from app.services.mimo_ota.executors.measure import MeasureExecutor

    request = MeasureExecutor._measurement_window_requests(
        getattr(driver, "adapter_manifest", None),
        throughput_scope=ThroughputMetrics.SCOPE_PCELL,
        requested_sample_count=1,
        simulated_diagnostic=True,
        statistical_basis_subframes=5000,
    )[0]
    window = await driver.measure_base_station_window(0.0, request=request)
    assert window.trust is not None
    assert window.trust.simulated is True
    assert window.trust.formally_confirmed is False
    assert window.confirmed is False
    assert all(
        item.status != "confirmed" for item in window.trust.stages
    )
    assert window.metrics.throughput_scope == ThroughputMetrics.SCOPE_SIMULATED
    assert not any(value is True for value in window.metrics.kpi_valid.values())
    receipt = await driver.apply_config(subject.requested_config)
    assert receipt.simulated is True
    assert receipt.confirmed is False


def certify_registration_gate(subject: AdapterCertificationSubject) -> None:
    """五件套之注册门：新 adapter 与生产注册表**合并**后过同一把生产尺子
    ``validate_base_station_adapter_registrations``（判据不复制）。

    提炼自 test_p2_46_base_station_capability_manifest.py:339
    （第三 adapter 不改注册表代码也能通过注册校验）。
    """

    from app.services import instrument_hal_service

    production = instrument_hal_service._real_driver_registry()["baseStation"]
    combined: dict[str, BaseStationAdapterRegistration] = {}
    for model_name, driver_class in production.items():
        combined[model_name] = BaseStationAdapterRegistration(
            manifest=driver_class.adapter_manifest,
            driver_class=driver_class,
            profile_model=getattr(driver_class, "adapter_profile_model", None),
        )
    if subject.model_name in combined:
        # 已注册 adapter（uxm/cmw500）：注册的必须就是认证对象本身（自证）。
        assert combined[subject.model_name].driver_class is subject.driver_class
    else:
        # 第三 adapter：与生产注册**合并**后过同一把尺子，注册表零改动。
        combined[subject.model_name] = BaseStationAdapterRegistration(
            manifest=subject.driver_class.adapter_manifest,
            driver_class=subject.driver_class,
            profile_model=subject.profile_model,
        )
    certified = combined.get(subject.model_name)
    assert certified is not None, (
        f"{subject.label}: 目标 adapter 必须实际进入生产校验器的 mapping"
    )
    assert certified.driver_class is subject.driver_class
    assert certified.manifest is subject.driver_class.adapter_manifest
    assert certified.profile_model is subject.profile_model
    validate_base_station_adapter_registrations(combined)
    if subject.profile_model is not None:
        assert subject.sample_profile is not None
        subject.profile_model.model_validate(subject.sample_profile)


def certify_execution_plan_neutrality(
    subject: AdapterCertificationSubject,
) -> None:
    """五件套之计划 resolve：vendor-neutral 计划推导对新 adapter 零分支。

    提炼自 test_p2_50_execution_plan.py（planned 恒等于 adapter 声明、
    digest 稳定、无 adapter 身份分支）。
    """

    driver = subject.build_offline_driver()
    manifest = subject.driver_class.adapter_manifest
    plan = resolve_base_station_execution_plan(driver, manifest=manifest)
    assert plan.adapter_id == manifest.adapter_id
    again = resolve_base_station_execution_plan(driver, manifest=manifest)
    assert plan.digest == again.digest
    for dimension, _token, attr in _EXECUTION_PLAN_DIMENSIONS:
        declared = getattr(driver, attr, False) is True
        assert getattr(plan, dimension).planned is declared, (
            f"{subject.label}: 计划维度 {dimension} 必须等于 adapter 声明 {attr}"
        )


async def certify_common_consumer_native_window(
    subject: AdapterCertificationSubject,
) -> None:
    """零修改共同消费者的行为门：生产 MEASURE 采样器原样消费新 adapter。

    提炼自 test_p2_43:165（每个 adapter 只经共同 native 窗口契约、
    样本数由 manifest cardinality 决定）。
    """

    from app.services.mimo_ota.executors.measure import MeasureExecutor

    driver = subject.build_window_driver()
    manifest = subject.driver_class.adapter_manifest
    with patch(subject.sleep_patch_target, _instant_sleep):
        samples = await MeasureExecutor._measure_base_station_samples(
            driver,
            window_s=0.0,
            throughput_scope=ThroughputMetrics.SCOPE_PCELL,
            requested_sample_count=2,
            manifest=manifest,
            simulated_diagnostic=False,
            statistical_basis_subframes=5000,
        )
    expected = 1 if manifest.measurement.cardinality == "single" else 2
    assert len(samples) == expected
    assert all(sample.window is not None for sample in samples)
