# S5c逐帧离线评估

仅用于研究，不连接仪器、不调用正式执行、不生成通过判词。设计见
[实施设计](../../docs/plans/2026-11-14-s5c-evaluation-design.md)。

2026-11-14后续路线改为Lauraycs内置聚簇结果导出，再由接收端读取；CE独立聚簇不再是接入前置。
见[新设计](../../docs/plans/2026-11-14-s5c-native-cluster-design.md)。下方旧双算法工具继续保留为研究工具。

## 读取Lauraycs聚簇轨迹

```sh
python scripts/s5_evaluation/cluster_import.py /absolute/path/to/cluster-trajectory.json
```

读取`lauraycs-cluster-trajectory/1`，校验完整时间轴、复H、单位、预算和来源字段，
保留空帧与未知多普勒，不调用HyperRT或CE聚簇。成功只表示文件结构有效，
输出明确`hardwareEligible=false`；不将聚簇结果改装成原始射线。
原样本原生计算、资产保存、完整非均匀OTA轨迹合成和设备播放尚不能由此命令证明。

可加`--frequency-offsets-hz 0 1000000 5000000`，按明确的频率偏移网格重建每个原始时刻的模型频响。
计算使用复H与ns换算后的时延，不在帧间插值、不要求跨帧簇身份，也不重新聚簇。
无路径和全部过滤帧保持不可评价，不把缺失变成测得零响应；计算结果不代表实测宽带真值。

输入必须是S5a输出的`s5-raw-paths/1`和相同原ZIP。两个方向全部帧分别评价8/16/24个簇上限，保留原始非均匀时刻。
`--candidate-units`显式采用候选秒、度、Hz，仅作条件性研究，不把单位来源变成已验证。
频率偏移网格必须显式填写；它是单频射线模型的数学诊断，不是实测宽带准确性证明。

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
