# S5c：采集原版Lauraycs聚簇结果并交给CE

当前路线见[设计](../../docs/plans/2026-11-14-s5c-native-cluster-design.md)。
Lauraycs保持原版；不加载HyperRT、不在Meta-3D或CE重复聚簇。下面的采集只用于离线研究，不解除正式执行限制。

## 使用现有服务

准备一个`meta3d-lauraycs-request/1`清单，样本身份来自现有Lauraycs任务，时间来自该任务保存的物理时间或明确声明的推导依据。不要用FRAME_ID当秒数。
下例仅展示结构，`synthetic-example`与S3路径必须替换，不能直接拿来当真实结果：

```json
{
  "schemaVersion": "meta3d-lauraycs-request/1",
  "source": {
    "taskId": "synthetic-example",
    "mpdbPath": "s3://example/R0B0S0D.mpdb",
    "contentVersion": null,
    "softwareVersion": null,
    "additionalLoss": null
  },
  "carrierHz": 2400000000,
  "txAnt": 0,
  "rxAnt": 0,
  "angleCoordinateSystem": "LCS",
  "units": {"time":"s","delay":"ns","angles":"deg","doppler":"Hz","carrier":"Hz","response":"complex_scalar"},
  "clusterIdentity": "frame-local-only",
  "requestedClusterCount": 8,
  "timing": {"source":"synthetic-example","timesSeconds":[0,0.13,0.91]},
  "samples": [
    {"sampleIndex":0,"frameId":0,"internalLinkId":10},
    {"sampleIndex":1,"frameId":1,"internalLinkId":11},
    {"sampleIndex":2,"frameId":2,"internalLinkId":12}
  ]
}
```

```sh
python scripts/s5_evaluation/lauraycs_collect.py \
  --manifest /absolute/path/to/request.json \
  --base-url https://your-lauraycs-host \
  --ce-repo /absolute/path/to/ChannelEgine \
  --output /absolute/path/to/new-result.json

python scripts/s5_evaluation/cluster_import.py /absolute/path/to/new-result.json \
  --ce-repo /absolute/path/to/ChannelEgine \
  --frequency-offsets-hz 0 1000000 5000000
```

基地址填写服务根地址，程序调用原版`/api/task/channel-analysis/clustering/kmeans/analyze`。
如需授权，通过`LAURAYCS_AUTHORIZATION`环境变量提供完整Authorization头；不要写进清单或命令参数。
非本机服务要求HTTPS，禁止重定向，不自动重试计算请求。单帧请求超时60秒，响应上限16MiB。

输出`meta3d-cluster-trajectory/1`由Meta-3D组织，不是Lauraycs原生文件。
完整服务响应与规范化结果同时保留；未知多普勒为null，空帧与失败不同。
`complete`仅指清单里的请求都得到可识别结果，不证明覆盖完整任务，也不证明服务器源文件在逐次调用间未变。
失败帧不删除，整体incomplete且退出2。输出文件必须尚不存在。
HTTP错误正文及分块响应中断时取得的部分正文保存在`responses`的`bodyBase64`中（Base64编码原始字节，上限16MiB）；`bodyIncomplete`表示读取中断，`bodyTruncated`表示超过保存上限。HTTP错误另保留`httpStatus`；即使错误正文含`code:200`，该帧仍失败，不进入有效聚簇结果。
任务、载频、阵子、时间、源版本和坐标系声明不升级成服务回读证据；两种状态都`hardwareEligible=false`。
完整源元数据可放在`sourceMetadata`，原样保留。

CE库`mimo_ota_simulator.imported_cluster_trajectory`是校验与计算的唯一实现，Meta只包装调用。
支持该模块的CE版本必须已安装，或通过`--ce-repo`指定含本片实现的仓库。
频响计算只在已有时刻使用复H和时延，不进行帧间插值，不证明真实宽带或OTA设备适用性。
无路径及全部过滤帧保持不可评价，不补成已测零响应。

## 原有双算法研究工具

以下工具保留供可选研究，不是正式来源选择的必跑前置。
## 调用

使用装有各自原算法依赖的Python，两个算法分别在独立进程运行。下面路径须替换为实际位置，输出目录必须尚不存在。

```sh
python scripts/s5_evaluation/run.py \
  --engine lr --repo /absolute/path/to/Lauraycs-source \
  --input /absolute/path/to/adapted-final.json \
  --source-zip /absolute/path/to/original.zip \
  --output /absolute/path/to/new-lr-results \
  --candidate-units --frequency-offsets-hz -5000000 -2500000 0 2500000 5000000
```

CE检查使用`--engine ce --repo /absolute/path/to/ChannelEgine`。本版批处理针对当前缺旋转信息的输入，CE全部保留为blocked；不提供未经验证的命令行速度覆盖。底层适配器可通过独立、已知坐标的合成测试调用真实CE函数，这不表示本次原数据可用。

LR正常导入仓库内`_cluster_cdl_udf_result`，使用`include_doppler=False`：当前底层`_clusterCDL`不接受多普勒参数。原始多普勒保留在输入文件，聚簇后的多普勒保持未知，不以零代替。不复制算法、不替换原生模块。依赖、许可证或算法失败会逐帧记录，退出码2，不能把输出文件存在当评价成功。

输出包括`ce-clusters.json`或`lr-clusters.json`、`evaluation.json`及`manifest.json`。保存实际算法输出、过滤数/功率、每项状态、输入校验值和源码版本；按方向/预算统计可用数与不可用数，失败仍留在分母。指标汇总是分布描述，不是通过率。
进程退出0仅表示全部条件性计算完成；退出2表示存在阻塞/失败，仍不输出物理验收判词。

## 数学及来源限制

- H实虚部保持，功率为abs(H)平方。缺相位不补零；CE统计簇不生成虚构复响应。
- 显式H为零仍能计算绝对误差；仅参考频响平均能量为零时归一化误差无定义。
- 方位角用圆统计，天顶角用线性统计；方位圆合向量接近0时不宣称有平均方向。
- 原始数据标记LCS，缺天线姿态，因此世界坐标轨迹差分不能直接当局部速度。
- 不补跨帧路径身份、不把约一秒间隔直接用于完整快衰落谱、不用两算法互相一致替代物理真值。
- 零功率与无效输入保留状态；任何结果超出簇预算都失败，不截断凑数。

## 测试

从仓库根目录使用具有NumPy、pytest和原算法依赖的解释器：

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest scripts/s5_evaluation/tests -q --color=no
```

合成指标测试独立于算法；适配器的真实入口测试与批调度测试分开。依赖不满足造成的跳过须在验收记录单列，不能声称两算法均已跑通。纯离线脚本不触发后端全量；若后续修改生产共享契约，按仓库规则重新判定验证范围。
