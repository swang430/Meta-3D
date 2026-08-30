# BaseStation 分型号保存与 LabProfile 同步设计

## 可观察故障

`InstrumentConnection` 只有一份活动 endpoint/profile，而 GUI 在型号下拉框变化时立即调用保存接口。于是 UXM/CMW500 切换会在用户尚未点击“保存配置”时改写 `selected_model_id`，并可能清除 CMW500 七字段 profile；随后“同步 LabProfile”把这份混合真值复制进 LabProfile，最终出现 binding/model/endpoint/profile 分叉。

## 全集

产生方：仪器目录 bootstrap、仪器资源配置型号草稿、保存接口、历史活动 connection、LabProfile 显式同步。

消费方：仪器目录响应与 GUI 草稿、BaseStation manifest/profile 表单、HAL reload、`resolve_base_station_binding()`、binding preview、readiness、commissioning/formal runner execution freeze、site certification。

## 方案比较

1. 继续复用单份 connection，在切换时猜测旧值属于哪个型号：无法恢复被覆盖的数据，也会继续制造多真值。
2. 把 presets 塞进通用 `connection_params`：改动少，但会把服务器维护的型号快照暴露到可编辑 JSON，用户一次通用保存即可覆盖。
3. 在唯一 `InstrumentConnection` 上增加服务器维护的 `base_station_model_presets` JSON：活动 connection 仍是当前执行唯一真值；presets 只负责分型号保存草稿，不参与 resolver。选择本方案。

## 数据合同

`base_station_model_presets` 按 `InstrumentModel.id` 存不可变形状：

- `schema_version=1`
- `model_id`
- `endpoint`、`controller`、`notes`
- `connection_params`（不含 `base_station_adapter_profile`）
- `base_station_adapter_profile`（按目标 model manifest 校验；不适用则为 null）

目录 API 只读公开这些 presets；更新请求不允许客户端直接提交整张 presets map。

## 原子保存

型号下拉框只在浏览器内选择并从该型号的已保存 preset 初始化草稿，不调用后端。

“保存配置”一次请求同时携带 `modelId` 和完整 connection/profile。服务端在同一事务中：

1. 锁定 category 与唯一 connection；
2. 若旧活动型号尚无 preset，先把旧活动 connection 快照进去；
3. 用目标 manifest 校验目标 profile；
4. 写目标 preset；
5. 将同一目标 preset 投影为活动 `selected_model_id + connection`；
6. 单次 commit 后返回目录真值。

任何校验失败都不改变型号、活动 connection 或 presets。

## LabProfile 同步

同步接口不接收 GUI 草稿。它只锁定并读取数据库中已保存的活动型号/connection，先构造候选 binding，再用 `resolve_base_station_binding()` 验证；验证失败整笔回滚，成功才提交 LabProfile。GUI 按钮继续明确显示“同步已保存配置”。

## 兼容与恢复

迁移只把当前活动 BaseStation connection 快照为当前型号 preset，不猜测已丢失的其他型号值。现场已有历史 CMW500 配置由受控数据修复从 execution freeze 恢复为“已保存配置”，不把历史回读当作正式认证，也不改变 provenance/KPI 规则。

## 非目标

- 不新增或猜测 SCPI。
- 不改变 HAL registry、adapter manifest 或正式 provenance 白名单。
- presets 不参与 execution resolver；只有活动投影参与。
- 不自动同步 LabProfile，不自动 reload HAL。
