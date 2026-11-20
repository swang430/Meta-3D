# GCM 离线轨迹实施与交付

目标：把已确认单帧转换扩展为相邻2至38帧离线轨迹。跨帧身份必须有绑定输入内容的依据，不能把功率排序当身份。用户已授权实施至交付。

架构：复用 scripts/gcm_single_frame.py::convert_frame。scripts/gcm_trajectory.py 接受真实或合成输入，同样核验实际逐径文件、最终成员表、簇导出文件及跨帧映射文件，不相信来源自述或只有哈希字符串。另读独立跨帧关联来源文件，核其绑定的完整输入及三份实际文件哈希，再逐相邻帧核两端簇编号和同帧成员与持续身份的对应；不把跨帧成员同名当证据。成员集合和局部编号可变。逐文件读取和校验SHA256，再比较每个有序帧ID、批次、方向、成员及完整模型内容。跨帧映射同时绑定完整有序帧列表和每帧内容，成员不明或不一致拒绝。输入文件的真实性仍由交付方负责，内容一致性不是物理身份认证。

技术：Python标准库；无服务、网络、仪器、驱动或设备文件生成调用。

方案取舍：不采用功率排序或时延近邻猜身份；不采用虚构-100 dB占位。按手册第14.2节固定列定义，所有帧必须填满同样槽位，持续身份保持列位置。当前未取得不同簇同槽替换的厂商语义依据，出生、消失、空槽、重新出现均拒绝。没有可信身份依据的现有真实38帧拒绝；有完整可核验材料的真实接口可用，不设synthetic-only门。

时间：保留十进制秒原始字符串。CSV按十进制半入法取整为毫秒，拒绝原始或取整后的碰撞、逆序及跨日。清单保留两套时间、间隔及输出文件哈希。不重采样、不删末帧。

手册依据：Channel Studio GCM User Guide，Revision 15.0，§13.2.1–13.2.2（第82页）、§13.2.5（第83–84页）、§14.2（第87–88页）、§14.2.3（第89–91页）：CLUSTER相邻至少0.3m，多点总长至少25波长，原时间在最终厂商模型中可能被调整；每链路每时刻一行、生命周期内固定顺序、LOS编号0、NLOS最多24。取两个载频的较长波长是本工具保守计算策略。表4-2的原点与链路距离须小于100000m；不将通用编辑器1m误用于CLUSTER导入，不套用PATH的30m上限。§22.4内部插值不构成CSV缺位语法。第13章只支持相同上下行载频的时分双工。

一份输入只表达一条链路一个来源方向，同时声明DL/UL载频；不混合独立方向，不宣称复现两个方向。

验收关系：CLI/convert_trajectory → 实际文件内容和SHA256/逐帧完整身份映射 → 同源单帧转换与固定槽CSV → 2帧/38帧、功率互换、非均匀时间、0.299m拒绝/0.73m通过、出生消失/未知/未绑定真实输入拒绝。CSV及清单均离线，不等于厂商软件已导入或仪器已播放。

步骤：先写失败测试；实现离线脚本及合成材料；跑正反例、核心变异及CLI端到端；单帧先合并后同步origin/main；独立内审与GitHub两轮外审核HEAD；合并PR后核远端SHA，协调方同步本地主main，本工作树再跑合并版离线端到端。不得推送main。

影响面：独立脚本及材料，不改变生产服务、后端共享行为或界面；后端全量和GUI构建不适用，需跑全部新增脚本测试和单帧相关回归。内审按全套检查新证据契约，复用有效测试结果。

协作消息：/tmp/gcm-s5-trajectory-status.md；单帧接口：/tmp/gcm-s5-single-interface.md。

## 本地验证记录（单帧合并前）

全部文件均为本次离线实现的历史证据，不是硬件验收。命令 `PYTHONPATH=/Users/Simon/Tools/MIMO-gcm-frame/scripts python3 -m unittest discover -s scripts/tests -p test_gcm_trajectory.py`，结果17项、OK，见[输出](../evidence/2026-11-20-gcm-trajectory/green.log)。临时使用只读的单帧工作树，交付前必须同步已合并依赖后无额外PYTHONPATH复验。未连接应用或仪器。

[先红记录](../evidence/2026-11-20-gcm-trajectory/red.log)；[三个核心变异](../evidence/2026-11-20-gcm-trajectory/mutations.log)在临时副本执行，分别去掉文件字节哈希、生灭拒绝和毫秒碰撞判据，各自引起行为失败；工作树源文件不变。首次内审的两条功能发现和修复复审见[内审R1](../evidence/2026-11-20-gcm-trajectory/internal-r1.md)、[内审R2](../evidence/2026-11-20-gcm-trajectory/internal-r2.md)。R2核到的源文件SHA256为5054ccb000403a2024098b854ca68624c32869d94c020fa9e077222eb2b82dd7；随后只增加负例和文档，源码未变。

实际原件复核命令：`/Users/Simon/Tools/MIMO-First/api-service/.venv/bin/python scripts/inspect_mpdb.py /Users/Simon/.codex/artifacts/2026-11-11-s5-mpdb/original.zip --output /tmp/gcm-trajectory-real-inspection.json --speed-m-s 5 --coordinate-units metres`。输出上下行各38帧，原件SHA256为6cada6a493b04bbf05725ffdeaac61956e382a18897fad5c3efce94113a0037d。按下行RX位置、上行TX位置逐段Euclidean复算：总长180.8746968837547m，最短及末段0.72956886766057m，最大5.111417556779601m；满足0.3m和2400MHz下25波长要求。36.17493937675094秒是按已确认5m/s和米坐标推导，并非源文件实测时间。

对已有真实交换文件分别执行 `python3 scripts/gcm_trajectory.py /tmp/meta-s5-real-trajectory/downlink.json /tmp/gcm-trajectory-real-rejected-downlink` 及上行对应命令，均退出2、不创建输出目录。它们自述身份为frame-local-only，尚无本工具要求的同批成员与跨帧身份材料，且不是本接口格式；本次没有伪造转换为新格式再宣称真实验收通过。独立列出[原件距离与真实输入拒绝记录](../evidence/2026-11-20-gcm-trajectory/real-input-check.json)。坐标通过与身份不足是两件事。

真实来源分支的成功用例仅为构造完整材料的接口测试，不代表本批真实38帧已取得身份、姿态或正式播放证据。厂商导入与设备播放仍待独立验收。


## 用户审读草稿后的修正

用户指出，同一持续簇的局部逐径编号和成员集合可以跨帧变化，不能强制相同成员ID。因此删除跨帧成员集合相等的错误限制；每帧仍绑定自身实际成员表。另要求独立来源的跨帧关联文件，逐间隔核其两端局部编号、同帧成员、持续编号及实际输入哈希，不从同名成员推身份。补充成员、逐径编号和局部簇编号均变化的持续身份正例；同名但缺关联来源、关联文件哈希正确而对应不符的负例。完整格式见 scripts/gcm_trajectory.md。

本次修正的[先红](../evidence/2026-11-20-gcm-trajectory/association-red.log)、[20项通过](../evidence/2026-11-20-gcm-trajectory/association-green.log)、[三个变异](../evidence/2026-11-20-gcm-trajectory/association-mutations.log)单独保存，不覆盖上一阶段历史结果。当前核心变异为实际文件哈希、独立关联对应及取整碰撞；在临时副本执行，未改工作树源文件。

该增量已获[独立内审CLEAN](../evidence/2026-11-20-gcm-trajectory/internal-associations.md)，源码SHA256为7c991108961e71d310bdd2b75550438133f087066beac4b99f8affc3693f122c。独立定点还核验构造真实来源分支在成员变化后保留持续身份、缺关联拒绝，未将此称为实测验收。

## 已合并依赖版本的交付前验证

单帧#598已先合并，正式依赖origin/main为8d83386b0b5bb38d221ec1299812679cd8c51235。轨迹树合入该版本后，在5faf3470ecd45ee13b7a80980038625e670d5e2e上运行 `python3 -B -m unittest discover -s scripts/tests -p 'test_gcm*.py'`，33项全部通过（单帧13+轨迹20），没有额外PYTHONPATH或外部工作树源码。随后仅增加本段及验证输出，测试源码、模型、配置及依赖内容未变化，结果可复用。

[33项输出](../evidence/2026-11-20-gcm-trajectory/formal-dependency-tests.log)；[正式依赖下的三个核心变异](../evidence/2026-11-20-gcm-trajectory/formal-dependency-mutations.log)均在临时副本检出，复制本工作树单帧版本，不访问其他工作树。CLI命令 `python3 -B scripts/gcm_trajectory.py scripts/fixtures/gcm_trajectory/input.json /tmp/gcm-trajectory-formal-e2e` 生成38行36列，末帧00:00:37.018；独立CSV读取校验全部行持续ID、列数及文件SHA256，清单保持synthetic、formal_eligible=false、hardware_called=false。代码/依赖/输入/CSV哈希见[端到端摘要](../evidence/2026-11-20-gcm-trajectory/formal-dependency-e2e.json)。这仍是合成材料验证，不是厂商导入或设备播放。

## R1期间作者补查的内容类型修复

R1审查c42b8c1f时，作者定点发现实际来源中的布尔值true会被Python容器相等当成整数1，导致实际簇导出BSID=true而输出BSID=1仍被接受。同根两处是实际源帧索引true/1、独立关联持续ID true/1。实际文件哈希正确并不能补救这个内容比较错误。先补三种可观察负例，[旧实现三失败](../evidence/2026-11-20-gcm-trajectory/content-types-red.log)。修复把三份材料及独立关联对应比较换为既有规范JSON指纹比较，实际源帧索引要求整数；不新增机制。

[34项集成通过](../evidence/2026-11-20-gcm-trajectory/content-types-green.log)（单帧13+轨迹21），[四项核心变异](../evidence/2026-11-20-gcm-trajectory/content-types-mutations.log)在临时副本检出。内容类型变异同时恢复5处原逻辑，三种负例重新失败。测试、样本和依赖未另作改动；未知拒绝路径没有放宽。

外审R1回执已核对 reviewed commit=c42b8c1f5a、无重大问题，见 https://github.com/swang430/Meta-3D/pull/596#issuecomment-7043850063 。该回执仅签修复前版本；作者修复提交必须再由R2覆盖，不能以旧R1结论或内审替代。

该内容类型修复已获[独立内审CLEAN](../evidence/2026-11-20-gcm-trajectory/internal-content-types.md)，源码SHA256为a5355707435927ec554ec1ec1526c328f66425e5b884f0e7891311ea2502330f。额外独立定点核对实际向量false/0、成员表整数/浮点、独立关联局部编号整数/浮点，均拒绝。用户另外要求同步既有P2-16 S5补充一行，保留#595的RT-IMT-2030主线不动，随修复提交共同外审。

用户提供的S5路线图一行同步已获[独立文档内审CLEAN](../evidence/2026-11-20-gcm-trajectory/internal-roadmap.md)，核实三份链接、合成38帧证据与真实缺项界线；#595三项主线未修改。本轮代码、测试、说明和该行将由同一最新HEAD外审覆盖。
