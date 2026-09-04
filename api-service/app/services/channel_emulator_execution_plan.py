# -*- coding: utf-8 -*-
"""P2-59 ①：信道仿真器执行计划的启动期冻结与 MEASURE 期对账（services 侧）。

镜像 `channel_emulator_binding.py` 的冻结件家族：同一个 `TestExecution.config`、同样锁行、
同样拒绝给已有进度的执行行回填、同样「已存在只校验不重算」。计划本体与判据在
`app/hal/channel_emulator_execution_plan.py`。

顺序约束：计划在 binding **之后**冻结（它引用 binding_digest）；两处写方
（`test_case_runner` 与 `api/commissioning._freeze_instrument_lease`）都紧跟 binding 冻结调用。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.hal.base_station_compatibility import canonical_payload_digest
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.channel_emulator_execution_plan import (
    ChannelEmulatorRequestedLoadMode,
    ChannelEmulatorExecutionPlan,
    plan_from_frozen_payload,
    requested_channel_emulator_load_mode,
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import channel_emulator_manifest_of
from app.services.channel_emulator_binding import (
    CE_FREEZE_CONFIG_KEY,
    CHANNEL_EMULATOR_CATEGORY_KEY,
)

#: 冻结件在 `TestExecution.config` 里的键（与 `CE_FREEZE_CONFIG_KEY` 同一家族）。
CE_PLAN_FREEZE_CONFIG_KEY = "channel_emulator_execution_plan_freeze"
CE_LOAD_REQUEST_FREEZE_CONFIG_KEY = "channel_emulator_load_request_freeze"
CHANNEL_ASSET_RESOLUTION_FREEZE_KEY = "channel_asset_resolution"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class FrozenChannelAssetResolution(BaseModel):
    """Asset identity and executable content frozen under the BaseStation digest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    channel_asset_id: NonEmptyString
    source_type: Literal[
        "standard_3gpp", "custom_static", "vendor_file", "rt_dynamic"
    ]
    executable_content_digest: NonEmptyString
    digest: NonEmptyString


def _channel_asset_executable_content(asset: Any) -> dict[str, Any]:
    """Project every mutable ChannelAsset field consumed by the resolver."""

    instrument_connection_id = getattr(asset, "instrument_connection_id", None)
    return {
        "source_type": getattr(asset, "source_type", None),
        "payload": getattr(asset, "payload", None),
        "associated_file_path": getattr(asset, "associated_file_path", None),
        "center_frequency_hz": getattr(asset, "center_frequency_hz", None),
        "bandwidth_mhz": getattr(asset, "bandwidth_mhz", None),
        "ue_velocity_mps": getattr(asset, "ue_velocity_mps", None),
        "instrument_connection_id": (
            str(instrument_connection_id)
            if instrument_connection_id is not None
            else None
        ),
        "is_active": getattr(asset, "is_active", None),
    }


def validate_frozen_channel_asset_resolution(frozen: Any) -> dict[str, Any]:
    if not isinstance(frozen, Mapping):
        raise ValueError("已冻结的 channel asset resolution 不是对象（冻结件损坏）")
    try:
        FrozenChannelAssetResolution.model_validate(dict(frozen))
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(
            f"已冻结的 channel asset resolution 结构不合法（冻结件损坏）: {exc}"
        ) from exc
    payload = {key: value for key, value in frozen.items() if key != "digest"}
    if frozen.get("digest") != canonical_payload_digest(payload):
        raise ValueError(
            "已冻结的 channel asset resolution 与其 digest 不一致（冻结件被篡改）"
        )
    return dict(frozen)


def freeze_channel_asset_resolution(db: Any, configuration: Any) -> dict[str, Any] | None:
    """Resolve an explicit asset once, before the CE request/plan are created."""

    from app.services.mimo_ota.channel_asset_resolver import (
        ChannelAssetResolveError,
        resolve_channel_asset,
    )

    if getattr(configuration, "channel_asset_id", None) is None:
        return None
    try:
        resolved = resolve_channel_asset(db, configuration)
    except ChannelAssetResolveError as exc:
        raise ValueError(str(exc)) from exc
    if resolved is None:
        raise ValueError("channel_asset_id 已指定但 resolver 未返回资产")
    payload = {
        "schema_version": 1,
        "channel_asset_id": str(resolved.asset.id),
        "source_type": resolved.asset.source_type,
        "executable_content_digest": canonical_payload_digest(
            _channel_asset_executable_content(resolved.asset)
        ),
    }
    frozen = {**payload, "digest": canonical_payload_digest(payload)}
    return validate_frozen_channel_asset_resolution(frozen)


def validate_resolved_channel_asset_against_freeze(
    resolved: Any,
    frozen: Any,
    *,
    db: Any | None = None,
) -> dict[str, Any]:
    """Reject mutable asset or vendor-file byte drift before model loading."""

    identity = validate_frozen_channel_asset_resolution(frozen)
    asset = getattr(resolved, "asset", None)
    if asset is None:
        raise ValueError("frozen channel asset has no resolved executable content")
    if (
        str(getattr(asset, "id", "")) != identity["channel_asset_id"]
        or getattr(asset, "source_type", None) != identity["source_type"]
    ):
        raise ValueError("frozen channel asset identity drifted")
    current_digest = canonical_payload_digest(
        _channel_asset_executable_content(asset)
    )
    if current_digest != identity["executable_content_digest"]:
        raise ValueError("frozen channel asset executable content drifted")
    if identity["source_type"] == "vendor_file":
        if db is None:
            raise ValueError("vendor_file byte verification requires a database session")
        from app.services.smu_project_inventory import (
            verify_channel_asset_smu_project_bytes,
        )

        verify_channel_asset_smu_project_bytes(db, asset)
    return identity


class FrozenChannelEmulatorLoadRequest(BaseModel):
    """Resolver-owned effective load truth, independent of plan claim fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    source: Literal["mimo_configuration", "channel_asset"]
    mimo_configuration_digest: NonEmptyString
    channel_asset_id: NonEmptyString | None
    channel_asset_source_type: Literal[
        "standard_3gpp", "custom_static", "vendor_file", "rt_dynamic"
    ] | None
    effective_engine_mode: Literal[
        "keysight_gcm", "mimo_first_asc", "external_asc", "b2_parametric_tdl"
    ]
    requested_load_mode: ChannelEmulatorRequestedLoadMode
    plan_digest: NonEmptyString
    digest: NonEmptyString

    @model_validator(mode="after")
    def validate_source_projection(self) -> "FrozenChannelEmulatorLoadRequest":
        from app.services.mimo_ota.channel_asset_resolver import (
            engine_mode_for_channel_asset_source_type,
        )

        expected_load = requested_channel_emulator_load_mode(
            self.effective_engine_mode
        )
        if self.requested_load_mode != expected_load:
            raise ValueError(
                "channelEmulator frozen load mode does not match effective engine mode"
            )
        if self.source == "mimo_configuration":
            if self.channel_asset_id is not None or self.channel_asset_source_type is not None:
                raise ValueError(
                    "MIMO configuration load request carries channel asset identity"
                )
        else:
            if self.channel_asset_id is None or self.channel_asset_source_type is None:
                raise ValueError(
                    "channel asset load request has incomplete frozen identity"
                )
            expected_engine = engine_mode_for_channel_asset_source_type(
                self.channel_asset_source_type
            )
            if self.effective_engine_mode != expected_engine:
                raise ValueError(
                    "channel asset load request engine does not match frozen source type"
                )
        return self


def validate_frozen_channel_emulator_load_request(frozen: Any) -> dict[str, Any]:
    """Parse the complete resolver projection, then verify its original digest."""

    if not isinstance(frozen, Mapping):
        raise ValueError("已冻结的 channelEmulator load request 不是对象（冻结件损坏）")
    try:
        FrozenChannelEmulatorLoadRequest.model_validate(dict(frozen))
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(
            f"已冻结的 channelEmulator load request 结构不合法（冻结件损坏）: {exc}"
        ) from exc
    payload = {key: value for key, value in frozen.items() if key != "digest"}
    if frozen.get("digest") != canonical_payload_digest(payload):
        raise ValueError(
            "已冻结的 channelEmulator load request 与其 digest 不一致（冻结件被篡改）"
        )
    return dict(frozen)


def channel_emulator_for_execution_plan(hal: Any) -> tuple[Any, str]:
    """MEASURE 将要用的 CE 驱动（或类）与其来源 —— 与 `measure.py` 的兜底规则同源。

    HAL 里装了 channelEmulator 就是它（"hal"）；没有时 MEASURE 会就地造一个
    `MockChannelEmulator`，计划就按它的类级 manifest 算（"fallback_mock"）。
    冻结与 MEASURE 走同一个函数，两边才可能算出同一个 digest。
    """

    drivers = getattr(hal, "drivers", None)
    driver = (
        drivers.get(CHANNEL_EMULATOR_CATEGORY_KEY) if isinstance(drivers, Mapping) else None
    )
    if driver is None:
        return MockChannelEmulator, "fallback_mock"
    return driver, "hal"


def resolve_live_channel_emulator_execution_plan(
    hal: Any,
    *,
    engine_mode: str,
    binding_digest: str,
) -> ChannelEmulatorExecutionPlan:
    """按当下 HAL 装载情况算计划；驱动没有 manifest 一律 fail-closed（不宣称任何能力）。"""

    driver, source = channel_emulator_for_execution_plan(hal)
    manifest = channel_emulator_manifest_of(driver)
    if manifest is None:
        name = driver.__name__ if isinstance(driver, type) else type(driver).__name__
        raise ValueError(
            f"装载的 channelEmulator 驱动 {name} 没有声明 channel emulator manifest（fail-closed），"
            "无法派生执行计划"
        )
    return resolve_channel_emulator_execution_plan(
        manifest=manifest,
        driver_source=source,  # type: ignore[arg-type]
        requested_load_mode=requested_channel_emulator_load_mode(engine_mode),
        binding_digest=binding_digest,
    )


def _resolve_channel_emulator_load_request(db, execution) -> dict[str, Any]:
    """Resolve the effective engine once and freeze where that answer came from."""

    from app.services.mimo_ota.executors._helpers import load_mimo_ota_config

    try:
        configuration = load_mimo_ota_config(execution)
    except (RuntimeError, ValidationError) as exc:
        raise ValueError(
            f"无法读取执行的 MIMO OTA 配置，不能派生 channelEmulator 执行计划: {exc}"
        ) from exc
    # `canonicalize_mimo_ota_configuration_payload` deliberately preserves a
    # sparse JSON shape.  Bind the resolver answer to that exact immutable
    # payload when the base-station freeze already exists; model-dumping here
    # would insert defaults and make P2-66 compare two different truths.
    from app.services.base_station_adapter_profile import (
        FREEZE_CONFIG_KEY,
        MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    )

    execution_config = execution.config if isinstance(execution.config, Mapping) else {}
    base_station_freeze = execution_config.get(FREEZE_CONFIG_KEY)
    frozen_configuration = (
        base_station_freeze.get(MIMO_OTA_CONFIGURATION_FREEZE_KEY)
        if isinstance(base_station_freeze, Mapping)
        else None
    )
    configuration_payload = (
        dict(frozen_configuration)
        if isinstance(frozen_configuration, Mapping)
        else configuration.model_dump(mode="json")
    )
    frozen_asset = (
        base_station_freeze.get(CHANNEL_ASSET_RESOLUTION_FREEZE_KEY)
        if isinstance(base_station_freeze, Mapping)
        else None
    )
    return build_channel_emulator_load_request(
        configuration,
        configuration_payload=configuration_payload,
        frozen_asset=frozen_asset,
    )


def build_channel_emulator_load_request(
    configuration: Any,
    *,
    configuration_payload: Mapping[str, Any],
    frozen_asset: Any,
) -> dict[str, Any]:
    """Pure shared projection used by execution freeze and readiness preview."""

    if configuration.channel_asset_id is None:
        if frozen_asset is not None:
            raise ValueError(
                "channel asset resolution 与冻结 MIMO 配置的空资产身份矛盾"
            )
        source = "mimo_configuration"
        asset_id = None
        asset_source_type = None
        effective_engine_mode = configuration.engine_mode
    else:
        asset_identity = validate_frozen_channel_asset_resolution(frozen_asset)
        if asset_identity["channel_asset_id"] != str(configuration.channel_asset_id):
            raise ValueError(
                "channel asset resolution 与冻结 MIMO 配置的资产身份不一致"
            )
        from app.services.mimo_ota.channel_asset_resolver import (
            engine_mode_for_channel_asset_source_type,
        )

        source = "channel_asset"
        asset_id = asset_identity["channel_asset_id"]
        asset_source_type = asset_identity["source_type"]
        effective_engine_mode = engine_mode_for_channel_asset_source_type(
            asset_source_type
        )
    return {
        "source": source,
        "mimo_configuration_digest": canonical_payload_digest(configuration_payload),
        "channel_asset_id": asset_id,
        "channel_asset_source_type": asset_source_type,
        "effective_engine_mode": effective_engine_mode,
        "requested_load_mode": requested_channel_emulator_load_mode(
            effective_engine_mode
        ),
    }


def validate_frozen_channel_emulator_load_context(
    execution_config: Any,
    frozen_plan: Any,
) -> tuple[dict[str, Any], Any]:
    """Validate the independently frozen MIMO/asset/request/plan chain."""

    from app.schemas.mimo_ota.config import MIMOOTAConfiguration
    from app.services.base_station_adapter_profile import (
        FREEZE_CONFIG_KEY,
        MIMO_OTA_CONFIGURATION_FREEZE_KEY,
    )

    if not isinstance(execution_config, Mapping):
        raise ValueError("channelEmulator execution config 不是对象")
    has_plan = CE_PLAN_FREEZE_CONFIG_KEY in execution_config
    has_request = CE_LOAD_REQUEST_FREEZE_CONFIG_KEY in execution_config
    if has_plan != has_request:
        raise ValueError("channelEmulator load request / execution plan freeze 不完整")
    if not has_plan:
        raise ValueError("channelEmulator load request / execution plan 尚未冻结")
    validated_plan = validate_frozen_channel_emulator_execution_plan(frozen_plan)
    if execution_config[CE_PLAN_FREEZE_CONFIG_KEY] != frozen_plan:
        raise ValueError("channelEmulator scope plan 与 execution 冻结计划不一致")
    request = validate_frozen_channel_emulator_load_request(
        execution_config[CE_LOAD_REQUEST_FREEZE_CONFIG_KEY]
    )
    if request["plan_digest"] != validated_plan["digest"]:
        raise ValueError("channelEmulator load request 与执行计划 digest 不一致")

    base_freeze = execution_config.get(FREEZE_CONFIG_KEY)
    if not isinstance(base_freeze, Mapping):
        raise ValueError("channelEmulator plan 缺少冻结 MIMO 配置")
    outer_payload = {
        key: value for key, value in base_freeze.items() if key != "digest"
    }
    if base_freeze.get("digest") != canonical_payload_digest(outer_payload):
        raise ValueError("冻结 BaseStation adapter profile digest 不一致")
    frozen_mimo = base_freeze.get(MIMO_OTA_CONFIGURATION_FREEZE_KEY)
    if not isinstance(frozen_mimo, Mapping):
        raise ValueError("channelEmulator plan 缺少冻结 MIMO 配置")
    try:
        configuration = MIMOOTAConfiguration.model_validate(dict(frozen_mimo))
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(f"冻结 MIMO 配置不合法: {exc}") from exc
    if request["mimo_configuration_digest"] != canonical_payload_digest(
        dict(frozen_mimo)
    ):
        raise ValueError("channelEmulator load request 与冻结 MIMO 配置不一致")

    frozen_asset = base_freeze.get(CHANNEL_ASSET_RESOLUTION_FREEZE_KEY)
    asset_id = (
        str(configuration.channel_asset_id)
        if configuration.channel_asset_id is not None
        else None
    )
    if asset_id is None:
        if frozen_asset is not None:
            raise ValueError("冻结 MIMO 配置没有资产但存在 asset resolution")
        if (
            request["source"] != "mimo_configuration"
            or request["channel_asset_id"] is not None
            or request["channel_asset_source_type"] is not None
            or request["effective_engine_mode"] != configuration.engine_mode
        ):
            raise ValueError("channelEmulator load request 与冻结 MIMO 来源矛盾")
    else:
        identity = validate_frozen_channel_asset_resolution(frozen_asset)
        if identity["channel_asset_id"] != asset_id:
            raise ValueError("冻结 channel asset resolution 身份漂移")
        if (
            request["source"] != "channel_asset"
            or request["channel_asset_id"] != asset_id
            or request["channel_asset_source_type"] != identity["source_type"]
        ):
            raise ValueError(
                "channelEmulator load request 与独立冻结资产来源不一致"
            )
        from app.services.mimo_ota.channel_asset_resolver import (
            engine_mode_for_channel_asset_source_type,
        )

        authoritative_engine = engine_mode_for_channel_asset_source_type(
            identity["source_type"]
        )
        if request["effective_engine_mode"] != authoritative_engine:
            raise ValueError(
                "channelEmulator load request 与独立冻结资产 engine 不一致"
            )
    return request, configuration


def frozen_channel_emulator_binding_digest(execution_config: Mapping[str, Any]) -> str:
    """执行计划引用的 binding_digest 只能来自 P2-58 ① 的冻结件 —— 它必须先在。"""

    frozen_binding = execution_config.get(CE_FREEZE_CONFIG_KEY)
    digest = frozen_binding.get("binding_digest") if isinstance(frozen_binding, Mapping) else None
    if not isinstance(digest, str) or not digest.strip():
        raise ValueError(
            "channelEmulator binding 尚未冻结，执行计划必须在 binding 之后冻结"
        )
    resolved = frozen_binding.get("resolved_binding")
    if not isinstance(resolved, Mapping):
        raise ValueError(
            "channelEmulator binding 冻结件缺少 resolved_binding（冻结件损坏）"
        )
    if resolved.get("status") == "configured":
        manifest = resolved.get("manifest")
        manifest_version = (
            manifest.get("schema_version") if isinstance(manifest, Mapping) else None
        )
        if manifest_version != 2:
            raise ValueError(
                "channelEmulator binding 仍冻结 manifest v1，不能与新 execution plan v2 "
                "混搭；请重建未开始执行"
            )
    return digest


def validate_frozen_channel_emulator_execution_plan(frozen: Any) -> dict[str, Any]:
    """结构校验 + digest 复算；坏冻结件 → ValueError（镜像 binding：不静默重冻）。"""

    if not isinstance(frozen, Mapping):
        raise ValueError("已冻结的 channelEmulator 执行计划不是对象（冻结件损坏）")
    try:
        plan = plan_from_frozen_payload(frozen)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"已冻结的 channelEmulator 执行计划结构不合法（冻结件损坏）: {exc}") from exc
    # 摘要必须对冻结时的**原始 payload**校验，绝不把历史 v1
    # 先重建 / redump 成当前版本再算；那会改写历史语义。
    raw_payload = {key: value for key, value in frozen.items() if key != "digest"}
    if frozen.get("digest") != canonical_payload_digest(raw_payload):
        raise ValueError(
            "已冻结的 channelEmulator 执行计划与其 digest 不一致（冻结件被篡改）"
        )
    return dict(frozen)


def freeze_channel_emulator_execution_plan(db, hal, execution) -> dict[str, Any]:
    """把计划冻进 `execution.config`；已存在 → 校验后原样复用、**不重算**。

    加载模式不被 manifest 支持在这里 fail-loud（ValueError → 调用方转 CaseNotExecutable / 422）：
    把 `measure.py` 在 MEASURE 期才做的 `get_supported_load_modes()` 判定前移到启动期。
    """

    from sqlalchemy.orm.attributes import flag_modified

    execution_config = execution.config if isinstance(execution.config, dict) else {}
    has_plan = CE_PLAN_FREEZE_CONFIG_KEY in execution_config
    has_request = CE_LOAD_REQUEST_FREEZE_CONFIG_KEY in execution_config
    if has_plan != has_request:
        raise ValueError("channelEmulator load request / execution plan freeze 不完整")
    if has_plan:
        frozen_plan = validate_frozen_channel_emulator_execution_plan(
            execution_config[CE_PLAN_FREEZE_CONFIG_KEY]
        )
        # P2-59① rows created before the resolver projection existed remain
        # structurally readable.  They cannot acquire today's asset truth or
        # become formal evidence later; P2-66 classifies the missing projection
        # fail-closed instead of backfilling from mutable current state.
        validate_frozen_channel_emulator_load_context(
            execution_config, frozen_plan
        )
        if frozen_plan.get("schema_version") == 1:
            raise ValueError(
                "channelEmulator 执行计划 v1 不包含 P2-59② 运行时操作；"
                "未开始执行必须重建冻结件"
            )
        return frozen_plan
    load_request = _resolve_channel_emulator_load_request(db, execution)
    plan = resolve_live_channel_emulator_execution_plan(
        hal,
        engine_mode=load_request["effective_engine_mode"],
        binding_digest=frozen_channel_emulator_binding_digest(execution_config),
    )
    if not plan.load_mode_planned:
        raise ValueError(
            f"channelEmulator {plan.adapter_id} 未声明支持本用例要求的加载模式 "
            f"{plan.requested_load_mode}（{plan.load_mode_reason}），拒绝启动"
        )
    frozen = {**plan.as_payload(), "digest": plan.digest}
    request_payload = {
        "schema_version": 1,
        **load_request,
        "plan_digest": plan.digest,
    }
    frozen_request = {
        **request_payload,
        "digest": canonical_payload_digest(request_payload),
    }
    validate_frozen_channel_emulator_load_request(frozen_request)
    execution.config = {
        **execution_config,
        CE_LOAD_REQUEST_FREEZE_CONFIG_KEY: frozen_request,
        CE_PLAN_FREEZE_CONFIG_KEY: frozen,
    }
    flag_modified(execution, "config")
    db.flush()
    return frozen


def freeze_execution_channel_emulator_plan(db, hal, execution) -> dict[str, Any]:
    """锁 execution 行，在第一次仪器操作前冻结 CE 执行计划（镜像
    `freeze_execution_channel_emulator_binding`：已有硬件 / 相位进度的旧执行行不能回填）。"""

    from app.models.test_plan import TestExecution

    locked_execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution.id)
        .with_for_update()
        .one_or_none()
    )
    if locked_execution is None:
        raise ValueError("TestExecution 已不存在")
    config = locked_execution.config if isinstance(locked_execution.config, dict) else {}
    has_plan = CE_PLAN_FREEZE_CONFIG_KEY in config
    has_request = CE_LOAD_REQUEST_FREEZE_CONFIG_KEY in config
    if has_plan != has_request:
        raise ValueError("channelEmulator load request / execution plan freeze 不完整")
    if not has_plan:
        if locked_execution.status in {"completed", "failed", "cancelled", "skipped"}:
            raise ValueError(
                "执行行已结束，不能用当前 channelEmulator 配置回填执行计划"
            )
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
                "执行行已有硬件 / 相位进度，不能用当前 channelEmulator 配置回填执行计划"
            )
    return freeze_channel_emulator_execution_plan(db, hal, locked_execution)


def verify_frozen_channel_emulator_execution_plan(
    frozen: Any,
    live: ChannelEmulatorExecutionPlan,
    *,
    allow_legacy: bool = False,
) -> str | None:
    """冻结计划对账。

    新执行与 MEASURE 保持 v2-only；只有历史终态投影可显式允许按同一份
    schema-v1 manifest 重建并核验旧计划，不能用当前 v2 能力回填历史。
    """

    try:
        validated = validate_frozen_channel_emulator_execution_plan(frozen)
    except ValueError as exc:
        return str(exc)
    if validated.get("schema_version") == 1 and not allow_legacy:
        return (
            "channelEmulator 执行计划 v1 不包含 P2-59② MEASURE 所需操作；"
            "请重建未开始执行的冻结件"
        )
    if frozen["digest"] != live.digest:
        return (
            f"冻结时 {frozen.get('adapter_id')} / {frozen.get('requested_load_mode')}"
            f"（{frozen.get('driver_source')}），当下 {live.adapter_id} / {live.requested_load_mode}"
            f"（{live.driver_source}）—— 冻结后驱动或加载模式变了"
        )
    return None
