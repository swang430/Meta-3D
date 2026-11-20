# 有来源依据的 GCM 离线轨迹

本工具把同一链路、同一来源方向的相邻2至38帧转为 GCM CLUSTER CSV。它会读取实际材料并核对内容，拒绝未知身份、来源不一致及尚未确认的簇出生消失表示。真实来源和合成来源使用同样的核验过程。工具不连接服务或仪器，不生成设备可播放工程，不授予正式测试资格。

运行示例（输出目录必须不存在）：

```sh
python3 scripts/gcm_trajectory.py scripts/fixtures/gcm_trajectory/input.json /tmp/gcm-trajectory-example
python3 -m unittest discover -s scripts/tests -p 'test_gcm_trajectory.py'
```

输出目录有 `trajectory.csv` 和 `evidence.json`。清单保留所有输入文件哈希、身份映射、原始十进制秒、CSV毫秒时间、间隔及CSV哈希。合成标签会留在CSV的INFO列和清单。清单 `formal_eligible=false`；即使输入为真实来源，文件之间一致也不能证明测量真实、厂商导入成功或硬件验收通过。

## 输入材料

完整示例位于 [fixtures/gcm_trajectory/input.json](fixtures/gcm_trajectory/input.json)。它包含38帧构造数据、两簇功率互换及0.73米相邻位置。第二帧改变输入簇排序，持续身份和输出槽位仍保持稳定。这是测试材料，不是实际轨迹成果。

顶层 `schema=gcm-trajectory/1`，`provenance=real|synthetic`，明确 `batch_id` 和 `direction=downlink|uplink`。`frames` 为连续有序列表，每项有非空唯一 `frame_id`、连续整数 `frame_index`、十进制秒字符串 `time_seconds` 和单帧接口格式 `model`。`model` 的结构见 [gcm_single_frame.md](gcm_single_frame.md)。工具只在完整核验材料后调用单帧 `_convert` 做真实来源数值计算；绝不把真实输入改标为合成。

`inputs` 必须提供以下三份实际JSON文件，每份以 `{path,sha256}` 引用，路径相对于输入JSON目录（也接受绝对路径），SHA256按文件原始字节计算。每个材料顶层都含相同的 `batch_id`、`direction` 和覆盖全部帧的有序 `frames`。每帧含相同 `frame_id`：

- `raw_paths`：每帧 `paths` 与模型原始逐径列表完全相同，`time_seconds` 与 `frame_index` 是可核对的原始时序，必须与输入帧一致。模型 `common.TIMESTAMP` 必须等于原始秒的毫秒半入结果，矛盾不能覆盖。
- `final_membership`：每帧 `clusters=[{id,members}]` 与模型最终成员表完全相同。
- `cluster_export`：每帧 `model={common,clusters,propagation,directions,rotations}` 与输入完整模型这些字段完全相同，包含簇功率、绝对时延、方向含义与姿态矩阵。

单帧 `model.source` 的三条来源路径必须和以上实际读取路径相同；类型、批次和方向也必须匹配。实际材料比较同时保留JSON数值类型，布尔值true不能代替编号1。只给文件名或填“已确认”不能通过。

`identity_evidence` 以同样的 `{path,sha256}` 引用独立跨帧映射JSON，格式为 `schema=gcm-identity/1`，包含相同批次、方向和完整有序帧列表的 `frames_sha256`。每帧有 `frame_id`、`frame_sha256` 和 `mapping`。哈希函数为脚本导出的 `frames_sha256`：规范JSON排序键、不含空白、UTF-8、不允许NaN。整体哈希覆盖输入文档的整个 `frames` 列表；单帧哈希覆盖完整帧对象。

每项映射为 `{local_id,track_id,slot,member_ids}`：局部簇编号、跨帧持续编号、从0开始的固定列槽位、按字符串排序的最终成员ID。所有簇必须一一对应。每帧成员必须和同帧最终成员表一致，跨帧局部逐径ID、局部簇编号和成员集合可以变化；持续身份来自下述独立关联文件，槽位不得变化。本工具不会从同名成员、功率、时延或局部序号推断持续身份。

`association_evidence` 另以 `{path,sha256}` 引用实际关联来源文件，不能复用输出映射文件自身。它不是工具按照同名成员生成的推断，须由数据交付方独立提供。格式为 `schema=gcm-associations/1`，含同批 `batch_id`、`direction`、完整 `frames_sha256`、三份实际文件的 `input_sha256={raw_paths,final_membership,cluster_export}`，以及 `producer={name,version,method}` 说明产生方、版本和方法。没有该文件，即使所有帧成员同名，也会拒绝。

关联文件 `links` 必须覆盖全部相邻帧间隔，各项 `from_frame_id`、`to_frame_id` 和按持续ID排序的 `pairs`。每对为 `{track_id,from_local_id,to_local_id,from_member_ids,to_member_ids}`，明确关联两端的局部簇及各自同帧成员。实际关联必须与输出映射逐项相符；允许两端成员和编号不同，不允许拿输出映射自身代替关联来源。文件存在和内容一致仍不等于关联算法已经过物理验证，正式资格不因此放行。

## 表达范围与限制

手册依据：Channel Studio GCM User Guide Revision 15.0，第13章、第13.2.1–13.2.2节、第13.2.5节、第14.2节、第14.2.3节及表4-2。

- CLUSTER只接受上下行载频相同的时分双工；一个时刻一条链路一行，同时声明两个载频不表示复现了两套独立方向。每份输入只有一个明确来源方向，不能把独立上下行簇拼在一起。
- 不按功率、时延排序猜跨帧身份。直射身份始终0；非直射身份非0，生命周期内槽位不变。所有行使用相同列数。不确定的空槽、生灭及不同身份同槽替换均拒绝；第22.4节内部插值的−100 dB不是CSV缺位语法。
- CLUSTER相邻位置至少0.3米，多点总路长至少25波长。两频率取较长波长作为保守检查；当前还要求时分双工两者相等。不把通用编辑器1米或PATH导入30米上限套到CLUSTER，不做降采样或删除末帧。
- 保留原始非均匀时间，以十进制半入取整为CSV毫秒，拒绝原始或取整后的碰撞和逆序、跨日。第13.2.2节说明厂商最终模型可能调整时间，因此CSV时间不构成实际播放时间保证。
- 目前只接受固定基站、完整全局直角坐标以及单帧接口能处理的方向和成员；未知姿态、身份或成员不补零。未达到这些条件的真实38帧会明确拒绝，保留原件另行补证据。
