# -*- coding: utf-8 -*-
"""P2-59 ①：信道仿真器执行计划的启动期冻结与 MEASURE 期对账（services 侧）。

镜像 `channel_emulator_binding.py` 的冻结件家族：同一个 `TestExecution.config`、同样锁行、
同样拒绝给已有进度的执行行回填、同样「已存在只校验不重算」。计划本体与判据在
`app/hal/channel_emulator_execution_plan.py`。

顺序约束：计划在 binding **之后**冻结（它引用 binding_digest）；两处写方
（`test_case_runner` 与 `api/commissioning._freeze_instrument_lease`）都紧跟 binding 冻结调用。
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from app.hal.channel_emulator import MockChannelEmulator
from app.hal.channel_emulator_execution_plan import (
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


def requested_engine_mode_for_execution(db, execution) -> str:
    """启动期取 MEASURE 将要看到的 engine_mode —— 与 MEASURE **同一个源**：
    `load_mimo_ota_config(execution)`（基站冻结件里的 MIMO OTA 配置快照优先，否则 TestCase 行），
    再让显式 ChannelAsset 覆盖（与 `measure.py` 的 `resolve_channel_asset` →
    `config.engine_mode = resolved_asset.engine_mode` 同源）。两边读不同的源，对账就会自己漂。"""

    from app.services.mimo_ota.channel_asset_resolver import (
        ChannelAssetResolveError,
        resolve_channel_asset,
    )
    from app.services.mimo_ota.executors._helpers import load_mimo_ota_config

    try:
        config = load_mimo_ota_config(execution)
    except (RuntimeError, ValidationError) as exc:
        raise ValueError(
            f"无法读取执行的 MIMO OTA 配置，不能派生 channelEmulator 执行计划: {exc}"
        ) from exc
    try:
        resolved_asset = resolve_channel_asset(db, config)
    except ChannelAssetResolveError as exc:
        raise ValueError(str(exc)) from exc
    return resolved_asset.engine_mode if resolved_asset is not None else config.engine_mode


def frozen_channel_emulator_binding_digest(execution_config: Mapping[str, Any]) -> str:
    """执行计划引用的 binding_digest 只能来自 P2-58 ① 的冻结件 —— 它必须先在。"""

    frozen_binding = execution_config.get(CE_FREEZE_CONFIG_KEY)
    digest = frozen_binding.get("binding_digest") if isinstance(frozen_binding, Mapping) else None
    if not isinstance(digest, str) or not digest.strip():
        raise ValueError(
            "channelEmulator binding 尚未冻结，执行计划必须在 binding 之后冻结"
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
    if frozen.get("digest") != plan.digest:
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
    if CE_PLAN_FREEZE_CONFIG_KEY in execution_config:
        return validate_frozen_channel_emulator_execution_plan(
            execution_config[CE_PLAN_FREEZE_CONFIG_KEY]
        )
    plan = resolve_live_channel_emulator_execution_plan(
        hal,
        engine_mode=requested_engine_mode_for_execution(db, execution),
        binding_digest=frozen_channel_emulator_binding_digest(execution_config),
    )
    if not plan.load_mode_planned:
        raise ValueError(
            f"channelEmulator {plan.adapter_id} 未声明支持本用例要求的加载模式 "
            f"{plan.requested_load_mode}（{plan.load_mode_reason}），拒绝启动"
        )
    frozen = {**plan.as_payload(), "digest": plan.digest}
    execution.config = {**execution_config, CE_PLAN_FREEZE_CONFIG_KEY: frozen}
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
    if CE_PLAN_FREEZE_CONFIG_KEY not in config:
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
) -> str | None:
    """MEASURE 期对账：冻结件合法且 digest == 当下重算的 live 计划 → None；否则一句可操作的原因。"""

    try:
        validate_frozen_channel_emulator_execution_plan(frozen)
    except ValueError as exc:
        return str(exc)
    if frozen["digest"] != live.digest:
        return (
            f"冻结时 {frozen.get('adapter_id')} / {frozen.get('requested_load_mode')}"
            f"（{frozen.get('driver_source')}），当下 {live.adapter_id} / {live.requested_load_mode}"
            f"（{live.driver_source}）—— 冻结后驱动或加载模式变了"
        )
    return None
