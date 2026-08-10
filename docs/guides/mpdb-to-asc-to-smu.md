# 从 MPDB 到 F64 播放：ASC 生成与 .smu 组装现状

> 2026-08-06。仪器结论取自 PROPSIM 手册（标 **原文**+章节），手册没写的标 **手册未说明**。
> `CE/` = 独立仓 `ChannelEgine`，其余为本仓 `api-service/`。

## 0. 结论：这条链今天没有端到端打通

代码里是三段各自完整、**互不相连**的实现：

| 段 | 状态 |
|---|---|
| ① MPDB 射线入口 | schema / DB 表 / API 传参都有，**无 MPDB 文件解析器** —— 射线以 JSON 由人工或现场写进 `TestCase.configuration` 或 `channel_assets` |
| ② RT 射线 → 标注式 CDL 聚类 | **全部实现**（四种聚类 + §6 判决），产出 `AnnotatedCDLProfile` |
| ③ 标注式 CDL → .asc | 烘焙器实现了，但**唯一把 ①②③ 串起来的端点没有调用方** —— `synthesize_deterministic_b1` 端点 —— ⚠️ 它在 **`channel-engine-service` 这个服务**上（`channel-engine-service/app/api/endpoints/hardware_pipeline.py`），**不在主后端 `api-service` 上**，两个服务各有各的 `/api/v1` 前缀和端口，别照着打主后端。目前只有 CE 自己的测试在调它 |

**今天生产真正跑的是另一条路**：3GPP 标准 CDL（UMa/UMi/CDL-C…）→ 38.901 内部生成器造簇 → .asc，
不经过 MPDB、也不经过 native-fit 聚类。B-2（闭式谱参数）断得更早：参数表算出来了但 `.tap` 字节零实现，
`b2_parametric_strategy.py:110` **无条件 `return False`**。含多快照的 rt_dynamic 资产会被**直接拒**
（`channel_asset_resolver.py:116`）。

## 1. 三个正确性关注点落在哪

| 关注点 | 实现（均在 `CE/mimo_ota_simulator/`） | 状态 |
|---|---|---|
| **空间相关性** | `simulator.py:436` 探头权重（az/el 各向异性高斯、只取最近 4 探头、归一）→ `:961` `W_base = pol·√p·g_elem·(w_map @ g_tx)` 进复数 CIR → `:1016` 落 tap | ✅ |
| **相位连续性** | 初相 `simulator.py:840`（`phase_rad=None` fail-fast；`:861` 有意等量消耗 RNG，保证与「走标准扇」的随机流逐位一致）；时间轴 `exporters.py:338/348` 跨 chunk 连续、各链路共用 t=0 | ⚠️ **单快照内连续，跨快照未实现**（`b1_annotated_baker.py:113` 只烘 snapshot 0 并 warn） |
| **多普勒谱** | 逐射线 `fd=(v·k̂_rx)/λ`（`simulator.py:985`），谱形由 20 条子径**相干求和隐式产生**，时域旋转 `exp(j2πfd·t)` | ✅ 烘进 I/Q 这条实现了 |

聚类分裂判据是**多普勒谱 CDF-L1 残差**（`doppler_native_mapping.py:239`）；实际是**按时延初聚 + 按多普勒中位数二分**，
角度只用于导出统计量（**与设计文档 §4.1 写的「按角度聚类」不符**）。
⚠️ **生产路不把校准烘进 .asc**（`hardware_pipeline.py:516/618` 传 `calibration_config=None`）——
有意为之，cal 在射频侧经 `control_instructions` 施加。

## 2. .asc：手册要什么 vs 我们写什么

**手册（原文 §21.1.1/§21.1.2）**：header **9 行**；tap data 每抽头三元组 `Delay(ns) / Re / Im`，同行时延递增；
Re/Im 可任意（转 `.SIM` 时重缩放），但**转换保持通道间相对增益** → 同一仿真里所有文件必须**全局统一归一化**。

**我们的生成器**（`CE/mimo_ota_simulator/exporters.py:106-130`）只写 **4 行**：
`{CIRs} CIRs` / `{taps} Taps/CIR` / `{rate} CIR_Update_Rate` / `{fc} Carrier_Frequency`。

**① 时延单位可能差 10⁹。** 手册原文 `Delay value (measured in nanoseconds)`，示例 `0.00000 / 50.00000`；
我们写的是 `%.9e` 的**秒**（实测产物 `2.000000000e-07`）。按 ns 读即 2e-7 ns ≈ 0，所有抽头挤到零时延。
**手册未说明**单位不符时的行为 → **必须真机实测判定，不能推断**。

**② header 缺 5 个字段**：`Route_Closed/Open`、两个 Lock 标志、`Delay_Resolution`（手册说**始终用 5**）、`Sample_Density`。
手册对 `.asc` **没有**「可选字段」一节 —— 对比 `.MAT`（§21.3.2）专门定义 Optional variables 并给默认值，
故 9 行应视为全必填。`Sample_Density` 缺失有**原文后果**（Standard Channel Models §2）：
**移动速度无法计算，编辑框为空**。字段顺序是否敏感 —— **手册未说明**。

**其它**：1 个 .asc = 1 条链路（`exporters.py:80-104`），文件数 = Tx × 有效探头数（双极化 ×2）→ **2Tx × 16 双极化 = 64 个**。
生产硬编码 `duration_s=0.1`/`sample_rate_hz=1000`（每文件 **100 个 CIR**）与 `mode="B"`，
在 `hardware_pipeline.py:519/620/737`，**不受 TestCase 控制**，且与验证指南推荐的 Mode A 相反。
抽头数 = 簇数，**代码不做上限检查**（手册：1–48）。

## 3. .asc → .smu：怎么组装

**我们的代码不生成 .smu。** 两仓皆无生成代码；`.smu` 只被解析取频率（`app/hal/smu_project.py:34`，当 INI 读）、
按文件名猜频率（`app/hal/nr_arfcn.py:68`，注释明说仅作提示）、以及加载。
ASC 路今天的做法（`app/hal/propsim_f64.py:2189-2262`）是把 .asc 批量 FTP 上去，再
`CALC:FILT:FILE {remote_dir}\runtime_emulation.smu` —— **假定 F64 上已预先存在**建好的 .smu，
**没有任何「.asc → .smu」转换步骤**。

**F64 侧组装（原文，User Reference §3）**：

1. GUI 左栏 `EMULATION > New` 启动 **Scenario Wizard**
2. Step 1/5：仿真名、工作目录、**带宽**、拓扑样式
3. Step 2/5：点 MS↔BS 链路 → Link properties → `Downlink/Uplink channel model` → **Browse** → 选 .asc
   （向导原生支持 `.tap .ctap .ir .cir .rtc .asc .mat .aso .caso`）
4. Step 4/5：分配物理 RF Connector
5. Step 5/5：`Finish` / `Build & Run` → **向导后台把 .asc 编译打包成可运行的 .smu**

**`.smu`**（原文）= ready-to-run simulation file，顶层容器（拓扑 / 连接器映射 / 中心频率 / 各链路挂哪个模型），
编译时 .asc 转成硬件二进制 `.SIM`。上限（§1.2.1）**128 个衰落通道 = 128 个模型文件** → 我们 64 个在限内。
`IR and ASC converter`（§7.5）只做 `.ir ⇄ .asc` 互转、**不能生成 .smu**；**SCPI 不支持在线导入编译**。

**加载播放**（原文 ATE AN §2.2/§2.5；代码已实现于 `propsim_f64.py:1446/2247`）：

```
DIAG:SIMU:CLOSE                # 先关，避免前置状态污染
# 测试软件端把 VISA/socket 读超时临时拉到 40 s 以上
CALC:FILT:FILE D:\...\xxx.smu  # 必须在 CLOSED 态下发
*OPC?                          # 必须读完响应 "1" 再发下一条，否则 -400 Query error
SYST:ERR?                      # 判真失败
DIAG:SIMU:GO                   # 开播
```

## 4. 上机前先解决三件事

1. **实测判定时延单位**（手册未说明行为）—— 用已知时延的小 .asc 上机，看 F64 报错还是静默吃掉。
2. **补齐 header 9 字段**，尤其 `Delay_Resolution=5` 与 `Sample_Density`，否则速度/多普勒算不出来。
3. **定 Mode A / Mode B** —— 生产硬编码 B，验证指南推荐 A，两者定标处理不同。

MPDB 那条链要真正跑通，还差**把孤儿端点接上 api-service**；多快照连续演化另需先做跨快照 .asc 帧拼接。
