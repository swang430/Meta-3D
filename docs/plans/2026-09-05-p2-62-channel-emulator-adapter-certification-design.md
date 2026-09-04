# P2-62：第三种 Channel Emulator Adapter 接入认证套件设计

## 1. 可观察故障与边界

当前 P2-57～P2-61 已分别提供 manifest、binding/preset、执行计划与生命周期、逐操作回执、
站点认证，但缺少一套以 adapter 为参数的端到端认证合同。真实第三型号若直接接入，平台中的
型号分支只能在开发后期由 MEASURE、commissioning 或 certification 的失败暴露。

本片用仅存在于 `api-service/tests/` 的第三 adapter `certfake_ce` 证明：新增 adapter 只需
adapter/manifest/profile/manual-evidence/认证测试五件套即可穿过共同平台。它不注册生产 HAL，
不携带或猜测任何厂商命令，不授予正式厂商能力。

## 2. 改前全集（AGENTS.md §0.5）

### 2.1 产生方

- adapter 接口与 Mock：`app/hal/channel_emulator.py`
- 能力声明：`app/hal/channel_emulator_manifest.py`
- 执行计划：`app/hal/channel_emulator_execution_plan.py`
- 生产注册：`app/services/instrument_hal_service.py::_real_driver_registry`
- 分型号保存：`app/services/channel_emulator_model_preset.py`
- binding / preview / freeze：`app/services/channel_emulator_binding.py`
- 资产与加载计划冻结：`app/services/channel_emulator_execution_plan.py`
- 执行期操作回执：`app/services/channel_emulator_operation_receipt.py`
- lease / SAFE_IDLE / release / terminal：`app/services/channel_emulator_execution_session.py`
- 硬件身份与站点认证：`app/services/channel_emulator_certification.py`
- MEASURE 频率、路径损耗与运行证据：`app/services/mimo_ota/executors/measure.py`

### 2.2 消费方

- LabProfile sync / readiness / execution freeze
- formal runner 与五类 commissioning 入口
- P2-66 `ExecutionEvidenceOutcome`
- 执行详情、历史、报告、下载与 P2-67 审计导出
- GUI 只消费服务器投影，不自行重算 adapter 能力

### 2.3 已确认的非中立点

`derive_channel_emulator_site_certification_from_execution()` 的频率证明仍要求
`adapter_id == propsim_f64`、`per_instrument.F64`、`f64_center_readback_mhz` 与
`f64_bandwidth_source`。这会拒绝证据完整的第三 adapter。修复形状是**换源**：认证只消费
MEASURE 冻结的通用 Channel Emulator 频率证据，同时保留旧 F64 镜像供历史兼容。

## 3. 认证夹具

`tests/channel_emulator_certification_kit.py` 提供：

- `CertFakeChannelEmulatorProfile`：严格、不可变、测试域 profile；
- `CertFakeChannelEmulatorDriver`：实现 manifest v2 声明的操作；
- `CertFakeChannelTransport`：脚本化 fake transport，记录 command/query/error-queue 事件，
  可注入部分回读、拒绝、延迟、取消；事件是测试协议 token，不是 SCPI；
- `temporary_certfake_channel_emulator_registration()`：只在测试上下文临时注入
  profile/manifest/driver resolver，退出后恢复生产注册表；
- 参数化操作模板：对 asset load、start、动态调参、stop 逐项执行同一共同合同。

certfake 的 `source_reference` 明确写为测试夹具合同，不能冒充厂商手册。生产目录永久门禁止
出现 `certfake_ce` token。

## 4. 认证维度

1. 注册五件套与 manifest/实现对账；
2. binding/preset 保存、恢复、漂移拒绝；
3. vendor-neutral 执行计划解析与 digest；
4. fake transport 与 exchange 身份；
5. 部分回读保持 unknown，不把成功返回洗成 confirmed；
6. 错误队列拒绝能改变操作终态；
7. 超时/取消可控结束；
8. 资产加载与 load receipt；
9. start/stop/动态调参；
10. SAFE_IDLE 与 transport release；
11. simulated/unknown/diagnostic 排除正式 KPI；
12. MEASURE、commissioning、P2-66、certification 对 adapter 中立且 fail-closed。

## 5. 通用频率证据

MEASURE 在现有 `frequency_consistency` 下新增服务器权威子对象
`channel_emulator_evidence`，最小字段为：

- `schema_version`
- `adapter_id`
- `instrument_id`
- `center_readback_mhz`
- `bandwidth_source`
- `fully_verified`

它只从本次冻结 plan、live CE 中心频率回读和冻结 ChannelAsset/SCD 带宽生成；不查询可变
current state。现有 `F64`/`f64_*` 字段只在 F64 路径继续保留为兼容镜像；新认证逻辑仅为
pre-P2-62 历史执行读取旧镜像。

正式认证要求：通用证据结构完整、adapter 与冻结 plan/terminal/identity 一致、中心频率有真实回读、
带宽来自冻结资产/SCD、共同 frequency consistency 为 fully verified。缺失、模拟、错 adapter、
unknown 或篡改一律拒绝。

## 6. 安全方向

- 假阴性：第三 adapter 证据完整仍无法认证，代价是阻塞上线；
- 假阳性：不完整/伪造证据获正式认证，代价是错误仪器数据进入正式 KPI。

因此所有新门均 fail-closed。历史 F64 只通过已有完整旧形态兼容；不从 current state 补真。

## 7. 不做

- 不实现 P2-63 的真实厂商 adapter；
- 不新增或试探任何 SCPI；
- 不改变正式 provenance 白名单；
- 不以本地测试替代现场认证；
- 不改 P2-61 外审报告的两个非阻塞 P2；
- 不启动 P2-63、现场项、P2-32、P3-20/P3-21。
