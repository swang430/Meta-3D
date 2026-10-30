# PC-04A-8 全Mock校准软件验证（2026-10-30）

范围：本地实现与隔离软件验收，未创建/合并PR、未部署，不代表真机、计量认证或现场B/HOLD解除。实际测试统计及最终输入冻结见文末；独立任务/累计审查与同一Ready PR外审由主代理后续执行。

## 原r6：真实阻塞与声明缺项

仅使用本机已存 `/tmp/pc04a5d-BVAwTu/source-before.json`，没有查询或改写默认数据库。将 `nodes/connections/operating_modes` 三数组原样导入独立暗室/实验室，导入前与读回canonical SHA256逐数组相等。

生产 `route-calibration-paths?selection_scope=individual&operating_mode=mimo_ota` 实际返回 **422，`CE源端存在回接`**。这是本次动态证据，不把最初的无关上行参考节点误挡当作当前唯一阻塞。静态另查32条正常下行终端，均未声明从该探头出发的 `calibration` 参考边，且模式为 `calibration_e2e` 而非生产参考模式 `calibration`；静态缺项不是生产成功选出32路的证明。

没有为原图提交校准start，没有别名转换模式、补pins/参考边、删除上行边或改器件类型。原图全流程仍未完成。以下synthetic结果与此原图无资格继承关系。

## Synthetic32：独立计算及正式隔离

以既有独立声明小图深拷贝32次，ID前缀 `synthetic-01-` 至 `synthetic-32-`，CE B1–B32，探头0–15、V/H交替；每条都有独立PA、接收线缆和参考段。PA标称20 dB及既有99 dB校准字段保留为“不重复补偿”的反例，不从原图取得真实线缆声明。

矩阵为32路×2595/3500 MHz×5样本，共64组合/320样本。频率仅是演练输入，不是仪器频段能力声明。路索引 `i=0..31`、频点索引 `k=0..1`、样本索引 `j=0..4`：

```text
before = -30 + 0.2j
after  = -29.8 + 0.2j
received = -48 + 0.7i + 0.3k + 0.1j
Lrx = 2
loss_j = (before + after)/2 - (received + Lrx)
独立均值 = 16.3 - 0.7i - 0.3k
独立样本标准差 = sqrt(0.025)
```

独立期望不调用生产计算函数、不从返回损耗反推路编号。正损耗与负增益均保留。`expected_loss_db`只保存并显示差值，不参与服务器计算，不产生PASS判词。已知0与未知线缆由Task2专例验证；缺接收线缆值/来源时保存功率、两统计为null，不补0。

API使用真实FastAPI路由、数据库、作业与HAL Mock实例，preview/start后逐真实manual transition继续，按父项run_id读取全部64子记录，不使用默认历史20条代替全量。每项均 `simulated`、`operator_supplied_synthetic`、`formal_eligible=false`、`cleanup_confirmed=null`；采用确认422，正式冻结无 `confirmed_route`。父批 `finalization_committed=true`，但 `f64_control_released=null`、`all_started_cleanup_confirmed=false`，只证明软件演练终态，不证明真实停发/释放。

## 用户操作

1. 在全Mock实验室选择已保存启用图。单路从完整校准通路选路，批量明确选择路径与频点；填写参考天线身份、极化与位置并核对安全条件。
2. 单路主动开启“模拟演练样本”再填写每样本三功率；默认关闭，不自动随机生成数值。批量主动开启CSV模式，导入所选路径×频点完整唯一的样本矩阵。CSV列为 `chain_id,frequency_mhz,sample_index,source_before_dbm,received_dbm,source_after_dbm,receive_cable_loss_db,receive_cable_source,expected_loss_db`。
3. 样本编号完整1..N，必需数字不能空、bool、NaN/Inf；每组线损/来源/expected一致。参考身份先明确填写。预览后再次明确开始；等待时重新输入当前参考位置并勾选当前步骤确认，不能重用旧transition。
4. 从服务器历史读取模拟结果，点击“下载模拟演练 CSV（非正式报告）”。每样本一行，null空白、0保留，带run/Lab/chain/frequency、来源、处理时间与formal=false。文件是浏览器Blob演练导出，不是服务器签发的正式报告。

真实/混合/未知驱动不得录入模拟输入。dirty/pending/busy/unknown时输入和开始受既有锁约束；切Lab/图/模式清模拟草稿。unknown启动只使用原幂等键/原请求重读，不自动换键重发。跨SPA卸载不承诺持久草稿；Task3极端异步长文件/网络乱序未穷举。

## 消费者与权威源

| 路径 | 本片读取/隔离规则 |
|---|---|
| 选路 | 正常下行与参考段分开；已选下行仍拒绝参考类型节点；不放宽原图回接等拓扑门 |
| 单路/批preview/start/每项执行 | 当前Lab绑定、类别/型号/endpoint与实际 `is_mock_driver`；不能靠名字或客户端来源判断 |
| 样本/计算 | 与真实采集共用生产计算；显式输入来源在首控制前设置；失败/取消清统计不造成功 |
| 保存/详情/历史 | request或结果任一显式来源均保持模拟；读副本降级不写回历史数据库 |
| 采用/冻结/正式报告/KPI | 模拟数值不能取得正式采用；冻结只消费合法real采用，不新增直读模拟结果入口 |
| GUI/CSV | typed请求→真实服务器记录→独立演练显示/导出；原实测字段不给模拟数值 |
| 摘要身份 | 批/individual为selected-route scope；非batch单路必须重新读默认simultaneous整图scope，不复用批摘要 |

Task1–3生产消费者审计与局部变异记录保留在本机SDD报告；本片不改HAL命令、仪器语义或旧测试预期。

## 输入、证据与局限

本机证据目录：`output/playwright/pc04a8-task4/`（不作为远程下载链接），保留SQLite、bootstrap类别/所有Lab绑定/实际HAL审计、HTTP JSON、独立期望差值、真实截图、下载、日志与完整输入hash。所有库均新建于 `/tmp/pc04a8-...`，app导入前设置Mock/bootstrap/日志环境；默认库和用户服务不动。

常规synthetic验收以子进程新建隔离库，不依赖本机r6快照。`seed_world(db, source_path=None)`默认保单路+matrix；本地原图诊断用CLI `--source-snapshot /tmp/pc04a5d-BVAwTu/source-before.json`显式传入，缺文件明确失败，不用别的图替代。原 `collection_id/lab_id/chamber_id` 键保留，matrix映射新增，source键仅显式诊断时存在。

浏览器使用本任务新库与15148→18048专用代理、真实页面控件，不调用React handler、不伪造HTTP回复。启动时fixture仍自动建独立source世界；最终仅将source改显式可选。`fixture-equivalence.json`保留不同fixture hash，并将最终生成图的SA category映射到该浏览器库已审计类别，三数组canonical hash完全相等。GUI/生产输入未因该夹具调整改变，不能称启动夹具文件完全相同。

中间验收如实保留：图构造函数缺失为预期RED；首次完整API在index49附近触发120秒预算，改有界600秒；后两轮64项对账成功而尾部单路因误用批/individual摘要422。它们不是产品RED或整轮GREEN，未修改生产校验来迎合测试。Task3初始Node RED原stdout未由本片独立核验；Task3停服原件有时序差异、作者已更正，不用后续空端口证据倒填原件。

### 最终统计与复用范围

| 验证 | 实际结果 |
|---|---|
| 最终API验收 | 2 passed、40 warnings，210.73秒；64组合/320样本及单路取消/重入 |
| 前三任务相关后端集 | 425 passed、3 failed、1724 warnings，338.71秒 |
| GUI相关/构建 | 39 passed、0 failed、0 skipped；构建成功19.24秒，保留原警告 |
| 唯一全后端 | **exit 1：8213 passed、3 failed、17 skipped、10173 warnings，1047.75秒** |

全后端真实命令 `.venv/bin/python -m pytest -q`，UTC 07:26:09–07:43:46，未增ignore/deselect。三失败均为已知 `test_g8_docs_only_cite_live_plan_routes`、`test_g11_docs_cite_live_api_routes_full_domain`、`test_gitignore_does_not_shadow_tracked_sources`，没有新增失败，未改历史/门/ignore。不能称全绿；warnings未逐条重新归因或消除。

全量1156项代码/测试/GUI/契约/依赖声明输入起止0变化，文件集合hash `757604e0f1533416d077ee21e9283ec5b4bffc5b8b03c2f5699a686c3795390b`，安装包版本hash `a1524c2c5f15d80bdfc3e00fe52827eaddc0e7a272239835c9829407c8e8aa18`，commit/diff亦相等。原件为 `full-input-before/after.json`、`full-exit-code.txt`、`full.log`。

全量后仅经主代理批准，将**新增测试**的Python随机目录创建改为现有系统 `mktemp -d /tmp/pc04a8-XXXXXX`，避免随机后缀含下划线而被既有路径守卫拒绝；必要import随之删除。产品、矩阵、断言、守卫均不变。全量明确属于此行修改前的测试输入，不冒称新版测试文件与其hash相同；命名差异保留 `naming-only.diff`/前后hash，定点真实创建目录并bootstrap/全Mock及实际HAL审计exit0（`naming-bootstrap.json`）。按裁决不重复全量，仅限定复用生产/断言验证。

浏览器首次漏填参考位置产生的本地提示在最终成功只读历史上方仍有残留（`browser-final.png`）；32个实际continue均200、父64项终态与下载对账另有独立证据。是否本片引入、是否影响用户判断，留独立审查，不自行降为非缺陷或自动入backlog。

仅停止已核PID/cwd的本任务API57981、Vite58044；后续实际 `ports-after-stop.txt` 为0字节、lsof退出1，非仅凭SIGTERM推断。没有删除数据库或关用户Chrome/默认服务。

本地实现/验收已留痕，仍待独立任务/累计审查与同一Ready PR外审，未部署。未验：真机/现场接线、真实仪器停发及计量追溯、正式采用资格、原图完整校准、B/HOLD、PR外审和部署。
