# 虚拟路测交付设计：先把传导跑通

## 现状与交付边界

核对版本 5559f8fa。测试管理的虚拟路测已有三模式选择、场景库、执行历史和 OTA 映射入口。ScenarioCard 打开 TestExecutionModal；创建时 effectiveMode 会把需要硬件的模式改成 digital_twin。弹窗提示模拟演示。进度可由浏览器定时器推进。后端 road_test.py 已能检查传导 topology_id、持久化执行并控制状态；start 路径调用状态服务，能力接口将传导和 OTA 的 available 固定为 False。场景可选、数据库显示运行、进度走完均不能证明设备已播放路线。

报告和存档已有实现，客户端提交的测量会标记模拟并排除在正式判定外。使用独立临时 SQLite 和模拟仪器重跑 test_road_test_executions、test_road_test_scenarios、test_road_test_websocket、test_p1_48_vrt_no_fabrication，62 项通过。此次是源码核查与后端回归，没有浏览器或硬件实测。既往单天线工程在设备上的加载/运行记录只覆盖该资产和该操作。

## 传导首次交付的操作路径

选择场景及方向 → 选已登记的实验室接线与可播放资产 → 查看缺项和本次运行方式 → 显式启动 → 回读播放状态并采样 → 正常结束或安全停止 → 历史回看与报告。以本批下行 4 发 2 收为第一例；8 路 ASC 和工程 ZIP 是制备输入，能供设备加载的资产须有独立记录。上行、双向或其他端口规模仅在其资产、拓扑及测量能力具备证据时开放。固定标准信道的 MIMO OTA 用例继续走原入口。

| 软件片 | 验收场景 |
|---|---|
| P1-86 | 已配置时，GUI 请求、服务端执行记录和历史都保留 conducted、场景版本、资产摘要、实验室及八路端口映射。缺拓扑、端口冲突、资产不适配或未就绪时说明具体原因；可保存准备工作，不能误启动。能力取自本次绑定的资源。 |
| P1-87 | 启动前核对载频、带宽、端口方向、功率设置与适用校准。优先复用已有硬件驱动、锁及停止流程。成功依据设备回读；设备拒绝、连接中断、重复请求、停止和进程重启均有可见状态。暂停/恢复须有设备支持证据，否则界面禁用并说明。涉及仪器命令时实施前查对应厂商手册。 |
| P1-88 | 第一批展示连接状态、吞吐量和播放位置，逐项保存数据源、时间及单位。路线源帧时间、设备播放时间和采样时间分开记录；缺时间依据时可查看样本，禁止逐帧归因。以服务端事件恢复进度，模拟样本、缺测、失败、中止分别呈现，历史、导出与 PDF 一致。 |
| P1-89 | 隔离环境用同一场景跑完整浏览器流程，回读执行 ID、资产摘要、八路映射、样本来源、终态和归档报告。再覆盖错接映射、设备拒绝、刷新、停止及重试；浏览器关闭不能造成后台无人接管的输出。 |
| P2-111 | 相同场景及声明的模型参数可重放，演示记录全程标明模拟。路线或时间不相容时，两模式结果可各自查看，不输出误导性的差值。 |
| P2-112 | 在 OTA 模式独立验证探头位置、极化、校准范围、映射和资产方向；缺一项明确指出。三模式切换无残留选择、并发执行互斥。模拟环境总验归档。 |

## 单列现场验收

- **传导优先，待设备。** 在已核对的实际电缆拓扑上复核电平、八路映射及适用校准；以可播放资产完成基站连接、播放和仪器采样。核对服务端与仪器记录、终止后的安全状态及报告来源；已有的加载回读不能代替这次端到端运行。
- **OTA，待暗室。** 现场复核探头与校准，在指定测试区播放并取得真实测量，检查运行和安全停止，独立签署 OTA 验收。传导通过不自动授予 OTA 资格。

### 传导采样接口（P1-88）

准备服务通过 `/road-test/conducted` 建档，将模拟专用绑定和八路 ASC 文件 SHA-256 写入独立的服务端数据库列 `vrt_conducted_setup`。详情接口兼容返回 `config.conducted`；历史客户端配置中的同名项不回填，旧记录需重新准备。运行器仅在绑定允许且实际驱动均为模拟驱动时消费模拟资产。每次回读使用 `vrt_execution_service.record_observation(db, execution_id, metric=..., value=..., driver=..., time_s=...)`，传入本次回读的实际驱动和执行经过秒数。项目取 `connection_state`、`dl_throughput_mbps`、`ul_throughput_mbps` 或 `playback_position_s`。缺测传 None；有独立时间依据时可传 `source_frame_time_s`、`device_playback_time_s` 和 UTC 采样时间 `sampled_at`。界面用执行编号读取 `/executions/{id}/status` 和 `/executions/{id}/metrics` 的 `observations`，详情和归档读取同一批记录。客户端不能向传导执行写入采样。

### GUI、执行器与隔离验收共用的传导接口

前缀为 `/api/v1/road-test/conducted`。GET `/options` 返回 labs、topologies、assets（各项含 id、name）。POST `/prepare` 与 POST `/executions` 共用请求字段 scenario_id、lab_profile_id、topology_id、asset_id、direction。预览直接返回快照，建档返回执行详情，快照在 config.conducted；历史列表行的 conducted 保存同一份快照。ready 仅说明准备检查结果。启动仍通过执行控制接口并重新解析。

仅模拟资产取自所选 LabProfile.extra_metadata.vrt_conducted 数组的一条登记。每条包含 scenario_id、scenario_version、scenario_sha256、direction、topology_id、asset_id、sha256、port_mapping；模拟登记额外包含 kind="asc_manifest"、manifest_dir（服务端工程目录）、name。sha256 为 manifest.json 原始字节的 SHA-256，asset_id 为 UUID。port_mapping 各行含从 1 开始的 tx、rx、input_port、output_port。asset.links 保留清单中从 0 开始的 tx、rx、file、sha256。每次解析重验八条文件摘要。asset.mock_only=true、asset.mock_ref 是模拟驱动标识；该分支没有 instrument_path，不能交给真实驱动。

### 本批八路输入与真实执行的差距

本批 RT-IMT-2030 下行工程清单 SHA-256 为 `2b085a23350abd08b84476bdf6f7874dc034e6a8eb980aa2ca393324488c1f2e`，每路文件头登记 6188 个响应、24 个抽头。清单明确标记 `smu_built=false` 和 `hardware_verified=false`。

- 加载前可复用 `verify_channel_asset_smu_project_bytes` 重新核对所登记工程的实际字节，再用 `resolve_channel_emulator_binding` 对照本实验室的型号、连接和驱动。虚拟路测还需要将本次载频、带宽、端口方向、逐路电平和适用校准冻结到执行记录。已有 `evaluate_path_loss_preflight` 读取现有执行的冻结校准范围，直接套用暗室的路线映射不能证明本次电缆的损耗。
- F64 的 `load_local_scenario` 和 `confirm_scenario_loaded` 可复用已登记的设备本地 SMU 加载与稳态确认。ASC 路径 `upload_asc_files` 依赖预制的 runtime_emulation.smu 和已关联到链路的 RTC。此次清单没有提供它们，也没有八路输入与设备内八条运行链路逐一对应的回读证据。
- `channel_emulator_execution_scope` 可在取得设备控制前复核绑定和执行计划，结束时有安全收尾和设备操作结果记录。`stop_emulation` 复核播放已停止；基站可复用 stop_signaling() 后调用 ensure_safe_idle() 独立确认小区已关闭。现有校准以参考天线为终点，仍缺绑定基站物理发射端口、仿真器输入输出与车载接收端口的传导功率证据。四个物理端口的绝对功率也不能从未核实的均分假设推得。真实执行在这些证据齐备并接入 runner 前仍待实现与现场验收。

## 传导浏览器验收记录

隔离数据库中选择 RT-IMT-2030 下行四发二收场景。校验八路原始 ASC 的文件摘要和端口，使用模拟基站与模拟信道仿真器。按文件的 6188 个响应与更新率，首末响应间隔约 36.14 秒。界面提交准备记录、启动、刷新回看、查看报告、归档并取得 PDF。同一份准备配置可以再创建一次独立执行，中途停止后报告显示未完成。

执行编号 `da7f6044-607a-43af-859d-27604313026a`，归档编号 `7849019e-52c2-41bd-a32b-6813ad3d7c05`。报告记录 111 条模拟采样，正式指标为空，合格率为空，结论未判定。下载 PDF 并提取文本，八路文件摘要逐一匹配，存在“没有可用于正式判定的测量指标”说明。错接实验室将一条路径的仿真器输入从 1 改为 4，准备界面指出电缆不一致，改回正确登记后可启动。停止分支执行编号 `82259e9b-9644-4ab7-b1f7-f3ea5cb69867`。

故障复测让隔离服务中的模拟信道仿真器仅第一次拒绝启动。执行 `692f7e6b-7136-4f1c-b8b8-d0dfd0a36558` 返回 409，窗口显示执行失败。随后从同一窗口重新准备，执行 `b7bd5833-d7c1-4dbe-a5b1-f14deb01e422` 完成并下载归档 `c515c9e8-fdab-4c12-aa34-48f8a5be808f`。

复测使用 `gui/test/vrtConducted.browser.js`，提供隔离站点的浏览器页面、场景名、实验室名、错接实验室名、拓扑名、模拟资产名和清单摘要。运行中的进度来自服务端；具体采样条数随调度变化。仪器未回读的播放位置及路线帧时间为空。

登记时从准备接口取实际场景内容摘要。保存时冻结该场景，启动按冻结时长播放，历史和报告也从同一份场景取数。场景内容被修改后，旧登记须重新核对；已经执行的记录仍使用原场景。

场景冻结复测：执行 `e23dbf3b-6f65-4238-aaeb-b6947437101b` 的归档 `f535b110-054a-4001-ad31-ea3baa8336cb` 含 111 条模拟采样。下载 PDF 后逐项核对场景、清单、八个 ASC 共十个摘要。修改场景名称后，从改名后的场景卡重新打开，执行窗口仍显示保存时的名称。
