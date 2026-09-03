# -*- coding: utf-8 -*-
"""P2-58 ①：channelEmulator binding 预览的公开 API schema。

字段 = `app.services.channel_emulator_binding.ChannelEmulatorBindingPreview`
的全部字段 + `selected_asset_id`（per-TestCase 的信道资产，**不进** binding digest，
只在预览端点带 `test_case_id` 时附带 —— 镜像 BaseStation 把 compatibility 与
binding 分开的做法）。字段集合相等由测试门守着。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ChannelEmulatorBindingPreviewResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_serialization_defaults_required=True,
    )

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
    #: 预览端点带 `test_case_id` 时附带；不影响 binding_digest。
    selected_asset_id: str | None = None
