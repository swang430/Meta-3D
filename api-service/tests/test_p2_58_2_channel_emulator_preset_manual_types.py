"""P2-58 ②（前端片）：钉手写 ``gui/src/types/api.ts`` 那一面。

Agent I 的门 5（``test_p2_58_2_channel_emulator_preset_api.py::
test_channel_emulator_presets_are_typed_in_live_yaml_and_generated_mirrors``）只守 live /
yaml / 生成 TS 三面，**有意**不含手写文件。这里镜像
``test_base_station_model_preset_openapi.py:44-46``（手写 export + 可选 map 字段两条存在性断言），
并升一档成不变量门：手写类型与生成类型的**顶层字段集合相等**（手写漏一个字段 → 红）。

判定器 ``_top_level_fields`` 自带正反自测：能抓漏字段、不把嵌套对象的键算进来。
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANUAL = REPO_ROOT / "gui/src/types/api.ts"
GENERATED = REPO_ROOT / "gui/src/types/api.generated.ts"

PRESET_FIELDS = {
    "schema_version",
    "model_id",
    "endpoint",
    "controller",
    "notes",
    "connection_params",
}
BINDING_PREVIEW_FIELDS = {
    "status",
    "binding_digest",
    "execution_mode",
    "adapter_id",
    "model_name",
    "category_id",
    "instrument_model_id",
    "instrument_connection_id",
    "lab_profile_id",
    "resolved_binding",
    "runtime_driver",
    "detail",
    "selected_asset_id",
}
BINDING_STATES = ("configured", "not_applicable", "diagnostic_unbound", "invalid")

_FIELD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", re.MULTILINE)


def _block_body(source: str, header: str) -> str:
    """``header`` 之后第一个 ``{`` 到配对 ``}`` 之间的文本，嵌套的 ``{...}`` 整块折叠掉（只剩深度 1）。"""

    start = source.index(header)
    open_idx = source.index("{", start)
    depth = 0
    kept: list[str] = []
    for ch in source[open_idx:]:
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return "".join(kept)
            continue
        if depth == 1:
            kept.append(ch)
    raise AssertionError(f"unterminated type block after {header!r}")


def _top_level_fields(source: str, header: str) -> set[str]:
    return set(_FIELD_RE.findall(_block_body(source, header)))


_SELF_TEST_SNIPPET = """
export type Demo = {
  a: string
  /** 注释里的 {花括号} 成对出现，不影响深度 */
  b?: Record<string, unknown> | null
  nested: {
    inner: number
    deeper: { deepest: string }
  }
  c: 'x' | 'y'
}
export type Other = { z: number }
"""


def test_field_extractor_keeps_only_depth_one_keys_and_notices_a_missing_one():
    """判定器自测（正反两向）：嵌套键不算、可选键算；删掉一个顶层键集合就变。"""

    assert _top_level_fields(_SELF_TEST_SNIPPET, "export type Demo = ") == {"a", "b", "nested", "c"}
    assert _top_level_fields(_SELF_TEST_SNIPPET, "export type Other = ") == {"z"}
    without_c = _SELF_TEST_SNIPPET.replace("  c: 'x' | 'y'\n", "")
    assert _top_level_fields(without_c, "export type Demo = ") == {"a", "b", "nested"}
    generated_style = 'Demo: {\n  a: string;\n  b: {\n    [key: string]: unknown;\n  } | null;\n};'
    assert _top_level_fields(generated_style, "Demo: {") == {"a", "b"}


def test_manual_preset_type_mirrors_generated_and_hangs_off_connection():
    manual = MANUAL.read_text(encoding="utf-8")
    generated = GENERATED.read_text(encoding="utf-8")

    # 镜像 test_base_station_model_preset_openapi.py:44-46
    assert "export type ChannelEmulatorModelPreset = {" in manual
    assert (
        "channel_emulator_model_presets?: Record<string, ChannelEmulatorModelPreset>"
        in manual
    )

    assert _top_level_fields(manual, "export type ChannelEmulatorModelPreset = ") == PRESET_FIELDS
    assert _top_level_fields(generated, "ChannelEmulatorModelPreset: {") == PRESET_FIELDS
    # 手写 preset 无 adapter_profile 槽（CE 无 profile 层）——字段集合相等已经排除，这里把意图写明
    assert "base_station_adapter_profile" not in _block_body(
        manual, "export type ChannelEmulatorModelPreset = "
    )
    assert "schema_version: 1" in _block_body(manual, "export type ChannelEmulatorModelPreset = ")


def test_manual_binding_preview_mirrors_generated_and_readiness_field_is_required():
    manual = MANUAL.read_text(encoding="utf-8")
    generated = GENERATED.read_text(encoding="utf-8")

    assert "export type ChannelEmulatorBindingPreviewResponse = {" in manual
    assert (
        _top_level_fields(manual, "export type ChannelEmulatorBindingPreviewResponse = ")
        == _top_level_fields(generated, "ChannelEmulatorBindingPreviewResponse: {")
        == BINDING_PREVIEW_FIELDS
    )
    for source, header in (
        (manual, "export type ChannelEmulatorBindingPreviewResponse = "),
        (generated, "ChannelEmulatorBindingPreviewResponse: {"),
    ):
        body = _block_body(source, header)
        for state in BINDING_STATES:
            assert state in body, f"{header!r} lacks status {state!r}"

    readiness_manual = _block_body(manual, "export type HALReadinessResponse = ")
    assert "channel_emulator_binding: ChannelEmulatorBindingPreviewResponse | null" in readiness_manual
    assert "channel_emulator_binding?:" not in readiness_manual
    # ① 加进 readiness 的字段，手写 readiness 类型一个都不能少（反向也成立：手写不许多出不存在的字段）
    assert _top_level_fields(manual, "export type HALReadinessResponse = ") == _top_level_fields(
        generated, "HALReadinessResponse: {"
    )


def test_gui_consumers_and_mock_mirror_the_new_manual_types():
    service = (REPO_ROOT / "gui/src/api/labProfileService.ts").read_text(encoding="utf-8")
    assert "export async function fetchChannelEmulatorBindingPreview(" in service
    assert "Promise<ChannelEmulatorBindingPreviewResponse>" in service
    assert "instrument-bindings/channelEmulator/preview" in service

    readiness = (REPO_ROOT / "gui/src/features/Dashboard/ZoneReadiness.tsx").read_text(
        encoding="utf-8"
    )
    assert "projectChannelEmulatorBindingTruth(report.channel_emulator_binding)" in readiness

    draft = (
        REPO_ROOT / "gui/src/features/Equipment/channelEmulatorModelPresetDraft.ts"
    ).read_text(encoding="utf-8")
    assert "channel_emulator_model_presets" in draft

    # 契约第 4 步：mock 也带同一形状（readiness 字段 + preview 端点 + 分型号 preset map）
    mock_database = (REPO_ROOT / "gui/src/api/mockDatabase.ts").read_text(encoding="utf-8")
    assert "channel_emulator_binding: channelEmulatorBindingPreview" in mock_database
    assert "channel_emulator_model_presets: {" in mock_database
    assert "getChannelEmulatorBindingPreview(): ChannelEmulatorBindingPreviewResponse" in mock_database
    mock_server = (REPO_ROOT / "gui/src/api/mockServer.ts").read_text(encoding="utf-8")
    assert "instrument-bindings\\/channelEmulator\\/preview" in mock_server
    assert "mockDatabase.getChannelEmulatorBindingPreview()" in mock_server
