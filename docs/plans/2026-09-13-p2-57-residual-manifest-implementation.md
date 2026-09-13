# P2-57 声明面残项实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Channel Emulator 注册和显式 ChannelAsset 执行在首个仪器 I/O 前拒绝错误的静态资产/操作能力声明，不复制逐次正式证据。

**Architecture:** manifest 升 v3 并逐项声明四种资产来源；现有 source-type→engine-mode→load-mode 映射仍是唯一执行路由。注册时做纯类实现对账，冻结和历史读取共用 v3 来源门。执行计划继续写 v2，旧 manifest/plan 原摘要照常解析。

**Tech Stack:** Python 3.13、Pydantic v2、SQLAlchemy、pytest；无 DB migration、无新 SCPI。

**Spec:** `docs/plans/2026-09-13-p2-57-residual-manifest-design.md`

## Global Constraints

- 严格 WIP=1；只在 `codex/p2-57-remaining-manifest-declarations` 工作树修改。
- 不改通道/端口拓扑归属；不改正式 provenance 白名单、receipt/session/certification 判词。
- 不新增、猜测或修改任何仪器命令；NotebookLM 推断不能替代手册原文。
- 每一功能先写可观察失败测试并运行 RED，再做最小 GREEN；每个任务验证后独立提交。
- `api-service/.venv` 与 `gui/node_modules` 如需链接只是未跟踪本地依赖，不纳入提交。

---

### Task 1：manifest v3 与三种驱动的逐来源字面声明

**Files:**
- Modify: `api-service/app/hal/channel_emulator_manifest.py`
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/hal/propsim_fs16.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Test: `api-service/tests/test_p2_57_channel_emulator_manifest.py`

**Interfaces:**
- Produces: `ChannelEmulatorAssetSourceCapability`、`ChannelEmulatorManifest.implements_asset_source(source_type: str) -> bool`、`asset_source_rejection(source_type: str) -> str | None`。
- Keeps: `channel_emulator_manifest_for` 仍产生 v2 测试夹具；v1/v2 payload 不新增字段。

- [ ] **Step 1: RED**：新增行为测试：v3 缺任一资产类型或重复类型拒绝；同一个支持 `external_waveform` 的 manifest 可明确拒绝 `custom_static`；v2 历史 payload 原样往返；F64 四来源按当前软件路线声明、FS16 全拒、Mock 对 `rt_dynamic` 拒且其余三项仅说明诊断覆盖。先运行该测试文件，确认失败是新能力缺失，不是 fixture 拼错。

```python
def test_v3_can_reject_one_asset_source_while_load_mode_is_implemented():
    manifest = RealPropsimF64Driver.adapter_manifest.model_copy(
        update={"asset_sources": tuple(
            item.model_copy(update={"support": "not_implemented"})
            if item.source_type == "custom_static" else item
            for item in RealPropsimF64Driver.adapter_manifest.asset_sources
        )}
    )
    assert "external_waveform" in manifest.supported_load_modes()
    assert manifest.implements_asset_source("standard_3gpp") is True
    assert manifest.implements_asset_source("custom_static") is False
```

- [ ] **Step 2: GREEN**：新增固定四词汇 `ChannelEmulatorAssetSourceType`；v3 验证四项恰好一次且不可变；v1/v2 拒绝 `asset_sources`；生产三类逐格字面声明。F64：`standard_3gpp`/`custom_static`/`vendor_file`/`rt_dynamic` implemented（最后一种仅现有单快照路线，不扩多快照）；FS16 四项 not_implemented；Mock 前三项 implemented、`rt_dynamic` not_implemented。`reason`/`source_reference` 是说明，不参与 binding digest。

```python
class ChannelEmulatorAssetSourceCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_type: ChannelEmulatorAssetSourceType
    support: Literal["implemented", "not_implemented", "not_applicable"]
    reason: str
    source_reference: str | None = None

class ChannelEmulatorManifest(BaseModel):
    schema_version: Literal[1, 2, 3]
    asset_sources: tuple[ChannelEmulatorAssetSourceCapability, ...] = ()
```

- [ ] **Step 3: VERIFY + COMMIT**：运行 `pytest -q -o log_cli=false tests/test_p2_57_channel_emulator_manifest.py`，确认 GREEN；运行 `git diff --check`，只提交本任务文件。变异自问：若把 `custom_static` 错判为支持，新增测试应红。

### Task 2：注册期纯类实现对账

**Files:**
- Modify: `api-service/app/hal/channel_emulator_manifest.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Test: `api-service/tests/test_p2_57_channel_emulator_manifest.py`

**Interfaces:**
- Produces: `validate_channel_emulator_registration(driver_class: type, *, model_name: str) -> None`。
- Consumes: 当前 `ChannelEmulatorDriver` 基类拒绝桩、已注册类级 manifest、既有四来源→加载模式映射；无类实例化/连接。

- [ ] **Step 1: RED**：合成一个类，manifest 声称 `stop_emulation=implemented`，类却只继承基类拒绝桩；调用注册验证必须抛可读 `ValueError`。另用同类 manifest 声称 `custom_static=implemented` 而 `external_waveform=not_implemented`，注册必须拒；正常 F64/FS16 注册通过。实际 `_real_driver_registry()` 初始化须调用该验证，不能只测孤立 helper。

```python
def test_registration_rejects_inherited_stop_stub():
    class FalseStop(ChannelEmulatorDriver):
        adapter_manifest = RealPropsimF64Driver.adapter_manifest
    with pytest.raises(ValueError, match="stop_emulation"):
        validate_channel_emulator_registration(FalseStop, model_name="PROPSIM F64")
```

- [ ] **Step 2: GREEN**：在 real registry 构建完、缓存发布前逐个校验 `registry["channelEmulator"]`；使用类 `__mro__` 找出有效方法定义并拒基类 `NotImplementedError` 桩，不能以 `hasattr` 代替。校验 model name/adapter 身份及“implemented source 的既有路由 load mode 也 implemented”；Mock 走现有 mock 注册处的同一纯验证，但模拟白名单不变。失败不缓存半成品 registry。

```python
for model_name, driver_class in registry["channelEmulator"].items():
    validate_channel_emulator_registration(driver_class, model_name=model_name)
_REAL_DRIVER_REGISTRY_CACHE = registry
```

- [ ] **Step 3: VERIFY + COMMIT**：运行注册/manifest 专项与 `tests/test_p2_58_channel_emulator_binding.py`，确认 0 failures；`git diff --check` 后只提交本任务文件。

### Task 3：显式资产首个 I/O 前拒绝，历史冻结件不升级

**Files:**
- Modify: `api-service/app/hal/channel_emulator_execution_plan.py`
- Modify: `api-service/app/services/channel_emulator_execution_plan.py`
- Modify: `api-service/app/services/channel_emulator_binding.py`（仅在发现历史解析确需时）
- Test: `api-service/tests/test_p2_59_channel_emulator_execution_plan.py`
- Test: `api-service/tests/test_p2_66_execution_evidence_outcome.py`

**Interfaces:**
- Produces: 对 v3 manifest 的 `source_type × requested_load_mode` 同源校验；`resolve_channel_emulator_execution_plan` 从 manifest v3 仍输出 plan v2。
- Consumes: frozen `ChannelAssetResolution`、load request、binding manifest/driver；无 current TestCase/asset 回填。

- [ ] **Step 1: RED**：构造 source 为 `custom_static`、load mode 为 `external_waveform`、但 v3 manifest 只支持 `standard_3gpp` 的冻结请求；证明旧 freeze 仅看 load mode 会放行。用相同冻结件进入历史 outcome，必须分类 invalid。另证明 v3 manifest 不应把 plan 误写成 v3；精确 v2 历史 binding/plan 原摘要仍可读。

```python
def test_explicit_asset_requires_its_own_declared_source_type():
    partial = F64_MANIFEST.model_copy(update={"asset_sources": tuple(
        item.model_copy(update={"support": "not_implemented"})
        if item.source_type == "custom_static" else item
        for item in F64_MANIFEST.asset_sources
    )})
    with pytest.raises(ValueError, match="custom_static"):
        validate_channel_emulator_asset_source(
            manifest=partial,
            source_type="custom_static",
            requested_load_mode="external_waveform",
        )
```

- [ ] **Step 2: GREEN**：用既有 source→engine→load 映射核对请求，v3 source 不支持即 fail-loud；冻结写入和 `validate_frozen_channel_emulator_load_context` 共用同一纯判据，后者只读冻结 manifest，simulated 使用权威 Mock manifest。v1/v2 历史结果保持原摘要/历史证据分类；未完成的旧执行若今天仍要 I/O，则按 live v3 的来源拒绝声明核准，不回写旧冻结件，v3 冻结件不得由退回 v1/v2 的 live 声明执行。`resolve_channel_emulator_execution_plan` 的计划版本独立于 manifest：v1→v1，v2/v3→v2；`frozen_channel_emulator_binding_digest` 接受 v2/v3，仍拒 v1 与新计划混搭。修正从当前 F64 manifest dump 构造 v1/v2 历史 fixture 时必须显式去掉 `asset_sources`，不在生产解析器偷删字段。

```python
plan_schema_version = 1 if manifest.schema_version == 1 else 2
operation_vocabulary = channel_emulator_execution_plan_operations_for_schema(
    plan_schema_version
)
```

- [ ] **Step 3: VERIFY + COMMIT**：运行 `test_p2_57_channel_emulator_manifest.py`、`test_p2_58_channel_emulator_binding.py`、`test_p2_59_channel_emulator_execution_plan.py`、`test_p2_66_execution_evidence_outcome.py` 与相关 rule gates；旧完整冻结件不升级、现代不支持来源拒绝、Mock 仍诊断。`git diff --check` 后提交。

### Task 4：现状文档与最终验证

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-09-13-p2-57-residual-manifest-design.md`（只有与实际实现不符时）
- Test: 受影响契约及完整回归

**Interfaces:**
- Produces: 路线图清楚区分 P2-57 已交付静态声明、P2-59～62 动态证据、ChannelAsset 拓扑独立残项；无新的现场签收。

- [ ] **Step 1: 文档**：更新顶部滞后的 P2-70 状态及 P2-57 残项段；写出软件完成的具体文件/测试与仍保持 HOLD 的 P2-63、现场未验收的 P2-55，不覆盖历史叙述。`rg` 全仓核同义现状陈述。
- [ ] **Step 2: 最终门**：受影响链、全后端（SQLite 隔离结果单列，不当 PostgreSQL/真机证明）、GUI 契约与 production build（若无 GUI 改动也跑 build）、compileall、单一 Alembic head、`git diff --check`。输出须记录当前 HEAD/工作树与末行统计。
- [ ] **Step 3: fresh 审查与交付**：按 `AGENTS.md` 的功能 P1/本片 P2 边界做独立审查；修复功能问题须另开 RED→GREEN，复测；确认 P1=0 后提交、推送 Ready PR，按 R1→R2 至覆盖最新 HEAD 无 P1，才可合并。后续 P2/P3 只报告，不自动积压。
