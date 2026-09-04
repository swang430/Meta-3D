# -*- coding: utf-8 -*-
"""P2-58 ①：信道仿真器（channelEmulator）binding 的**唯一**只读 resolver。

逐项镜像 `app/services/base_station_binding.py`（P2-44），差别都是有意的：

  · 无 `profile`（CE 没有 adapter profile 这一层）、无 `formal_capability`
    （CE 的正式能力判定不在本片范围）—— 不抄恒空字段；
  · `manifest` 用 P2-57 的 `ChannelEmulatorManifest`，经
    `channel_emulator_manifest_of(...)` 取，类级 / 实例级都认；
  · 品类键**只认 `"channelEmulator"`**（用户 2026-09-03 拍板 ②）：
    不兼容 `"channel_emulator"`，消费方不得再替真值源打拼写补丁。

**零仪器 I/O**：本模块只读 DB 行与 driver 对象上**已有**的属性，
不 connect、不 query、不 write（有 AST 门守着）。

**runtime identity 刻意排除在 digest 之外**：装载的是 mock 还是真驱动、
装在哪个实例上，都是运行期事实；`binding_digest` 只对持久化真值负责，
所以 HAL reload 不会让已冻结的执行 digest 失配。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, model_validator

from app.hal.base import resolve_configured_tcpip_connection
from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.channel_emulator_manifest import (
    ChannelEmulatorManifest,
    channel_emulator_manifest_of,
)
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.services.instrument_hal_service import get_real_driver_class, is_mock_driver

#: 品类键唯一拼写。⚠️ 不要在这里加 `"channel_emulator"` 兼容 —— 那正是本片要治的
#: 「消费方替真值源打补丁」（设计稿 §2 B 项），有门守着。
CHANNEL_EMULATOR_CATEGORY_KEY = "channelEmulator"

_DRIVER_MODES = frozenset({"auto", "mock", "real"})
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChannelEmulatorRuntimeDriverIdentity(BaseModel):
    """当前装载的 CE 驱动是谁 —— 可审计，但**不进** binding_digest。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    driver_module: str | None
    driver_name: str | None
    #: 装载驱动**自己**声明的 manifest.adapter_id（Mock 也有：`mock_channel_emulator`）。
    adapter_id: str | None
    simulated: bool
    #: host / port / resource；simulated 时为 None。
    transport: dict[str, Any] | None


class ResolvedChannelEmulatorBinding(BaseModel):
    """不可变的解析结果；runtime identity 刻意排除在 digest 之外。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    status: Literal["configured", "not_applicable", "diagnostic_unbound"]
    execution_mode: Literal["real", "simulated"]
    category_id: str
    instrument_model_id: str | None
    instrument_connection_id: str | None
    lab_profile_id: str
    #: 所选型号在注册表里那个真驱动类声明的 manifest（P2-57）。
    #: 真驱动模式下它**必须**等于装载驱动的 manifest（resolver 校验）；
    #: mock 模式下它仍是所选型号的声明 —— mock 自己的身份在 `runtime_driver.adapter_id`。
    manifest: ChannelEmulatorManifest | None
    expected_driver_module: str | None
    expected_driver_name: str | None
    #: 复用 `resolve_configured_tcpip_connection` 的形状：{host, port, resource}。
    expected_transport: dict[str, Any] | None
    binding_digest: str
    runtime_driver: ChannelEmulatorRuntimeDriverIdentity

    def stable_projection(self) -> dict[str, Any]:
        """JSON 安全的 binding 真值投影，preview / readiness / freeze 共用。"""

        return self.model_dump(
            mode="json",
            exclude={"execution_mode", "runtime_driver"},
        )


class FrozenChannelEmulatorTransport(BaseModel):
    """Exact immutable transport identity embedded in a frozen CE binding."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    host: NonEmptyString
    port: int | None
    resource: str | None


class FrozenResolvedChannelEmulatorBinding(BaseModel):
    """Stable resolver projection embedded inside the outer freeze."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    status: Literal["configured", "not_applicable", "diagnostic_unbound"]
    category_id: NonEmptyString
    instrument_model_id: NonEmptyString | None
    instrument_connection_id: NonEmptyString | None
    lab_profile_id: NonEmptyString
    manifest: ChannelEmulatorManifest | None
    expected_driver_module: NonEmptyString | None
    expected_driver_name: NonEmptyString | None
    expected_transport: FrozenChannelEmulatorTransport | None
    binding_digest: NonEmptyString

    @model_validator(mode="after")
    def validate_status_identity(self) -> "FrozenResolvedChannelEmulatorBinding":
        identity = (
            self.instrument_model_id,
            self.instrument_connection_id,
            self.manifest,
            self.expected_driver_module,
            self.expected_driver_name,
            self.expected_transport,
        )
        if self.status == "configured" and any(value is None for value in identity):
            raise ValueError("configured frozen channelEmulator binding identity is incomplete")
        if self.status == "diagnostic_unbound" and any(
            value is not None for value in identity
        ):
            raise ValueError(
                "diagnostic_unbound frozen channelEmulator binding carries configured identity"
            )
        return self


class FrozenChannelEmulatorBinding(BaseModel):
    """Strict immutable outer execution freeze; digest is necessary, not sufficient."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    category_id: NonEmptyString
    instrument_model_id: NonEmptyString | None
    instrument_connection_id: NonEmptyString | None
    lab_profile_id: NonEmptyString
    execution_mode: Literal["real", "simulated"]
    expected_driver_module: NonEmptyString | None
    expected_driver_name: NonEmptyString | None
    expected_driver_connection: FrozenChannelEmulatorTransport | None
    binding_digest: NonEmptyString
    resolved_binding: FrozenResolvedChannelEmulatorBinding
    digest: NonEmptyString

    @model_validator(mode="after")
    def validate_mirrored_identity(self) -> "FrozenChannelEmulatorBinding":
        resolved = self.resolved_binding
        mirrors = (
            (self.category_id, resolved.category_id),
            (self.instrument_model_id, resolved.instrument_model_id),
            (self.instrument_connection_id, resolved.instrument_connection_id),
            (self.lab_profile_id, resolved.lab_profile_id),
            (self.expected_driver_module, resolved.expected_driver_module),
            (self.expected_driver_name, resolved.expected_driver_name),
            (self.binding_digest, resolved.binding_digest),
        )
        if any(outer != inner for outer, inner in mirrors):
            raise ValueError("frozen channelEmulator binding identity mirrors drift")
        if self.execution_mode == "real":
            if resolved.status != "configured":
                raise ValueError("real frozen channelEmulator binding is not configured")
            if self.expected_driver_connection != resolved.expected_transport:
                raise ValueError("real frozen channelEmulator transport mirror drift")
        elif self.expected_driver_connection is not None:
            raise ValueError("simulated frozen channelEmulator carries real transport identity")
        return self


class ChannelEmulatorBindingPreview(BaseModel):
    """给 API sync / readiness 面用的只读结构化投影。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["configured", "not_applicable", "diagnostic_unbound", "invalid"]
    binding_digest: str | None
    execution_mode: Literal["real", "simulated"] | None
    adapter_id: str | None
    model_name: str | None
    category_id: str | None
    instrument_model_id: str | None
    instrument_connection_id: str | None
    lab_profile_id: str
    resolved_binding: dict[str, Any] | None
    runtime_driver: dict[str, Any] | None
    detail: str

    @classmethod
    def invalid(
        cls,
        lab_profile_id: object,
        detail: str,
    ) -> "ChannelEmulatorBindingPreview":
        return cls(
            status="invalid",
            binding_digest=None,
            execution_mode=None,
            adapter_id=None,
            model_name=None,
            category_id=None,
            instrument_model_id=None,
            instrument_connection_id=None,
            lab_profile_id=str(lab_profile_id),
            resolved_binding=None,
            runtime_driver=None,
            detail=detail,
        )

    @classmethod
    def from_resolved(
        cls,
        resolved: ResolvedChannelEmulatorBinding,
    ) -> "ChannelEmulatorBindingPreview":
        manifest = resolved.manifest
        return cls(
            status=resolved.status,
            binding_digest=resolved.binding_digest,
            execution_mode=resolved.execution_mode,
            adapter_id=manifest.adapter_id if manifest is not None else None,
            model_name=manifest.model_name if manifest is not None else None,
            category_id=resolved.category_id,
            instrument_model_id=resolved.instrument_model_id,
            instrument_connection_id=resolved.instrument_connection_id,
            lab_profile_id=resolved.lab_profile_id,
            resolved_binding=resolved.stable_projection(),
            runtime_driver=resolved.runtime_driver.model_dump(mode="json"),
            detail="channelEmulator binding 已按当前服务端真值解析",
        )


def build_channel_emulator_binding_preview(
    db,
    hal,
    selected_lab_profile: LabProfile,
) -> ChannelEmulatorBindingPreview:
    """解析成预览；真值不一致时显式标 `invalid`，绝不看起来像 ready。"""

    try:
        resolved = resolve_channel_emulator_binding(db, hal, selected_lab_profile)
    except ValueError as exc:
        return ChannelEmulatorBindingPreview.invalid(
            selected_lab_profile.id,
            str(exc),
        )
    return ChannelEmulatorBindingPreview.from_resolved(resolved)


# ----------------------------------------------------------------------
# 内部辅助（全部只读：不碰 transport，不调驱动方法）
# ----------------------------------------------------------------------


def _loaded_channel_emulator(hal):
    drivers = getattr(hal, "drivers", None)
    if not isinstance(drivers, dict):
        return None
    # ⚠️ 只认驼峰键。`drivers.get("channel_emulator")` 的兼容写法是本片要删的病。
    return drivers.get(CHANNEL_EMULATOR_CATEGORY_KEY)


def _driver_transport(driver) -> dict[str, Any]:
    """读驱动构造期已解析好的连接身份（`InstrumentDriver.__init__` 写入），零 I/O。"""

    return {
        "host": getattr(driver, "_connection_host", None),
        "port": getattr(driver, "_connection_port", None),
        "resource": getattr(driver, "_connection_resource", None),
    }


def _expected_transport(connection: InstrumentConnection) -> dict[str, Any]:
    config: dict[str, Any] = {
        "endpoint": connection.endpoint,
        "ip": connection.controller_ip,
        "port": connection.port,
        "protocol": connection.protocol,
    }
    if isinstance(connection.connection_params, dict):
        config.update(connection.connection_params)
    host, port, resource, error = resolve_configured_tcpip_connection(config)
    if error:
        raise ValueError(f"所选 channelEmulator 连接配置无效：{error}")
    if not host:
        raise ValueError("所选 channelEmulator 连接没有可用的 transport host")
    return {"host": host, "port": port, "resource": resource}


def _driver_type_name(driver) -> str:
    try:
        return type(driver).__name__
    except Exception:  # noqa: BLE001 —— 取名不许抛，理由见 channel_emulator_manifest.py
        return "<取名失败的对象>"


def _single_binding(lab: LabProfile, category_id: str) -> dict[str, Any]:
    """从 LabProfile.instrument_bindings 取该品类**唯一**一条 binding；0 条 / 多条都拒。"""

    bindings = lab.instrument_bindings
    if not isinstance(bindings, list):
        raise ValueError("LabProfile.instrument_bindings 必须是列表")
    matches = [
        item
        for item in bindings
        if isinstance(item, dict) and str(item.get("category_id")) == category_id
    ]
    if len(matches) != 1:
        raise ValueError(
            "LabProfile 必须恰好包含一条 channelEmulator binding"
            f"（当前 {len(matches)} 条）"
        )
    return matches[0]


def _runtime_driver_identity(
    driver,
    simulated: bool,
    loaded_manifest: ChannelEmulatorManifest | None,
) -> dict[str, Any]:
    return {
        "driver_module": type(driver).__module__,
        "driver_name": type(driver).__name__,
        "adapter_id": loaded_manifest.adapter_id if loaded_manifest is not None else None,
        "simulated": simulated,
        "transport": None if simulated else _driver_transport(driver),
    }


def _digest_safe_manifest_payload(manifest: ChannelEmulatorManifest) -> dict[str, Any]:
    """manifest 进 digest 的投影：剔除纯说明性文案。

    镜像 BaseStation 的 `digest_safe_manifest_payload` 的理由：`reason` /
    `source_reference` 只是给人读的解释，改一句文案不该让已冻结执行的
    `binding_digest` 失配、进而被降级。`operation` / `support` / `mode` 是
    语义内容，照常进 digest —— 翻一格 support 就该让 digest 变。
    """

    return manifest.model_dump(
        mode="json",
        exclude={
            "operations": {"__all__": {"reason", "source_reference"}},
            "load_modes": {"__all__": {"reason"}},
        },
    )


def _validate_loaded_real_driver(
    *,
    driver,
    expected_class: type,
    expected_manifest: ChannelEmulatorManifest,
    loaded_manifest: ChannelEmulatorManifest,
    expected_transport: dict[str, Any],
) -> str | None:
    """真驱动模式：装载驱动必须与所选型号 / 连接完全一致。零 I/O。"""

    if type(driver) is not expected_class:
        return (
            f"装载的 channelEmulator 驱动 {_driver_type_name(driver)} 与所选型号"
            f"注册的驱动类 {expected_class.__name__} 不一致；请重新加载 HAL"
        )
    if loaded_manifest != expected_manifest:
        return (
            "装载的 channelEmulator 驱动实例声明的 manifest 与所选型号注册的"
            " manifest 不一致"
        )
    if _driver_transport(driver) != expected_transport:
        return (
            "装载的 channelEmulator 驱动连接身份 / transport 与所选连接不一致；"
            "请重新加载 HAL"
        )
    return None


# ----------------------------------------------------------------------
# resolver 本体
# ----------------------------------------------------------------------


def resolve_channel_emulator_binding(
    db,
    hal,
    selected_lab_profile: LabProfile,
    *,
    lock: bool = False,
) -> ResolvedChannelEmulatorBinding:
    """解析持久化 binding 真值 + 装载驱动身份，**零仪器 I/O**。

    `ValueError` = 真值不一致（调用方转 422 / preview `invalid`）。
    锁序与 BaseStation 一致：category → LabProfile → connection。
    """

    category_query = db.query(InstrumentCategory).filter(
        InstrumentCategory.category_key == CHANNEL_EMULATOR_CATEGORY_KEY
    )
    if lock:
        category_query = category_query.execution_options(
            populate_existing=True
        ).with_for_update()
    category = category_query.one_or_none()
    if category is None:
        raise ValueError(
            f"仪器品类 {CHANNEL_EMULATOR_CATEGORY_KEY!r} 未配置"
            "（品类键只认这一种拼写）"
        )

    lab = selected_lab_profile
    if lock:
        lab = (
            db.query(LabProfile)
            .filter(LabProfile.id == selected_lab_profile.id)
            .execution_options(populate_existing=True)
            .with_for_update()
            .one_or_none()
        )
        if lab is None:
            raise ValueError("所选 LabProfile 已不存在")
    binding = _single_binding(lab, str(category.id))

    category_driver_mode = category.driver_mode or "auto"
    binding_driver_mode = binding.get("driver_mode")
    if category_driver_mode not in _DRIVER_MODES:
        raise ValueError(
            f"channelEmulator 品类的驱动模式 {category_driver_mode!r} 非法"
        )
    if binding_driver_mode not in _DRIVER_MODES:
        raise ValueError(
            f"LabProfile channelEmulator binding 的驱动模式 {binding_driver_mode!r} 非法"
        )
    if binding_driver_mode != category_driver_mode:
        raise ValueError(
            f"LabProfile channelEmulator binding 的驱动模式 {binding_driver_mode!r} "
            f"与品类当前驱动模式 {category_driver_mode!r} 不一致"
        )

    binding_model_id = binding.get("instrument_model_id")
    selected_model_id = category.selected_model_id
    driver = _loaded_channel_emulator(hal)
    if driver is None:
        raise ValueError("HAL 未装载 channelEmulator 驱动")
    simulated = is_mock_driver(driver)
    # fail-closed：装载的驱动（mock 或真）必须声明 manifest，否则能力无从判断。
    # `channel_emulator_manifest_of` 对 MagicMock 的自动属性判 None，替身混不进来。
    loaded_manifest = channel_emulator_manifest_of(driver)
    if loaded_manifest is None:
        raise ValueError(
            f"装载的 channelEmulator 驱动 {_driver_type_name(driver)} 没有声明"
            " channel emulator manifest（fail-closed）"
        )

    if (binding_model_id is None) != (selected_model_id is None):
        raise ValueError(
            "channelEmulator binding 的 instrument_model_id 与品类 selected_model_id "
            "必须同时配置或同时为空"
        )
    if binding_model_id is None:
        if not simulated:
            raise ValueError(
                "未绑定型号的 channelEmulator 诊断只允许权威 mock 驱动"
            )
        if category_driver_mode == "real":
            raise ValueError(
                "装载的驱动模式（mock）与品类显式的 real 驱动模式不一致"
            )
        persistent: dict[str, Any] = {
            "schema_version": 1,
            "status": "diagnostic_unbound",
            "category_id": str(category.id),
            "instrument_model_id": None,
            "instrument_connection_id": None,
            "lab_profile_id": str(lab.id),
            "manifest": None,
            "expected_driver_module": None,
            "expected_driver_name": None,
            "expected_transport": None,
            "binding": {
                "driver_mode": binding_driver_mode,
                "role": binding.get("role"),
            },
            "category_driver_mode": category_driver_mode,
        }
        return ResolvedChannelEmulatorBinding(
            **{
                key: value
                for key, value in persistent.items()
                if key not in {"binding", "category_driver_mode"}
            },
            execution_mode="simulated",
            binding_digest=canonical_payload_digest(persistent),
            runtime_driver=_runtime_driver_identity(driver, True, loaded_manifest),
        )

    if category_driver_mode == "real" and simulated:
        raise ValueError(
            "装载的驱动模式（mock）与品类显式的 real 驱动模式不一致"
        )
    if category_driver_mode == "mock" and not simulated:
        raise ValueError(
            "装载的驱动模式（real）与品类显式的 mock 驱动模式不一致"
        )

    if str(binding_model_id) != str(selected_model_id):
        raise ValueError(
            "LabProfile channelEmulator binding 的 instrument_model_id 与品类"
            " selected_model_id 不一致"
        )
    model_query = db.query(InstrumentModel).filter(
        InstrumentModel.id == selected_model_id,
        InstrumentModel.category_id == category.id,
    )
    if lock:
        # InstrumentModel 是注册表元数据、本流程不改它，但持久化行都已加锁之后，
        # 预加载在 identity map 里的旧值不能当 binding 真值（镜像 BaseStation 的禁令）。
        model_query = model_query.execution_options(populate_existing=True)
    model = model_query.one_or_none()
    if model is None:
        raise ValueError("品类 selected_model_id 指向的 channelEmulator 型号不在注册表里")

    connection_query = db.query(InstrumentConnection).filter(
        InstrumentConnection.category_id == category.id
    )
    if lock:
        connection_query = connection_query.execution_options(
            populate_existing=True
        ).with_for_update()
    connection = connection_query.one_or_none()
    if connection is None:
        raise ValueError("channelEmulator 品类没有连接配置（InstrumentConnection）")
    binding_endpoint = binding.get("connection_endpoint")
    if (
        not isinstance(binding_endpoint, str)
        or binding_endpoint.strip() != (connection.endpoint or "").strip()
    ):
        raise ValueError(
            "LabProfile channelEmulator binding 的 connection_endpoint 与所选连接的"
            " endpoint 不一致"
        )

    expected_class = get_real_driver_class(CHANNEL_EMULATOR_CATEGORY_KEY, model.model)
    if expected_class is None:
        raise ValueError(
            f"所选 channelEmulator 型号 {model.model!r} 没有注册真驱动"
        )
    expected_manifest = channel_emulator_manifest_of(expected_class)
    if expected_manifest is None:
        raise ValueError(
            f"所选 channelEmulator 型号 {model.model!r} 注册的驱动"
            f" {expected_class.__name__} 没有声明 channel emulator manifest（fail-closed）"
        )
    expected_transport = _expected_transport(connection)
    if not simulated:
        driver_binding_error = _validate_loaded_real_driver(
            driver=driver,
            expected_class=expected_class,
            expected_manifest=expected_manifest,
            loaded_manifest=loaded_manifest,
            expected_transport=expected_transport,
        )
        if driver_binding_error is not None:
            raise ValueError(driver_binding_error)

    persistent = {
        "schema_version": 1,
        "status": "configured",
        "category_id": str(category.id),
        "instrument_model_id": str(model.id),
        "instrument_connection_id": str(connection.id),
        "lab_profile_id": str(lab.id),
        "manifest": _digest_safe_manifest_payload(expected_manifest),
        "expected_driver_module": expected_class.__module__,
        "expected_driver_name": expected_class.__name__,
        "expected_transport": expected_transport,
        "binding": {
            "connection_endpoint": binding_endpoint.strip(),
            "driver_mode": binding_driver_mode,
            "role": binding.get("role"),
        },
        "category_driver_mode": category_driver_mode,
    }
    return ResolvedChannelEmulatorBinding(
        **{
            key: value
            for key, value in persistent.items()
            if key not in {"binding", "category_driver_mode", "manifest"}
        },
        manifest=expected_manifest,
        execution_mode="simulated" if simulated else "real",
        binding_digest=canonical_payload_digest(persistent),
        runtime_driver=_runtime_driver_identity(driver, simulated, loaded_manifest),
    )


# ----------------------------------------------------------------------
# execution freeze（P2-58 ①）：把解析结果冻进 TestExecution.config
# 镜像 `app/services/base_station_adapter_profile.py:173-320`；差别都是有意的：
#   · 无 `resolution` / `compatibility` / `mimo_ota_configuration` /
#     `cmw500_lte_2x2_formal_capability` —— 那是 P1-75 / P2-54 的 BaseStation 专属，
#     CE 在 ① 没有 adapter profile 层、也没有 TestCase 需求对账，不抄恒空块；
#   · 无 `validate_frozen_*_before_remote` 复核与 `freeze_execution_qualification`
#     —— CE 在 ① 无租约校验器、无认证链；
#   · 冻结件损坏（键在但不是 dict / digest 不自洽）→ ValueError，不像 BS 那样静默重冻。
# ----------------------------------------------------------------------

#: 冻结件在 `TestExecution.config` 里的键（设计稿 §8.4）。
CE_FREEZE_CONFIG_KEY = "channel_emulator_binding_freeze"

#: 冻结 identity 的键集合，逐字取自设计稿 §8.4；`digest` 在其外另加。
CE_FREEZE_IDENTITY_KEYS = frozenset(
    {
        "schema_version",
        "category_id",
        "instrument_model_id",
        "instrument_connection_id",
        "lab_profile_id",
        "execution_mode",
        "expected_driver_module",
        "expected_driver_name",
        "expected_driver_connection",
        "binding_digest",
        "resolved_binding",
    }
)


def _validate_existing_channel_emulator_freeze(existing: Any) -> dict[str, Any]:
    """已存在冻结件的严格结构与摘要校验。

    通过 → 原样返回**不重算**；不通过 → ValueError（冻结件损坏或被篡改）。
    """

    if not isinstance(existing, dict):
        raise ValueError("已冻结的 channelEmulator binding 不是 dict（冻结件损坏）")
    digest = existing.get("digest")
    if not isinstance(digest, str) or not digest:
        raise ValueError("已冻结的 channelEmulator binding 缺少 digest（冻结件损坏）")
    binding_digest = existing.get("binding_digest")
    if not isinstance(binding_digest, str) or not binding_digest:
        raise ValueError(
            "已冻结的 channelEmulator binding 缺少 binding_digest（冻结件损坏）"
        )
    identity = {key: value for key, value in existing.items() if key != "digest"}
    if canonical_payload_digest(identity) != digest:
        raise ValueError(
            "已冻结的 channelEmulator binding 与其 digest 不一致（冻结件被篡改）"
        )
    try:
        FrozenChannelEmulatorBinding.model_validate(existing)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(
            f"channelEmulator binding freeze is malformed: {exc}"
        ) from exc
    return existing


def validate_frozen_channel_emulator_binding(frozen: Any) -> dict[str, Any]:
    """Public pure validator for downstream execution-evidence consumers."""

    return _validate_existing_channel_emulator_freeze(frozen)


def validate_frozen_channel_emulator_before_remote(hal, frozen: Any) -> str | None:
    """把 execution-frozen CE 身份与活动 HAL 对账；纯读取、零仪器 I/O。

    该函数只消费冻结件与驱动构造期身份。真机要求注册类和 transport 精确一致；
    模拟只接受仪器 HAL 权威白名单里的 ``MockChannelEmulator``，不靠名字猜。
    """

    from app.hal.channel_emulator import MockChannelEmulator

    try:
        validated = _validate_existing_channel_emulator_freeze(frozen)
    except ValueError as exc:
        return str(exc)
    mode = validated.get("execution_mode")
    driver = _loaded_channel_emulator(hal)
    if driver is None:
        return "loaded channelEmulator driver is missing"
    if mode == "real":
        if is_mock_driver(driver):
            return "loaded channelEmulator driver changed from real to mock"
        if (
            type(driver).__module__ != validated.get("expected_driver_module")
            or type(driver).__name__ != validated.get("expected_driver_name")
        ):
            return "loaded channelEmulator driver does not match frozen registry class"
        if _driver_transport(driver) != validated.get("expected_driver_connection"):
            return "loaded channelEmulator connection identity does not match frozen connection"
        return None
    if mode == "simulated":
        if not is_mock_driver(driver):
            return "loaded channelEmulator driver changed from mock to real"
        if not isinstance(driver, MockChannelEmulator):
            return "loaded mock driver is not a channelEmulator mock"
        if validated.get("expected_driver_connection") is not None:
            return "simulated channelEmulator freeze unexpectedly carries a connection"
        return None
    return "frozen channelEmulator execution mode is invalid"


def freeze_channel_emulator_binding(
    db,
    hal,
    execution,
    selected_lab_profile: LabProfile,
) -> dict[str, Any]:
    """解析一次，把不可变的 execution 级 CE binding 快照写进 `execution.config`。

    已存在 → 结构校验后原样复用、**不重算**；否则 `lock=True` 解析 → identity →
    `digest`。`binding_digest` 直接取 resolver 算好的那个（六个消费方共用同一 digest，
    设计稿 §8.4），这里不重算。ValueError = 真值不一致 / 冻结件损坏，由调用方转
    CaseNotExecutable / 422。
    """

    from sqlalchemy.orm.attributes import flag_modified

    execution_config = execution.config if isinstance(execution.config, dict) else {}
    if CE_FREEZE_CONFIG_KEY in execution_config:
        return _validate_existing_channel_emulator_freeze(
            execution_config[CE_FREEZE_CONFIG_KEY]
        )

    resolved = resolve_channel_emulator_binding(
        db,
        hal,
        selected_lab_profile,
        lock=True,
    )
    identity = {
        "schema_version": 1,
        "category_id": resolved.category_id,
        "instrument_model_id": resolved.instrument_model_id,
        "instrument_connection_id": resolved.instrument_connection_id,
        "lab_profile_id": resolved.lab_profile_id,
        "execution_mode": resolved.execution_mode,
        "expected_driver_module": resolved.expected_driver_module,
        "expected_driver_name": resolved.expected_driver_name,
        # 契约解释 #4：`expected_transport` 本身就是 {host, port, resource} dict，
        # 不是类型化模型 —— 直接拷一份，不 `.model_dump()`。
        "expected_driver_connection": (
            None
            if resolved.execution_mode == "simulated"
            or resolved.expected_transport is None
            else dict(resolved.expected_transport)
        ),
        "binding_digest": resolved.binding_digest,
        "resolved_binding": resolved.stable_projection(),
    }
    frozen = {**identity, "digest": canonical_payload_digest(identity)}
    execution.config = {**execution_config, CE_FREEZE_CONFIG_KEY: frozen}
    flag_modified(execution, "config")
    db.flush()
    return frozen


def freeze_execution_channel_emulator_binding(
    db,
    hal,
    execution,
    test_case,
) -> dict[str, Any]:
    """锁 execution / 取 LabProfile，在第一次仪器操作前冻结 CE binding。

    镜像 BaseStation 的 `freeze_execution_base_station_adapter_profile`：已有硬件 /
    相位进度的旧执行行**不能**从今天的目录回填 provenance；已存在的冻结件只做
    结构校验后复用。`test_case` 只需带 `lab_profile_id`（runner 传执行快照）。
    """

    from app.models.test_plan import TestExecution

    locked_execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution.id)
        .with_for_update()
        .one_or_none()
    )
    if locked_execution is None:
        raise ValueError("TestExecution 已不存在")
    config = (
        locked_execution.config if isinstance(locked_execution.config, dict) else {}
    )
    if CE_FREEZE_CONFIG_KEY not in config:
        has_progress = any(
            value not in (None, {}, [])
            for value in (
                locked_execution.measurements,
                locked_execution.test_results,
                locked_execution.phase_results,
                config.get("phase_progress"),
            )
        )
        if has_progress:
            raise ValueError(
                "执行行已有硬件 / 相位进度，不能用当前 channelEmulator 配置回填冻结件"
            )

    lab_profile_id = getattr(test_case, "lab_profile_id", None)
    if lab_profile_id is None:
        raise ValueError("TestCase 没有 LabProfile，无法解析 channelEmulator binding")
    selected_lab = (
        db.query(LabProfile)
        .filter(LabProfile.id == lab_profile_id)
        .one_or_none()
    )
    if selected_lab is None:
        raise ValueError("所选 LabProfile 已不存在")
    return freeze_channel_emulator_binding(db, hal, locked_execution, selected_lab)
