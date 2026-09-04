"""信道仿真器（channelEmulator）分型号的服务端 saved preset（P2-58 ②）。

逐行镜像 ``app/services/base_station_model_preset.py``（#426），有意差别见设计稿
``docs/plans/2026-09-04-p2-58-2-channel-emulator-model-presets-design.md`` §2：

* **没有** adapter_profile 槽 —— CE 没有 profile 层。``alignment_name`` /
  ``available_channel_models`` / ``topology_profile_id`` / ``default_emulation_file`` /
  ``smu_project_scan`` 一律住在 ``connection_params`` 里，preset **原样**带着。
* ``CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS`` 今天是**空集**：CE 没有任何在 HAL
  ``connect()`` 路径上回读进 ``connection_params`` 的运行期观测键。
  ``available_channel_models`` **不是**运行期键（外审 #451 R2 纠正）：它的 4 个写点全在
  API / 服务层（``api/instrument.py`` 操作员增删、``standard_channel_service.py`` SCD 关联
  投影、``smu_project_inventory.py`` smu-sync 扫描），F64 ATE 模式无 MMEM/FTP 无法运行期
  重新发现 —— 剔掉它会在切型号时清空操作员维护的模型清单。
  往这个集合加键前，先在 ``app/hal/`` 里找到 ``connect()`` 路径的写入点：
  ``tests/test_p2_58_2_channel_emulator_model_presets.py`` 的门会逐键要求这一点。
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)
from sqlalchemy.orm.attributes import flag_modified

from app.models.instrument import InstrumentConnection, InstrumentModel


# 空集但保留常量与函数：与 BS 同形，给将来真正的连接期回读键留位。
CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS: frozenset[str] = frozenset()


def persistent_channel_emulator_connection_params(raw: Any) -> dict[str, Any]:
    """只保留操作员持久化的参数，剔除运行期观测键（今天集合为空 = 原样返回副本）。"""

    params = dict(raw or {})
    for key in CHANNEL_EMULATOR_RUNTIME_CONNECTION_PARAM_KEYS:
        params.pop(key, None)
    return params


class ChannelEmulatorModelPreset(BaseModel):
    """一份按型号保存的草稿；永远不直接当执行真值用（活动连接字段才是）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    model_id: UUID
    endpoint: str
    controller: str = ""
    notes: str = ""
    connection_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint")
    @classmethod
    def _endpoint_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("信道仿真器 preset 的 endpoint 不能为空")
        return normalized

    @field_validator("controller", "notes")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        return value.strip()


def parse_channel_emulator_model_presets(
    raw: Any,
) -> dict[str, ChannelEmulatorModelPreset]:
    """解析服务端持有的整张 map；库里存坏了就大声失败，绝不静默丢项。"""

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("信道仿真器型号 preset 必须是以型号 id 为键的对象")
    parsed: dict[str, ChannelEmulatorModelPreset] = {}
    for key, value in raw.items():
        try:
            preset = ChannelEmulatorModelPreset.model_validate(value)
        except ValidationError as exc:
            raise ValueError(
                f"信道仿真器型号 preset[{key!r}] 格式非法：{exc}"
            ) from exc
        canonical_key = str(preset.model_id)
        if key != canonical_key or canonical_key in parsed:
            raise ValueError(
                f"信道仿真器型号 preset 的键 {key!r} 必须等于其唯一 model_id {canonical_key}"
            )
        parsed[canonical_key] = preset
    return parsed


def _snapshot_active_connection(
    model: InstrumentModel, connection: InstrumentConnection
) -> ChannelEmulatorModelPreset | None:
    """把当前活动连接字段原样快照成 ``model`` 的 preset；endpoint 为空则无可快照。"""

    endpoint = (connection.endpoint or "").strip()
    if not endpoint:
        return None
    params = persistent_channel_emulator_connection_params(connection.connection_params)
    return ChannelEmulatorModelPreset(
        model_id=model.id,
        endpoint=endpoint,
        controller=connection.protocol or "",
        notes=connection.notes or "",
        connection_params=params,
    )


def save_channel_emulator_model_preset(
    *,
    category: Any,
    current_model: InstrumentModel | None,
    target_model: InstrumentModel,
    connection: InstrumentConnection,
    endpoint: str,
    controller: str,
    notes: str,
    connection_params: dict[str, Any] | None,
    parsed_controller_ip: str | None,
    parsed_port: int | None,
) -> None:
    """原子地：旧活动型号未存过则先快照 → 只改 map 里 target 键 → 目标投影成活动真值。

    「不覆盖其他型号」只靠一条：除 ``target`` 键外，map 里其余键原样回写。
    """

    presets = parse_channel_emulator_model_presets(
        connection.channel_emulator_model_presets
    )
    if (
        current_model is not None
        and current_model.id != target_model.id
        and str(current_model.id) not in presets
    ):
        old = _snapshot_active_connection(current_model, connection)
        if old is not None:
            presets[str(old.model_id)] = old

    target = ChannelEmulatorModelPreset(
        model_id=target_model.id,
        endpoint=endpoint,
        controller=controller,
        notes=notes,
        connection_params=persistent_channel_emulator_connection_params(
            connection_params
        ),
    )
    presets[str(target.model_id)] = target
    connection.channel_emulator_model_presets = {
        key: value.model_dump(mode="json") for key, value in presets.items()
    }
    flag_modified(connection, "channel_emulator_model_presets")

    connection.endpoint = target.endpoint
    connection.controller_ip = parsed_controller_ip
    connection.port = parsed_port
    connection.protocol = target.controller
    connection.notes = target.notes
    connection.connection_params = dict(target.connection_params)
    flag_modified(connection, "connection_params")
    category.selected_model_id = target.model_id


def synchronize_saved_active_channel_emulator_preset_params(
    *,
    selected_model_id: Any,
    connection: InstrumentConnection,
) -> bool:
    """把操作员在活动连接上持久化的 ``connection_params`` 改动镜像进当前型号的 saved preset。

    镜像 ``synchronize_saved_active_base_station_preset_params``：只动 ``connection_params``
    （endpoint / controller / notes 只能经 ``save_channel_emulator_model_preset`` 改）；
    当前型号没有 preset 就返回 False、**不建** —— 建 preset 只走 ``save_*``（要过 endpoint
    非空校验），而首次切型号时 ``save_*`` 的快照分支会把此刻的活动连接原样带进 map，
    所以 False 不是漏洞。调用方 = PUT 之外写活动 ``connection_params`` 的端点
    （``api/instrument.py`` 的 channel-models 增删）。
    以及服务层的两处写方：`standard_channel_service._sync_projection_for_binding`（SCD 关联投影，W4）与
    `smu_project_inventory.sync_smu_project_truth`（smu-sync，W5）—— 活动 connection_params 的五个写方全部回写（Agent K 接）。
    """

    if selected_model_id is None:
        return False
    presets = parse_channel_emulator_model_presets(
        connection.channel_emulator_model_presets
    )
    key = str(selected_model_id)
    preset = presets.get(key)
    if preset is None:
        return False
    presets[key] = preset.model_copy(
        update={
            "connection_params": persistent_channel_emulator_connection_params(
                connection.connection_params
            )
        }
    )
    connection.channel_emulator_model_presets = {
        preset_key: value.model_dump(mode="json")
        for preset_key, value in presets.items()
    }
    flag_modified(connection, "channel_emulator_model_presets")
    return True


def require_saved_active_channel_emulator_preset(
    *,
    model: InstrumentModel,
    connection: InstrumentConnection,
) -> ChannelEmulatorModelPreset:
    """要求活动执行真值等于其服务端 saved preset（sync-current 的 fail-closed 检测器）。

    镜像 ``require_saved_active_base_station_preset`` 去掉 adapter_profile 比对（CE 无 profile 层）。
    它只**检测**漂移、不修复：活动 ``connection_params`` 在 PUT 之外的四个写点（channel-models 增删 /
    SCD 关联投影 / smu-sync）都已经 ``synchronize_*`` 回写 preset，所以正常操作下这里恒相等；
    不相等 = 出现了带外写方，宁可 422 让操作员重新保存，也不让一条与 preset 不一致的活动配置
    进 LabProfile。
    """

    presets = parse_channel_emulator_model_presets(
        connection.channel_emulator_model_presets
    )
    preset = presets.get(str(model.id))
    if preset is None:
        raise ValueError(
            "channelEmulator 当前型号没有已保存配置；请先在仪器资源配置中点击保存配置"
        )

    mismatches: list[str] = []
    if (connection.endpoint or "").strip() != preset.endpoint:
        mismatches.append("endpoint")
    if (connection.protocol or "").strip() != preset.controller:
        mismatches.append("controller")
    if (connection.notes or "").strip() != preset.notes:
        mismatches.append("notes")
    if (
        persistent_channel_emulator_connection_params(connection.connection_params)
        != preset.connection_params
    ):
        mismatches.append("connection_params")
    if mismatches:
        raise ValueError(
            "活动 channelEmulator 连接与已保存 preset 不一致（"
            + ", ".join(mismatches)
            + "），请重新保存后再同步"
        )
    return preset
