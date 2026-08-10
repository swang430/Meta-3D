# 暗室首测 RF 冷启动初始化实施计划

> 设计依据：`docs/plans/2026-08-10-commissioning-rf-initialization-design.md`
>
> 执行原则：所有硬件动作先写失败测试；不新增无手册出处的 SCPI；任何初始化失败都必须发生在 DUT attach 之前。

## Task 1：钉死“初始化先于 attach”的执行契约

**文件：**

- 修改：`api-service/tests/test_attach_milestones.py`
- 参考：`api-service/app/services/mimo_ota/executors/measure.py`

**步骤：**

1. 增加行为测试，记录 F64 模型加载、中心频率/工作点配置、STATIC2 直通和 UXM `start_signaling` 的调用顺序。
2. 断言模型加载和直通回读均早于 `start_signaling`。
3. 增加初始化失败用例，断言 `start_signaling` 从未调用。
4. 运行新增用例，确认当前代码失败，保存失败原因作为回归基线。

## Task 2：重排后端 RF 初始化事务

**文件：**

- 修改：`api-service/app/services/mimo_ota/executors/measure.py`
- 可能新增：`api-service/app/services/mimo_ota/rf_initialization.py`
- 修改：与抽取接口直接相关的后端测试 fixture

**步骤：**

1. 将信道资产解析、F64 模型加载、中心频率核验和显式 F64 工作点设置组织为可审计的初始化阶段。
2. 将初始化阶段放在 UXM `start_signaling` 之前；初始化失败立即返回，不允许尝试 attach。
3. 模型加载后再建立 `STOPPED + STATIC2`（或请求指定的旁路档）并消费驱动返回值。
4. 删除原有“加载前设一次、加载后再设一次”的遗留依赖，确保一次执行只使用本次加载后的状态。
5. 保持 attach 后 `STATIC0 + GO`、RUNNING 核验和 DUT 二次核验的现有语义。
6. 运行 Task 1 用例及相关 measure/输入电平/F64 状态机回归。

## Task 3：纠正 F64 带宽与中心频率真值语义

**文件：**

- 修改：`api-service/app/hal/propsim_f64.py`
- 修改：`api-service/app/services/mimo_ota/frequency_consistency.py` 或其调用方
- 修改：`api-service/tests/test_frequency_consistency.py`
- 修改：F64 frequency identity 相关测试

**步骤：**

1. 写失败测试，证明 F64 不得把 `SYST:INFO? Bandwidth:100` 能力值当作当前 `.smu` 仿真带宽。
2. 保留 `CALC:FILT:CENT:CH?` 的实时中心频率闭环。
3. F64 带宽只从已登记 ChannelAsset/SCD 声明进入一致性检查；无可信元数据时保持 `unknown`，不制造完整 `FrequencyIdentity`。
4. 在执行结果/警告中区分“F64 中心频率已回读”和“F64 带宽仅资产声明或未知”。
5. 运行频率一致性、信道资产解析和 F64 中心频率相关回归。

## Task 4：让暗室首测界面显式提交现场工作点

**文件：**

- 修改：`gui/src/components/Commissioning/api.ts`
- 修改：`gui/src/components/Commissioning/index.tsx`
- 修改或新增：Commissioning 前端测试

**步骤：**

1. 写请求构造测试，要求创建会话包含中心频率、带宽、UXM 功率、F64 输入参考、crest、输出电平、`.smu`/资产和旁路档。
2. 将 `createSession` 改为具名参数对象，避免位置参数继续扩散。
3. 在会话创建区展示 RF 初始化字段；现场基线可以预填，但必须随请求保存。
4. 对 GCM 模式要求显式 `.smu` 或信道资产；不允许靠仪器残留场景。
5. 运行前端单测、类型检查和生产构建。

## Task 5：整体验证与提交

**文件：**

- 检查：`api/openapi.yaml`（若既有 schema 已覆盖则不修改）
- 检查：`CLAUDE.md`、现状文档中与暗室首测初始化顺序直接相关的描述

**步骤：**

1. 运行所有本轮直接相关的后端测试。
2. 运行后端规则门和前端构建；检查 `git diff --check`。
3. 审阅硬件失败路径：模型加载失败、中心频率不符、工作点设置失败、旁路失败、UXM 配置失败均不得进入 attach。
4. 确认没有改动用户的未跟踪仪表资料与现场数据库。
5. 提交实现，记录现场复验所需的同一 execution 证据点。
