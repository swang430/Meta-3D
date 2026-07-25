# 2026-07-21 现场调试总结 + 待办清单(用户已 review)

> 本文只记**当天亲眼观察到的事实**和**由事实直接推出的修改**。
>
> **2026-07-21 用户逐项 review 完成**:标 **[用户 review]** 的项有补充意见、已并入正文;
> 其余项(P0-1 / P1-1 / P1-2 / P1-3 / P2-1 / P2-2)用户**明确同意、无补充**——**不是删除,照做**。

## 一、当天实际发生了什么(诚实综述)

- **目标**:重跑一条干净的测试链(UXM 配频点功率 → F64 load .smu → 调输入参考/峰均比 →
  设输出 → DUT attach → 启动信道播放),在此基础上做可重复性 + 降功率实验。
- **实际结果**:全天消耗在**恢复 F64/UXM 会话 + 排障**上。加了 6 个 F64 控制端点;
  F64 PropSim 被操作搞**卡死一次**(现场重启 PropSim 才恢复);UXM 配置在后端重启后**变
  成错误默认值**被排查出来。**本轮没有拿到新的吞吐/attach 数据**——问题是暴露 + 部分修复
  了一批驱动/流程缺陷。

## 二、需要的修改(Todo,按优先级)

### P0 — 阻断下次现场,必须先修

- [x] **P0-1 F64/UXM 驱动加"断线自动重连"(懒重连)** ✅ 已完成(查实)
  - 事实:F64 PropSim 重启后,后端连不上(VISA 会话失效);长脚本被系统杀掉(SIGTERM)后
    VISA 会话被搞坏;每次都要人工调 `hal/switch` 重连。**这是当天最大的时间杀手**。
  - ✅ **2026-07-23 查实早已完成**:commit `0a3df3f`(2026-05-14,比现场早两个月)把懒重连
    推广到全 4 个 PyVISA 驱动(F64/FS16/UXM/ENA)且**下沉到底层 IO** —— F64
    `_do_write_unlocked`/`_do_query_unlocked` + UXM `_do_write`/`_do_query` 对 conn-lost
    (`VI_ERROR_CONN_LOST`/`INV_OBJECT`,共享分类器 `_visa_reconnect`)自动重连重试,全 SCPI
    命令覆盖、对上层无感,正确区分 conn-lost(重连) vs 超时(排水不重连)。测试
    `test_f64_visa_reconnect.py` + `test_fs16_uxm_ena_visa_reconnect.py`。
  - **教训**:todo 原"F64/UXM 没有"是现场收工凭旧印象写的过时事实,没查 git/代码 → 现场白
    手动重连。见 memory `feedback_check_verifiable_state_yourself`(2026-07-23 实例)。
  - **⚠ 遗留缺口**(F64 review 发现,挪 F64R-1):懒重连只覆盖 socket 断,业务层挂死(反复 GO
    搞卡)/进程重启不在覆盖内 —— 需 `DIAG:SIMU:STATE?` 检测 + 排水失败升级 reconnect。

- [ ] **P0-2 测试流程必须显式下发 + 读回验证 UXM 完整配置(不假设保留)**
  - 事实:后端重启后,UXM 变成 `ARFCN 623334 / BW100 / DL:POWer -50`(错误默认),
    **不是**工作点 `636666 / BW40 / -46`。我错误假设配置保留、只激活小区,导致小区起不来
    (`ACTive=1` 但 `STATus=OFF`)。
  - 改:流程强制 `OFF → 下发 band/arfcn/dl:bw/ul:bw/dl:power/ssb → ON → 读回逐项验证`;
    建议加一个 UXM 配置端点封装这套顺序(含改配置前必须 OFF、激活后等小区起来)。
  - **[用户 review]** 泛化到**所有参与测试的仪表**(UXM/F64/…),不止 UXM:每个测试项开跑时,
    仪表都要从**通用测试参数**主动取值并配置到位,来源 = **测试参数 / 手机配置 / SIM 卡配置**,
    **绝不靠仪表继承来的旧值**。这是"仪表配置单一真值源"原则,是本项的本质。

- [x] **P0-3 ✅ 完成 (#223, 2026-07-23) — F64 软件加载 .smu 前置序列重写 + 状态机收敛**
  - **实际落地**:从"缩范围 load 序列 + 频率回读"经 6 轮 Codex + 多轮 pre-commit 评审,滚成 F64
    加载状态机大修(GCM/ASC/B-2 **三路**)。两大母题各收敛到**单一入口**:**CLOSE 确认卸载**
    (`_close_and_read_state` = CLOSE+`*OPC?`+`STATE?` 回读,治盲发-CLOSE-硬闯-FILE 的现场超时)
    + **状态复位**(`_apply_unload`/`_apply_session_reset`)。关键洞察:`STOPPED`=仍加载(暂停)
    ≠ `CLOSED`=已卸载 → close≠CLOSED 保留 identity 不硬闯 FILE;`running` 按手册"RUNNING=发射,
    其余不发射"语义置(NotebookLM 手册穷尽验证全 7 状态);频率从 `CALC:FILT:CENT:CH?` 回读
    (治 `3600M.smu` 实为 3550);pipeline 全 load 路 success-only 对称。+40 回归,全量 2360 passed。
  - **注**:P0-3 缩范围原本只切 GCM 路,评审中发现 ASC/B-2 有**同一个**"盲发 CLOSE + 硬闯 FILE"
    bug(正是 P0-3 要治的根因),用户 2026-07-23 拍板本 PR 内三路全治。下面原实现要点保留作历史。
  - 事实:旧 `load_local_scenario`(**P2-1 已从代码移除**)开头发的 `DIAG:SIMU:CLOSE` 在
    F64 干净/某态被拒(`wrong device state`)→ 后面 `CALC:FILT:FILE` 拿不到 `*OPC?` →
    `VI_ERROR_TMO` 超时。软件 load .smu **从没成功过**,当天全靠操作员在 F64 界面手动 load。
  - 改:对照 F64 手册(库里已有 `Instrument_API_Doc/Keysight PromSim F64`)确认加载 .smu
    的正确前置 SCPI 序列,**从零重新实现** `load_local_scenario` + `/load-scenario` 端点
    (CLOSE 容错 / 换正确前置 / 判是否需要先进某模式)。**重写 checklist**:加载成功后
    必须同步 4 类缓存(Codex 在 P2-1 旧实现上逐条挑出过)——① `_loaded_emulation_file`
    文件名、② `_center_freq_programmed` 复位(新 .smu 频率由文件定)、③ 默认文件同步
    MIMO 拓扑 `_tx/_rx_antennas`、④ `_emulation_running`(未 GO 前不能谎报在播);
    对照 `set_channel_model` 的加载副作用做域枚举,别再补一条漏一条。
  - **[用户 review]** 以往是通过**文件共享方式**调用这些配置文件的。修之前必须**复合以前的
    现场测试经验**(git log / 旧现场文档里 .smu 到底怎么被引用和加载)**+ F64 手册**一起确认
    调用方式对不对,不能只凭手册闭门造。

- [ ] **P0-4 F64 大幅输出功率调整改用"整体输出"命令(逐口 loss/gain 范围不够)**
  - 事实:`OUTP:LOSS:SET` / `OUTP:GAIN:CH` 是**逐口精细补偿**,有 per-port 范围上限——
    同一个 `loss=-40`,口 3/4 生效、口 1/2 卡住不动,并报 `-200 Parameter exceeds set
    limits`;想把衰落态输出从本底 -105 提到工作电平 -35(差 ~70dB)**根本补不动**。
  - 事实:当天早上能把 F64 输出调到工作点,靠的是 **F64 面板的整体输出功率/衰减旋钮**,
    不是逐口 loss/gain。
  - 改:对照 F64 手册找**整体输出功率/衰减**的 SCPI 命令,软件用它做大幅调整;逐口
    loss/gain 只留作小范围 per-probe 校准补偿。文档写清两者分工。
  - **[用户 review]** 功率调整要具备**三种方式**:①逐端口调整(per-port);②**归一化总功率
    调整**(总功率再分到各探头);③数字功率调整。**正常测试只调归一化总功率**,不直接管每个
    端口。今天逐端口抬 3/10dB **只是为了看到效果、不是精确测量**;正式测量走归一化功率。
  - **★ 2026-07-23 F64 review 补充**:手册答案已成型(见 review 文档 P0-4 节)——绝对电平
    `OUTP:LEV:AMP:CH <口>,<dBm>`(不受 -45~0 增益钳位)做主力 + `SYST:MAXOUTGain:SET` 抬顶;
    归一化总功率 = 循环逐口绝对电平(口数用真实物理输出口,见 F64R-2,不是 tx×rx)。

---

### ⭐ 2026-07-23 F64 驱动全量 review 回填(用户同意)

> NotebookLM 对照审完整 F64 驱动,29 问题 7 母题,主线「该问仪器的地方在猜」。权威详录:
> [`architecture/f64-driver-scpi-review-20260723.md`](../architecture/f64-driver-scpi-review-20260723.md)。
> **P0-3 的 load 序列、P0-4 的输出方案手册答案都在里面,直接可落。P0-3 已完成(#223,
> 且顺带把状态复位 + CLOSE 确认卸载收敛到单一入口);F64R-2 已完成(端口/通道从拓扑回读)。
> 下一个 F64 大项 = F64R-1(`STATE?` 全接入,P0-3 已落地加载路,余 GO/GOS/get_metrics/bypass)。**

- [ ] **F64R-1 F64 接入 `DIAG:SIMU:STATE?` 作运行状态真值源** (新 P0 大项,**P0-3(#223)已部分落地**)
  - **P0-3 部分落地**:加载路(GCM/ASC/B-2)已接 `DIAG:SIMU:STATE?` —— CLOSE 确认卸载
    (`_close_and_read_state` 判 `==CLOSED`)+ close≠CLOSED 的 running 真值(按手册"RUNNING=发射"
    语义置)。**剩余**:GO/GOS 前查 `STATE?` 消歧、`get_metrics` 读缓存谎报在跑、bypass 进出漂移、
    超时挂死不自动恢复 —— 这些仍未接。
  - 全驱动原**零调用** `DIAG:SIMU:STATE?`(手册唯一运行状态真值源),状态全靠本地布尔 + 猜 -200
    错误文字。**含 P2-1(#221) 刚 merge 的 GO 豁免——方向对(回读消歧)但信号选错**(用
    `STATIC?==0`,该 `STATE?==RUNNING`;STATIC? 只报旁路档不报运行态)。
  - 改:GO/GOS/CLOSE 前查 `STATE?` 消歧,一次解决 GO 假报启动 / get_metrics 读缓存谎报在跑 /
    bypass 进出 `_emulation_running` 漂移 / 超时挂死不自动恢复(排水失败升级
    `_silent_reconnect_visa`,= P0-1 遗留的业务挂死盲区)。详见 review 母题①。跟 P1-2 合并考虑。

- [x] **F64R-2 F64 端口/通道数从拓扑回读,别用 tx×rx / 整机 64 猜** ✅ **已完成**(本项 PR)
  - `tx×rx` 是**逻辑衰落通道数,不是物理输出口数**(手册 3.1)。`set_path_loss`/`get_metrics`
    输出口用 `tx×rx` → 默认 3600M 32 探头按 16 配、**路损只设一半 17-32 留工程默认**;
    `set_baseband_power` 输入口 / CENT / doppler 循环全用错口径。
  - **已落地**:`_readback_topology()` 在三条加载路(GCM/ASC/B-2)成功后回读
    `MODEL:INFO?`(口数)+ `GROUP:GET?`/`GROUP:CHANNELS:GET?`(组与代表通道)+
    **`GROUP:INPUTS:GET?`/`GROUP:OUTPUTS:GET?`(真实端口号)**,读写共用,替掉所有
    `_tx_antennas`/`tx×rx`/`_channel_count` 推断。详见 review 母题②。
  - **口数不够、还要端口号**:数量 N 不保证端口号是 1..N(仿真可能占非连续口如 {2,4}),
    照 1..N 发会误配一个漏配一个 —— 端口号也回读,并与口数交叉校验。
  - **CENT 改 per-group**:同组判定是"输入相同**或**输出相同"(§20.4.6.4/6),组数
    **不可推算**(全交叉拓扑可能只有 1 组),按 `GROUP:GET?` 回读值逐组发。
  - 拓扑未知(未加载/回读失败)时:**写**操作 fail-loud 拒绝(不回退猜),**读**
    (`get_metrics`)降级跳过并在 `query_errors` 标注。
  - **冷缓存不做硬门**:后端重启后驱动缓存空、但 F64 硬件仍加载着仿真在播(2026-07-21
    实证)。此时**先查 `STATE?`,非 CLOSED 就按需补回读一次**,仍读不到才拒 —— 否则唯一
    恢复途径是重新 load,而 load 第一步 CLOSE **会打断正在跑的仿真和 UE attach**。
  - **⚠ 现场兜底开关 `topology_override`**:`GROUP:*` / `MODEL:INFO?` 这几条**尚未在真机
    验证**,而本项目实证过"手册里有、这台机器回 -100"(MMEM/FTP/`*OPT?`)。若真机不支持,
    在仪器 `connection_params` 里配:
    ```json
    {"topology_override": {"inputs": [1,2], "outputs": [1,2,3,4],
                           "channels": [1,2,3,4,5,6,7,8]}}
    ```
    (端口/通道**号**列表,不是数量;三者必须齐全,否则整体作废并打 ERROR)。
    **回读到的真值永远优先**,声明值只在回读失败时生效并打 WARNING。
    → **下次现场第一件事**:确认这 5 条命令在真机上是否可用,可用就别配这个开关。
  - **范围界定(2026-07-24 用户拍板 A)**:本项**只解决"配几个口"(口数从拓扑回读),不解决
    "配什么值"**。修完的真实效果 = 现有那个**手填的统一**增益/损耗从"只落到前 16 个探头"
    变成"落到全部真实输出口"。**逐探头校准值的下发是独立一件事,单列 F64R-5**(本项是它
    的前提:先有真实口数,才谈得上把 N 个校准值对到 N 个口)。

- [ ] **F64R-5 校准值下发通路缺失 —— per-probe 路损从没进过 F64** (2026-07-24 用户 review
      F64R-2 设计时发现;**先查补偿层次再设计**,依赖 F64R-2)
  - 事实:**校准数据是有的** —— `path_loss_calibration_service.py:296-378` 按 `probe_id × 极化`
    逐个实测,存 `probe_path_losses`。
  - 事实:**F64 驱动也有逐口下发能力** —— `propsim_f64.py:1817 set_output_path_loss(output_num,
    loss_db)`(P2-10 建的"HAL 能力先行"),注释自己写着"真实暗室每个 probe 路损不同(校准
    per-probe 出值)"。
  - 事实:**两者从没接上** —— `set_output_path_loss` 与 batch 版 `set_path_loss` 在生产代码里
    **零调用方**(全仓 grep 只有定义/注释/单测)。唯一真往 F64 输出口写值的是
    `measure.py:745-770` 的 `f64_output_gain_db`:操作员**手填的一个标量**,给所有口写同一个值。
  - **⚠ 先决问题(动手前必须查清,否则会补两遍)**:射频校准按既有结论是走 **1/H_sys 后处理
    预失真、乘在 I/Q 上、烘进 .asc**(memory `project_ota_probe_baseband_rf_two_layer`)。若
    校准已在 .asc 里补过,再在 F64 `OUTP:LOSS` 补一次 = **重复补偿**。要先查 ChannelEgine 侧
    烘焙到底补没补,定死"补偿在哪一层做",再谈接线。
  - **待定维度**:校准是 32 探头 × 双极化 = 64 个值,F64 是 32 个物理输出口,映射关系待定。
  - 另需定:校准证书选取口径(哪个 lab / 哪个频点 / 有效期)。

- [ ] **F64R-6 F64R-2 代码收敛残余**(纯代码,不依赖真机;2026-07-24 F64R-2 收口时转出)
  > F64R-2 经 7 轮 pre-commit 复审收敛(11/10/11/8/9/10/9 条),P1 已清零、P2 已全修。
  > 以下是**明确判定不阻塞合并**的残余,统一在后续 PR 里收:
  - **推导做硬拒的另一处**:`min(inputs,outputs)` 已从硬拒降级为 WARNING(推导≠仪器契约),
    但紧接着的 **union-size 交叉校验**(`len(in_ports)==_active_inputs` 等)依赖**同一条推导**,
    仍是硬拒。真机若组语义非路由连通分量,症状还是"命令全支持却什么都配不上",只是换了道门。
    → 保留硬拒但文案写明"可用 topology_override 兜底";真机验证后再定是否降级。
  - **合理性上界口径不齐**:`_TOPOLOGY_SANITY_MAX` 只约束三个**口数**,端口号/通道号本身不受约束
    (会话错位回 `"1e20"` 且恰好口数=1 时,能下发 `OUTP:LOSS:SET 1e20,...`;后果有界——仪器拒 →
    gated write fail-loud,不挂死)。
  - **`_topology_fields()` AST 抽取的盲区**:只处理 `ast.Assign`,漏 `AnnAssign` / 元组解包 /
    委托式实现;且清单从 `_clear_topology` **自身**派生 → "新字段写进了回读却忘了加进 clear"
    仍然全绿(正是它要防的母题)。→ 改成抽 `_readback_topology_from_instrument` +
    `_apply_topology_override` 的写入字段,断言 ⊆ `_clear_topology`。
  - **`topology_source` 覆盖不全**:`unknown` 态与 `get_channel_state` 侧零断言;
    该字段把"口数来源"和"口号来源"混成一个(回读到口数、只有口号是声明值时报 `declared`)
    → 考虑拆 counts/ports 两个来源字段。
  - **端点入参校验与回读侧不对称**:回读侧严格拦非正整数端口号,而 `InputReferenceRequest` /
    `OutputGainRequest` / `CrestFactorRequest` 接受 `[0]` / `[-3]` 照发(只能靠仪器拒)。
    → 加 `Field(ge=1)`。⚠ 注意 `set_input_measurement_mode` 语义里 `<in>=0` 是"全部输入",
    所以 `ge=1` 不是纯风格问题,改前先确认各端点语义。
  - **`/input-reference` 缺 `min_length=1`**:显式 `[]` 被当成"没给"→ 用回读口号写全部口,
    与"我明确说了一个口都不写"相反;两个兄弟端点(`/crest-factor`、`/output-gain`)都会 422。
  - `OutputGainRequest.ports` 注释仍写 "(1..16)",与 32 探头矛盾。

- [ ] **F64R-8 ⚠ `pyvisa.ResourceManager('@py')` 是单例 —— 一个驱动 disconnect 会关掉
      其它驱动的会话** (2026-07-25 F64R-1 复审实测发现的**既有**地雷,非本次引入)
  > 实测: `ResourceManager('@py')` 两次取到同一个对象;其 `close()` 源码是
  > `for resource in self._created_resources: resource.close()`,官方 docstring 明写
  > "will also terminate connections obtained from other ResourceManager instances"。
  > 而 `propsim_f64.py` / `propsim_fs16.py` / `rs_fsva.py` / `rf_switch.py` **四个驱动
  > 都用 `'@py'`** → **F64 断开会把 FS16 / 频谱仪 / 射频开关的会话一并关掉**。
  - 现场表现推测:HAL 重载或单个仪表重连后,别的仪表"莫名其妙断了"。F64R-1 之后这些
    被误关的驱动至少**能自愈**了(已关句柄抛 `InvalidSession` → 归入 conn-lost → 懒重连),
    但根因还在。
  - 修法候选:各驱动持有自己的 RM 实例并只 `close()` 自己的 resource(不调 `rm.close()`);
    或全局共享一个 RM、由 HAL 生命周期统一管。**要一起改四个驱动,单独开 PR。**

- [ ] **F64R-9 `_drain_errors` 也会解冻重连冷却(小口子)** (2026-07-25 F64R-1 复审转出)
  > `_do_query_unlocked` 已加 `note_success=False` 堵住 `_drain_after_timeout`,但
  > `_drain_errors` 走外层 `self._query`(note_success 默认 True)——会话错位时它读到
  > stale 应答也算"成功"→ 解冻。影响有限:1 Hz 轮询路(`get_metrics` / `_ensure_topology`
  > / `_readback_topology`)**不调** `_drain_errors`,只有人发起的事务(GO/GOS/STATIC/load)
  > 会调,频率低,不成风暴。彻底解法 = 把判据从"读到了"升级为"读到了**可解析的 clean
  > 应答**"。

- [ ] **F64R-7 ⭐⭐ `STATE?` 语义真机验证(F64R-1 转出,**开机第一件事**,2026-07-25)**
  > F64R-1 把 `DIAG:SIMU:STATE?` 接成了运行状态的**唯一判据** ——
  > GO 成不成看它、GOS 停没停看它、监控面报不报"在跑"也看它。手册对这几点写得很死
  > (§20.4.3.14 七态 + GOS 后必 STOPPED),但**有两处手册管不到、且我们有相反的现场实证**,
  > 不验就上等于拿现场时间赌:
  - **① ⭐ GOS 之后 STATE? 到底报什么**(风险最高,先做):
    `emulation-control` 端点的注释白纸黑字记着 2026-07-21 实证 ——「本固件下 GOS 在运行态
    **未观察到真停**(数据流不断)」。若属实,`stop_emulation()` 会**恒返回 False**(如实
    fail-loud,不是 bug),连带:直通态测量步骤直接 FAILED(`measure.py` 已消费布尔)、
    `disconnect()` 恒报 False。**验法**:GO 起播 → `DIAG:SIMU:GOS` → `*OPC?` →
    `DIAG:SIMU:STATE?` 看是 STOPPED 还是 RUNNING,同时看功率/数据流是否真停。
    - 若报 STOPPED 且真停 → 判定正确,收工。
    - 若报 RUNNING(或报 STOPPED 但仍在发) → **当场记下**,回来定对策(候选:改用
      `DIAG:SIMU:STOP` 暂停语义 / 加一次重试 / 给直通预备一条明确的逃生路径)。
      ⚠ 不要在现场临时把判据放宽成"当作停住了"—— 那正是本 PR 删掉的假成功。
  - **② 旁路(STATIC 1/2/3)下 STATE? 报什么**:手册七态里**没有 BYPASS 态**,进旁路
    "仿真被暂停"、退旁路"若之前在跑则恢复"。当前代码在旁路路**只取 running、不做
    破坏性清理**(`allow_unload=False`),就是为了防"旁路下报 CLOSED → 误清加载态"。
    验法:STATIC 3 建直通后查一次 STATE?,记下字面值。
  - **③ 顺带**:RUNNING 态重复 GO 的实际行为(手册未涵盖;当前设计不依赖它,但
    `emulation-control` 注释记着"反复 GO 会 -200 累积、极端会把业务层搞卡死",
    验一次好定端点要不要加前置查状态)。

- [ ] **F64R-7 ⭐ 三层兜底机制的**真机验证与存废**(必须现场做,不要在本地凭空改)**
      (2026-07-24 F64R-2 收口时转出)
  > F64R-2 为"拓扑读不到"叠了**三层**兜底。它们都是在**没有真机验证**的前提下设计的 ——
  > `GROUP:*` / `MODEL:INFO?` 这 5 条命令**从未在本项目的 F64 上跑过**,而本项目实证过
  > "手册里有、这台机器回 -100"(MMEM / FTP / `*OPT?`)。**下次现场第一件事就是验它们**,
  > 结果决定这三层留哪几层 —— 不验就改是在猜上面再猜。
  - **① 先验命令是否可用**(仿真已加载状态下逐条跑):
    `DIAG:SIMU:MODEL:INFO?` / `GROUP:GET?` / `GROUP:CHANNELS:GET? 1` /
    `GROUP:INPUTS:GET? 1` / `GROUP:OUTPUTS:GET? 1`。device-selfcheck 页已收录这 5 条
    (is_critical=True),跑一次自检即可。
  - **② 顺带验推导**:逐组 `GROUP:OUTPUTS:GET?` 的并集是否等于 `MODEL:INFO?` 的 outputs?
    组数是否 ≤ min(inputs, outputs)?默认 3600M .smu 是几组?(这决定 F64R-6 第一条怎么收。)
  - **③ 三层机制的存废**——全都取决于 ①②:
    - **按需补读**(`_ensure_topology`:缓存空 → 查 `STATE?` 非 CLOSED 就补读一次)。
      同一母题的**另一面**是"操作员从前面板换 .smu 后驱动缓存永久 stale"(原第四轮 F4):
      驱动无从知情,只能靠人点写操作时补读。**两者一起做更省** —— 现场确认前面板换图的
      实际频率后,再定要不要加"手动刷新拓扑"端点 / 在 `_ensure_topology` 快路径顺带比对
      `STATE?` 或 loaded-file 变化。
    - **失败节流**(`_TOPOLOGY_RETRY_COOLDOWN_S=30`,只作用于 `get_metrics` 轮询路)。
      若 ① 全部可用,这层几乎不会触发,可考虑简化;若不可用,要现场量一次"每秒重试"
      对 SCPI 通道的实际影响再定数值。
    - **人工声明兜底**(`connection_params.topology_override`)。若 ① 全部可用 → **不要配**,
      并考虑是否保留这个口子;若不可用 → 它是唯一解(`f64_output_gain_db` 没有 per-step
      端口参数),那时再补"口数对但口号偏移抓不到"这个已知缺口的说明。
  - **④ 顺带量一次性能**(原第四轮 F9):`get_metrics` 每轮 SCPI 往返从旧口径 20 条涨到
    36 条(4 输入 + 32 探头),broadcaster 1 Hz。**没人量过真机上 36 条 `OUTP:MEAS:RES:GET?`
    一轮要多久** —— 跑不完会持续堵锁。现场量一次,必要时给"逐口电平查询"加降频/开关。

- [ ] **F64R-3 现场调试走正常 TestCase 流程,退役临时脚本** (2026-07-23 用户定,一个 PR)
  - 现场临时脚本**不查源码**重复以前的错(懒重连早有却手动重连 / STATIC-STATE 混用 / 端口靠猜),
    还长(SIGTERM 杀断 VISA)、缺单步验证。
  - 改:一个 PR 两件事——① **能力保障**:TestCase 流程(runner + 仪表使用参数)覆盖现场 bring-up /
    单步调试 / 参数即时调整; ② **规则固化**:现场禁临时脚本、走"建计划→调参→执行→报告"闭环,
    写进 CLAUDE.md 操作规范。依赖 ARCH-1(测试管理简化) + P0-2(参数真值源)。见 memory
    `feedback_onsite_testcase_flow_no_adhoc_scripts`。

- [ ] **F64R-4 F64 驱动 P1 清理** (review 母题⑤⑥⑦)
  - 禁盲试:connect 两条手册**不存在**的命令(`INTERFerence:LIST?`/`USER:LIST?` → `:GET?`);写
    命令 fail-loud 收敛(input_phase / runtime_env / output_gain 静默钳位 / user_alignment 空
    标定 / output_calib null 混淆);健康检查 `*OPT?` 必误报 BLOCKER + MMEM 能力误判(手册其实
    完整支持)。

### P1 — 正确性(撤销错误诊断 + 状态机对齐)

- [ ] **P1-1 撤销"功率暴力开局"错误诊断(单位口径混淆)**
  - 事实:UXM DL 功率屏幕显示 `-15 dBm/BW`,脚本默认 `-46 dBm/SCS`(EPRE)。这俩是**同一个
    功率的两种口径**:BW40 有 1272 子载波,`10·log10(1272)≈31dB`,`-46 EPRE + 31 = -15 BW`
    (屏幕正好显示 -14.96)。
  - 事实:我之前把这两个当成不同功率,得出"闭环起点 -14.96 比 -46 热了 31dB、暴力开局把
    手机震掉线"的**误判**,并据此加了 `input_loop_initial_dl_power_dbm=-46`。
  - 改:撤销这个错误参数/诊断;修正 `onsite-results-20260721.md` 里所有"暴力开局/热 31dB/
    -46 基线"的措辞,标明 EPRE vs BW 口径;确认**功率从头到尾一直正常**。手机 attach 后
    burst 一下掉线的真因要重新归到 F64 信道侧,不是功率。

- [ ] **P1-2 F64 状态机对齐真固件(GO/GOS/STOP/CLOSE 语义)**
  - 事实(真机实测):`DIAG:SIMU:GOS` 在本固件下**没真停**(吞吐没断);随后 `GO` 撞"已在
    运行态"→ `-200 wrong device state`;反复 GO/操作把 PropSim **业务层搞卡死**(SCPI 通信
    层 `SYST:INFO?` 还能应答,但所有业务命令 wrong state,`*RST/*CLS` 都救不回,只能现场
    重启 PropSim)。
  - 改:对照 F64 手册理清 GO/GOS/STOP/CLOSE/STATIC 的真实状态转移;`start/stop_emulation`
    加"目标态已达成就跳过"的保护,避免对已运行态再 GO 触发死锁。

- [ ] **P1-3 UXM 查询串包防护 + 激活失败根因**
  - 事实:`BSE:STATus?` 经常读回吞吐统计 JSON(响应串包错位);`SCS?` 报 `-113 Undefined
    header`;下发 `ACTive:STATe 1` 后 `ACTive=1` 但 `STATus` 持续 `OFF`。疑似 UXM Test App
    遥控口被搞僵(当天两次)。
  - 改:UXM 驱动查询读到非预期格式(含 `{`/长度异常)时重试/丢弃再读;查清"激活位=1 但
    小区 OFF"的根因(缺 SSB/SCS 前置?遥控口卡?);串包严重时明确提示操作员重启 Test App。

### 架构 — 简化"测试管理"(用户 2026-07-21 拍板,借这次修改一并做)

- [ ] **ARCH-1 砍掉「计划管理」+「执行队列」,测试管理回到 TestCase 为核心**
  - 背景:今天本想赶一条**正常测试流程**(不靠现场脚本方式),赶出来发现问题太多。根子之一
    是当前"测试管理"为了整体设计,定义了**「计划管理(Test Plans)」+「执行队列(Execution
    Queue)」**,把整个状态机搞得**太复杂**。
  - 决定:**取消**「计划管理」和「执行队列」;**保留**「测试用例库(TestCase Library)」
    「步骤编排(Step Orchestration)」「执行历史(Execution History)」「虚拟路测(VRT)」。
    成批 / 成队列的测试**后续再增量补**,不在这一版。
  - 范围(待细化):
    - 前端 `gui/src/features/TestManagement/`——从 4 Tab(计划管理/步骤编排/执行队列/执行
      历史)砍到 3(用例库/步骤编排/执行历史)+ 虚拟路测。
    - 后端 test_plan / execution-queue 相关路由、状态机、runner 一并下线或封存。
    - 现有靠 TestPlan 的执行路径(commissioning 会话 / onsite 脚本)迁移到以 TestCase 直接
      驱动。
  - 注:与 memory `project_testcase_first_architecture`(测试管理基础是 TestCase 而非
    TestPlan)一致——这次是把它真正落地。**这是大改,先出设计再动手,不 inline 硬拆。**

### P2 — 收尾 / 固化

- [ ] **P2-1 把当天 HAL 控制端点 + 驱动改动整理成 PR**(PR #221)
  - 事实(工作树未提交):`instrument.py` 新增 `emulation-control / output-gain /
    output-calibration / input-reference / crest-factor` 五个端点;
    `propsim_f64.py` 有 `start_emulation` 冷缓存放行 + GO/GOS/STATIC 幂等豁免修复;
    `uxm_base_station.py` 也有改动(OPC 超时热修)。
  - **`load-scenario` 端点 + `load_local_scenario` 方法已从本 PR 移除**:真机实测失败
    (CLOSE 撞 wrong device state → CALC:FILT:FILE 超时),Codex 连挑 4 轮「加载后漏同步
    的缓存」(GO 无关豁免→stale 文件→stale 频率→拓扑→emulation_running),是半成品 ——
    正确的 F64 load 前置序列留到 **P0-3** 专门重写(见下)。
  - 改:整理成 PR,**过 pre-commit-reviewer agent**(现场热修例外已用完,收工必补);端点
    遵循 scpi-command 先例(不进 openapi.yaml),在 HAL 端点清单登记。

- [ ] **P2-2 重启后端脚本清 Python 字节码缓存**
  - 事实:某次重启后新端点全 404,`git` 显示代码在、`grep` 也在,清掉 `__pycache__` 重启
    才生效(旧 `.pyc` 被加载)。
  - 改:重启脚本加 `find app -name __pycache__ -exec rm -rf` ;或查为什么 `.py` mtime 没
    触发重编译(疑 git/文件操作改了 mtime)。

- [ ] **P2-3 设计"内生经验配置"的加载机制 + 固化正确测试链**
  - 事实:当天摸出的正确顺序 = `UXM 显式配置+激活 → F64 load .smu(手动) → 补输入参考
    -17/峰均比 15 → F64 输出调工作电平 → F64 直通(STATIC 3)让 DUT attach 到 CONN →
    切衰落(STATIC 0 + GO)播放`。且 load .smu **必带回**工程默认输入参考 20/峰均比 12,
    加载后必须重写 -17/15。
  - **[用户 review]** 这里的参数(输入参考 -17 / 峰均比 15 / 输出补偿等)**不是**通用测试
    参数(测试例/手机/SIM 那一类,那是 P0-2),而是**内生经验配置**——系统内部调试积累的经验
    值。它们**也要在测试时加载**,但来源和通用测试参数不同。**需要专门做这个设计**:内生经验
    配置怎么存、怎么在测试链里自动加载(与 P0-2 的通用测试参数是**两条并行的加载路径**)。
  - 改:①做"内生经验配置"存储 + 加载设计;②在此基础上把正确测试链写成**单步、每步验证**的
    流程(避免长脚本被杀 + 漏步)。

## 三、操作规范教训(我当天犯的,写给自己)

- **脚本要短、单步**:长脚本(等 attach 90s + 采样)被系统杀掉时,正在执行的 SCPI 会把
  VISA 会话搞坏 → 连锁故障。
- **健康检查要测驱动 SCPI 层**:我只 ping `hal/status`(HTTP 200)就说"服务没挂",实际
  驱动会话全断了。API 活着 ≠ 驱动会话活着。
- **用户的简单指令不扩展、不自作主张**:用户只让"抬高 10dB",我却又分析又建议重置又让面板
  调——被明确批评。让做什么就做什么。
- **少折腾,循序渐进**:反复重连 / 反复 GO / 反复设 loss,把 F64 PropSim 和后端 VISA 会话
  越搞越乱。

---
**下次现场前**:P0-1~P0-4 在本地(mock/离线)先修好验证,现场只调硬件,不在现场写驱动代码
(这正是 roadmap governance 的原始教训)。
