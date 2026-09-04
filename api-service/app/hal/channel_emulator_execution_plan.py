# -*- coding: utf-8 -*-
"""P2-59 ①：ChannelEmulatorExecutionPlan —— execution-frozen、vendor-neutral 的信道仿真器执行计划。

镜像 `app/hal/base_station.py` 的 `BaseStationExecutionPlan`（P2-50）。有意差别（设计稿
`docs/plans/2026-09-04-p2-59-channel-emulator-execution-plan-design.md` §3）：

  · 计划的来源是「MEASURE 将要用的那个驱动」的 manifest —— HAL 里装了 channelEmulator 就用它，
    没有就按 `measure.py` 既有的兜底规则取 `MockChannelEmulator` 的类级 manifest（取法在 services 侧
    `channel_emulator_for_execution_plan`，冻结与 MEASURE 共用）。所以同一驱动上每个能力问题的
    答案与 P2-57 的 manifest 查询逐字相同；① 新增的只有三处 fail-closed（设计稿 §8.G）：
    加载模式不支持提前到启动期拒、无 manifest 的驱动启动期拒、冻结与测量之间换驱动 / 换 engine_mode
    → digest 漂移 → I/O 前拒绝。
  · 除该 schema 固定词汇中各操作的 `planned`，还冻 **请求的加载模式**（由 engine_mode 派生）与**阶段顺序**
    （字面常量）。加载模式不被 manifest 支持在这里只**记录**（`load_mode_planned=False`），
    启动期 fail-loud 由 services 侧冻结函数做 —— 纯函数保持全域可算，MEASURE 的 live 重算
    才不会因为别的原因先炸。
  · 没有任何 F64 / FS16 / mock 的名字分支：所有判据都从 manifest 声明取。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Mapping

from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.channel_emulator_manifest import (
    CHANNEL_EMULATOR_OPERATIONS,
    CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS,
    ChannelEmulatorManifest,
)

#: 已经落库的 P2-59① v1 词汇必须永久固定。
CHANNEL_EMULATOR_EXECUTION_PLAN_V1_OPERATIONS = (
    CHANNEL_EMULATOR_MANIFEST_V1_OPERATIONS
)
#: P2-59② 新写入的 v2 词汇。
CHANNEL_EMULATOR_EXECUTION_PLAN_V2_OPERATIONS = CHANNEL_EMULATOR_OPERATIONS


def channel_emulator_execution_plan_operations_for_schema(
    schema_version: int,
) -> tuple[str, ...]:
    if schema_version == 1:
        return CHANNEL_EMULATOR_EXECUTION_PLAN_V1_OPERATIONS
    if schema_version == 2:
        return CHANNEL_EMULATOR_EXECUTION_PLAN_V2_OPERATIONS
    raise ValueError("unsupported channel emulator execution plan schema")

ChannelEmulatorRequestedLoadMode = Literal[
    "native_model", "external_waveform", "parametric_tdl"
]
ChannelEmulatorPlanDriverSource = Literal["hal", "fallback_mock"]

#: engine_mode（`app.services.channel_generation.base_generator.EngineMode` 的取值）→ 请求的加载模式。
#: 映射逐条取自各策略实际下发的 `ChannelLoadMode`：`gcm_strategy` → NATIVE_MODEL；
#: `asc_strategy` / `external_asc_strategy` → EXTERNAL_WAVEFORM；`b2_parametric_strategy` → PARAMETRIC_TDL。
#: 按字面值写、不 import EngineMode，是为了让 hal 层不反向依赖 services；
#: 门断言键集合 == EngineMode 取值集合，新增 engine_mode 不声明加载模式就红。
ENGINE_MODE_TO_REQUESTED_LOAD_MODE: Mapping[str, ChannelEmulatorRequestedLoadMode] = {
    "keysight_gcm": "native_model",
    "mimo_first_asc": "external_waveform",
    "external_asc": "external_waveform",
    "b2_parametric_tdl": "parametric_tdl",
}

#: 单一会话（P2-59 ③）要走的阶段顺序 —— 字面常量，进 payload 是为了让顺序变化成为可见的 digest 漂移。
CHANNEL_EMULATOR_PHASE_ORDER: tuple[str, ...] = (
    "acquire",
    "identity",
    "load",
    "configure",
    "run",
    "safe_idle",
    "release",
    "terminal",
)


def requested_channel_emulator_load_mode(engine_mode: str) -> ChannelEmulatorRequestedLoadMode:
    """engine_mode → 本次执行会向 CE 请求的加载模式；未知 engine_mode 当场炸（拼错不是「不支持」）。"""

    try:
        return ENGINE_MODE_TO_REQUESTED_LOAD_MODE[engine_mode]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"未知 engine_mode，无法派生信道加载模式: {engine_mode!r}") from exc


@dataclass(frozen=True)
class ChannelEmulatorExecutionPlanItem:
    """一条 execution-frozen 的操作计划项。

    ``planned`` 是共同执行器唯一的能力判据；``capability_source`` 记录它来自 manifest 的哪条声明，
    ``reason`` 是 manifest 里给操作员看的那句依据。计划说 planned 但驱动缺方法属于计划 / 实现漂移，
    消费方必须 fail-loud，而不是回退成跳过。
    """

    operation: str
    planned: bool
    capability_source: str
    reason: str

    def __post_init__(self) -> None:
        if self.operation not in CHANNEL_EMULATOR_OPERATIONS:
            raise ValueError(
                "execution plan operation is not a known channel emulator operation: "
                f"{self.operation!r}"
            )
        if type(self.planned) is not bool:
            raise TypeError("execution plan planned must be bool")
        for name, value in (
            ("capability_source", self.capability_source),
            ("reason", self.reason),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"execution plan {name} must be non-empty")

    def __bool__(self) -> bool:
        raise TypeError(
            "ChannelEmulatorExecutionPlanItem must not be used as bool; read .planned"
        )


@dataclass(frozen=True)
class ChannelEmulatorExecutionPlan:
    """Execution-frozen、vendor-neutral 的信道仿真器执行计划（P2-59 ①）。"""

    schema_version: Literal[1, 2]
    #: MEASURE 将要用的驱动的 manifest.adapter_id（HAL 装载的驱动，或兜底的 mock）。
    adapter_id: str
    driver_source: ChannelEmulatorPlanDriverSource
    requested_load_mode: ChannelEmulatorRequestedLoadMode
    load_mode_planned: bool
    load_mode_reason: str
    #: 按 schema 版本的固定词汇恰好覆盖一次，且保持 canonical 顺序。
    operations: tuple[ChannelEmulatorExecutionPlanItem, ...]
    phase_order: tuple[str, ...]
    #: P2-58 ① 冻结件里的 binding_digest，只引用不重复其字段。
    binding_digest: str

    def __post_init__(self) -> None:
        expected_operations = channel_emulator_execution_plan_operations_for_schema(
            self.schema_version
        )
        if not isinstance(self.adapter_id, str) or not self.adapter_id.strip():
            raise ValueError("execution plan adapter_id must be non-empty")
        if self.driver_source not in ("hal", "fallback_mock"):
            raise ValueError("execution plan driver_source is not a known source")
        if self.requested_load_mode not in set(ENGINE_MODE_TO_REQUESTED_LOAD_MODE.values()):
            raise ValueError("execution plan requested_load_mode is not a known load mode")
        if type(self.load_mode_planned) is not bool:
            raise TypeError("execution plan load_mode_planned must be bool")
        if not isinstance(self.load_mode_reason, str) or not self.load_mode_reason.strip():
            raise ValueError("execution plan load_mode_reason must be non-empty")
        if not isinstance(self.operations, tuple) or any(
            not isinstance(item, ChannelEmulatorExecutionPlanItem) for item in self.operations
        ):
            raise TypeError("execution plan operations must be a tuple of plan items")
        if tuple(item.operation for item in self.operations) != expected_operations:
            raise ValueError(
                "execution plan must cover every channel emulator operation exactly once, "
                "in canonical order"
            )
        if tuple(self.phase_order) != CHANNEL_EMULATOR_PHASE_ORDER:
            raise ValueError("execution plan phase_order must be the canonical phase order")
        if not isinstance(self.binding_digest, str) or not self.binding_digest.strip():
            raise ValueError("execution plan binding_digest must be non-empty")

    def item(self, operation: str) -> ChannelEmulatorExecutionPlanItem:
        # 与 `channel_emulator_implements` 同一条规矩：操作名拼错当场炸，不能被当成「不支持」。
        if operation not in CHANNEL_EMULATOR_OPERATIONS:
            raise ValueError(f"unknown channel emulator operation: {operation!r}")
        if operation not in channel_emulator_execution_plan_operations_for_schema(
            self.schema_version
        ):
            raise ValueError(
                f"execution plan v{self.schema_version} has no operation {operation!r}; "
                "请重建执行冻结件"
            )
        for item in self.operations:
            if item.operation == operation:
                return item
        raise ValueError(f"execution plan has no item for {operation!r}")  # __post_init__ 保证到不了

    def planned(self, operation: str) -> bool:
        """共同执行器唯一的能力问法（替代 `channel_emulator_implements(emulator, op)`）。"""

        return self.item(operation).planned

    def rejection(self, operation: str) -> str:
        """未计划时给调用方一条可操作的理由（替代 `channel_emulator_rejection`）。"""

        item = self.item(operation)
        return f"{self.adapter_id} 的执行计划未包含 {operation}：{item.reason}"

    def as_payload(self) -> Dict[str, Any]:
        """canonical JSON-safe payload（不含 digest，digest 对它计算）。"""

        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "driver_source": self.driver_source,
            "requested_load_mode": self.requested_load_mode,
            "load_mode_planned": self.load_mode_planned,
            "load_mode_reason": self.load_mode_reason,
            "operations": [
                {
                    "operation": item.operation,
                    "planned": item.planned,
                    "capability_source": item.capability_source,
                    "reason": item.reason,
                }
                for item in self.operations
            ],
            "phase_order": list(self.phase_order),
            "binding_digest": self.binding_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_payload_digest(self.as_payload())

    def __bool__(self) -> bool:
        raise TypeError(
            "ChannelEmulatorExecutionPlan must not be used as bool; read .planned(op)"
        )


def resolve_channel_emulator_execution_plan(
    *,
    manifest: ChannelEmulatorManifest,
    driver_source: ChannelEmulatorPlanDriverSource,
    requested_load_mode: ChannelEmulatorRequestedLoadMode,
    binding_digest: str,
) -> ChannelEmulatorExecutionPlan:
    """从 manifest 声明推导冻结计划 —— 纯函数、零 I/O、无型号分支。

    manifest 是唯一判据（P2-57 已保证它恰好覆盖自身 schema 的操作各一次）；没有 manifest 的驱动
    在调用方就已 fail-closed，这里不接受 None。
    """

    if not isinstance(manifest, ChannelEmulatorManifest):
        raise ValueError(
            "channel emulator execution plan requires a channel emulator manifest (fail-closed)"
        )
    operation_vocabulary = channel_emulator_execution_plan_operations_for_schema(
        manifest.schema_version
    )
    load_capability = next(
        (item for item in manifest.load_modes if item.mode == requested_load_mode), None
    )
    if load_capability is None:
        load_mode_planned = False
        load_mode_reason = (
            f"{manifest.adapter_id} 的 manifest 未声明加载模式 {requested_load_mode}"
        )
    else:
        load_mode_planned = load_capability.support == "implemented"
        load_mode_reason = load_capability.reason
    declared = {item.operation: item for item in manifest.operations}
    operations = tuple(
        ChannelEmulatorExecutionPlanItem(
            operation=operation,
            planned=manifest.implements(operation),
            capability_source=f"manifest.operations:{operation}",
            reason=declared[operation].reason,
        )
        for operation in operation_vocabulary
    )
    return ChannelEmulatorExecutionPlan(
        schema_version=manifest.schema_version,
        adapter_id=manifest.adapter_id,
        driver_source=driver_source,
        requested_load_mode=requested_load_mode,
        load_mode_planned=load_mode_planned,
        load_mode_reason=load_mode_reason,
        operations=operations,
        phase_order=CHANNEL_EMULATOR_PHASE_ORDER,
        binding_digest=binding_digest,
    )


def plan_from_frozen_payload(frozen: Mapping[str, Any]) -> ChannelEmulatorExecutionPlan:
    """把冻结件（`as_payload()` + digest）重建成计划，供结构校验与 digest 复算。

    键缺失 / 类型不对 → KeyError / TypeError / ValueError，由调用方统一转「冻结件损坏」。
    """

    return ChannelEmulatorExecutionPlan(
        schema_version=frozen["schema_version"],
        adapter_id=frozen["adapter_id"],
        driver_source=frozen["driver_source"],
        requested_load_mode=frozen["requested_load_mode"],
        load_mode_planned=frozen["load_mode_planned"],
        load_mode_reason=frozen["load_mode_reason"],
        operations=tuple(
            ChannelEmulatorExecutionPlanItem(
                operation=item["operation"],
                planned=item["planned"],
                capability_source=item["capability_source"],
                reason=item["reason"],
            )
            for item in frozen["operations"]
        ),
        phase_order=tuple(frozen["phase_order"]),
        binding_digest=frozen["binding_digest"],
    )
