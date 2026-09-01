"""P1-75：TestCase × BaseStation adapter 执行兼容性纯判定器。

零 I/O、零 DB、零 SCPI。判据只消费两端的结构化声明：
- 需求端：``BaseStationExecutionRequirements``（TestCase 冻结时定格的
  requested RAT + 执行链所需操作）；
- 供给端：注册 manifest（``rat_capabilities`` / ``operations``）。

判据红线（roadmap 条目原文，测试钉死）：不读 TestCase 名称、不读 adapter
名称前缀、不读 driver 自报的能力并集 —— evaluator 的输入签名里根本没有
driver。真实驱动的后置 RAT 拒绝（``apply_requested_config``）是纵深防线，
与本判定器互不替代。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from app.hal.base_station_manifest import BaseStationAdapterManifest


# measure 执行链经共同 SPI 实际调用的操作全集（required_operations 真值源）：
#   identity            —— connect 后的身份校验 / 接管对账
#   config              —— set_cell_config 工作点下发
#   cell_attach         —— start_signaling → UE attach 里程碑链
#   measurement_window  —— measure_base_station_window 正式测量窗口
#   safe_idle_release   —— cleanup / 释放远程会话的安全收尾
# 两家现有 adapter（uxm / cmw500）的注册 manifest 今天都声明这 5 个 ——
# 现状全放行；此门守的是未来 adapter 漏声明。
MEASURE_REQUIRED_OPERATIONS: tuple[str, ...] = (
    "identity",
    "config",
    "cell_attach",
    "measurement_window",
    "safe_idle_release",
)


def canonical_payload_digest(payload: Any) -> str:
    """Canonical JSON sha256 —— 与 services 侧两份既有实现算法逐字一致。

    外审 R1 指出仓内已有同算法两份（``base_station_adapter_profile.py::
    _canonical_digest`` 与 ``execution_scpi_evidence.py::
    canonical_snapshot_digest``）。本函数公开命名，供 P2-65（Readiness 复用
    判定器）/ P2-66（证据终态）落地时把两份 services 实现**换源到此处**收敛；
    本片不动既有两份（⑦：不改它们，本片故障已修）。
    """

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BaseStationExecutionRequirements(BaseModel):
    """TestCase 对 BaseStation adapter 的结构化执行需求（冻结时定格）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    # 外审 R3：收窄成封闭 Literal（与 TestCase schema 的取值域同源），
    # 非法形态（含大写 "LTE"）在**构造层**即拒、理由直指值非法 —— 而不是
    # 流进 evaluator 得到误导性的「rat 不被 manifest 支持」。刻意**不做**
    # lower() 归一化：大写只可能来自从未通过 schema 校验的数据，宽容化
    # 输入域等于悄悄扩大契约（从非法形态补真，撞本仓不变量）。
    requested_rat: Literal["nr5g", "lte"]
    required_operations: tuple[str, ...]
    # P2-54 的显式扩展槽位：本片绝不发明 MAC profile 判据（条目红线）。
    mac_profile: None = None

    @field_validator("required_operations")
    @classmethod
    def _unique_operations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if not normalized or any(not value for value in normalized):
            raise ValueError("required_operations must be non-empty tokens")
        if len(set(normalized)) != len(normalized):
            raise ValueError("required_operations must be unique")
        return normalized

    @property
    def digest(self) -> str:
        # 外审 R3（真 high）：omit-when-None（P1-74 statistical_basis 同款）。
        # 站点 B 用 model_validate(旧 payload) 后重算 digest 与冻结值比对 ——
        # 若 None 字段进 digest，P2-54 新增任何可选字段都会让升级前冻结的
        # pending 执行全部误拒（新代码给旧数据填默认 None → dump 多出新键
        # → digest 漂移）。exclude_none 下：旧 payload 缺新字段与新代码
        # 默认 None 算出同一 digest；字段真正赋值时 digest 才变（应当变）。
        return canonical_payload_digest(
            self.model_dump(mode="json", exclude_none=True)
        )


def build_measure_execution_requirements(
    requested_rat: str,
) -> BaseStationExecutionRequirements:
    """measure 执行链的标准需求：requested RAT + 固定操作全集。"""

    try:
        return BaseStationExecutionRequirements(
            schema_version=1,
            requested_rat=requested_rat,  # type: ignore[arg-type]  # Literal 域校验即为目的
            required_operations=MEASURE_REQUIRED_OPERATIONS,
            mac_profile=None,
        )
    except ValidationError as exc:
        raise ValueError(
            f"TestCase radio_technology {requested_rat!r} is not a valid RAT "
            "(expected 'nr5g' or 'lte', case-sensitive; the value never passed "
            "schema validation)"
        ) from exc


def build_measure_execution_requirements_from_configuration(
    configuration: Any,
) -> BaseStationExecutionRequirements:
    """Project the saved TestCase PCell RAT using the freeze contract.

    Only the single compatibility input is read.  Unrelated MIMO OTA schema
    validation must not change the compatibility verdict, while legacy rows
    without ``component_carriers[0].radio_technology`` retain the schema's
    exact ``nr5g`` default.
    """

    requested_rat = "nr5g"
    if isinstance(configuration, Mapping):
        carriers = configuration.get("component_carriers")
        if isinstance(carriers, (list, tuple)) and carriers:
            pcell = carriers[0]
            if isinstance(pcell, Mapping):
                value = pcell.get("radio_technology", "nr5g")
                if isinstance(value, str) and value.strip():
                    requested_rat = value.strip()
    return build_measure_execution_requirements(requested_rat)


class BaseStationCompatibilityVerdict(BaseModel):
    """一次兼容性对账的冻结结论。

    ``no_adapter`` 是 ``diagnostic_unbound`` 的显式记录：无 adapter 无
    manifest —— 不存在「组合」，无从谈逻辑不可能，保持既有放行语义。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    status: Literal["compatible", "incompatible", "no_adapter"]
    compatible: bool
    reasons: tuple[str, ...]
    requirements_digest: str
    manifest_digest: str | None

    @model_validator(mode="after")
    def _consistent_shape(self):
        if self.compatible != (self.status != "incompatible"):
            raise ValueError("compatible flag must mirror the verdict status")
        if bool(self.reasons) != (self.status == "incompatible"):
            raise ValueError("reasons are required exactly when incompatible")
        if (self.manifest_digest is None) != (self.status == "no_adapter"):
            raise ValueError(
                "manifest_digest is absent exactly for the no_adapter verdict"
            )
        return self


def manifest_compatibility_digest(manifest: BaseStationAdapterManifest) -> str:
    """注册 manifest 的 canonical JSON sha256（对账 / 复核共用）。"""

    if not isinstance(manifest, BaseStationAdapterManifest):
        raise TypeError(
            "compatibility digest requires a registered adapter manifest"
        )
    # 同上 omit-when-None：manifest 模型未来加可选字段时，旧 frozen 的
    # manifest_digest 不因 None 默认值漂移。
    return canonical_payload_digest(
        manifest.model_dump(mode="json", exclude_none=True)
    )


def evaluate_base_station_compatibility(
    requirements: BaseStationExecutionRequirements,
    manifest: BaseStationAdapterManifest,
) -> BaseStationCompatibilityVerdict:
    """纯函数对账：需求 vs 注册 manifest 的结构化声明。

    ① requested_rat ∈ manifest 派生 rats（源自 rat_capabilities）；
    ② required_operations ⊆ manifest.operations。
    """

    if not isinstance(requirements, BaseStationExecutionRequirements):
        raise TypeError(
            "compatibility evaluation requires structured execution requirements"
        )
    if not isinstance(manifest, BaseStationAdapterManifest):
        raise TypeError(
            "compatibility evaluation requires a registered adapter manifest"
        )

    reasons: list[str] = []
    declared_rats = tuple(item.rat for item in manifest.rat_capabilities)
    if requirements.requested_rat not in declared_rats:
        reasons.append(
            f"requested RAT {requirements.requested_rat!r} is not implemented "
            f"by adapter {manifest.adapter_id!r} "
            f"(manifest rats: {', '.join(declared_rats)})"
        )
    missing_operations = tuple(
        operation
        for operation in requirements.required_operations
        if operation not in manifest.operations
    )
    if missing_operations:
        reasons.append(
            f"adapter {manifest.adapter_id!r} manifest does not declare "
            f"required operations: {', '.join(missing_operations)}"
        )

    return BaseStationCompatibilityVerdict(
        schema_version=1,
        status="compatible" if not reasons else "incompatible",
        compatible=not reasons,
        reasons=tuple(reasons),
        requirements_digest=requirements.digest,
        manifest_digest=manifest_compatibility_digest(manifest),
    )


def build_no_adapter_verdict(
    requirements: BaseStationExecutionRequirements,
) -> BaseStationCompatibilityVerdict:
    """diagnostic_unbound 的显式结论：无 adapter，保持既有放行。"""

    return BaseStationCompatibilityVerdict(
        schema_version=1,
        status="no_adapter",
        compatible=True,
        reasons=(),
        requirements_digest=requirements.digest,
        manifest_digest=None,
    )


def build_frozen_compatibility_payload(
    requirements: BaseStationExecutionRequirements,
    verdict: BaseStationCompatibilityVerdict,
) -> dict[str, Any]:
    """封进 frozen dict 的 JSON-safe payload（随既有 digest 一并封存）。"""

    if requirements.digest != verdict.requirements_digest:
        raise ValueError("verdict does not belong to these requirements")
    return {
        "schema_version": 1,
        "requirements": requirements.model_dump(mode="json"),
        "verdict": verdict.model_dump(mode="json"),
    }


def build_compatibility_payload(
    requirements: BaseStationExecutionRequirements,
    manifest: BaseStationAdapterManifest | None,
) -> dict[str, Any]:
    """Build the one projection consumed by preview/readiness/freeze."""

    verdict = (
        evaluate_base_station_compatibility(requirements, manifest)
        if manifest is not None
        else build_no_adapter_verdict(requirements)
    )
    return build_frozen_compatibility_payload(requirements, verdict)


def verify_frozen_base_station_compatibility(
    compatibility: Any,
    *,
    live_manifest: Any,
    simulated: bool,
) -> str | None:
    """站点 B（measure 锁内、首次 I/O 前）：对当前 live manifest 复核。

    返回 ``None`` = 放行；返回字符串 = 拒绝原因。缺失的 compatibility
    （本门之前冻结的历史执行）按「当时未评估」放行 —— 不回填不猜测
    （P2-66 收口终态语义）。
    """

    if compatibility is None:
        return None
    if not isinstance(compatibility, Mapping):
        return "frozen compatibility payload is malformed"
    try:
        requirements = BaseStationExecutionRequirements.model_validate(
            compatibility.get("requirements")
        )
        verdict = BaseStationCompatibilityVerdict.model_validate(
            compatibility.get("verdict")
        )
    except ValidationError:
        return "frozen compatibility payload does not parse"
    if requirements.digest != verdict.requirements_digest:
        return "frozen compatibility requirements digest drifted"
    if verdict.status == "incompatible" or verdict.compatible is not True:
        return "frozen compatibility verdict is incompatible"
    if verdict.status == "no_adapter":
        if live_manifest is None:
            return None
        if simulated is not True:
            return (
                "frozen verdict recorded no adapter, but the loaded driver "
                "now declares an adapter manifest"
            )
        if not isinstance(live_manifest, BaseStationAdapterManifest):
            return "loaded simulated adapter manifest is not registered"
        # P2-64: diagnostic_unbound 冻结仍明确表示“无 adapter”；
        # 运行基础设施只能加载已注册、manifest-scoped 的唯一 Mock。
        # 该 manifest 只决定模拟命令/窗口形状，不回填冻结结论。
        return None
    # status == "compatible"：冻结时曾对某个注册 manifest 对过账
    if live_manifest is None:
        if simulated:
            # 授权 mock 不携带注册 manifest（与执行计划 manifest=None 形态
            # 同构）；adapter 身份已由既有 frozen adapter / lease 检查钉住。
            return None
        return "loaded real driver no longer declares its adapter manifest"
    if not isinstance(live_manifest, BaseStationAdapterManifest):
        return "loaded adapter manifest is not a registered manifest"
    if manifest_compatibility_digest(live_manifest) != verdict.manifest_digest:
        return (
            "loaded adapter manifest drifted from the frozen compatibility "
            "manifest"
        )
    live_verdict = evaluate_base_station_compatibility(
        requirements, live_manifest
    )
    if live_verdict != verdict:
        return "live compatibility verdict no longer matches the frozen verdict"
    return None
