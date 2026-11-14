# S5c离线工具与首次运行记录

日期：2026-11-14。**S5c评估未完成，不能选择正式接入路线。** 本片交付可复算工具、合成验证和真实阻塞记录；没有原样本的成功聚簇误差曲线。

## 输入与版本

- 原ZIP SHA256：`6cada6a493b04bbf05725ffdeaac61956e382a18897fad5c3efce94113a0037d`。
- S5a适配JSON SHA256：`bba63f0ca0b4450070c8e904bb14b04b88cb2ac932492690c80853403d61a919`。
- ChannelEgine `1ba1130d5ff3ea9de7f992273b3fd72145aed2ed`；Lauraycs `53ea4cf97842d8e9c18d97e07d081b2b98fbc316`，正常导入现有函数，未复制算法、未修改两个外部仓库。
- 上下行各38帧、三个簇上限8/16/24，每算法228项。原时间轴保留，总跨度36.17493937675094秒；候选秒/度/Hz解释明确标记，不据此确认原始单位来源。
- 复频响诊断网格为−5、−2.5、0、2.5、5MHz；这是显式研究参数，不代表实测带宽或设备设置。因实际算法未成功，该网格没有产生原样本误差结论。

## 原样本实际结果

| 路线 | 结果 | 原因及解除条件 |
|---|---|---|
| ChannelEgine | 228项blocked；未调用原样本聚簇 | 两向`source_document.meta.lauraycsPlatform.angleCoordinateSystem`明确为`LCS`，LINK无天线旋转信息。需要与本次生成记录一致的姿态/坐标变换及运动端约定，不能直接使用世界坐标差分当局部速度。该速度还影响簇分裂，因此整帧不可评价 |
| Lauraycs | 228项failed；均在正常原生包导入阶段失败 | `HyperRT/CG.py:22`报`NameError: name 'AbstractCameraF' is not defined`。需要可正常加载的官方原生绑定/运行环境；没有替换模块、修改HyperRT或绕许可证 |

两条命令均退出2，输出完整项数及错误。没有静默略过方向、帧或预算，也没有将失败置成零误差。
此次LR失败是导入错误；不能把它混同S5a原生射线测试的许可证过期，也不能宣称修好绑定后许可一定可用。
原包还缺`R0B0S0D.mpgeom`、`R0B0S0U.mpgeom`；这些附件本身是否足以补齐所有旋转证据尚未确认。

## 已验证的软件行为

- 输入校验保留帧身份、非均匀时刻、复响应实虚部和缺失多普勒；错行、重复、非有限值明确拒绝。
- 独立指标用解析构造核验：时延分布、方位圆统计、天顶角、复频响及相消。CE统计输出无相位时不补造H。
- 内审发现相消输出为零仍应可计算误差：新增红测试后删除错误提前返回。原始两径`H=1,-1`、时延`0,1μs`，输出0，偏移`0,500kHz`时绝对RMS为√2、归一化均方误差为1。
- CE已知坐标合成单径、双径合并使用真实函数通过；这不证明原始LCS数据可接入。
- LR四项真实入口测试因上述原生导入错误跳过，不能用指标单测代替LR成功实跑。
- 内审核实上层`include_doppler=True`会把当前底层`_clusterCDL`不接受的doppler参数传入。适配器已收窄为False，原始多普勒保留在输入中，聚簇输出保持未知；没有修改HyperRT。该问题与原生导入错误分别记录，不能因导入失败尚未走到此处就忽略。
- 内存逆变异：时间偷换为等间隔、丢复相位、丢阻塞行三项均被断言抓到；没有改写磁盘生产源码。
- 内审发现后续校验失败会丢算法返回结果，已先红后修：返回即保留输出，状态仍为失败；不可严格JSON编码的原始返回保留文本表示，不进入指标。

## 命令、环境与产物

调用方式见[scripts/s5_evaluation](../../scripts/s5_evaluation/README.md)。实际输入为：
`/Users/Simon/.codex/artifacts/2026-11-11-s5a/p2-final/adapted-final.json`及
`/Users/Simon/.codex/artifacts/2026-11-11-s5-mpdb/original.zip`。
结果、环境版本清单、变异记录及测试日志保存在`/Users/Simon/.codex/artifacts/2026-11-14-s5c/`。
原始样本不上传仓库。输出manifest记录具体脚本校验值，旧运行不冒充后续代码结果。

CE使用现有`/Users/Simon/Tools/ChannelEgine/.venv/bin/python`。LR另建`/tmp/s5c-lr-adapter-venv`，Python3.12.11；没有修改用户现有环境。安装后正常调用仍失败，详细依赖以`lr-environment.txt`为准（包括torch2.3.1、NumPy2.4.3、pytest9.2.0）。

最终离线测试命令（仓库根目录）：

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/s5c-lr-adapter-venv/bin/python -m pytest scripts/s5_evaluation/tests -q -rs --color=no
```

结果：`110 passed, 4 skipped in 5.62s`。此前107通过/4跳过是修复底层调用与补充留痕检查前的版本，不能混报同一测试集合。最终批运行在`ce-v2/`与`lr-v2/`，两者manifest源码校验值对应本片最终脚本。
本片只新增离线脚本、测试和说明；正式resolver、计算服务、报告、仪器驱动均未改变，不跑后端全量。
暂存新文件后复跑`tests/test_rule_gates.py`：68通过、2失败，8.44秒；G8/G11命中仍为S5a/b已核实的旧文档路由，日志`doc-gates-final.log`保留。独立内审最终无新增实质缺陷。

## 下一步

补齐与该数据相匹配的坐标/姿态依据及可正常运行的Lauraycs原生环境后，用同一工具重跑全部帧与预算，再讨论误差曲线和用途容限。S5c正式接入、S6单位及设备验收保持未完成；本片没有任何正式信道或硬件验收结论。
